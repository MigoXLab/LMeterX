#!/bin/bash

# LMeterX Quick Deployment Script
# Use pre-built Docker images to quickly start all services

set -eo pipefail

echo "🚀 LMeterX Quick Deployment Script"
echo "=================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed, please install Docker first"
    exit 1
fi

# Determine which Docker Compose command to use
COMPOSE_CMD=""
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    echo "❌ Error: Docker Compose is not installed or available"
    echo "   Please install Docker Compose or ensure Docker includes the compose plugin"
    exit 1
fi

echo "ℹ️  Using Docker Compose command: $COMPOSE_CMD"

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs

# Download necessary configuration files (if not exists)
if [ ! -f "docker-compose.yml" ]; then
    echo "📥 Downloading docker-compose.yml..."
    curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/MigoXLab/LMeterX/main/docker-compose.yml
fi

# Download and sync data directory
echo "📁 Syncing data directory..."
DATA_DIR="data"
ARCHIVE_URL="https://codeload.github.com/MigoXLab/LMeterX/tar.gz/refs/heads/main"
TMP_DIR="$(mktemp -d)"

cleanup_tmp_dir() {
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
}
trap cleanup_tmp_dir EXIT

curl -fsSL "$ARCHIVE_URL" | tar -xz --strip-components=1 -C "$TMP_DIR" LMeterX-main/data

if [ ! -d "$TMP_DIR/data" ]; then
    echo "❌ Error: Failed to locate data directory in repository archive"
    exit 1
fi

rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"
cp -R "$TMP_DIR/data/." "$DATA_DIR/"

# Pull latest images
echo "📦 Pulling latest Docker images..."
docker pull charmy1220/lmeterx-mysql:latest
docker pull charmy1220/lmeterx-be:latest
docker pull charmy1220/lmeterx-eng:latest
docker pull charmy1220/lmeterx-fe:latest

# Stop and clean up old containers (if exists)
echo "🧹 Cleaning up old containers..."
$COMPOSE_CMD -f docker-compose.yml down --remove-orphans 2>/dev/null || true

# Start infrastructure services first (MySQL + VictoriaMetrics)
echo "🚀 Starting infrastructure services (MySQL, VictoriaMetrics)..."
$COMPOSE_CMD -f docker-compose.yml up -d mysql victoria-metrics

# Wait for MySQL to be healthy
echo "⏳ Waiting for MySQL to be ready..."
MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if docker inspect --format='{{.State.Health.Status}}' lmeterx-mysql 2>/dev/null | grep -q "healthy"; then
        echo "✅ MySQL is ready!"
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "   Waiting... (${WAITED}s/${MAX_WAIT}s)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "⚠️  MySQL did not become healthy within ${MAX_WAIT}s, checking logs..."
    docker logs lmeterx-mysql --tail 20
    echo ""
    echo "Continuing anyway, services may still start..."
fi

# Wait for VictoriaMetrics to be healthy
echo "⏳ Waiting for VictoriaMetrics to be ready..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if docker inspect --format='{{.State.Health.Status}}' lmeterx-victoria-metrics 2>/dev/null | grep -q "healthy"; then
        echo "✅ VictoriaMetrics is ready!"
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "   Waiting... (${WAITED}s/${MAX_WAIT}s)"
done

# Start remaining services
echo "🚀 Starting application services (backend, engine, frontend)..."
$COMPOSE_CMD -f docker-compose.yml up -d

# Wait for application services to start
echo "⏳ Waiting for application services to start..."
sleep 15

# Check service status
echo "🔍 Checking service status..."
$COMPOSE_CMD -f docker-compose.yml ps

echo ""
echo "✅ LMeterX deployment completed!"
echo ""
echo "📋 Access Information:"
echo "  🌐 Frontend: http://localhost:8080"
echo "  🔧 Backend API: http://localhost:5001"
echo "  ⚡ Load Testing Engine: http://localhost:5002"
echo ""
echo "📝 Common Commands:"
echo "  Check service status: $COMPOSE_CMD -f docker-compose.yml ps"
echo "  View logs: $COMPOSE_CMD -f docker-compose.yml logs -f"
echo "  Stop services: $COMPOSE_CMD -f docker-compose.yml down"
echo "  Restart services: $COMPOSE_CMD -f docker-compose.yml restart"
echo ""
echo "🎉 Start using LMeterX for performance testing!"
