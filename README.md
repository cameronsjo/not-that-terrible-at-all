# not-that-terrible-at-all

> Deploy GitHub repos to your Unraid server from your phone. Yes, really.

## The Problem

You're on your phone. You find a cool web app on GitHub. You want it running on your Unraid server. But:

1. No Dockerfile (fixable)
2. Setting up deployment pipelines requires a computer (annoying)
3. Managing secrets across apps is tedious (very annoying)
4. You're worried about supply chain attacks (valid)
5. You just want to do this from your phone (same)

## Phone-Friendliness: The Honest Truth

Let's be real about what you can and can't do from your phone:

| Task | Strategy One (SSH) | Strategy Two (TOTP) |
|------|-------------------|---------------------|
| **One-time setup** | Terminal required | Terminal required |
| **Add new app** | Terminal (secrets) | Phone (web UI) |
| **Deploy** | Automatic | Phone (TOTP code) |
| **Monitor** | GitHub logs | Phone (web UI) |

**The bottom line:** Both strategies require terminal access for initial setup. After that, Strategy Two is *actually* phone-friendly. Strategy One is "phone-friendly" in that you don't have to do anything—it's automatic.

**What about editing docker-compose.yml?** Both strategies sync config from your Git repo. Edit the file on GitHub (works on phone), push, and the new config deploys automatically. No SSH required for config changes.

## Two Strategies, One Repo

Choose based on your priorities:

| | Strategy One: SSH | Strategy Two: TOTP Gate |
|---|-------------------|------------------------|
| **Speed** | ~2 min, automated | ~5 min + manual approval |
| **GitHub compromise** | Attacker has SSH to server | Attacker blocked by TOTP |
| **Best for** | Experimental apps | Production apps |
| **Config sync** | SCP pushes files | OCI artifact pull |

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STRATEGY ONE (SSH)                               │
│                                                                          │
│  Push → Build → SCP configs → SSH docker-compose up → Done              │
│                                                                          │
│  Fast. Automated. Trust GitHub fully.                                   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                       STRATEGY TWO (TOTP GATE)                           │
│                                                                          │
│  Push → Build → Gate polls → Notification → You enter 6-digit code      │
│                                              │                           │
│                              Gate pulls config + image → Restart → Done │
│                                                                          │
│  Secure. Manual approval. GitHub-independent authentication.            │
└─────────────────────────────────────────────────────────────────────────┘
```

See [docs/choosing-a-strategy.md](docs/choosing-a-strategy.md) for the full comparison.

## Quick Start: Strategy One (SSH)

Fast, automated deployments. Requires SSH key in GitHub.

### 1. Add Org Secrets

GitHub → Your Org → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `UNRAID_HOST` | Your Unraid IP/hostname |
| `UNRAID_USER` | `root` |
| `UNRAID_SSH_KEY` | Private SSH key |
| `GHCR_PAT` | Token with `read:packages` scope |

### 2. Add Workflow to Your App

```yaml
name: Deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy-ssh.yml@main
    secrets: inherit
```

Done. Push to main, app deploys.

## Quick Start: Strategy Two (TOTP Gate)

Secure deployments with phone-based approval.

### 1. One-Time Unraid Setup

```bash
# Install the TOTP Approval Gate
mkdir -p /mnt/user/appdata/approval-gate
cd /mnt/user/appdata/approval-gate
# Copy files from this repo's approval-gate/ directory

# Run setup (generates QR code)
docker-compose run --rm gate python setup.py

# Scan QR code with 1Password or any authenticator

# Edit config/.env - set GATE_URL to your Tailscale URL

