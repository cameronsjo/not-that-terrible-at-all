#!/usr/bin/env python3
"""
TOTP Approval Gate for Docker Image Updates

Polls GHCR for new images, sends push notification, requires TOTP to approve pull.
Completely decoupled from GitHub - attacker needs your phone to approve.

Supports multiple notification methods:
- Ntfy (self-hosted, no account needed)
- Telegram (free bot)
- Pushover (paid but polished)
- Discord (webhook)
- None (just check the web UI)
"""

import json
import logging
import os
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pyotp
import requests
from flask import Flask, jsonify, render_template_string, request

# Configuration from environment
CONFIG = {
    # TOTP settings
    "TOTP_SECRET": os.environ.get("TOTP_SECRET", ""),
    "TOTP_ISSUER": os.environ.get("TOTP_ISSUER", "UnraidDeploy"),

    # Notification method: "ntfy", "telegram", "pushover", "discord", or "none"
    "NOTIFY_METHOD": os.environ.get("NOTIFY_METHOD", "none"),

    # Ntfy (recommended - self-hostable, no account needed)
    "NTFY_URL": os.environ.get("NTFY_URL", "https://ntfy.sh"),
    "NTFY_TOPIC": os.environ.get("NTFY_TOPIC", ""),
    "NTFY_TOKEN": os.environ.get("NTFY_TOKEN", ""),  # Optional auth

    # Telegram
    "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.environ.get("TELEGRAM_CHAT_ID", ""),

    # Pushover
    "PUSHOVER_TOKEN": os.environ.get("PUSHOVER_TOKEN", ""),
    "PUSHOVER_USER": os.environ.get("PUSHOVER_USER", ""),

    # Discord
    "DISCORD_WEBHOOK_URL": os.environ.get("DISCORD_WEBHOOK_URL", ""),

    # GHCR settings
    "GITHUB_ORG": os.environ.get("GITHUB_ORG", ""),
    "GHCR_TOKEN": os.environ.get("GHCR_TOKEN", ""),

    # Polling settings
    "POLL_INTERVAL": int(os.environ.get("POLL_INTERVAL", "300")),
    "GATE_URL": os.environ.get("GATE_URL", "http://localhost:9999"),
    "IMAGES_FILE": os.environ.get("IMAGES_FILE", "/config/images.json"),
    "STATE_FILE": os.environ.get("STATE_FILE", "/config/state.json"),
    "APPROVAL_TIMEOUT": int(os.environ.get("APPROVAL_TIMEOUT", "3600")),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)


@dataclass
class PendingUpdate:
    """An image update waiting for approval."""

    image: str
    container: str
    app_dir: str  # Directory containing docker-compose.yml
    old_digest: str
    new_digest: str
    detected_at: datetime
    token: str


# In-memory state
pending_updates: dict[str, PendingUpdate] = {}
state_lock = threading.Lock()


def load_state() -> dict:
    """Load persisted state (known digests)."""
    state_file = Path(CONFIG["STATE_FILE"])
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"digests": {}}


def save_state(state: dict) -> None:
    """Persist state."""
    state_file = Path(CONFIG["STATE_FILE"])
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2))


def load_images() -> list[dict]:
    """Load list of images to monitor."""
    images_file = Path(CONFIG["IMAGES_FILE"])
    if images_file.exists():
        return json.loads(images_file.read_text())
    return []


