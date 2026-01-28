# LMeterX Complete Deployment Guide

This document provides a complete deployment process for LMeterX from development to production.

## 📋 Overview

LMeterX offers multiple deployment methods:

1. **One-Click Deployment**: Suitable for quick experience and testing
2. **Development Deployment**: Suitable for development and custom requirements

## 🚀 One-Click Deployment (For Users)

### Use Cases
- Quick experience of LMeterX features
- One-click deployment for production environment
- No need to modify source code

### Environment Requirements

- **Operating System**: Linux, macOS, Windows
- **Docker**: 20.10.0+
- **Docker Compose**: 2.0.0+
- **Memory**: 4GB+
- **Disk Space**: 5GB+

### Deployment Steps

```bash
# One-click deployment command
curl -fsSL https://raw.githubusercontent.com/MigoXLab/LMeterX/main/quick-start.sh | bash
```

### Access URLs
- Frontend Interface: http://localhost:8080

### Pre-built Image List

| Service | Docker Hub Image | Size | Description |
|---------|------------------|------|-------------|
| Frontend | `luckyyc/lmeterx-frontend:latest` | ~20MB | React + Nginx |
| Backend | `luckyyc/lmeterx-backend:latest` | ~80MB | FastAPI + Python |
| Engine | `luckyyc/lmeterx-engine:latest` | ~130MB | Locust + Python |
| Database | `luckyyc/lmeterx-mysql:latest`  | ~130MB | Official MySQL image + Database initialization |

## ⚙️ Development Deployment (For Developers)

### Use Cases
- Need to modify source code
- Development and debugging
- Custom configuration

### Docker-compose Deployment

#### Environment Requirements

- **Docker**: 20.10.0+
- **Docker Compose**: 2.0.0+

```bash
# 1. Clone repository
git clone https://github.com/MigoXLab/LMeterX.git
cd LMeterX

# 2. Start services
docker-compose -f docker-compose.dev.yml up -d

# 3. Check status
docker-compose -f docker-compose.dev.yml ps

```

#### Access URLs
- Frontend Interface: http://localhost:8080

### Manual Deployment

#### Environment Requirements
- **Python**: 3.10+
- **Node.js**: 18+ and **npm**
- **MySQL**: 5.7+

```bash
# Clone repository
git clone https://github.com/MigoXLab/LMeterX.git
cd LMeterX

```
#### Start Backend Service

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure database (MySQL): Edit .env file or config/db_config.py
# Import initialization script: init_db.sql

# Start service
python app.py
```

#### Start Load Testing Engine

```bash
cd st_engine

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure database (MySQL): Edit .env file or config/db_config.py
# Import initialization script: init_db.sql

# Start service
python app.py
```

#### Start Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Or build production version
npm run build:prod
npm run preview
```
#### Access URLs
- Frontend Interface: http://localhost:5173

## 🔍 Deployment Verification

### Health Check

```bash
# Check service status
curl http://localhost:5001/health
curl http://localhost:5002/health

# Check container status
docker-compose ps
```

### Functional Testing

1. Access frontend interface: http://localhost:8080 or http://localhost:5173
2. Create test task
3. View test results
4. Check log output

## 🛠️ Troubleshooting

### Common Issues
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

#### 2. Frontend Inaccessible

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

#### 3. API Request Failure

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
curl -s http://localhost:5001/api/health

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

# Or stop services occupying the ports
sudo systemctl stop nginx  # If system Nginx occupies port 80
```

#### 6. Insufficient Disk Space

**Symptoms**: Services exit abnormally, logs show insufficient disk space

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
```

#### 3. Performance Analysis
```bash
# View service resource usage
docker-compose top

# View container resource usage
docker stats --no-stream

# View detailed statistics
docker stats $(docker-compose ps -q)
```

## Production Deployment Recommendations

### Security Configuration

1. **Change Default Passwords**:
   ```bash
   # Change database password
   MYSQL_ROOT_PASSWORD=your_strong_password
   MYSQL_PASSWORD=your_strong_password
   DB_PASSWORD=your_strong_password

   # Change application secret key
   SECRET_KEY=your_random_secret_key
   JWT_SECRET_KEY=your_random_jwt_secret_key
   ```

