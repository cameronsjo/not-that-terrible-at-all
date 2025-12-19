# Choosing a Deployment Mode

This project offers two deployment modes. Choose based on your priorities.

## Phone-Friendly Reality Check

Let's be honest about what requires a terminal and what doesn't:

| Task | ✈️ Autopilot | 🛡️ Checkpoint |
|------|-------------|---------------|
| **One-time setup** | Terminal | Terminal |
| **Add GitHub secrets** | Terminal/Web | N/A |
| **Add new app to gate** | N/A | Phone (web UI at `/images`) |
| **Edit docker-compose.yml** | Phone (GitHub web) | Phone (GitHub web) |
| **Deploy** | Automatic | Phone (TOTP code) |
| **Monitor pending** | GitHub Actions | Phone (`/pending`, `/images`) |

**Key insight:** After initial setup, Checkpoint is fully phone-friendly. Autopilot requires terminal access to add secrets for each new repo, but then runs automatically.

## Quick Decision Tree

```
Do you want protection if your GitHub account is compromised?
│
├─ Yes → 🛡️ Checkpoint
│        Security first. Manual approval required.
│
└─ No  → ✈️ Autopilot
         Speed first. Fully automated.
```

## Mode Comparison

| Aspect | ✈️ Autopilot | 🛡️ Checkpoint |
|--------|-------------|---------------|
| **Speed** | ~2 min (automated) | ~5 min + manual approval |
| **GitHub compromise** | Full server access | Blocked by TOTP |
| **Secrets in GitHub** | SSH key, PAT, host/user | None |
| **Config sync** | SCP pushes files | OCI artifact pull |
| **Network** | Inbound to Unraid | Outbound only |
| **Setup complexity** | Per-repo secrets | One-time gate setup |

## ✈️ Autopilot Mode

**Best for:** Experimental apps, rapid iteration, trusted environments.

```yaml
# .github/workflows/deploy.yml
name: Autopilot Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy-autopilot.yml@main
    secrets: inherit
    with:
      config-files: "docker-compose.yml,config/*"
```

### Required Secrets (org-level)

| Secret | Description |
|--------|-------------|
| `UNRAID_HOST` | IP or hostname |
| `UNRAID_USER` | SSH user (usually `root`) |
| `UNRAID_SSH_KEY` | Private SSH key |
| `GHCR_PAT` | Personal access token with `read:packages` |

### Flow

```
Push → Build image → SCP configs → SSH docker-compose up → Done
         ~1 min         instant           instant
```

### Security Model

```
GitHub account compromised?
│
└─ Attacker has SSH key
   └─ Full shell access to Unraid
      └─ Game over
```

## 🛡️ Checkpoint Mode

**Best for:** Production apps, sensitive data, paranoid users.

```yaml
# .github/workflows/deploy.yml
name: Checkpoint Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    uses: cameronsjo/not-that-terrible-at-all/.github/workflows/deploy-checkpoint.yml@main
    secrets: inherit
```

### Required Setup

1. Run approval gate on Unraid (one-time)
2. Scan QR code with 1Password (one-time)
3. Add entry via web UI at `/images` (per app, phone-friendly)

### Flow

```
Push → Build image → Push config artifact → Gate polls → Notification
                                                              │
                                     You enter 6-digit code ◄─┘
                                              │
                              Gate pulls config + image → Restart → Done
```

### Security Model

```
GitHub account compromised?
│
└─ Attacker pushes malicious image
   └─ Gate asks for TOTP code
      └─ Attacker doesn't have your phone
         └─ Attack blocked
```

## Hybrid Approach

Use both modes for different apps:

```
┌─────────────────────────────────────────────────────────────┐
│                        YOUR APPS                             │
├────────────────────────────┬────────────────────────────────┤
│  Low Risk                  │  High Risk                      │
│  ─────────                 │  ─────────                      │
│  • Experimental apps       │  • Production apps              │
│  • Dev/staging             │  • Apps with user data          │
│  • Non-sensitive           │  • Infrastructure tools         │
│                            │                                  │
│  → ✈️ Autopilot            │  → 🛡️ Checkpoint                │
│                            │                                  │
│  deploy-autopilot.yml      │  deploy-checkpoint.yml          │
│  Fast, automated           │  Secure, manual approval        │
└────────────────────────────┴────────────────────────────────┘
```

## Config Drift: Solved in Both

Both modes sync your `docker-compose.yml` from Git:

| Mode | How Config Syncs |
|------|-----------------|
| Autopilot | SCP copies files before `docker-compose up` |
| Checkpoint | OCI artifact pulled before restart |

If you add a new port or env var in Git, it deploys with the new image.

## Migration Path

Start with Autopilot for developer satisfaction. As your homelab matures:

1. Identify critical apps (data, infrastructure)
2. Set up Checkpoint gate once
3. Move critical apps to Checkpoint
4. Keep experimental apps on Autopilot

No need to choose upfront. Use the right tool for each job.
