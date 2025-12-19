# not-that-terrible-at-all

Phone-friendly deployment pipeline for GitHub repos to Unraid servers.

## Project Purpose

Solve the "I found a cool app on GitHub and want to run it on my Unraid server from my phone" problem.

## Architecture

```
GitHub (phone-accessible)          Unraid (via Tailscale)
┌─────────────────────────┐        ┌─────────────────────────────────┐
│ App Repo                │        │ Verified Updater                │
│ └── .github/workflows/  │        │ └── polls GHCR                  │
│     └── deploy.yml ─────┼──uses──┼─▶ verifies cosign signature     │
│         (10 lines)      │        │ └── pulls only if valid         │
│                         │        │                                 │
│ This Repo               │        │ Nginx Proxy Manager             │
│ └── .github/workflows/  │        │ └── routes domains              │
│     └── deploy.yml ◀────┼────────┼─ reusable workflow              │
│         (the magic)     │        │   + cosign signing              │
└─────────────────────────┘        └─────────────────────────────────┘
```

## Security Model

See `docs/security-model.md` for full details.

| Layer | What | Phone-Friendly |
|-------|------|----------------|
| Environment protection | Approval before build | Yes (tap in GitHub app) |
| Cosign signing | Image signatures | Automatic |
| Pinned actions | SHA-pinned deps | Automatic |
| Unraid verification | Verify before pull | Automatic |
| Your own key | GitHub-independent trust | One-time setup |

**Fork-friendly note:** The caller template at `templates/deploy.yml` has one line to update with your org/username.

## Key Decisions (ADR-0001)

- **Registry + Watchtower/Verified Updater** over SSH deploys (no inbound connections)
- **GitHub Org secrets** for shared API keys (`secrets: inherit`)
- **Reusable workflows** over GitHub App (simpler, native GitHub)
- **Cosign signing** for supply chain security
- **Nginx Proxy Manager** for reverse proxy (GUI, phone-friendly)

## File Structure

| Path | Purpose |
|------|---------|
| `.github/workflows/deploy.yml` | Reusable workflow - build, sign, push to GHCR |
| `templates/Dockerfile.*` | Copy-paste Dockerfiles for common app types |
| `templates/deploy.yml` | Workflow caller template (10 lines) |
| `templates/docker-compose.yml` | Unraid deployment template |
| `templates/docker-compose.verified-updater.yml` | Signature-verifying updater |
| `scripts/verify-and-pull.sh` | Manual signature verification |
| `docs/unraid-setup.md` | One-time Unraid configuration |
| `docs/new-app-guide.md` | Phone-friendly deploy walkthrough |
| `docs/security-model.md` | Threat model and security layers |

## Workflow Inputs

The reusable workflow at `.github/workflows/deploy.yml` accepts:

| Input | Default | Description |
|-------|---------|-------------|
| `app-name` | repo name | Docker image name |
| `dockerfile` | `Dockerfile` | Path to Dockerfile |
| `context` | `.` | Build context |
| `platforms` | `linux/amd64` | Target architectures |
| `build-args` | (none) | Build arguments (multiline) |
| `tag-strategy` | `latest` | `latest`, `sha`, `branch`, `semver` |
| `environment` | (none) | GitHub environment for approval |
| `sign-image` | `true` | Cosign signing + attestation |

## Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `GHCR_TOKEN` | No | Falls back to `GITHUB_TOKEN` |
| `COSIGN_PRIVATE_KEY` | No | Your own signing key (base64) |
| `COSIGN_PASSWORD` | No | Password for signing key |

## Common Tasks

### Adding a new Dockerfile template

1. Create `templates/Dockerfile.{type}`
2. Follow existing patterns: multi-stage build, non-root user, health check
3. Update `scripts/bootstrap.sh` to detect the new type
4. Add example to `docs/new-app-guide.md`

### Modifying the reusable workflow

1. Edit `.github/workflows/deploy.yml`
2. Test by pushing to a branch, then referencing `@branch-name` from a test repo
3. Merge to main when verified

### Updating action SHAs

When updating pinned actions:
1. Find the release tag on the action's repo
2. Get the full commit SHA for that tag
3. Update the SHA in the workflow
4. Add a comment with the version: `# vX.Y.Z`

### Adding security features

- Environment protection: Document in `docs/security-model.md`
- New verification methods: Add to `scripts/` and update docs

## Dependencies

- GitHub Actions (workflow execution)
- GitHub Container Registry (image storage)
- Docker Buildx (multi-platform builds)
- Cosign/Sigstore (image signing)

## Testing

To test the reusable workflow:

1. Fork/create a simple test app repo
2. Add workflow: `uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy.yml@main`
3. Push and verify:
   - Image appears in GHCR
   - Image is signed: `cosign verify ghcr.io/yourorg/app:latest --certificate-identity-regexp='.*' --certificate-oidc-issuer='https://token.actions.githubusercontent.com'`

## Related

- [Sigstore/Cosign](https://docs.sigstore.dev/)
- [GitHub reusable workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [Nginx Proxy Manager](https://nginxproxymanager.com/)
