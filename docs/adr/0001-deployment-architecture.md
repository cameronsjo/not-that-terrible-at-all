# ADR-0001: Phone-Friendly Deployment Architecture for Unraid

## Status

Accepted

## Context

Deploying GitHub repositories to a personal Unraid server currently requires:

1. Adding a Dockerfile (if missing)
2. Configuring deployment pipelines
3. Managing secrets/API keys
4. Setting up networking/routing

Steps 2-4 are difficult to accomplish from a mobile device. The goal is to create a system ("not-that-terrible-at-all") that enables deploying new applications to Unraid with minimal friction, ideally just adding a small workflow file from GitHub's mobile interface.

### Constraints

- **Primary interface**: Mobile phone via GitHub web UI
- **Network access**: Unraid accessible via Tailscale (not publicly exposed)
- **Existing infrastructure**: Unraid server, no reverse proxy currently configured
- **Secrets**: Need to share common secrets (API keys, etc.) across multiple applications

### Options Evaluated

#### Deployment Method

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| SSH + docker-compose | GitHub Action SSHs to Unraid, runs docker-compose | Simple, flexible, full control | SSH key in GitHub secrets, inbound connection required |
| Registry + Watchtower | Build image → push to GHCR → Watchtower pulls | No inbound connections, no SSH keys exposed | Slightly more moving parts, polling delay |
| Self-hosted runner | GitHub runner on Unraid pulls work | Most secure (outbound only), native GitHub integration | Runner maintenance, resource usage |

#### Secrets Management

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| GitHub Org secrets | Secrets stored at organization level, inherited by repos | Native GitHub, easy mobile access, `secrets: inherit` | All repos see all secrets |
| Secrets file on Unraid | `.env` file(s) on Unraid, referenced by docker-compose | Secrets never leave Unraid | Must SSH/manage file separately |
| Vault/Infisical | Dedicated secrets management | Full audit trail, rotation | Overkill for personal use |

#### Workflow Injection

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| GitHub App | Custom app watches repos, auto-injects workflows | Zero-touch after initial setup | Must build, host, and maintain the app |
| Reusable workflows | Shared workflow in central repo, apps reference it | Simple, native GitHub, ~10 lines per app | Must add file to each repo |

## Decision

### Primary Architecture: Registry + Watchtower

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GITHUB                                          │
│  ┌─────────────┐    ┌──────────────────┐    ┌─────────────────────────────┐ │
│  │ App Repo    │───▶│ GitHub Actions   │───▶│ GitHub Container Registry   │ │
│  │ (your fork) │    │ (build + push)   │    │ (ghcr.io/you/app:latest)    │ │
│  └─────────────┘    └──────────────────┘    └─────────────────────────────┘ │
│         │                                              │                     │
│         │ references                                   │                     │
│         ▼                                              │                     │
│  ┌─────────────────────────────┐                       │                     │
│  │ not-that-terrible-at-all    │                       │                     │
│  │ (reusable workflow)         │                       │                     │
│  └─────────────────────────────┘                       │                     │
└─────────────────────────────────────────────────────────│─────────────────────┘
                                                         │
                                                         │ pulls (outbound)
                                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              UNRAID (via Tailscale)                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │ Watchtower  │───▶│ App Container│    │ Traefik/   │◀── spa.sjo.lol      │
│  │ (polls GHCR)│    │ (auto-updated│    │ NPM        │◀── api.sjo.lol      │
│  └─────────────┘    └─────────────┘    └─────────────┘                      │
│                            │                  ▲                              │
│                            └──────────────────┘                              │
│                              routes to container                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Secrets: GitHub Organization Secrets

- Create a GitHub Organization for personal projects
- Store shared secrets at org level: `GHCR_TOKEN`, common API keys
- App workflows use `secrets: inherit` to access them
- App-specific secrets added at repo level

### Workflow: Reusable GitHub Actions

- Central `not-that-terrible-at-all` repo contains the reusable workflow
- App repos add a ~10 line caller workflow:

```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    uses: YOUR-ORG/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
    with:
      app-name: my-cool-app
      port: 3000
```

### Reverse Proxy: Nginx Proxy Manager

- GUI-based, easy to configure from phone
- Runs as container on Unraid
- Unraid WebUI moves to port 8443
- NPM takes 80/443, routes by hostname

## Consequences

### Positive

- **Phone-friendly**: Adding a new app = fork repo + add one small YAML file
- **Secure**: No SSH keys in GitHub, no inbound connections, Tailscale-only access
- **Low maintenance**: Watchtower handles updates automatically
- **Shared config**: Org secrets mean no per-repo secret configuration for common values
- **Flexible**: Can override defaults per-app via workflow inputs

### Negative

- **Polling delay**: Watchtower polls on interval (default 5min), not instant deploys
- **GitHub dependency**: Relies on GHCR availability
- **Org requirement**: Need GitHub organization (free tier works)
- **Initial setup**: One-time Unraid configuration required (Watchtower, NPM, move WebUI port)

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| GHCR rate limits | Use authenticated pulls (GHCR_TOKEN), personal use is well under limits |
| Watchtower updates wrong container | Use explicit image tags, label containers for Watchtower scope |
| NPM becomes unmaintained | Traefik is a solid alternative, can migrate |

## References

- [GitHub Reusable Workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [Watchtower](https://containrrr.dev/watchtower/)
- [Nginx Proxy Manager](https://nginxproxymanager.com/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
