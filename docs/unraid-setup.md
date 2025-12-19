# Unraid One-Time Setup

This guide walks through the initial Unraid configuration needed before deploying apps.

## Prerequisites

- Unraid server with Docker enabled
- Tailscale installed and connected
- Access to Unraid WebUI

## Step 1: Move Unraid WebUI Port

The WebUI defaults to ports 80/443. We need to free those for the reverse proxy.

1. Go to **Settings** → **Management Access**
2. Change **HTTP port** from `80` to `8080`
3. Change **HTTPS port** from `443` to `8443`
4. Click **Apply**
5. Access WebUI at `https://your-unraid-ip:8443` going forward

## Step 2: Create Shared Docker Network

This allows containers to communicate and enables reverse proxy routing.

SSH into Unraid or use the terminal in WebUI:

```bash
docker network create proxy
```

## Step 3: Install Nginx Proxy Manager

NPM provides a GUI for managing reverse proxy routes and SSL certificates.

### Via Community Applications

1. Go to **Apps** tab
2. Search for "Nginx Proxy Manager"
3. Install with these settings:
   - **Network Type**: Custom: `proxy`
   - **HTTP Port**: `80`
   - **HTTPS Port**: `443`
   - **Admin Port**: `81`

### Via Docker Compose

Create `/mnt/user/appdata/npm/docker-compose.yml`:

```yaml
services:
  npm:
    image: jc21/nginx-proxy-manager:latest
    container_name: nginx-proxy-manager
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "81:81"
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
    networks:
      - proxy

networks:
  proxy:
    external: true
```

Then run:

```bash
cd /mnt/user/appdata/npm
docker-compose up -d
```

### First Login

1. Access NPM at `http://your-unraid-ip:81`
2. Default credentials:
   - Email: `admin@example.com`
   - Password: `changeme`
3. Change these immediately after first login

## Step 4: Install Watchtower

Watchtower automatically updates containers when new images are pushed to GHCR.

### Via Community Applications

1. Go to **Apps** tab
2. Search for "Watchtower"
3. Install with default settings

### Via Docker Compose

Create `/mnt/user/appdata/watchtower/docker-compose.yml`:

```yaml
services:
  watchtower:
    image: containrrr/watchtower:latest
    container_name: watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      # Check for updates every 5 minutes
      - WATCHTOWER_POLL_INTERVAL=300
      # Only update containers with the enable label
      - WATCHTOWER_LABEL_ENABLE=true
      # Remove old images after updating
      - WATCHTOWER_CLEANUP=true
      # Timezone
      - TZ=America/Chicago
    # Optional: notifications
    # environment:
    #   - WATCHTOWER_NOTIFICATIONS=slack
    #   - WATCHTOWER_NOTIFICATION_SLACK_HOOK_URL=https://hooks.slack.com/...
```

Then run:

```bash
cd /mnt/user/appdata/watchtower
docker-compose up -d
```

## Step 5: Authenticate with GHCR

Watchtower needs to pull images from GitHub Container Registry.

### Create a GitHub Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token with `read:packages` scope
3. Save the token securely

### Configure Docker Authentication

SSH into Unraid:

```bash
# Login to GHCR
docker login ghcr.io -u YOUR_GITHUB_USERNAME

# Enter the token when prompted for password
```

This creates `/root/.docker/config.json` which Watchtower will use.

## Step 6: Create App Directory Structure

Organize your apps in a consistent location:

```bash
mkdir -p /mnt/user/appdata/apps
```

Each app will get its own subdirectory:

```
/mnt/user/appdata/apps/
├── app-one/
│   ├── docker-compose.yml
│   ├── .env
│   └── data/
├── app-two/
│   ├── docker-compose.yml
│   ├── .env
│   └── data/
└── ...
```

## Step 7: Configure DNS (Optional but Recommended)

For custom domains like `app.sjo.lol`:

### Cloudflare Setup

1. Add A record pointing to your public IP (or Cloudflare Tunnel)
2. Or use CNAME to Tailscale MagicDNS hostname

### Tailscale MagicDNS

If only accessing via Tailscale, use MagicDNS names directly:

- `your-unraid.tailnet-name.ts.net`

Or set up Tailscale Funnel for public access.

## Verification Checklist

- [ ] Unraid WebUI accessible on port 8443
- [ ] `proxy` Docker network exists (`docker network ls`)
- [ ] Nginx Proxy Manager running and accessible on port 81
- [ ] Watchtower running (`docker ps | grep watchtower`)
- [ ] Docker authenticated to GHCR (`cat /root/.docker/config.json`)
- [ ] App directory exists (`ls /mnt/user/appdata/apps`)

## Troubleshooting

### Watchtower not updating containers

1. Check the container has the label: `com.centurylinklabs.watchtower.enable=true`
2. Verify GHCR authentication: `docker pull ghcr.io/YOUR_ORG/your-app:latest`
3. Check Watchtower logs: `docker logs watchtower`

### NPM can't get SSL certificates

1. Ensure ports 80/443 are forwarded to Unraid
2. Check DNS is pointing to correct IP
3. Try using DNS challenge instead of HTTP challenge

### Container can't connect to other containers

1. Ensure both containers are on the `proxy` network
2. Use container names as hostnames, not `localhost`
