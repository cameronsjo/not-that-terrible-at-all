# not-that-terrible-at-all

Phone-friendly deployment pipeline for GitHub repos to Unraid servers, with two strategies: fast+automated (SSH) or secure+TOTP (approval gate).

## What This Project Does

Solves: "I found a cool app on GitHub and want to deploy it to my Unraid server from my phone, without worrying about supply chain attacks."

## Two Deployment Strategies

### Strategy One: SSH + SCP (Fast)

```
Push → Build → SCP configs → SSH docker-compose up → Done (~2 min)
```

- **Best for:** Experimental apps, dev/staging, rapid iteration
- **Tradeoff:** SSH key stored in GitHub. If GitHub compromised, attacker has server access.
- **Phone-friendly:** Automatic after setup. No interaction needed.

### Strategy Two: TOTP Gate (Secure)

```
Push → Build → Gate polls → Notification → TOTP code → Pull → Done (~5 min)
```

- **Best for:** Production apps, sensitive data, paranoid users
- **Security:** If GitHub compromised, attacker blocked by TOTP on your phone.
- **Phone-friendly:** Web UI for image management, TOTP for approvals.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GITHUB                                          │
│  ┌──────────────┐    ┌────────────────────────────┐    ┌─────────────────┐  │
│  │ User's App   │───▶│ deploy.yml (TOTP strategy) │───▶│ GHCR            │  │
│  │ Repo         │    │ or                          │    │ image + config  │  │
│  │              │    │ deploy-ssh.yml (SSH strat)  │    │ artifact        │  │
│  └──────────────┘    └────────────────────────────┘    └─────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┴───────────────────────┐
            │                                               │
            ▼ Strategy One                      Strategy Two ▼
┌───────────────────────────┐            ┌───────────────────────────┐
│ SCP + SSH                  │            │ TOTP Approval Gate        │
│ ────────────               │            │ ────────────────          │
│ Push configs via SCP      │            │ Polls GHCR for changes   │
│ Run docker-compose up     │            │ Sends notification       │
│ via SSH                   │            │ User enters TOTP code    │
│                           │            │ Pulls config + image     │
│ Automatic, no approval    │            │ Restarts container       │
└───────────────────────────┘            └───────────────────────────┘
```

## File Map

| Path | What It Does |
|------|--------------|
| `.github/workflows/deploy.yml` | **Strategy Two workflow.** Build, cosign sign, push image + config artifact. |
| `.github/workflows/deploy-ssh.yml` | **Strategy One workflow.** Build, SCP, SSH. |
| `approval-gate/app.py` | **TOTP Gate service.** Flask app: polls GHCR, web UI for images, TOTP verification. |
| `approval-gate/setup.py` | Generates TOTP secret + QR code for initial setup. |
| `templates/deploy.yml` | Strategy Two workflow template for user repos. |
| `templates/deploy-ssh.yml` | Strategy One workflow template for user repos. |
| `templates/Dockerfile.*` | Copy-paste Dockerfiles for node/python/go/static. |
| `docs/choosing-a-strategy.md` | Comparison guide with phone-friendliness matrix. |
| `docs/security-architecture.md` | Full diagram of trust boundaries. |

## Key Design Decisions

### Two strategies, not one

Originally we built only TOTP (secure). Then we realized some users want speed over security for experimental apps. Now both strategies exist, use the right tool for each job.

### TOTP over Cosign for GitHub compromise protection

- **Cosign keyless:** Signs with GitHub OIDC identity. If GitHub compromised, attacker's images get valid signatures.
- **Cosign with your key:** Key stored in GitHub secrets. If GitHub compromised, attacker has the key.
- **TOTP:** Secret stored in 1Password + Unraid. GitHub never sees it. Attacker can push images but can't approve pulls.

### OCI artifacts for config sync

Both strategies now sync `docker-compose.yml` from Git:
- **SSH:** SCP copies files before `docker-compose up`
- **TOTP:** Workflow pushes config as `:config` artifact, gate pulls and extracts on approval

This solves "config drift" where your new image needs a new port but the server has the old compose file.

### Web UI for image management

The approval gate has `/images` endpoint with a phone-friendly UI for adding/removing monitored images. Protected by TOTP for writes.

## Phone-Friendly Matrix

| Task | Strategy One (SSH) | Strategy Two (TOTP) |
|------|-------------------|---------------------|
| One-time setup | Terminal | Terminal |
| Add new app | Terminal (secrets) | Phone (web UI at `/images`) |
| Edit docker-compose.yml | Phone (GitHub web) | Phone (GitHub web) |
| Deploy | Automatic | Phone (TOTP code) |
| Monitor | GitHub Actions | Phone (`/pending`, `/images`) |

## Common Tasks

### Adding a new Dockerfile template

1. Create `templates/Dockerfile.{type}`
2. Pattern: multi-stage build, non-root user, health check
3. Update `docs/new-app-guide.md`

### Updating pinned action SHAs

Actions are pinned to SHA for supply chain security:

1. Find new release on action's repo
2. Get full commit SHA for that tag
3. Update SHA in workflow, add comment with version

### Adding a notification backend

1. Add config vars to `CONFIG` dict in `approval-gate/app.py`
2. Create `notify_{method}()` function
3. Add case to `send_notification()`
4. Update `.env` template in `setup.py`
5. Document in `approval-gate/README.md`

## API Endpoints (TOTP Gate)

| Endpoint | Description |
|----------|-------------|
| `GET /` | Status and config info |
| `GET /pending` | List pending updates (JSON) |
| `GET /approve/<token>` | Approval page |
| `POST /approve/<token>` | Submit TOTP code |
| `GET /images` | Image management UI |
| `POST /images/add` | Add image (requires TOTP) |
| `POST /images/delete` | Remove image (requires TOTP) |

## Security Layers

| Layer | Protects Against | Which Strategy |
|-------|------------------|----------------|
| TOTP Approval Gate | GitHub account/org compromise | Two only |
| Config sync | Config drift between Git and server | Both |
| Cosign signing | MITM, registry tampering | Two (optional) |
| Pinned actions | Compromised actions | Both |
| OIDC auth | Stolen PATs | Both |

## Dependencies

- **GitHub Actions** — workflow execution
- **GitHub Container Registry** — image storage
- **Docker Buildx** — multi-platform builds
- **Cosign/Sigstore** — image signing (Strategy Two)
- **ORAS** — OCI artifact push/pull for config sync
- **Flask** — approval gate web framework
- **pyotp** — TOTP implementation
- **appleboy/ssh-action** — SSH deployment (Strategy One)
- **appleboy/scp-action** — SCP file transfer (Strategy One)