def get_remote_digest(image: str) -> str | None:
    """Fetch current digest from GHCR."""
    if not image.startswith("ghcr.io/"):
        log.warning("Only GHCR images supported: %s", image)
        return None

    parts = image.replace("ghcr.io/", "").split(":")
    repo = parts[0]
    tag = parts[1] if len(parts) > 1 else "latest"

    url = f"https://ghcr.io/v2/{repo}/manifests/{tag}"
    headers = {
        "Accept": "application/vnd.docker.distribution.manifest.v2+json",
    }

    if CONFIG["GHCR_TOKEN"]:
        headers["Authorization"] = f"Bearer {CONFIG['GHCR_TOKEN']}"

    try:
        resp = requests.head(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.headers.get("docker-content-digest")
        log.warning("Failed to fetch digest for %s: %s", image, resp.status_code)
    except Exception as e:
        log.error("Error fetching digest for %s: %s", image, e)

    return None


def pull_config_artifact(image: str, app_dir: str) -> bool:
    """Pull and extract config artifact from registry."""
    # Config artifact is stored at image:config
    config_ref = image.rsplit(":", 1)[0] + ":config"

    try:
        log.info("Checking for config artifact: %s", config_ref)

        # Use oras to pull the config artifact
        # First check if oras is available
        result = subprocess.run(
            ["which", "oras"],
            capture_output=True,
        )
        if result.returncode != 0:
            log.warning("oras not installed, skipping config sync")
            return True  # Not a failure, just skip

        # Create temp directory for download
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pull_result = subprocess.run(
                ["oras", "pull", config_ref, "-o", tmpdir],
                capture_output=True,
                env={
                    **os.environ,
                    "ORAS_REGISTRY": "ghcr.io",
                },
            )

            if pull_result.returncode != 0:
                stderr = pull_result.stderr.decode()
                if "not found" in stderr.lower() or "manifest unknown" in stderr.lower():
                    log.info("No config artifact found for %s, skipping", image)
                    return True  # Not a failure, just no config to sync
                log.error("Failed to pull config artifact: %s", stderr)
                return False

            # Find and extract the tarball
            tarball = Path(tmpdir) / "config.tar.gz"
            if not tarball.exists():
                # Look for any .gz file
                gz_files = list(Path(tmpdir).glob("*.gz"))
                if gz_files:
                    tarball = gz_files[0]
                else:
                    log.warning("No config tarball found in artifact")
                    return True

            # Extract to app directory
            log.info("Extracting config to %s", app_dir)
            Path(app_dir).mkdir(parents=True, exist_ok=True)

            extract_result = subprocess.run(
                ["tar", "xzf", str(tarball), "-C", app_dir],
                capture_output=True,
            )

            if extract_result.returncode != 0:
                log.error("Failed to extract config: %s", extract_result.stderr.decode())
                return False

            log.info("Config synced successfully to %s", app_dir)
            return True

    except Exception as e:
        log.error("Error syncing config for %s: %s", image, e)
        return False


# =============================================================================
# Notification backends
# =============================================================================


def notify_ntfy(update: PendingUpdate, approve_url: str) -> bool:
    """Send notification via Ntfy."""
    if not CONFIG["NTFY_TOPIC"]:
        log.warning("NTFY_TOPIC not configured")
        return False

    url = f"{CONFIG['NTFY_URL']}/{CONFIG['NTFY_TOPIC']}"
    headers = {
        "Title": "Deploy Approval Required",
        "Priority": "high",
        "Tags": "whale,lock",
        "Click": approve_url,
        "Actions": f"view, Approve, {approve_url}",
    }

    if CONFIG["NTFY_TOKEN"]:
        headers["Authorization"] = f"Bearer {CONFIG['NTFY_TOKEN']}"

    message = f"New image: {update.image}\nContainer: {update.container}"

    try:
        resp = requests.post(url, data=message, headers=headers, timeout=30)
        if resp.status_code == 200:
            log.info("Ntfy notification sent for %s", update.image)
            return True
        log.error("Ntfy error: %s", resp.text)
    except Exception as e:
        log.error("Failed to send Ntfy notification: %s", e)

    return False


def notify_telegram(update: PendingUpdate, approve_url: str) -> bool:
    """Send notification via Telegram."""
    if not CONFIG["TELEGRAM_BOT_TOKEN"] or not CONFIG["TELEGRAM_CHAT_ID"]:
        log.warning("Telegram not configured")
        return False

    url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_BOT_TOKEN']}/sendMessage"

    message = (
        f"🐳 *Deploy Approval Required*\n\n"
        f"Image: `{update.image}`\n"
        f"Container: `{update.container}`\n\n"
        f"[Tap to approve]({approve_url})"
    )

    try:
        resp = requests.post(
            url,
            json={
                "chat_id": CONFIG["TELEGRAM_CHAT_ID"],
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            log.info("Telegram notification sent for %s", update.image)
            return True
        log.error("Telegram error: %s", resp.text)
    except Exception as e:
        log.error("Failed to send Telegram notification: %s", e)

    return False


def notify_pushover(update: PendingUpdate, approve_url: str) -> bool:
    """Send notification via Pushover."""
    if not CONFIG["PUSHOVER_TOKEN"] or not CONFIG["PUSHOVER_USER"]:
        log.warning("Pushover not configured")
        return False

    message = (
        f"🐳 New image available\n\n"
        f"Image: {update.image}\n"
        f"Container: {update.container}"
    )

    try:
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": CONFIG["PUSHOVER_TOKEN"],
                "user": CONFIG["PUSHOVER_USER"],
                "message": message,
                "title": "Deploy Approval Required",
                "url": approve_url,
                "url_title": "Approve Update",
                "priority": 1,
                "sound": "pushover",
            },
            timeout=30,
        )
        if resp.status_code == 200:
            log.info("Pushover notification sent for %s", update.image)
            return True
        log.error("Pushover error: %s", resp.text)
    except Exception as e:
        log.error("Failed to send Pushover notification: %s", e)

    return False


def notify_discord(update: PendingUpdate, approve_url: str) -> bool:
    """Send notification via Discord webhook."""
    if not CONFIG["DISCORD_WEBHOOK_URL"]:
        log.warning("Discord webhook not configured")
        return False

    embed = {
        "title": "🐳 Deploy Approval Required",
        "color": 3447003,  # Blue
        "fields": [
            {"name": "Image", "value": f"`{update.image}`", "inline": False},
            {"name": "Container", "value": f"`{update.container}`", "inline": False},
        ],
        "footer": {"text": "Enter TOTP code to approve"},
    }

    try:
        resp = requests.post(
            CONFIG["DISCORD_WEBHOOK_URL"],
            json={
                "content": f"**New deployment pending approval**\n{approve_url}",
                "embeds": [embed],
            },
            timeout=30,
        )
        if resp.status_code in (200, 204):
            log.info("Discord notification sent for %s", update.image)
            return True
        log.error("Discord error: %s", resp.text)
    except Exception as e:
        log.error("Failed to send Discord notification: %s", e)

    return False


def send_notification(update: PendingUpdate) -> bool:
    """Send notification via configured method."""
    approve_url = f"{CONFIG['GATE_URL']}/approve/{update.token}"
    method = CONFIG["NOTIFY_METHOD"].lower()

    if method == "none":
        log.info("Notifications disabled. Pending approval at: %s", approve_url)
        return True
    elif method == "ntfy":
        return notify_ntfy(update, approve_url)
    elif method == "telegram":
        return notify_telegram(update, approve_url)
    elif method == "pushover":
        return notify_pushover(update, approve_url)
    elif method == "discord":
        return notify_discord(update, approve_url)
    else:
        log.warning("Unknown notification method: %s", method)
        return False


def pull_and_restart(image: str, container: str, app_dir: str | None = None) -> bool:
    """Pull config artifact (if any), pull new image, and restart container."""
    try:
        # Step 1: Sync config artifact (if app_dir provided and oras available)
        if app_dir:
            if not pull_config_artifact(image, app_dir):
                log.error("Config sync failed, aborting update")
                return False

        # Step 2: Pull new image
        log.info("Pulling image: %s", image)
        subprocess.run(["docker", "pull", image], check=True, capture_output=True)

        # Step 3: Restart using docker-compose if app_dir provided, otherwise just restart
        if app_dir and Path(app_dir).joinpath("docker-compose.yml").exists():
            log.info("Restarting via docker-compose in %s", app_dir)
            subprocess.run(
                ["docker", "compose", "up", "-d", "--remove-orphans"],
                cwd=app_dir,
                check=True,
                capture_output=True,
            )
        else:
            log.info("Restarting container: %s", container)
            subprocess.run(["docker", "restart", container], check=True, capture_output=True)

        log.info("Successfully updated %s", container)
        return True
    except subprocess.CalledProcessError as e:
        log.error("Failed to update %s: %s", container, e.stderr.decode())
        return False


def check_for_updates() -> None:
    """Poll for new images and queue for approval."""
    state = load_state()
    images = load_images()

    for entry in images:
        image = entry.get("image", "")
        container = entry.get("container", "")
        app_dir = entry.get("app_dir", "")  # Optional: directory for config sync

        if not image or not container:
            continue

        current_digest = get_remote_digest(image)
        if not current_digest:
            continue

        known_digest = state["digests"].get(image)

        if known_digest != current_digest:
            log.info("New version detected for %s", image)

            with state_lock:
                already_pending = any(
                    u.image == image and u.new_digest == current_digest
                    for u in pending_updates.values()
                )

            if already_pending:
                log.info("Update already pending approval for %s", image)
                continue

            token = secrets.token_urlsafe(32)
            update = PendingUpdate(
                image=image,
                container=container,
                app_dir=app_dir,
                old_digest=known_digest or "unknown",
                new_digest=current_digest,
                detected_at=datetime.now(),
                token=token,
            )

            with state_lock:
                pending_updates[token] = update

            send_notification(update)


def cleanup_expired() -> None:
    """Remove expired pending updates."""
    now = datetime.now()
    timeout = timedelta(seconds=CONFIG["APPROVAL_TIMEOUT"])

    with state_lock:
        expired = [
            token
            for token, update in pending_updates.items()
            if now - update.detected_at > timeout
        ]
        for token in expired:
            log.info("Expired pending update: %s", pending_updates[token].image)
            del pending_updates[token]


def poller_loop() -> None:
    """Background polling loop."""
    while True:
        try:
            check_for_updates()
            cleanup_expired()
        except Exception as e:
            log.exception("Poller error: %s", e)

        time.sleep(CONFIG["POLL_INTERVAL"])


# =============================================================================
# Web UI
# =============================================================================

APPROVAL_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Approve Update</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, system-ui, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            padding: 20px;
        }
        .card {
            background: #16213e;
            border-radius: 16px;
            padding: 32px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        h1 { margin: 0 0 8px 0; font-size: 24px; }
        .subtitle { color: #888; margin-bottom: 24px; }
        .info { background: #0f3460; padding: 16px; border-radius: 8px; margin-bottom: 24px; }
        .info div { margin: 8px 0; }
        .label { color: #888; font-size: 12px; text-transform: uppercase; }
        .value { font-family: monospace; word-break: break-all; }
        form { display: flex; flex-direction: column; gap: 16px; }
        input[type="text"] {
            background: #0f3460;
            border: 2px solid #333;
            color: #fff;
            padding: 16px;
            border-radius: 8px;
            font-size: 24px;
            text-align: center;
            letter-spacing: 8px;
            font-family: monospace;
        }
        input[type="text"]:focus { outline: none; border-color: #4CAF50; }
        button {
            background: #4CAF50;
            color: white;
            border: none;
            padding: 16px;
            border-radius: 8px;
            font-size: 18px;
            cursor: pointer;
        }
        button:hover { background: #45a049; }
        .error { background: #f44336; color: white; padding: 12px; border-radius: 8px; margin-bottom: 16px; }
        .success { background: #4CAF50; color: white; padding: 16px; border-radius: 8px; text-align: center; }
    </style>
</head>
<body>
    <div class="card">
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}

        {% if success %}
        <div class="success">
            <h2>✓ Approved</h2>
            <p>{{ container }} is updating...</p>
        </div>
        {% elif not found %}
        <div class="error">
            <h2>Not Found</h2>
            <p>This approval link has expired or was already used.</p>
        </div>
        {% else %}
        <h1>🔐 Approve Update</h1>
        <p class="subtitle">Enter your 6-digit code</p>

        <div class="info">
            <div>
                <span class="label">Image</span>
                <div class="value">{{ image }}</div>
            </div>
            <div>
                <span class="label">Container</span>
                <div class="value">{{ container }}</div>
            </div>
        </div>

        <form method="POST">
            <input type="text" name="code" maxlength="6" pattern="[0-9]{6}"
                   placeholder="000000" autofocus autocomplete="off" inputmode="numeric">
            <button type="submit">Approve & Deploy</button>
        </form>
        {% endif %}
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    """Simple status page."""
    with state_lock:
        pending_count = len(pending_updates)

    return jsonify({
        "status": "ok",
        "pending_updates": pending_count,
        "poll_interval": CONFIG["POLL_INTERVAL"],
        "notify_method": CONFIG["NOTIFY_METHOD"],
    })


@app.route("/approve/<token>", methods=["GET", "POST"])
def approve(token: str):
    """Approval page with TOTP verification."""
    with state_lock:
        update = pending_updates.get(token)

    if not update:
        return render_template_string(APPROVAL_PAGE, found=False)

    error = None
    success = False

    if request.method == "POST":
        code = request.form.get("code", "").strip()

        totp = pyotp.TOTP(CONFIG["TOTP_SECRET"])
        if totp.verify(code, valid_window=1):
            log.info("TOTP verified for %s, proceeding with update", update.image)

            state = load_state()
            state["digests"][update.image] = update.new_digest
            save_state(state)

            with state_lock:
                del pending_updates[token]

            threading.Thread(
                target=pull_and_restart,
                args=(update.image, update.container, update.app_dir or None),
                daemon=True,
            ).start()

            success = True
        else:
            log.warning("Invalid TOTP code for %s", update.image)
            error = "Invalid code. Please try again."

    return render_template_string(
        APPROVAL_PAGE,
        found=True,
        image=update.image,
        container=update.container,
        error=error,
        success=success,
    )


@app.route("/pending")
def list_pending():
    """List pending updates."""
    with state_lock:
        pending = [
            {
                "image": u.image,
                "container": u.container,
                "detected_at": u.detected_at.isoformat(),
                "approve_url": f"{CONFIG['GATE_URL']}/approve/{token}",
            }
            for token, u in pending_updates.items()
        ]
    return jsonify(pending)


def main():
    """Entry point."""
    if not CONFIG["TOTP_SECRET"]:
        log.error("TOTP_SECRET not set! Run setup script first.")
        return

    log.info("Starting approval gate...")
    log.info("Notification method: %s", CONFIG["NOTIFY_METHOD"])
    log.info("Poll interval: %ds", CONFIG["POLL_INTERVAL"])

    poller_thread = threading.Thread(target=poller_loop, daemon=True)
    poller_thread.start()

    app.run(host="0.0.0.0", port=9999, debug=False)


if __name__ == "__main__":
    main()
