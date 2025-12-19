#!/usr/bin/env bash
# Bootstrap script for adding deployment to a new app repo
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/YOUR_ORG/not-that-terrible-at-all/main/scripts/bootstrap.sh | bash
#
# Or with options:
#   curl -sSL ... | bash -s -- --org myorg --app myapp --type node

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

# Default values
ORG="${ORG:-YOUR_ORG}"
APP_NAME=""
APP_TYPE=""
FORCE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --org)
            ORG="$2"
            shift 2
            ;;
        --app)
            APP_NAME="$2"
            shift 2
            ;;
        --type)
            APP_TYPE="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: bootstrap.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --org ORG      GitHub organization name (default: YOUR_ORG)"
            echo "  --app NAME     App name (default: current directory name)"
            echo "  --type TYPE    App type: node, python, static, go (auto-detected if not specified)"
            echo "  --force        Overwrite existing files"
            echo "  -h, --help     Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Detect app name from current directory if not specified
if [[ -z "$APP_NAME" ]]; then
    APP_NAME=$(basename "$(pwd)")
fi

log_info "Bootstrapping deployment for: ${APP_NAME}"

# Detect app type if not specified
detect_app_type() {
    if [[ -f "package.json" ]]; then
        # Check if it's a static site (React, Vue, etc.) or a server
        if grep -qE '"(next|nuxt|gatsby|vite|react-scripts|vue)"' package.json 2>/dev/null; then
            echo "static"
        else
            echo "node"
        fi
    elif [[ -f "requirements.txt" ]] || [[ -f "pyproject.toml" ]] || [[ -f "setup.py" ]]; then
        echo "python"
    elif [[ -f "go.mod" ]]; then
        echo "go"
    elif [[ -f "index.html" ]]; then
        echo "static"
    else
        echo ""
    fi
}

if [[ -z "$APP_TYPE" ]]; then
    APP_TYPE=$(detect_app_type)
    if [[ -n "$APP_TYPE" ]]; then
        log_info "Detected app type: ${APP_TYPE}"
    else
        log_warn "Could not detect app type. Please specify with --type"
        echo "Available types: node, python, static, go"
        exit 1
    fi
fi

# Base URL for templates
TEMPLATE_BASE="https://raw.githubusercontent.com/${ORG}/not-that-terrible-at-all/main/templates"

# Create .github/workflows directory
mkdir -p .github/workflows

# Download workflow file
WORKFLOW_FILE=".github/workflows/deploy.yml"
if [[ -f "$WORKFLOW_FILE" ]] && [[ "$FORCE" != true ]]; then
    log_warn "Workflow file already exists: ${WORKFLOW_FILE}"
    log_warn "Use --force to overwrite"
else
    log_info "Creating workflow file..."

    # Create the workflow file with the correct org
    cat > "$WORKFLOW_FILE" << EOF
name: Deploy to Unraid

on:
  push:
    branches:
      - main
      - master
  workflow_dispatch:

jobs:
  deploy:
    uses: ${ORG}/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
    with:
      app-name: ${APP_NAME}
EOF

    log_success "Created: ${WORKFLOW_FILE}"
fi

# Check for Dockerfile
if [[ ! -f "Dockerfile" ]]; then
    log_info "No Dockerfile found. Downloading template for ${APP_TYPE}..."

    DOCKERFILE_URL="${TEMPLATE_BASE}/Dockerfile.${APP_TYPE}"

    if curl -sSL -f "$DOCKERFILE_URL" -o Dockerfile 2>/dev/null; then
        log_success "Created: Dockerfile (${APP_TYPE} template)"
    else
        log_warn "Could not download Dockerfile template. Create one manually."
    fi
else
    log_info "Dockerfile already exists, skipping"
fi

# Create .dockerignore if it doesn't exist
if [[ ! -f ".dockerignore" ]]; then
    log_info "Creating .dockerignore..."
    cat > .dockerignore << 'EOF'
# Dependencies
node_modules/
__pycache__/
*.pyc
.venv/
venv/

# Build outputs
dist/
build/
*.egg-info/

# IDE
.idea/
.vscode/
*.swp

# Git
.git/
.gitignore

# Docker
Dockerfile*
docker-compose*.yml

# CI/CD
.github/

# Misc
*.md
*.log
.env*
!.env.example
EOF
    log_success "Created: .dockerignore"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "Bootstrap complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. Review the generated Dockerfile and customize if needed"
echo "  2. Commit and push to main branch"
echo "  3. GitHub Actions will build and push to GHCR"
echo "  4. Watchtower on Unraid will pull the new image"
echo ""
echo "Your image will be available at:"
echo "  ghcr.io/$(echo "${ORG}" | tr '[:upper:]' '[:lower:]')/${APP_NAME}:latest"
echo ""
