# LmeterX Docker Compose Deployment Guide

LmeterX is a benchmarking tool specifically designed for testing the performance of OpenAI compatible APIs. This document provides detailed steps for installing and configuring LmeterX using Docker Compose.

## Project Overview

LmeterX is a comprehensive large language model performance testing platform that supports load testing for any LLM service implementing the OpenAI API format. It provides an easy-to-use web interface for managing test tasks and viewing detailed performance metrics.

### Core Features

- **OpenAI-Compatible API Testing**: Support for any LLM service implementing the OpenAI API format
- **Load Testing Scenarios**: Support for pure text and multimodal conversation load testing
- **Concurrent User Simulation**: Support for custom load test configurations: concurrent user count, test duration
- **Core Performance Metrics Collection**: First token latency, Requests Per Second (RPS), Token Throughput, basic error rate statistics
- **Web Interface Management**: User-friendly dashboard to manage test tasks and view results

## System Architecture

LmeterX consists of four main components:

1. **MySQL Database**: Stores test tasks, results, and configuration data
2. **Backend API**: FastAPI-based REST API service that manages test tasks and results
3. **Engine Service**: Locust-based load testing engine that executes actual performance tests
4. **Frontend**: React + Vite-based web interface providing user interaction

## Prerequisites

Before you begin, ensure that the following software is installed on your system:

- **Docker** (20.10.0+)
- **Docker Compose** (2.0.0+)
- **Git**
- **At least 4GB available memory**
- **At least 5GB available disk space**

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/LuckyYC/LMeterX.git
cd lmeterx
```

### 2. Configure Environment Variables (Optional)

If you need custom configuration, you can create a `.env` file or directly modify environment variables in `docker-compose.yml`:

```bash
# Copy example configuration file
cp .env.example .env

# Edit configuration file
vim .env
```

### 3. Start Services

Start all services using Docker Compose:

```bash
# Start all services in background
docker-compose up -d

# View startup logs
docker-compose logs -f
```

### 4. Verify Deployment

After the services start, you can verify the installation through:

- **Frontend Interface**: http://localhost
- **Backend API Documentation**: http://localhost/api/docs (Swagger UI)

Wait for all service health checks to pass (usually takes 1-2 minutes).

## Detailed Configuration

### docker-compose.yml Configuration Details

#### MySQL Service Configuration

```yaml
mysql:
  image: mysql:5.7
  container_name: lmeterx-mysql
  restart: always
  environment:
    MYSQL_ROOT_PASSWORD: lmeterx_root_password
    MYSQL_DATABASE: lmeterx
    MYSQL_USER: lmeterx
    MYSQL_PASSWORD: lmeterx_password
  ports:
    - "3306:3306"
  volumes:
    - mysql_data:/var/lib/mysql
    - ./backend/db/init_db.sql:/docker-entrypoint-initdb.d/init_db.sql
  command: --default-authentication-plugin=mysql_native_password --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci --init-connect='SET NAMES utf8mb4'
```

**Configuration Details**:
- Uses MySQL 5.7 version for compatibility
- Automatically executes database initialization scripts
- Configures UTF8MB4 character set for Chinese and special character support
- Data persistence to Docker volumes

#### Backend API Service Configuration

```yaml
backend:
  build:
    context: ./backend
    dockerfile: Dockerfile
  container_name: lmeterx-backend
  restart: always
  depends_on:
    mysql:
      condition: service_healthy
  environment:
    - DB_HOST=mysql
    - DB_PORT=3306
    - DB_USER=lmeterx
    - DB_PASSWORD=lmeterx_password
    - DB_NAME=lmeterx
    - SECRET_KEY=your_secret_key_here
    - FLASK_DEBUG=false
  volumes:
    - ./logs:/logs
    - upload_files:/app/upload_files
  ports:
    - "5001:5001"
```

**Configuration Details**:
- Built on Python 3.12 using FastAPI framework
- Uses Uvicorn as ASGI server with 2 worker processes
- Starts after MySQL service health check passes
- Supports file upload functionality

#### Engine Service Configuration

```yaml
engine:
  build:
    context: ./st_engine
    dockerfile: Dockerfile
  container_name: lmeterx-engine
  restart: always
  depends_on:
    mysql:
      condition: service_healthy
  environment:
    - DB_HOST=mysql
    - DB_PORT=3306
    - DB_USER=lmeterx
    - DB_PASSWORD=lmeterx_password
    - DB_NAME=lmeterx
    - SECRET_KEY=your_secret_key_here
    - FLASK_DEBUG=false
  volumes:
    - ./logs:/logs
  ports:
    - "5002:5002"
```

**Configuration Details**:
- Built on Locust 2.33.2 load testing engine
- Independent service architecture that can be horizontally scaled

#### Frontend Service Configuration

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  container_name: lmeterx-frontend
  restart: always
  depends_on:
    backend:
      condition: service_healthy
  ports:
    - "80:80"
  environment:
    - VITE_API_BASE_URL=/api
  volumes:
    - ./frontend/nginx.conf:/etc/nginx/conf.d/default.conf
    - ./frontend/nginx-map.conf:/etc/nginx/conf.d/map.conf
    - upload_files:/usr/share/nginx/html/uploads
```

