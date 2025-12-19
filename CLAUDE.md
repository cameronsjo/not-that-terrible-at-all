# not-that-terrible-at-all

Phone-friendly deployment pipeline for GitHub repos to Unraid servers, with two modes: ✈️ Autopilot (fast+automated) or 🛡️ Checkpoint (secure+TOTP).

## What This Project Does

Solves: "I found a cool app on GitHub and want to deploy it to my Unraid server from my phone, without worrying about supply chain attacks."

## Two Deployment Modes

### ✈️ Autopilot Mode (Fast)

```
Push → Build → SCP configs → SSH docker-compose up → Done (~2 min)
```

- **Best for:** Experimental apps, dev/staging, rapid iteration
- **Tradeoff:** SSH key stored in GitHub. If GitHub compromised, attacker has server access.
- **Phone-friendly:** Automatic after setup. No interaction needed.

### 🛡️ Checkpoint Mode (Secure)

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
│  │ User's App   │───▶│ deploy-checkpoint.yml      │───▶│ GHCR            │  │
│  │ Repo         │    │ or                          │    │ image + config  │  │
│  │              │    │ deploy-autopilot.yml        │    │ artifact        │  │
│  └──────────────┘    └────────────────────────────┘    └─────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┴───────────────────────┐
            │                                               │
            ▼ ✈️ Autopilot                    🛡️ Checkpoint ▼
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
| `.github/workflows/deploy-checkpoint.yml` | **🛡️ Checkpoint workflow.** Build, cosign sign, push image + config artifact. |
| `.github/workflows/deploy-autopilot.yml` | **✈️ Autopilot workflow.** Build, SCP, SSH. |
| `approval-gate/app.py` | **TOTP Gate service.** Flask app: polls GHCR, web UI for images, TOTP verification. |
| `approval-gate/setup.py` | Generates TOTP secret + QR code for initial setup. |
| `templates/deploy-checkpoint.yml` | 🛡️ Checkpoint workflow template for user repos. |
| `templates/deploy-autopilot.yml` | ✈️ Autopilot workflow template for user repos. |
| `templates/Dockerfile.*` | Copy-paste Dockerfiles for node/python/go/static. |
| `docs/choosing-a-strategy.md` | Comparison guide with phone-friendliness matrix. |
| `docs/security-architecture.md` | Full diagram of trust boundaries. |

## Key Design Decisions

### Two modes, not one

Originally we built only Checkpoint (secure). Then we realized some users want speed over security for experimental apps. Now both modes exist, use the right tool for each job.

### TOTP over Cosign for GitHub compromise protection

- **Cosign keyless:** Signs with GitHub OIDC identity. If GitHub compromised, attacker's images get valid signatures.
- **Cosign with your key:** Key stored in GitHub secrets. If GitHub compromised, attacker has the key.
- **TOTP:** Secret stored in 1Password + Unraid. GitHub never sees it. Attacker can push images but can't approve pulls.

### OCI artifacts for config sync

Both modes sync `docker-compose.yml` from Git:
- **Autopilot:** SCP copies files before `docker-compose up`
- **Checkpoint:** Workflow pushes config as `:config` artifact, gate pulls and extracts on approval

This solves "config drift" where your new image needs a new port but the server has the old compose file.

### Web UI for image management

The approval gate has `/images` endpoint with a phone-friendly UI for adding/removing monitored images. Protected by TOTP for writes.

## Phone-Friendly Matrix

| Task | ✈️ Autopilot | 🛡️ Checkpoint |
|------|-------------|---------------|
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

## API Endpoints (Checkpoint Gate)

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

| Layer | Protects Against | Which Mode |
|-------|------------------|------------|
| TOTP Approval Gate | GitHub account/org compromise | Checkpoint only |
| Config sync | Config drift between Git and server | Both |
| Cosign signing | MITM, registry tampering | Checkpoint (optional) |
| Pinned actions | Compromised actions | Both |
| OIDC auth | Stolen PATs | Both |

## Claude Code: Setting Up a New Repo

When asked to "set up deployment" or "deploy this app" for a GitHub repo:

### 1. Detect App Type

Check for these files to determine Dockerfile template:

| File | App Type | Template |
|------|----------|----------|
| `package.json` + Node keywords | Node.js | `Dockerfile.node` |
| `requirements.txt` or `pyproject.toml` | Python | `Dockerfile.python` |
| `go.mod` | Go | `Dockerfile.go` |
| `index.html` (no server) | Static | `Dockerfile.static` |

### 2. Create Files

**Always create these files:**

1. `Dockerfile` — use appropriate template from `templates/`
2. `.github/workflows/deploy.yml` — copy from `templates/deploy-autopilot.yml` or `templates/deploy-checkpoint.yml`
3. `docker-compose.yml` — use template from `templates/docker-compose.yml`

**Replace placeholders:**

- `YOUR_ORG` → user's GitHub org/username
- `APP_NAME` → repo name (or user-specified name)
- Port numbers → match app type defaults

### 3. Customize for App

- **Entry point:** Update Dockerfile CMD if not `index.js`/`main.py`/etc.
- **Port:** Match between Dockerfile EXPOSE and docker-compose.yml ports
- **Build step:** Check if app needs `npm run build` or similar

### 4. Mode Selection

Ask user which mode they want, or use these defaults:

- **Experimental/dev app** → ✈️ Autopilot
- **Production/sensitive data** → 🛡️ Checkpoint
- **User hasn't set up Autopilot secrets** → 🛡️ Checkpoint

### 5. Checkpoint-Specific

If using Checkpoint mode, remind user to:

1. Add image to gate via web UI at `/images`
2. Or provide JSON for `images.json`:

```json
{
  "image": "ghcr.io/ORG/APP:latest",
  "container": "APP",
  "app_dir": "/mnt/user/appdata/APP"
}
```

See `docs/new-app-guide.md` for complete templates and troubleshooting.

## Dependencies

- **GitHub Actions** — workflow execution
- **GitHub Container Registry** — image storage
- **Docker Buildx** — multi-platform builds
- **Cosign/Sigstore** — image signing (Checkpoint)
- **ORAS** — OCI artifact push/pull for config sync
- **Flask** — approval gate web framework
- **pyotp** — TOTP implementation
- **appleboy/ssh-action** — SSH deployment (Autopilot)
- **appleboy/scp-action** — SCP file transfer (Autopilot)
