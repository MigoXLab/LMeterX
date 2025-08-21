#!/bin/bash

# LMeterX Quick Deployment Script
# Use pre-built Docker images to quickly start all services

set -e

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

# Pull latest images
echo "📦 Pulling latest Docker images..."
docker pull charmy1220/lmeterx-mysql:latest
docker pull charmy1220/lmeterx-be:latest
docker pull charmy1220/lmeterx-eng:latest
docker pull charmy1220/lmeterx-fe:latest

# Stop and clean up old containers (if exists)
echo "🧹 Cleaning up old containers..."
$COMPOSE_CMD -f docker-compose.yml down --remove-orphans 2>/dev/null || true

# Start services
echo "🚀 Starting LMeterX services..."
$COMPOSE_CMD -f docker-compose.yml up -d

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 10

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