# Start
docker-compose up -d
```

### 2. Add Workflow to Your App

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

### 3. Add to images.json

```json
[
  {
    "image": "ghcr.io/yourorg/yourapp:latest",
    "container": "yourapp",
    "app_dir": "/mnt/user/appdata/yourapp"
  }
]
```

Push → Build → Notification → Enter TOTP → Done.

## Security Model

**Worried about your GitHub getting hacked?** Strategy Two has you covered.

```
GitHub compromised → Attacker pushes malicious image →
TOTP Gate asks for 6-digit code → Attacker doesn't have your phone →
Attack blocked
```

| Layer | What | Protects Against |
|-------|------|------------------|
| **TOTP Approval Gate** | 6-digit code before any pull | GitHub account/org compromise |
| **Config Sync** | OCI artifacts for docker-compose.yml | Config drift between Git and server |
| **Cosign signing** | Cryptographic image signatures | Tampering, MITM |
| **Pinned actions** | SHA-pinned dependencies | Compromised actions |

See [docs/security-architecture.md](docs/security-architecture.md) for the full diagram.

## Project Structure

```
not-that-terrible-at-all/
├── .github/workflows/
│   ├── deploy.yml              # Strategy Two: TOTP Gate (secure)
│   └── deploy-ssh.yml          # Strategy One: SSH (fast)
│
├── approval-gate/              # TOTP approval service
│   ├── app.py                  # Main service (Flask + polling + config sync)
│   ├── setup.py                # Generate TOTP secret + QR code
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── README.md
│
├── templates/
│   ├── Dockerfile.node         # Node.js apps
│   ├── Dockerfile.python       # Python apps
│   ├── Dockerfile.go           # Go apps
│   ├── Dockerfile.static       # SPAs / static sites
│   ├── docker-compose.yml      # Basic Unraid deployment
│   ├── deploy.yml              # Strategy Two template
│   └── deploy-ssh.yml          # Strategy One template
│
├── scripts/
│   ├── bootstrap.sh            # Quick setup script
│   └── verify-and-pull.sh      # Manual signature verification
│
└── docs/
    ├── choosing-a-strategy.md  # Strategy comparison guide
    ├── security-architecture.md # Full system diagram
    ├── unraid-setup.md         # One-time server setup
    ├── new-app-guide.md        # Phone-friendly deploy guide
    └── adr/
        └── 0001-deployment-architecture.md
```

## Workflow Inputs

### Strategy Two (deploy.yml)

| Input | Default | Description |
|-------|---------|-------------|
| `app-name` | repo name | Docker image name |
| `dockerfile` | `Dockerfile` | Path to Dockerfile |
| `context` | `.` | Docker build context |
| `platforms` | `linux/amd64` | Target architectures |
| `build-args` | (none) | Build arguments |
| `tag-strategy` | `latest` | `latest`, `sha`, `branch`, `semver` |
| `sign-image` | `true` | Cosign signing + SBOM attestation |
| `push-config` | `true` | Push config artifact for sync |
| `config-files` | `docker-compose.yml` | Files to include in config artifact |

### Strategy One (deploy-ssh.yml)

| Input | Default | Description |
|-------|---------|-------------|
| `app-name` | repo name | Docker image name |
| `dockerfile` | `Dockerfile` | Path to Dockerfile |
| `config-files` | `docker-compose.yml` | Files to SCP to server |
| `app-dir` | `/mnt/user/appdata/{app-name}` | Target directory on Unraid |
| `env-vars` | (none) | Extra env vars for .env file |

## Notification Options

The TOTP gate supports multiple notification methods (or none):

| Method | Setup | Cost |
|--------|-------|------|
| **none** | Just bookmark `/pending` | Free |
| **ntfy** | Self-hostable, no account needed | Free |
| **telegram** | Create a bot | Free |
| **discord** | Create a webhook | Free |
| **pushover** | Create an account | $5 one-time |

## Requirements

- GitHub account (free tier)
- Unraid server with Docker
- Tailscale (or other VPN access to Unraid)
- Phone with authenticator app (for Strategy Two)

## Forking This Repo

1. Update `templates/deploy.yml` line 37 with your org/username
2. Update `templates/deploy-ssh.yml` line 21 with your org/username
3. Update `approval-gate/setup.py` default `GITHUB_ORG`

## License

MIT
