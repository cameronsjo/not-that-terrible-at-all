#!/usr/bin/env python3
"""
TOTP Approval Gate for Docker Image Updates

Polls GHCR for new images, sends push notification, requires TOTP to approve pull.
Completely decoupled from GitHub - attacker needs your phone to approve.
"""

import hashlib
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
from flask import Flask, jsonify, redirect, render_template_string, request

# Configuration from environment
CONFIG = {
    "TOTP_SECRET": os.environ.get("TOTP_SECRET", ""),
    "TOTP_ISSUER": os.environ.get("TOTP_ISSUER", "UnraidDeploy"),
    "PUSHOVER_TOKEN": os.environ.get("PUSHOVER_TOKEN", ""),
    "PUSHOVER_USER": os.environ.get("PUSHOVER_USER", ""),
    "GITHUB_ORG": os.environ.get("GITHUB_ORG", ""),
    "GHCR_TOKEN": os.environ.get("GHCR_TOKEN", ""),
    "POLL_INTERVAL": int(os.environ.get("POLL_INTERVAL", "300")),
    "GATE_URL": os.environ.get("GATE_URL", "http://localhost:9999"),
    "IMAGES_FILE": os.environ.get("IMAGES_FILE", "/config/images.json"),
    "STATE_FILE": os.environ.get("STATE_FILE", "/config/state.json"),
    "APPROVAL_TIMEOUT": int(os.environ.get("APPROVAL_TIMEOUT", "3600")),  # 1 hour
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
    old_digest: str
    new_digest: str
    detected_at: datetime
    token: str  # Random token for this approval request


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
    # Parse image name
    # Format: ghcr.io/org/name:tag
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


def send_notification(update: PendingUpdate) -> bool:
    """Send Pushover notification."""
    if not CONFIG["PUSHOVER_TOKEN"] or not CONFIG["PUSHOVER_USER"]:
        log.warning("Pushover not configured, skipping notification")
        return False

    approve_url = f"{CONFIG['GATE_URL']}/approve/{update.token}"

    message = (
        f"🐳 New image available\n\n"
        f"Image: {update.image}\n"
        f"Container: {update.container}\n\n"
        f"Tap to approve update:"
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
                "priority": 1,  # High priority
                "sound": "pushover",
            },
            timeout=30,
        )
        if resp.status_code == 200:
            log.info("Notification sent for %s", update.image)
            return True
        log.error("Pushover error: %s", resp.text)
    except Exception as e:
        log.error("Failed to send notification: %s", e)

    return False


def pull_and_restart(image: str, container: str) -> bool:
    """Pull new image and restart container."""
    try:
        log.info("Pulling image: %s", image)
        subprocess.run(["docker", "pull", image], check=True, capture_output=True)

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

        if not image or not container:
            continue

        current_digest = get_remote_digest(image)
        if not current_digest:
            continue

        known_digest = state["digests"].get(image)

        if known_digest != current_digest:
            log.info("New version detected for %s", image)

            # Check if already pending
            with state_lock:
                already_pending = any(
                    u.image == image and u.new_digest == current_digest
                    for u in pending_updates.values()
                )

            if already_pending:
                log.info("Update already pending approval for %s", image)
                continue

            # Create pending update
            token = secrets.token_urlsafe(32)
            update = PendingUpdate(
                image=image,
                container=container,
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


# HTML template for approval page
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
            # Approved! Pull and restart
            log.info("TOTP verified for %s, proceeding with update", update.image)

            # Update state with new digest
            state = load_state()
            state["digests"][update.image] = update.new_digest
            save_state(state)

            # Remove from pending
            with state_lock:
                del pending_updates[token]

            # Pull and restart in background
            threading.Thread(
                target=pull_and_restart,
                args=(update.image, update.container),
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
    """List pending updates (for debugging)."""
    with state_lock:
        pending = [
            {
                "image": u.image,
                "container": u.container,
                "detected_at": u.detected_at.isoformat(),
            }
            for u in pending_updates.values()
        ]
    return jsonify(pending)


def main():
    """Entry point."""
    if not CONFIG["TOTP_SECRET"]:
        log.error("TOTP_SECRET not set! Run setup script first.")
        return

    log.info("Starting approval gate...")
    log.info("Poll interval: %ds", CONFIG["POLL_INTERVAL"])
    log.info("Approval timeout: %ds", CONFIG["APPROVAL_TIMEOUT"])

    # Start background poller
    poller_thread = threading.Thread(target=poller_loop, daemon=True)
    poller_thread.start()

    # Run Flask
    app.run(host="0.0.0.0", port=9999, debug=False)


if __name__ == "__main__":
    main()
