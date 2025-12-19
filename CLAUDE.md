# not-that-terrible-at-all

Phone-friendly deployment pipeline for GitHub repos to Unraid servers, with TOTP-based security that's independent of GitHub.

## What This Project Does

Solves: "I found a cool app on GitHub and want to deploy it to my Unraid server from my phone, without worrying about supply chain attacks."

**The flow:**
1. User forks a repo, adds Dockerfile + workflow file (from phone)
2. GitHub Actions builds image, signs with cosign, pushes to GHCR
3. TOTP Approval Gate on Unraid detects new image
4. User gets notification, enters 6-digit code from 1Password
5. Gate pulls image, restarts container

**Key security property:** Even if GitHub account/org is fully compromised, attacker cannot deploy—they don't have the TOTP secret (stored in 1Password + Unraid, never touches GitHub).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GITHUB                                          │
│  ┌──────────────┐    ┌────────────────────┐    ┌─────────────────────────┐  │
│  │ User's App   │───▶│ Reusable Workflow  │───▶│ GHCR                    │  │
│  │ Repo         │    │ (this repo)        │    │ ghcr.io/org/app:latest  │  │
│  │              │    │ • Build image      │    │ + cosign signature      │  │
│  │ 10-line      │    │ • Sign with cosign │    │                         │  │
│  │ workflow.yml │    │ • Push to GHCR     │    │                         │  │
│  └──────────────┘    └────────────────────┘    └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                                            │
                                                            │ polls
                                                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         UNRAID (via Tailscale)                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ TOTP Approval Gate                                                    │   │
│  │ ─────────────────                                                     │   │
│  │ 1. Polls GHCR for new digests                                        │   │
│  │ 2. New image? → Send notification (ntfy/telegram/discord/pushover)  │   │
│  │ 3. User opens link, enters TOTP code                                 │   │
│  │ 4. Code valid? → Pull image, restart container                       │   │
│  │                                                                       │   │
│  │ TOTP secret: In 1Password + here. NOT in GitHub.                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │ App Container    │  │ Nginx Proxy Mgr  │                                 │
│  │ (auto-updated)   │  │ (routes domains) │                                 │
│  └──────────────────┘  └──────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## File Map

| Path | What It Does |
|------|--------------|
| `.github/workflows/deploy.yml` | **Reusable workflow.** Build, cosign sign, push to GHCR. Called by user repos. |
| `approval-gate/app.py` | **TOTP Gate service.** Flask app that polls GHCR, sends notifications, verifies TOTP, pulls images. |
| `approval-gate/setup.py` | Generates TOTP secret + QR code for initial setup. |
| `approval-gate/docker-compose.yml` | Deploy the gate on Unraid. |
| `templates/Dockerfile.*` | Copy-paste Dockerfiles for node/python/go/static. |
| `templates/deploy.yml` | The 10-line workflow users add to their repos. |
| `scripts/verify-and-pull.sh` | Manual cosign verification (alternative to gate). |
| `docs/security-architecture.md` | Full diagram of what protects against what. |
| `docs/security-model.md` | Threat model and layer explanations. |

## Key Design Decisions

### TOTP over Cosign for GitHub compromise protection

- **Cosign keyless:** Signs with GitHub OIDC identity. If GitHub compromised, attacker's images get valid signatures.
- **Cosign with your key:** Key stored in GitHub secrets. If GitHub compromised, attacker has the key.
- **TOTP:** Secret stored in 1Password + Unraid. GitHub never sees it. Attacker can push images but can't approve pulls.

**Verdict:** TOTP is simpler and actually works for the "GitHub compromised" threat model. Cosign is still useful for MITM/tampering protection.

### Multiple notification backends (or none)

Notifications are convenience, not security. The gate supports:
- `none` — just check `/pending` manually
- `ntfy` — free, self-hostable
- `telegram` — free bot
- `discord` — webhook
- `pushover` — paid but polished

Default is `none` for simplest setup.

### Reusable workflow over GitHub App

A GitHub App would auto-inject workflows, but:
- More complex to build and maintain
- Another thing to host
- Single point of failure

Reusable workflow: user adds 10 lines, done. More transparent.

## Common Tasks

### Adding a new Dockerfile template

1. Create `templates/Dockerfile.{type}`
2. Pattern: multi-stage build, non-root user, health check, common ports
3. Update `scripts/bootstrap.sh` detection logic
4. Add copy-paste example to `docs/new-app-guide.md`

### Updating pinned action SHAs

Actions in `.github/workflows/deploy.yml` are pinned to SHA for supply chain security.

1. Find new release on action's repo (e.g., `actions/checkout`)
2. Get full commit SHA for that tag
3. Update SHA in workflow
4. Add comment with version: `# v4.2.2`

### Adding a notification backend

1. Add config vars to `CONFIG` dict in `approval-gate/app.py`
2. Create `notify_{method}()` function
3. Add case to `send_notification()`
4. Update `.env` template in `setup.py`
5. Document in `approval-gate/README.md`

### Modifying the reusable workflow

1. Edit `.github/workflows/deploy.yml`
2. Test: push to branch, reference `@branch-name` from test repo
3. Verify image builds, signs, pushes correctly
4. Merge to main

## Security Layers Explained

| Layer | Protects Against | Phone-Friendly |
|-------|------------------|----------------|
| TOTP Approval Gate | GitHub account/org compromise | Yes (enter code) |
| Environment protection | Accidental/malicious PRs | Yes (tap approve) |
| Cosign signing | MITM, registry tampering | Automatic |
| Pinned actions | Compromised actions | Automatic |
| OIDC auth | Stolen PATs | Automatic |

**See `docs/security-architecture.md` for the full trust boundary diagram.**

## Testing

### Test the reusable workflow

1. Create test repo with simple app
2. Add workflow: `uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy.yml@main`
3. Push and verify:
   - Image appears in GHCR
   - Cosign signature verifiable

### Test the approval gate

1. Run `docker-compose up` locally
2. Add test image to `config/images.json`
3. Push a new tag to that image
4. Verify notification (if configured) and approval flow

## Dependencies

- **GitHub Actions** — workflow execution
- **GitHub Container Registry** — image storage
- **Docker Buildx** — multi-platform builds
- **Cosign/Sigstore** — image signing
- **Flask** — approval gate web framework
- **pyotp** — TOTP implementation
- **requests** — HTTP client for notifications and GHCR polling

## Related Docs

- [Sigstore/Cosign](https://docs.sigstore.dev/)
- [GitHub Reusable Workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [Ntfy](https://ntfy.sh/)
- [pyotp](https://pyauth.github.io/pyotp/)
