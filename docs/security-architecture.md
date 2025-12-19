# Security Architecture

Full diagram of the deployment pipeline and security layers.

## System Overview

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                            YOUR PHONE                                          ║
║  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                ║
║  │ GitHub App      │  │ Pushover        │  │ 1Password       │                ║
║  │ (optional)      │  │                 │  │ (TOTP codes)    │                ║
║  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘                ║
║           │                    │                    │                          ║
║     Tap approve          Tap link              Enter code                      ║
║     (Layer 1)            (Layer 2)             (Layer 2)                       ║
╚═══════════╪════════════════════╪════════════════════╪══════════════════════════╝
            │                    │                    │
            ▼                    │                    │
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              GITHUB                                            ║
║                                                                                ║
║  ┌─────────────┐      ┌─────────────────────────────────────────────────────┐ ║
║  │ Your Repo   │      │ GitHub Actions                                      │ ║
║  │             │─────▶│                                                     │ ║
║  │ Push to     │      │  ┌─────────────────────────────────────────────┐   │ ║
║  │ main        │      │  │ LAYER 1: Environment Protection (optional)  │   │ ║
║  └─────────────┘      │  │ ─────────────────────────────────────────── │   │ ║
║        ▲              │  │ Workflow WAITS for your approval in GitHub  │   │ ║
║        │              │  │ app before proceeding. Phone notification.  │   │ ║
║   Attacker            │  │                                             │   │ ║
║   pushes here         │  │ IF GitHub compromised: Attacker can skip ❌ │   │ ║
║   if compromised      │  └─────────────────────────────────────────────┘   │ ║
║                       │                       │                             │ ║
║                       │                       ▼                             │ ║
║                       │  ┌─────────────────────────────────────────────┐   │ ║
║                       │  │ Build Docker Image                          │   │ ║
║                       │  │ • Pinned actions (SHA, not @v4)             │   │ ║
║                       │  │ • OIDC auth (no stored tokens)              │   │ ║
║                       │  └─────────────────────────────────────────────┘   │ ║
║                       │                       │                             │ ║
║                       │                       ▼                             │ ║
║                       │  ┌─────────────────────────────────────────────┐   │ ║
║                       │  │ CRYPTOGRAPHIC: Cosign Signing               │   │ ║
║                       │  │ ───────────────────────────────────────────│   │ ║
║                       │  │ Signs image with:                          │   │ ║
║                       │  │ • Keyless (Sigstore): GitHub OIDC identity │   │ ║
║                       │  │ • Your key: Private key in GitHub secrets  │   │ ║
║                       │  │                                             │   │ ║
║                       │  │ IF GitHub compromised:                      │   │ ║
║                       │  │ • Keyless: Attacker CAN sign (owns OIDC) ❌│   │ ║
║                       │  │ • Your key: Attacker HAS it in secrets ❌  │   │ ║
║                       │  └─────────────────────────────────────────────┘   │ ║
║                       │                       │                             │ ║
║                       └───────────────────────┼─────────────────────────────┘ ║
║                                               │                               ║
║                                               ▼                               ║
║                            ┌─────────────────────────────────────┐            ║
║                            │ GitHub Container Registry           │            ║
║                            │ ghcr.io/you/app:latest              │            ║
║                            │ + signature                         │            ║
║                            └─────────────────────────────────────┘            ║
║                                               │                               ║
╚═══════════════════════════════════════════════╪═══════════════════════════════╝
                                                │
                    ┌───────────────────────────┴──────────────────────┐
                    │                                                  │
                    ▼                                                  ▼
        ╔═══════════════════════╗                      ╔═══════════════════════╗
        ║ WITHOUT TOTP GATE     ║                      ║ WITH TOTP GATE        ║
        ╠═══════════════════════╣                      ╠═══════════════════════╣
        ║                       ║                      ║                       ║
        ║  Watchtower           ║                      ║  Approval Gate        ║
        ║  ───────────          ║                      ║  ─────────────        ║
        ║  • Polls GHCR         ║                      ║  • Polls GHCR         ║
        ║  • Sees new image     ║                      ║  • Sees new image     ║
        ║  • Pulls immediately  ║                      ║  • Sends Pushover     ║
        ║                       ║                      ║  • WAITS for TOTP     ║
        ║  Cosign verify?       ║                      ║  • You enter code     ║
        ║  • Optional           ║                      ║  • THEN pulls         ║
        ║  • But if GitHub      ║                      ║                       ║
        ║    compromised,       ║                      ║  ✓ TOTP secret is     ║
        ║    signature valid ❌ ║                      ║    NOT in GitHub      ║
        ║                       ║                      ║  ✓ Attacker can't     ║
        ║  ❌ AUTO-DEPLOYS      ║                      ║    approve            ║
        ║    MALWARE            ║                      ║                       ║
        ║                       ║                      ║  ✅ BLOCKS ATTACK     ║
        ╚═══════════════════════╝                      ╚═══════════════════════╝