**Configuration Details**:
- Built on Node.js 18 using Vite bundler
- Uses Nginx Alpine as production web server
- Supports SPA routing and API proxy
- Integrated file upload functionality

### Nginx Configuration Details

The frontend service uses Nginx as the web server with the following configuration:

#### Main Features
- **API Proxy**: Proxies `/api/` requests to backend service
- **Static Resource Serving**: Serves frontend static files
- **SPA Routing Support**: Supports React Router client-side routing
- **Gzip Compression**: Optimizes transfer performance
- **Security Headers**: Enhances security
- **Caching Strategy**: Optimizes static resource loading

#### Key Configuration
```nginx
# API request proxy
location /api/ {
    proxy_pass http://backend:5001/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}

# SPA routing support
location / {
    try_files $uri $uri/ /index.html;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
}
```

## Environment Variables

### General Environment Variables

| Variable | Description | Default Value | Required |
|---------|-------------|---------------|----------|
| SECRET_KEY | Application security key | your_secret_key_here | Yes |

### Database Environment Variables

| Variable | Description | Default Value | Required |
|---------|-------------|---------------|----------|
| DB_HOST | Database host address | mysql | Yes |
| DB_PORT | Database port | 3306 | Yes |
| DB_USER | Database username | lmeterx | Yes |
| DB_PASSWORD | Database password | lmeterx_password | Yes |
| DB_NAME | Database name | lmeterx | Yes |

### MySQL Environment Variables

| Variable | Description | Default Value | Required |
|---------|-------------|---------------|----------|
| MYSQL_ROOT_PASSWORD | MySQL root password | lmeterx_root_password | Yes |
| MYSQL_DATABASE | Initial database name | lmeterx | Yes |
| MYSQL_USER | MySQL username | lmeterx | Yes |
| MYSQL_PASSWORD | MySQL user password | lmeterx_password | Yes |

### Application Environment Variables

| Variable | Description | Default Value | Required |
|---------|-------------|---------------|----------|
| FLASK_DEBUG | Debug mode | false | No |
| VITE_API_BASE_URL | Frontend API base URL | /api | Yes |

## Common Operations

### Service Management

#### Start Services
```bash
# Start all services
docker-compose up -d

# Start specific services
docker-compose up -d mysql backend

# Start in foreground (view real-time logs)
docker-compose up
```

#### Stop Services
```bash
# Stop all services
docker-compose down

# Stop specific service
docker-compose stop backend

# Stop and remove data volumes (dangerous operation)
docker-compose down -v
```

#### Restart Services
```bash
# Restart all services
docker-compose restart

# Restart specific services
docker-compose restart backend frontend
```

### Log Management

#### View Logs
```bash
# View all service logs
docker-compose logs

# View specific service logs
docker-compose logs backend
docker-compose logs frontend
docker-compose logs mysql
docker-compose logs engine

# Follow logs in real-time
docker-compose logs -f backend

# View last 100 lines of logs
docker-compose logs --tail=100 backend
```

#### Log File Locations
- **Application Logs**: `./logs/` directory
- **Nginx Logs**: `/var/log/nginx/` inside container
- **MySQL Logs**: `/var/log/mysql/` inside container

### Data Management

#### Data Backup
```bash
# Backup MySQL data
docker-compose exec mysql mysqldump -u root -plmeterx_root_password lmeterx > backup.sql

# Backup upload files
docker run --rm -v lmeterx_upload_files:/data -v $(pwd):/backup alpine tar czf /backup/upload_files_backup.tar.gz -C /data .
```

#### Data Restore
```bash
# Restore MySQL data
docker-compose exec -T mysql mysql -u root -plmeterx_root_password lmeterx < backup.sql

# Restore upload files
docker run --rm -v lmeterx_upload_files:/data -v $(pwd):/backup alpine tar xzf /backup/upload_files_backup.tar.gz -C /data
```

### Service Updates

#### Update Application Code
```bash
# Pull latest code
git pull origin main

# Rebuild and start services
docker-compose build --no-cache
docker-compose up -d

# Or execute step by step
docker-compose down
docker-compose build
docker-compose up -d
```

#### Update Specific Services
```bash
# Update only backend service
docker-compose build --no-cache backend
docker-compose up -d backend

# Update only frontend service
docker-compose build --no-cache frontend
docker-compose up -d frontend
```

### Performance Monitoring

#### View Service Status
```bash
# View service running status
docker-compose ps

# View service resource usage
docker-compose top

# View detailed statistics
docker stats $(docker-compose ps -q)
```

#### Health Checks
```bash
# Check service health status
curl -s http://localhost/api/health
curl -s http://localhost:5002/health

# Check database connection
docker-compose exec mysql mysql -u lmeterx -plmeterx_password -e "SELECT 1"
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Database Connection Failure

**Symptoms**: Backend service cannot connect to database

**Possible Causes**:
- Database service not fully started
- Database configuration error
- Network connection issues

**Solutions**:
```bash
# Check database service status
docker-compose ps mysql

# View database logs
docker-compose logs mysql

