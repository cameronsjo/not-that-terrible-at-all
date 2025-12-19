# Deploying a New App

This guide covers setting up a new repo for deployment to Unraid. Designed to be used by humans on phones or by Claude Code for automation.

## Quick Decision: Which Mode?

```
Is this a production app with sensitive data?
│
├─ Yes → 🛡️ Checkpoint (secure, TOTP approval)
│
└─ No  → ✈️ Autopilot (fast, automated)
```

| Mode | Security | Speed | After Push |
|------|----------|-------|------------|
| ✈️ Autopilot | SSH key in GitHub | ~2 min | Automatic deploy |
| 🛡️ Checkpoint | TOTP on phone | ~5 min | Manual approval |

## ✈️ Autopilot Mode Setup

### Prerequisites

Org secrets must already exist:
- `UNRAID_HOST` - IP/hostname
- `UNRAID_USER` - SSH user (usually `root`)
- `UNRAID_SSH_KEY` - Private SSH key
- `GHCR_PAT` - Token with `read:packages`

### Step 1: Add Dockerfile

If the repo doesn't have one, create `Dockerfile` using the appropriate template below.

### Step 2: Add Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Autopilot Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    uses: YOUR_ORG/not-that-terrible-at-all/.github/workflows/deploy-autopilot.yml@main
    secrets: inherit
    # with:
    #   config-files: "docker-compose.yml"  # Files to SCP
    #   app-dir: "/mnt/user/appdata/myapp"  # Override default
```

**Replace:** `YOUR_ORG` with your GitHub org/username.

### Step 3: Add docker-compose.yml

Create `docker-compose.yml` in the repo root (it gets synced to Unraid automatically):

```yaml
services:
  app:
    image: ghcr.io/YOUR_ORG/APP_NAME:latest
    container_name: APP_NAME
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - TZ=America/Chicago
    volumes:
      - ./data:/app/data

networks:
  default:
    name: proxy
    external: true
```

**Replace:** `YOUR_ORG`, `APP_NAME`, port number as needed.

### Step 4: Push

Push to main. The workflow will:
1. Build and push image to GHCR
2. SCP docker-compose.yml to Unraid
3. SSH and run `docker-compose up -d`

Done. App is live.

---

## 🛡️ Checkpoint Mode Setup

### Prerequisites

The approval gate must already be running on Unraid (one-time setup).

### Step 1: Add Dockerfile

If the repo doesn't have one, create `Dockerfile` using the appropriate template below.

### Step 2: Add Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Checkpoint Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    uses: YOUR_ORG/not-that-terrible-at-all/.github/workflows/deploy-checkpoint.yml@main
    secrets: inherit
    with:
      sign-image: true
      push-config: true
      # config-files: "docker-compose.yml config/nginx.conf"
```

**Replace:** `YOUR_ORG` with your GitHub org/username.

### Step 3: Add docker-compose.yml

Create `docker-compose.yml` in the repo root:

```yaml
services:
  app:
    image: ghcr.io/YOUR_ORG/APP_NAME:latest
    container_name: APP_NAME
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - TZ=America/Chicago
    volumes:
      - ./data:/app/data

networks:
  default:
    name: proxy
    external: true
```

**Replace:** `YOUR_ORG`, `APP_NAME`, port number as needed.

### Step 4: Register with Gate

**Option A: Web UI (phone-friendly)**

1. Open `http://your-gate:9999/images`
2. Fill in the form:
   - Image: `ghcr.io/YOUR_ORG/APP_NAME:latest`
   - Container: `APP_NAME`
   - App Dir: `/mnt/user/appdata/APP_NAME`
3. Enter TOTP code
4. Submit

**Option B: Manual edit**

SSH to Unraid and edit `/mnt/user/appdata/approval-gate/config/images.json`:

```json
[
  {
    "image": "ghcr.io/YOUR_ORG/APP_NAME:latest",
    "container": "APP_NAME",
    "app_dir": "/mnt/user/appdata/APP_NAME"
  }
]
```

### Step 5: Push

Push to main. The workflow will:
1. Build and push image to GHCR
2. Push config as OCI artifact
3. Gate polls, finds new image
4. Sends notification (if configured)
5. You enter TOTP code
6. Gate pulls config + image, restarts container

Done.

---

## Dockerfile Templates

Choose based on your app type.