2. **Enable LDAP/AD Authentication** (Recommended for Enterprise):

   LMeterX supports enterprise LDAP/Active Directory authentication for centralized user management and SSO.

   **Step 1: Configure Backend LDAP Settings**

   Add the following environment variables to the `backend` service in `docker-compose.yml`:

   ```yaml
   backend:
     environment:
       # Enable LDAP authentication
       - LDAP_ENABLED=on

       # LDAP server connection
       - LDAP_SERVER=ldap://ldap.example.com
       - LDAP_PORT=389
       - LDAP_USE_SSL=false          # Set to true for LDAPS
       - LDAP_TIMEOUT=5

       # LDAP search configuration
       - LDAP_SEARCH_BASE=dc=example,dc=com
       - LDAP_SEARCH_FILTER=(sAMAccountName={username})

       # Choose one authentication method:
       # Method 1: Direct bind (simple LDAP)
       - LDAP_USER_DN_TEMPLATE=cn={username},ou=users,dc=example,dc=com

       # Method 2: Service account (Active Directory)
       - LDAP_BIND_DN=cn=service,ou=users,dc=example,dc=com
       - LDAP_BIND_PASSWORD=service_password

       # JWT configuration
       - JWT_SECRET_KEY=change-me-to-a-random-string
       - JWT_EXPIRE_MINUTES=480      # 8 hours
   ```

   **Step 2: Enable Frontend Login UI**

   Add the following environment variable to the `frontend` service:

   ```yaml
   frontend:
     environment:
       - VITE_LDAP_ENABLED=on
       - VITE_PERSIST_ACCESS_TOKEN=true
   ```

   **Step 3: Restart Services**

   ```bash
   docker-compose down
   docker-compose up -d
   ```

   **Common LDAP Configuration Examples:**

   <details>
   <summary>Active Directory (Microsoft AD)</summary>

   ```bash
   LDAP_ENABLED=on
   LDAP_SERVER=ldap://ad.company.com
   LDAP_PORT=389
   LDAP_USE_SSL=false
   LDAP_SEARCH_BASE=dc=company,dc=com
   LDAP_SEARCH_FILTER=(sAMAccountName={username})
   LDAP_BIND_DN=cn=ldapservice,ou=ServiceAccounts,dc=company,dc=com
   LDAP_BIND_PASSWORD=YourServicePassword
   ```
   </details>

   <details>
   <summary>OpenLDAP</summary>

   ```bash
   LDAP_ENABLED=on
   LDAP_SERVER=ldap://ldap.example.com
   LDAP_PORT=389
   LDAP_USE_SSL=false
   LDAP_SEARCH_BASE=ou=users,dc=example,dc=com
   LDAP_USER_DN_TEMPLATE=uid={username},ou=users,dc=example,dc=com
   ```
   </details>

   <details>
   <summary>LDAPS (Secure LDAP)</summary>

   ```bash
   LDAP_ENABLED=on
   LDAP_SERVER=ldaps://ldap.example.com
   LDAP_PORT=636
   LDAP_USE_SSL=true
   LDAP_SEARCH_BASE=dc=example,dc=com
   LDAP_BIND_DN=cn=admin,dc=example,dc=com
   LDAP_BIND_PASSWORD=admin_password
   ```
   </details>

   **Testing LDAP Connection:**

   ```bash
   # Check backend logs for LDAP connection status
   docker-compose logs backend | grep -i ldap

   # Test login via API
   curl -X POST http://localhost:5001/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser","password":"testpass"}'
   ```

3. **Restrict Network Access**:
   ```yaml
   # Only expose necessary ports
   ports:
     - "127.0.0.1:80:80"
   ```

4. **Enable HTTPS**:
   ```nginx
   # Add SSL configuration in Nginx config
   server {
       listen 443 ssl;
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
   }
   ```
## 📊 Monitoring and Logging

### Log Management

```bash
# View all service logs
docker-compose logs

# Real-time tracking of specific service logs
docker-compose logs -f backend
docker-compose logs frontend

# View last 100 lines of logs
docker-compose logs --tail=100 engine
```

### Performance Monitoring

```bash
# View service running status
docker-compose ps

# View service resource usage
docker-compose top

# View detailed statistics
docker stats $(docker-compose ps -q)
```

## 🔄 Updates and Maintenance

### Version Updates

```bash
# Pull latest images
docker-compose -f docker-compose.yml pull

# Restart services
docker-compose -f docker-compose.yml up -d
```

### Update Application Code
```bash
# Pull latest code
git pull origin main

# Rebuild and start services
docker-compose -f docker-compose.yml build --no-cache
docker-compose -f docker-compose.yml up -d
```

**Choose the deployment method that suits you and start using LMeterX for performance testing!** 🚀
