# Security Model

Defense-in-depth for phone-friendly deployments.

## Threat Model

| Threat | Likelihood | Impact | Mitigation |
|--------|------------|--------|------------|
| Malicious PR merged | Medium | High | Environment approval, branch protection |
| GitHub account compromised | Low | Critical | Signature verification on Unraid |
| GitHub org compromised | Very Low | Critical | Your own signing key + Unraid verification |
| Compromised base image | Low | High | Pin images to digest |
| Compromised GitHub Action | Low | High | Pin actions to SHA |
| Stolen PAT/secrets | Medium | High | OIDC, no long-lived tokens |
| Malicious dependencies | Medium | Medium | Lock files, isolated builds |

## Security Layers

### Layer 1: GitHub Environment Protection

**What it does:** Requires your approval before the workflow runs.

**Phone-friendly:** Yes - tap "Approve" in GitHub mobile app.

**Setup:**
1. Go to repo → Settings → Environments
2. Create "production" environment
3. Add yourself as required reviewer
4. Enable in workflow: `environment: production`

```yaml
with:
  environment: production
```

### Layer 2: Cosign Image Signing

**What it does:** Cryptographically signs your Docker images.

**Two modes:**

| Mode | Trust Boundary | Setup |
|------|----------------|-------|
| Keyless (Sigstore) | Trusts GitHub OIDC identity | Automatic, nothing to configure |
| Your own key | Only trusts your key | One-time setup, key stored securely |

**Keyless (default):** Images are signed with GitHub Actions' OIDC identity. Verification proves the image was built by GitHub Actions from your repo.

**Your own key:** If GitHub is compromised, attacker can't forge your signature.

Generate a key (one-time, from computer):
```bash
cosign generate-key-pair

# Add to GitHub org secrets:
#   COSIGN_PRIVATE_KEY = base64 of cosign.key
#   COSIGN_PASSWORD = the password you chose

# Keep cosign.pub for Unraid verification
```

### Layer 3: Pinned Actions

**What it does:** Uses specific, audited versions of GitHub Actions.

**Protection:** Prevents supply chain attacks via compromised actions.

All actions in the reusable workflow are pinned to SHA:
```yaml
uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
```

### Layer 4: Unraid Signature Verification

**What it does:** Verifies image signatures BEFORE pulling. Last line of defense.

**This is your protection against GitHub org compromise.**

**Option A: Verified Updater (replaces Watchtower)**

```bash
# On Unraid
mkdir -p /mnt/user/appdata/verified-updater
cd /mnt/user/appdata/verified-updater

# Copy from this repo:
# - docker-compose.verified-updater.yml → docker-compose.yml
# - images.txt

# Edit images.txt with your apps
# Edit docker-compose.yml with your GITHUB_ORG

docker-compose up -d
```

**Option B: Manual verification script**

```bash
# Install cosign on Unraid
curl -sSL https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64 \
  -o /usr/local/bin/cosign
chmod +x /usr/local/bin/cosign

# Verify before pulling
./verify-and-pull.sh ghcr.io/yourorg/yourapp:latest
```

### Layer 5: OIDC Authentication (No Stored Tokens)

**What it does:** Uses GitHub's built-in OIDC for GHCR authentication.

**Protection:** No long-lived PATs to steal.

The workflow uses `GITHUB_TOKEN` which:
- Is short-lived (expires after job)
- Is scoped to the repo
- Can't be extracted and reused

### Layer 6: TOTP Approval Gate (Recommended)

**What it does:** Requires a 6-digit TOTP code from your phone before pulling any new image.

**This is the simplest protection against GitHub org compromise.**

```
New image detected → Pushover notification → You tap link →
Enter 6-digit code from authenticator → Image pulled
```

**Why it works:**
- TOTP secret lives only on Unraid + your authenticator app
- GitHub never sees the secret
- Attacker can push malicious images, but can't approve the pull
- No complex key management like cosign