# Check database connection
docker-compose exec mysql mysql -u root -plmeterx_root_password -e "SHOW DATABASES;"

# Restart database service
docker-compose restart mysql

# Wait for database to fully start then restart backend services
sleep 30
docker-compose restart backend engine
```

#### 2. Frontend Access Issues

**Symptoms**: Browser cannot open frontend page or shows 502 error

**Possible Causes**:
- Frontend service not started
- Nginx configuration error
- Backend service unavailable

**Solutions**:
```bash
# Check frontend service status
docker-compose ps frontend

# View frontend logs
docker-compose logs frontend

# Check Nginx configuration
docker-compose exec frontend nginx -t

# Restart frontend service
docker-compose restart frontend

# Check if backend service is accessible
curl -s http://localhost:5001/api/health
```

#### 3. API Request Failures

**Symptoms**: Frontend page loads but API requests fail

**Possible Causes**:
- Backend service exception
- Database connection issues
- API routing configuration error

**Solutions**:
```bash
# Check backend service logs
docker-compose logs backend

# Check API health status
curl -s http://localhost/api/health

# Check database connection
docker-compose exec backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
async def test_db():
    engine = create_async_engine('mysql+aiomysql://lmeterx:lmeterx_password@mysql:3306/lmeterx')
    async with engine.begin() as conn:
        result = await conn.execute('SELECT 1')
        print('Database connection successful')
asyncio.run(test_db())
"

# Restart backend service
docker-compose restart backend
```

#### 4. Engine Service Exception

**Symptoms**: Cannot create or execute test tasks

**Possible Causes**:
- Engine service not started
- Database connection issues
- Insufficient resources

**Solutions**:
```bash
# Check engine service status
docker-compose ps engine

# View engine service logs
docker-compose logs engine

# Check engine service health status
curl -s http://localhost:5002/health

# Restart engine service
docker-compose restart engine

# Check system resources
docker stats $(docker-compose ps -q)
```

#### 5. Port Conflicts

**Symptoms**: Service startup fails with port already in use error

**Solutions**:
```bash
# Check port usage
netstat -tlnp | grep -E ':(80|3306|5001|5002)'

# Modify port mapping in docker-compose.yml
# For example, change 80:80 to 8080:80

# Or stop services using the ports
sudo systemctl stop nginx  # If system Nginx is using port 80
```

#### 6. Insufficient Disk Space

**Symptoms**: Services exit abnormally with disk space insufficient logs

**Solutions**:
```bash
# Check disk usage
df -h

# Clean Docker resources
docker system prune -a

# Clean log files
docker-compose exec mysql mysql -u root -plmeterx_root_password -e "RESET MASTER;"

# Clean application logs
rm -rf ./logs/*
```

### Debugging Tips

#### 1. Enter Container for Debugging
```bash
# Enter backend container
docker-compose exec backend bash

# Enter frontend container
docker-compose exec frontend sh

# Enter database container
docker-compose exec mysql bash
```

#### 2. View Container Details
```bash
# View container configuration
docker-compose config

# View container detailed information
docker inspect lmeterx-backend

# View network configuration
docker network ls
docker network inspect lmeterx_default
```

#### 3. Performance Analysis
```bash
# View container resource usage
docker stats --no-stream

# View container processes
docker-compose exec backend ps aux

# View network connections
docker-compose exec backend netstat -tlnp
```

## Production Deployment Recommendations

### Security Configuration

1. **Change Default Passwords**:
   ```bash
   # Change database passwords
   MYSQL_ROOT_PASSWORD=your_strong_password
   MYSQL_PASSWORD=your_strong_password
   DB_PASSWORD=your_strong_password
   
   # Change application secret key
   SECRET_KEY=your_random_secret_key
   ```

2. **Restrict Network Access**:
   ```yaml
   # Only expose necessary ports
   ports:
     - "127.0.0.1:80:80"  # Local access only
   ```

3. **Enable HTTPS**:
   ```nginx
   # Add SSL configuration in Nginx config
   server {
       listen 443 ssl;
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
   }
   ```

### Performance Optimization

1. **Resource Limits**:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2.0'
         memory: 2G
       reservations:
         cpus: '1.0'
         memory: 1G
   ```

2. **Database Optimization**:
   ```yaml
   command: >
     --default-authentication-plugin=mysql_native_password
     --character-set-server=utf8mb4
     --collation-server=utf8mb4_unicode_ci
     --innodb-buffer-pool-size=1G
     --max-connections=200
   ```

### Monitoring and Logging

1. **Log Rotation**:
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

2. **Health Checks**:
   ```yaml
   healthcheck:
     test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
     interval: 30s
     timeout: 10s
     retries: 3
     start_period: 40s
   ```

## Summary

LmeterX provides a complete containerized deployment solution through Docker Compose, supporting rapid deployment and scaling. Through the detailed instructions in this document, you should be able to:

1. Successfully deploy the LmeterX system
2. Understand the role and configuration of each component
3. Perform daily operational tasks
4. Resolve common deployment issues
5. Optimize configuration for production environments

If you encounter issues during deployment, please refer to the troubleshooting section or check the project's GitHub Issues. 