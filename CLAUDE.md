# not-that-terrible-at-all

Phone-friendly deployment pipeline for GitHub repos to Unraid servers.

## Project Purpose

Solve the "I found a cool app on GitHub and want to run it on my Unraid server from my phone" problem.

## Architecture

```
GitHub (phone-accessible)          Unraid (via Tailscale)
┌─────────────────────────┐        ┌─────────────────────────┐
│ App Repo                │        │ Watchtower              │
│ └── .github/workflows/  │        │ └── polls GHCR          │
│     └── deploy.yml ─────┼──uses──┼─▶ pulls new images      │
│         (10 lines)      │        │                         │
│                         │        │ Nginx Proxy Manager     │
│ This Repo               │        │ └── routes domains      │
│ └── .github/workflows/  │        │                         │
│     └── deploy.yml ◀────┼────────┼─ reusable workflow      │
│         (the magic)     │        │                         │
└─────────────────────────┘        └─────────────────────────┘
```

## Key Decisions (ADR-0001)

- **Registry + Watchtower** over SSH deploys (no inbound connections, no SSH keys in GitHub)
- **GitHub Org secrets** for shared API keys (`secrets: inherit`)
- **Reusable workflows** over GitHub App (simpler, native GitHub, ~10 lines per app)
- **Nginx Proxy Manager** for reverse proxy (GUI, phone-friendly)

## File Structure

| Path | Purpose |
|------|---------|
| `.github/workflows/deploy.yml` | Reusable workflow - builds Docker image, pushes to GHCR |
| `templates/Dockerfile.*` | Copy-paste Dockerfiles for common app types |
| `templates/deploy.yml` | The 10-line workflow file apps add |
| `templates/docker-compose.yml` | Template for Unraid deployment |
| `docs/unraid-setup.md` | One-time Unraid configuration |
| `docs/new-app-guide.md` | Phone-friendly deploy walkthrough |

## Workflow Inputs

The reusable workflow at `.github/workflows/deploy.yml` accepts:

- `app-name`: Docker image name (default: repo name)
- `dockerfile`: Path to Dockerfile (default: `Dockerfile`)
- `context`: Build context (default: `.`)
- `platforms`: Target architectures (default: `linux/amd64`)
- `build-args`: Build arguments (multiline string)
- `tag-strategy`: `latest`, `sha`, `branch`, or `semver`

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

### Updating documentation

- Keep `docs/new-app-guide.md` phone-friendly (copy-pasteable snippets)
- Update ADR if architectural decisions change

## Dependencies

- GitHub Actions (workflow execution)
- GitHub Container Registry (image storage)
- Docker Buildx (multi-platform builds)

## Testing

To test the reusable workflow:

1. Fork/create a simple test app repo
2. Add workflow referencing this repo: `uses: ORG/not-that-terrible-at-all/.github/workflows/deploy.yml@main`
3. Push and verify image appears in GHCR

## Related

- [Watchtower docs](https://containrrr.dev/watchtower/)
- [GitHub reusable workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [Nginx Proxy Manager](https://nginxproxymanager.com/)