```

## Where Crypto Helps vs Doesn't

### Scenario: Normal operation (GitHub NOT compromised)

| Layer | Status | Notes |
|-------|--------|-------|
| Cosign keyless | ✅ Works | Proves image came from YOUR GitHub Actions |
| Cosign your key | ✅ Works | Proves image signed with YOUR key |
| TOTP gate | ✅ Works | Extra approval step (belt + suspenders) |

All three work. Cosign catches tampering in transit.

### Scenario: GitHub account/org COMPROMISED

| Layer | Status | Notes |
|-------|--------|-------|
| Cosign keyless | ❌ Useless | Attacker's image has valid signature (they control the GitHub OIDC identity) |
| Cosign your key | ❌ Useless | Attacker has your key from GitHub secrets |
| TOTP gate | ✅ Saves you | Secret is in 1Password + Unraid, NOT GitHub |

### Scenario: MITM / Registry tampering

| Layer | Status | Notes |
|-------|--------|-------|
| Cosign | ✅ Saves you | Signature won't verify - attack detected |
| TOTP | ⚠️ Won't help | You might approve a tampered image (doesn't verify content) |

## The Bottom Line

```
TOTP Gate = "Is this YOU approving?"     (authentication)
Cosign    = "Is this the REAL image?"    (integrity)
```

| Threat | TOTP Gate | Cosign |
|--------|-----------|--------|
| GitHub compromised | ✅ Saves you | ❌ Useless |
| Network/registry tampering | ❌ Won't help | ✅ Saves you |

## Recommendations

### For most users: TOTP Gate

The main threat is GitHub account compromise. TOTP handles this simply.

```bash
# One-time setup
cd /mnt/user/appdata/approval-gate
docker-compose run --rm gate python setup.py
# Scan QR with 1Password
docker-compose up -d
```

### For paranoid users: TOTP + Cosign

If you also want protection against network/registry attacks, add cosign verification. But note that for GitHub compromise protection, the signing key would need to be stored OUTSIDE GitHub (e.g., on your laptop), which breaks the phone-friendly workflow.

### Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                     GITHUB TRUST BOUNDARY                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ • Your code                                                │  │
│  │ • GitHub Actions workflows                                 │  │
│  │ • GitHub Secrets (including cosign private key)           │  │
│  │ • Environment protection approvals                         │  │
│  │ • Cosign keyless signatures (OIDC identity)               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  If attacker controls GitHub, they control ALL of this.         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    OUTSIDE GITHUB (SAFE)                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ • TOTP secret (in 1Password + Unraid)                      │  │
│  │ • Your phone (Pushover notifications)                      │  │
│  │ • Unraid server (approval gate service)                    │  │
│  │ • Cosign key on your laptop (if not in GitHub secrets)    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Attacker with GitHub access CANNOT touch these.                │
└─────────────────────────────────────────────────────────────────┘
```
