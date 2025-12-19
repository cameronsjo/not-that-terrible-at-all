# Deploying a New App (Phone-Friendly Guide)

This guide is optimized for doing everything from your phone via GitHub's mobile web interface.

## The 5-Minute Deploy

### Step 1: Fork the Repo (1 min)

1. Open the repo you want to deploy
2. Tap **Fork**
3. Fork to your org (the one with the shared secrets)

### Step 2: Add Dockerfile (2 min)

If the repo doesn't have a Dockerfile:

1. Tap **Add file** → **Create new file**
2. Name it `Dockerfile`
3. Paste the appropriate template (see below)
4. Tap **Commit new file**

### Step 3: Add Deploy Workflow (1 min)

1. Tap **Add file** → **Create new file**
2. Name it `.github/workflows/deploy.yml`
3. Paste this:

```yaml
name: Deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    uses: YOUR_ORG/not-that-terrible-at-all/.github/workflows/deploy.yml@main
    secrets: inherit
```

4. Tap **Commit new file**

### Step 4: Add to Unraid (1 min)

SSH to Unraid (or use Tailscale SSH from phone) and run:

```bash
mkdir -p /mnt/user/appdata/apps/APP_NAME
cd /mnt/user/appdata/apps/APP_NAME

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  app:
    image: ghcr.io/YOUR_ORG/APP_NAME:latest
    container_name: APP_NAME
    restart: unless-stopped
    ports:
      - "3000:3000"
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
    networks:
      - proxy

networks:
  proxy:
    external: true
EOF

docker-compose up -d
```

### Step 5: Add to Reverse Proxy (1 min)

1. Open NPM at `http://unraid:81`
2. **Hosts** → **Proxy Hosts** → **Add**
3. Fill in:
   - Domain: `app.yourdomain.com`
   - Forward Hostname: `APP_NAME` (container name)
   - Forward Port: `3000`
4. SSL tab → Request new certificate
5. Save

Done. Your app is live and will auto-update on every push.

---

## Dockerfile Templates

Copy-paste these when the repo doesn't have a Dockerfile.

### Node.js (Express, Fastify, etc.)

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
ENV PORT=3000
EXPOSE 3000
CMD ["node", "index.js"]
```

### Python (FastAPI, Flask)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Static Site (React, Vue, HTML)

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

### Go

```dockerfile
FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /server .

FROM scratch
COPY --from=build /server /server
EXPOSE 8080
ENTRYPOINT ["/server"]
```

---

## Quick Reference

### Workflow Inputs

Customize your deploy workflow:

```yaml
with:
  # Custom image name (default: repo name)
  app-name: my-app

  # Different Dockerfile location
  dockerfile: docker/Dockerfile

  # Multi-architecture build
  platforms: linux/amd64,linux/arm64

  # Build arguments
  build-args: |
    NODE_ENV=production
    API_URL=https://api.example.com
```

### Common Ports

| App Type | Default Port |
|----------|--------------|
| Node.js  | 3000         |
| Python   | 8000         |
| Go       | 8080         |
| Static   | 80           |

### Environment Variables

For apps needing secrets, create `.env` on Unraid:

```bash
cd /mnt/user/appdata/apps/APP_NAME
cat > .env << 'EOF'
API_KEY=your-api-key
DATABASE_URL=postgres://...
EOF
```

Add to docker-compose.yml:

```yaml
services:
  app:
    env_file:
      - .env
```

---

## Troubleshooting from Phone

### Check if build succeeded

1. Go to repo → **Actions** tab
2. Find latest workflow run
3. Green check = success, red X = failure

### Check Watchtower logs

If you have Tailscale SSH on phone:

```bash
docker logs watchtower --tail 50
```

### Force container update

```bash
docker pull ghcr.io/YOUR_ORG/APP_NAME:latest
docker-compose up -d
```

### View app logs

```bash
docker logs APP_NAME --tail 100
```