### Node.js (Express, Fastify, Next.js, etc.)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN if [ -f "package.json" ] && grep -q '"build"' package.json; then npm run build; fi

FROM node:20-alpine AS runtime
WORKDIR /app
RUN addgroup -g 1001 -S appgroup && adduser -u 1001 -S appuser -G appgroup
COPY --from=builder --chown=appuser:appgroup /app .
USER appuser
ENV PORT=3000
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:${PORT}/health || exit 1
CMD ["node", "index.js"]
```

**Customize:** Change `index.js` to your entry point (e.g., `server.js`, `dist/index.js`).

### Python (FastAPI, Flask, Django)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN groupadd -g 1001 appgroup && useradd -u 1001 -g appgroup -s /bin/bash appuser
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
COPY --chown=appuser:appgroup . .
USER appuser
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Customize:** Change `main:app` to your module:app (e.g., `app:app` for Flask).

### Go

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
RUN apk add --no-cache ca-certificates
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags='-w -s -extldflags "-static"' -o /app/server .

FROM scratch AS runtime
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /app/server /server
EXPOSE 8080
USER 1001
ENTRYPOINT ["/server"]
```

### Static Site / SPA (React, Vue, Svelte, plain HTML)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN if [ -f "package.json" ]; then npm ci; fi
COPY . .
RUN if [ -f "package.json" ] && grep -q '"build"' package.json; then npm run build; fi
RUN mkdir -p /output && \
    if [ -d "dist" ]; then cp -r dist/* /output/; \
    elif [ -d "build" ]; then cp -r build/* /output/; \
    elif [ -d "out" ]; then cp -r out/* /output/; \
    elif [ -d "public" ]; then cp -r public/* /output/; \
    else cp -r . /output/; \
    fi

FROM nginx:alpine AS runtime
RUN echo 'server { listen 80; root /usr/share/nginx/html; index index.html; location / { try_files $uri $uri/ /index.html; } location /health { return 200 "healthy"; add_header Content-Type text/plain; } }' > /etc/nginx/conf.d/default.conf
COPY --from=builder /output /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
```

---

## Common Customizations

### Different Ports

Update both `Dockerfile` (EXPOSE) and `docker-compose.yml` (ports).

| App Type | Default Port |
|----------|--------------|
| Node.js | 3000 |
| Python | 8000 |
| Go | 8080 |
| Static/nginx | 80 |

### Environment Variables

For sensitive values, don't put them in docker-compose.yml. Create `.env` on Unraid:

```bash
# On Unraid
cd /mnt/user/appdata/APP_NAME
echo "API_KEY=secret" >> .env
echo "DATABASE_URL=postgres://..." >> .env
```

Then reference in docker-compose.yml:

```yaml
services:
  app:
    env_file:
      - .env
```

### Persistent Data

Mount volumes for data that should survive container restarts:

```yaml
volumes:
  - ./data:/app/data      # App data
  - ./config:/app/config  # Config files
  - ./logs:/app/logs      # Log files
```

### Multi-Architecture

For ARM support (Raspberry Pi, etc.):

```yaml
with:
  platforms: linux/amd64,linux/arm64
```

---

## Troubleshooting

### Build Failed

1. Check GitHub Actions tab for error logs
2. Common issues:
   - Missing `package.json` or `requirements.txt`
   - Wrong entry point in Dockerfile CMD
   - Missing build dependencies

### Container Won't Start

SSH to Unraid and check logs:

```bash
docker logs APP_NAME --tail 100
```

### Image Not Found

For private images, ensure `GHCR_PAT` has `read:packages` scope.

### Checkpoint: No Notification

1. Check gate logs: `docker logs approval-gate`
2. Verify `NOTIFY_METHOD` is set correctly
3. Check notification credentials

### Checkpoint: TOTP Rejected

1. Ensure phone time is synced
2. Codes valid for ~30 seconds
3. Using correct authenticator entry

---

## Claude Code Automation Checklist

When Claude Code sets up a new repo, verify:

- [ ] Dockerfile exists and is appropriate for the app type
- [ ] `.github/workflows/deploy.yml` uses correct workflow reference
- [ ] `docker-compose.yml` has correct image reference
- [ ] All `YOUR_ORG` and `APP_NAME` placeholders replaced
- [ ] Port numbers match between Dockerfile and docker-compose.yml
- [ ] For Checkpoint: image registered with gate (via web UI or images.json)
