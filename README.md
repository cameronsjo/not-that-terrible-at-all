# not-that-terrible-at-all

> Deploy GitHub repos to your Unraid server from your phone. Yes, really.

## The Problem

You're on your phone. You find a cool web app on GitHub. You want it running on your Unraid server. But:

1. No Dockerfile (fixable)
2. Setting up deployment pipelines requires a computer (annoying)
3. Managing secrets across apps is tedious (very annoying)
4. You're worried about supply chain attacks (valid)
5. You just want to do this from your phone (same)

## The Solution

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  Fork repo      │────▶│ Add 10-line  │────▶│ GitHub builds image  │
│  Add Dockerfile │     │ workflow.yml │     │ + signs with cosign  │
└─────────────────┘     └──────────────┘     └──────────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  App is live    │◀────│ TOTP Gate    │◀────│ You enter 6-digit    │
│  Auto-updates   │     │ (optional)   │     │ code to approve      │
└─────────────────┘     └──────────────┘     └──────────────────────┘
```

## Security Model

**Worried about your GitHub getting hacked?** The TOTP Approval Gate has you covered.

```
GitHub compromised → Attacker pushes malicious image →
TOTP Gate asks for 6-digit code → Attacker doesn't have your phone →
Attack blocked
```

| Layer | What | Protects Against | Phone-Friendly |
|-------|------|------------------|----------------|
| **TOTP Approval Gate** | 6-digit code before any pull | GitHub account/org compromise | Yes |
| Environment protection | Approve before build | Accidental deploys | Yes |
| Cosign signing | Cryptographic image signatures | Tampering, MITM | Automatic |
| Pinned actions | SHA-pinned dependencies | Compromised actions | Automatic |

**The key insight:** TOTP secret lives in your 1Password + Unraid. Never touches GitHub. Even if your entire GitHub org is compromised, attacker can't approve deployments.

See [docs/security-architecture.md](docs/security-architecture.md) for the full diagram.

## Quick Start

### One-Time Unraid Setup

```bash
# 1. Install the TOTP Approval Gate
mkdir -p /mnt/user/appdata/approval-gate
cd /mnt/user/appdata/approval-gate
# Copy files from this repo's approval-gate/ directory

# 2. Run setup (generates QR code)
docker-compose run --rm gate python setup.py

# 3. Scan QR code with 1Password or any authenticator

# 4. Edit config/.env
#    - Set GATE_URL to your Tailscale URL
#    - Optionally configure notifications (ntfy, telegram, discord, pushover)

# 5. Add images to monitor in config/images.json

# 6. Start
docker-compose up -d
```

See [docs/unraid-setup.md](docs/unraid-setup.md) for Nginx Proxy Manager setup.

### Deploy a New App

From your phone:

1. **Fork** the repo you want to deploy
2. **Add Dockerfile** (copy from `templates/Dockerfile.*`)
3. **Add workflow** at `.github/workflows/deploy.yml`:

```yaml
name: Deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
```

4. **Add to Unraid** - edit `config/images.json` on your approval gate
5. **Push** - image builds, you get notified, enter TOTP, done

See [docs/new-app-guide.md](docs/new-app-guide.md) for the complete walkthrough.

## Project Structure

```
not-that-terrible-at-all/
├── .github/workflows/
│   └── deploy.yml              # Reusable workflow (build + sign)
│
├── approval-gate/              # TOTP approval service
│   ├── app.py                  # Main service (Flask + polling)
│   ├── setup.py                # Generate TOTP secret + QR code
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── README.md               # Detailed setup instructions
│
├── templates/
│   ├── Dockerfile.node         # Node.js apps
│   ├── Dockerfile.python       # Python apps
│   ├── Dockerfile.go           # Go apps
│   ├── Dockerfile.static       # SPAs / static sites
│   ├── docker-compose.yml      # Basic Unraid deployment
│   └── deploy.yml              # Workflow caller template
│
├── scripts/
│   ├── bootstrap.sh            # Quick setup script
│   └── verify-and-pull.sh      # Manual signature verification
│
└── docs/
    ├── adr/
    │   └── 0001-deployment-architecture.md
    ├── unraid-setup.md         # One-time server setup
    ├── new-app-guide.md        # Phone-friendly deploy guide
    ├── security-model.md       # Threat model & mitigations
    └── security-architecture.md # Full system diagram
```

## Notification Options

The approval gate supports multiple notification methods (or none):

| Method | Setup | Cost |
|--------|-------|------|
| **none** | Just bookmark `/pending` | Free |
| **ntfy** | Self-hostable, no account needed | Free |
| **telegram** | Create a bot | Free |
| **discord** | Create a webhook | Free |
| **pushover** | Create an account | $5 one-time |

Notifications are optional. The security comes from TOTP, not the notification channel.

## Workflow Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `app-name` | repo name | Docker image name |
| `dockerfile` | `Dockerfile` | Path to Dockerfile |
| `context` | `.` | Docker build context |
| `platforms` | `linux/amd64` | Target architectures |
| `build-args` | (none) | Build arguments |
| `tag-strategy` | `latest` | `latest`, `sha`, `branch`, `semver` |
| `sign-image` | `true` | Cosign signing + SBOM attestation |
| `environment` | (none) | GitHub environment for build approval |

## Forking This Repo

1. Update `templates/deploy.yml` line 37 with your org/username
2. Update `approval-gate/setup.py` default `GITHUB_ORG`
3. That's it—everything else auto-detects

## Requirements

- GitHub account (free tier)
- Unraid server with Docker
- Tailscale (or other VPN access to Unraid)
- Phone with authenticator app (1Password works great)

## Architecture Decisions

See [ADR-0001](docs/adr/0001-deployment-architecture.md) for why we chose:

- Registry + TOTP Gate over SSH deploys
- GitHub Org secrets over Vault
- Reusable workflows over GitHub Apps
- Cosign for optional cryptographic verification
- TOTP for GitHub-independent authentication

## License

MIT
