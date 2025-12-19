# Go application Dockerfile
# Produces a minimal scratch-based image
#
# Build: docker build -f Dockerfile -t app .
# Run:   docker run -p 8080:8080 app

FROM golang:1.22-alpine AS builder

WORKDIR /app

# Install CA certificates for HTTPS requests
RUN apk add --no-cache ca-certificates

# Download dependencies first (better layer caching)
COPY go.mod go.sum* ./
RUN go mod download

# Copy source code
COPY . .

# Build static binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags='-w -s -extldflags "-static"' \
    -o /app/server .

# Minimal production image
FROM scratch AS runtime

# Copy CA certificates for HTTPS
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Copy binary
COPY --from=builder /app/server /server

# Default port
EXPOSE 8080

# Run as non-root (UID 1001)
USER 1001

ENTRYPOINT ["/server"]