**Setup:**
```bash
cd /mnt/user/appdata/approval-gate
docker-compose run --rm gate python setup.py
# Scan QR code with authenticator app
# Configure Pushover credentials
docker-compose up -d
```

See `approval-gate/README.md` for full setup instructions.

## Attack Scenarios

### Scenario: Malicious PR gets merged

**Attack path:** Attacker submits innocent-looking PR, it gets merged, deploys malware.

**Defenses:**
1. Environment protection → You must approve the workflow
2. Branch protection → Require review before merge
3. Signature verification → Image is signed (but attacker's code is in it)

**Gap:** If you approve the PR and workflow, malicious code deploys.

**Mitigation:** Review code carefully. Use environment protection as a speed bump.

### Scenario: GitHub account compromised

**Attack path:** Attacker gets your GitHub password/session, pushes malicious code.

**Defenses:**
1. 2FA / hardware key → Makes account takeover harder
2. Environment protection → Attacker needs access to your phone too
3. Cosign keyless → Images are signed, but attacker controls the repo
4. **Unraid verification** → Still passes (keyless trusts GitHub identity)

**Gap:** Keyless signing trusts GitHub OIDC. Compromised account = valid signatures.

**Mitigation:** Use your own signing key (stored outside GitHub).

### Scenario: GitHub org fully compromised

**Attack path:** Attacker has full control of your GitHub org.

**Defenses:**
1. **TOTP Approval Gate** → Attacker can't approve without your phone
2. **Your own cosign key** → Attacker can't sign without your private key
3. **Unraid verification** → Rejects images not signed by your key

**This is the nuclear scenario.** TOTP Approval Gate is the simplest defense. Cosign with your own key is the most robust.

## Recommended Setup

### Minimum (casual use)

```yaml
# Just use defaults - you get:
# - Cosign keyless signing
# - SBOM attestation
# - Pinned actions

with:
  sign-image: true
```

### Standard (recommended)

Use **TOTP Approval Gate** - simplest protection against GitHub compromise.

```bash
# One-time setup on Unraid
cd /mnt/user/appdata/approval-gate
docker-compose run --rm gate python setup.py
# Scan QR, configure Pushover, start
docker-compose up -d
```

Plus:
- Environment protection in workflow (optional extra approval)
- 2FA on GitHub with hardware key

### Paranoid (belt-and-suspenders)

Everything in Standard, plus:

1. Generate your own cosign key pair
2. Store private key in GitHub secrets (COSIGN_PRIVATE_KEY)
3. Store public key on Unraid
4. Configure Verified Updater to use your public key
5. Enable Pushover/Telegram alerts for failed verifications

```bash
# On your computer (one-time)
cosign generate-key-pair

# Add to GitHub org secrets
# COSIGN_PRIVATE_KEY = $(cat cosign.key | base64)
# COSIGN_PASSWORD = your-password

# Copy public key to Unraid
scp cosign.pub unraid:/mnt/user/appdata/verified-updater/
```

## Verification Commands

```bash
# Verify keyless signature
cosign verify ghcr.io/yourorg/yourapp:latest \
  --certificate-identity-regexp='https://github.com/yourorg/.*' \
  --certificate-oidc-issuer='https://token.actions.githubusercontent.com'

# Verify with your public key
cosign verify --key cosign.pub ghcr.io/yourorg/yourapp:latest

# View image attestations
cosign tree ghcr.io/yourorg/yourapp:latest
```

## Quick Reference

| Feature | Default | Phone-Friendly | Protects Against |
|---------|---------|----------------|------------------|
| Cosign keyless | On | N/A (automatic) | Tampering, MITM |
| Environment protection | Off | Yes (tap to approve) | Accidental/malicious pushes |
| Pinned actions | On | N/A | Compromised actions |
| **TOTP Approval Gate** | Off | **Yes (enter 6-digit code)** | **GitHub org compromise** |
| Your own signing key | Off | No (one-time setup) | GitHub org compromise |
| Unraid verification | Off | N/A (runs on Unraid) | All of the above |
