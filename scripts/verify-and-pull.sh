#!/usr/bin/env bash
# Verify cosign signature and pull image
# This is your last line of defense - runs on Unraid, doesn't trust GitHub
#
# Usage:
#   ./verify-and-pull.sh ghcr.io/yourorg/yourapp:latest
#
# Requirements:
#   - cosign installed on Unraid
#   - For keyless: just works (verifies against Sigstore)
#   - For your key: set COSIGN_PUBLIC_KEY env var or place at ~/.cosign/cosign.pub

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
IMAGE="${1:-}"
GITHUB_ORG="${GITHUB_ORG:-cameronsjo}"  # Your GitHub org/username
COSIGN_PUBLIC_KEY="${COSIGN_PUBLIC_KEY:-}"

if [[ -z "$IMAGE" ]]; then
    echo "Usage: $0 <image>"
    echo "Example: $0 ghcr.io/cameronsjo/myapp:latest"
    exit 1
fi

# Check if cosign is installed
if ! command -v cosign &> /dev/null; then
    log_error "cosign not installed. Install with:"
    echo "  curl -sSL https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64 -o /usr/local/bin/cosign"
    echo "  chmod +x /usr/local/bin/cosign"
    exit 1
fi

log_info "Verifying signature for: $IMAGE"

# Determine verification method
if [[ -n "$COSIGN_PUBLIC_KEY" ]]; then
    # Verify with your own public key
    log_info "Verifying with your public key..."

    if [[ -f "$COSIGN_PUBLIC_KEY" ]]; then
        KEY_FILE="$COSIGN_PUBLIC_KEY"
    else
        # Assume it's the key content
        echo "$COSIGN_PUBLIC_KEY" > /tmp/cosign.pub
        KEY_FILE="/tmp/cosign.pub"
    fi

    if cosign verify --key "$KEY_FILE" "$IMAGE" 2>/dev/null; then
        log_success "Signature verified with your key!"
        VERIFIED=true
    else
        log_error "Signature verification FAILED with your key!"
        VERIFIED=false
    fi

    rm -f /tmp/cosign.pub

elif [[ -f "$HOME/.cosign/cosign.pub" ]]; then
    # Use default key location
    log_info "Verifying with key at ~/.cosign/cosign.pub..."

    if cosign verify --key "$HOME/.cosign/cosign.pub" "$IMAGE" 2>/dev/null; then
        log_success "Signature verified with your key!"
        VERIFIED=true
    else
        log_error "Signature verification FAILED!"
        VERIFIED=false
    fi

else
    # Keyless verification (Sigstore)
    log_info "Verifying with Sigstore keyless (GitHub Actions OIDC)..."

    # Verify the image was signed by GitHub Actions from your org
    if cosign verify "$IMAGE" \
        --certificate-identity-regexp="https://github.com/${GITHUB_ORG}/.*" \
        --certificate-oidc-issuer="https://token.actions.githubusercontent.com" 2>/dev/null; then
        log_success "Signature verified via Sigstore!"
        log_info "Image was signed by GitHub Actions from org: $GITHUB_ORG"
        VERIFIED=true
    else
        log_error "Signature verification FAILED!"
        log_error "Image was NOT signed by GitHub Actions from your org"
        VERIFIED=false
    fi
fi

# Pull if verified
if [[ "$VERIFIED" == "true" ]]; then
    log_info "Pulling verified image..."
    docker pull "$IMAGE"
    log_success "Image pulled successfully!"

    # Optionally restart container
    CONTAINER_NAME="${2:-}"
    if [[ -n "$CONTAINER_NAME" ]]; then
        log_info "Restarting container: $CONTAINER_NAME"
        docker restart "$CONTAINER_NAME" || true
    fi

    exit 0
else
    log_error "Refusing to pull unverified image!"
    log_error "This could be a supply chain attack."
    log_error ""
    log_error "If you trust this image, you can force pull with:"
    log_error "  docker pull $IMAGE"
    exit 1
fi
