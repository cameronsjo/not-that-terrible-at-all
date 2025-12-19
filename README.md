# not-that-terrible-at-all

Deploy GitHub repos to your Unraid server from your phone in 5 minutes.

## The Problem

You find a cool web app on GitHub. You want to run it on your Unraid server. But:

1. It doesn't have a Dockerfile (easy fix)
2. Setting up deployment pipelines requires a computer
3. Managing secrets across apps is annoying
4. You just want to do this from your phone while high
5. You're paranoid about supply chain attacks

## The Solution

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  Fork repo      │────▶│ Add 10-line  │────▶│ GitHub builds image  │
│  Add Dockerfile │     │ workflow.yml │     │ + signs with cosign  │
└─────────────────┘     └──────────────┘     └──────────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  App is live    │◀────│ Verified     │◀────│ Verifies signature   │
│  Auto-updates   │     │ Updater      │     │ Pulls only if valid  │
└─────────────────┘     └──────────────┘     └──────────────────────┘
```

## Security First

All images are signed with [cosign/Sigstore](https://docs.sigstore.dev/). Your Unraid server verifies signatures before pulling.

| Layer | What | Phone-Friendly |
|-------|------|----------------|
| Environment protection | Approve before build | Yes (tap in GitHub app) |
| Cosign signing | Cryptographic signatures | Automatic |
| Pinned actions | SHA-pinned dependencies | Automatic |
| Unraid verification | Verify before pull | Automatic |
| Your own key | GitHub-independent trust | One-time setup |

See [docs/security-model.md](docs/security-model.md) for the full threat model.

## Quick Start

### One-Time Unraid Setup

See [docs/unraid-setup.md](docs/unraid-setup.md) for complete instructions.

TL;DR:

1. Move Unraid WebUI to port 8443
2. Install Nginx Proxy Manager (ports 80/443)
3. Install Verified Updater (or Watchtower)
4. Authenticate Docker with GHCR

### Deploy a New App

See [docs/new-app-guide.md](docs/new-app-guide.md) for the phone-friendly walkthrough.

TL;DR:

1. Fork the repo to your org
2. Add a Dockerfile (use templates in `/templates`)
3. Add `.github/workflows/deploy.yml`:

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
    with:
      sign-image: true
      # environment: production  # Uncomment for approval before build
```

4. Create docker-compose on Unraid
5. Add to Nginx Proxy Manager
6. Done

## Project Structure

```
not-that-terrible-at-all/
├── .github/workflows/
│   └── deploy.yml                        # Reusable workflow (build + sign)
├── templates/
│   ├── Dockerfile.{node,python,go,static}
│   ├── docker-compose.yml                # Basic Unraid deployment
│   ├── docker-compose.verified-updater.yml  # Signature-verifying updater
│   ├── deploy.yml                        # Workflow caller template
│   └── env.example
├── scripts/
│   ├── bootstrap.sh                      # Quick setup script
│   └── verify-and-pull.sh                # Manual signature verification
├── docs/
│   ├── adr/0001-deployment-architecture.md
│   ├── unraid-setup.md
│   ├── new-app-guide.md
│   └── security-model.md                 # Threat model & security layers
└── README.md
```

## Workflow Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `app-name` | repo name | Docker image name |
| `dockerfile` | `Dockerfile` | Path to Dockerfile |
| `context` | `.` | Docker build context |
| `platforms` | `linux/amd64` | Target architectures |
| `build-args` | (none) | Build arguments |
| `tag-strategy` | `latest` | `latest`, `sha`, `branch`, or `semver` |
| `sign-image` | `true` | Cosign signing + SBOM attestation |
| `environment` | (none) | GitHub environment for approval |

Example with security options:

```yaml
jobs:
  deploy:
    uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
    with:
      app-name: my-cool-app
      platforms: linux/amd64,linux/arm64
      sign-image: true
      environment: production  # Requires your approval before build
```

## Forking This Repo

If you fork this repo for your own use:

1. Update `templates/deploy.yml` line 37 with your org/username
2. Update `templates/images.txt` with your org/username
3. That's it - everything else auto-detects via `${{ github.repository_owner }}`

## Architecture Decisions

See [ADR-0001](docs/adr/0001-deployment-architecture.md) for the full rationale.

## Requirements

- GitHub account (free tier works)
- GitHub Organization (free, needed for org-level secrets)
- Unraid server with Docker enabled
- Tailscale (or other VPN access)
- Domain name (optional)

## Verifying Images

```bash
# Verify keyless signature (Sigstore)
cosign verify ghcr.io/yourorg/yourapp:latest \
  --certificate-identity-regexp='https://github.com/yourorg/.*' \
  --certificate-oidc-issuer='https://token.actions.githubusercontent.com'

# Verify with your own key
cosign verify --key cosign.pub ghcr.io/yourorg/yourapp:latest
```

## License

MIT
