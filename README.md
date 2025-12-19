# not-that-terrible-at-all

Deploy GitHub repos to your Unraid server from your phone in 5 minutes.

## The Problem

You find a cool web app on GitHub. You want to run it on your Unraid server. But:

1. It doesn't have a Dockerfile (easy fix)
2. Setting up deployment pipelines requires a computer
3. Managing secrets across apps is annoying
4. You just want to do this from your phone while high

## The Solution

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  Fork repo      │────▶│ Add 10-line  │────▶│ GitHub builds image  │
│  Add Dockerfile │     │ workflow.yml │     │ Pushes to GHCR       │
└─────────────────┘     └──────────────┘     └──────────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  App is live    │◀────│ Watchtower   │◀────│ Pulls new images     │
│  Auto-updates   │     │ on Unraid    │     │ automatically        │
└─────────────────┘     └──────────────┘     └──────────────────────┘
```

## Quick Start

### One-Time Unraid Setup

See [docs/unraid-setup.md](docs/unraid-setup.md) for complete instructions.

TL;DR:

1. Move Unraid WebUI to port 8443
2. Install Nginx Proxy Manager (ports 80/443)
3. Install Watchtower
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
    uses: YOUR_ORG/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
```

4. Create docker-compose on Unraid
5. Add to Nginx Proxy Manager
6. Done

## Project Structure

```
not-that-terrible-at-all/
├── .github/workflows/
│   └── deploy.yml           # Reusable workflow (the magic)
├── templates/
│   ├── Dockerfile.node      # Node.js apps
│   ├── Dockerfile.python    # Python apps
│   ├── Dockerfile.static    # SPAs and static sites
│   ├── Dockerfile.go        # Go apps
│   ├── docker-compose.yml   # Unraid deployment template
│   ├── deploy.yml           # Workflow caller template
│   └── env.example          # Environment variables template
├── scripts/
│   └── bootstrap.sh         # Quick setup script
├── docs/
│   ├── adr/
│   │   └── 0001-deployment-architecture.md
│   ├── unraid-setup.md      # One-time server setup
│   └── new-app-guide.md     # Phone-friendly deploy guide
└── README.md
```

## How It Works

### GitHub Side

1. Your app repo has a minimal workflow that calls this repo's reusable workflow
2. On push to main, GitHub Actions builds a Docker image
3. Image is pushed to GitHub Container Registry (ghcr.io)
4. Org-level secrets are inherited (no per-repo configuration)

### Unraid Side

1. Watchtower polls GHCR for new images every 5 minutes
2. When a new image is found, container is automatically updated
3. Nginx Proxy Manager routes `app.yourdomain.com` to the container
4. All accessible via Tailscale (never exposed to public internet)

### Secrets Management

- Common secrets stored as GitHub Organization secrets
- App-specific secrets in repo-level secrets or `.env` on Unraid
- Workflows use `secrets: inherit` to access org secrets

## Workflow Inputs

The reusable workflow accepts these inputs:

| Input | Default | Description |
|-------|---------|-------------|
| `app-name` | repo name | Docker image name |
| `dockerfile` | `Dockerfile` | Path to Dockerfile |
| `context` | `.` | Docker build context |
| `platforms` | `linux/amd64` | Target architectures |
| `build-args` | (none) | Build arguments |
| `tag-strategy` | `latest` | `latest`, `sha`, `branch`, or `semver` |

Example with all options:

```yaml
jobs:
  deploy:
    uses: YOUR_ORG/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
    with:
      app-name: my-cool-app
      dockerfile: docker/Dockerfile.prod
      platforms: linux/amd64,linux/arm64
      tag-strategy: semver
      build-args: |
        NODE_ENV=production
        API_URL=https://api.example.com
```

## Architecture Decision

See [ADR-0001](docs/adr/0001-deployment-architecture.md) for the full rationale behind:

- Why Registry + Watchtower over SSH deploys
- Why GitHub Org secrets over Vault
- Why reusable workflows over GitHub Apps
- Why Nginx Proxy Manager over Traefik

## Requirements

- GitHub account (free tier works)
- GitHub Organization (free tier works, needed for org-level secrets)
- Unraid server with Docker enabled
- Tailscale (or other VPN access to Unraid)
- Domain name (optional, for pretty URLs)

## License

MIT
