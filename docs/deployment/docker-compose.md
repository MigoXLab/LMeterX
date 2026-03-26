# LmeterX Docker Compose 部署指南

LmeterX 是一个专门为测试 OpenAI 兼容 API 性能而设计的基准测试工具。本文档提供了使用 Docker Compose 安装和配置 LmeterX 的详细步骤。

## 🚀 一键部署（推荐）

### 快速开始

使用预构建的Docker镜像，无需克隆仓库和构建过程，一键启动所有服务：

```bash
# 方式1: 直接运行一键部署脚本
curl -fsSL https://raw.githubusercontent.com/LuckyYC/LMeterX/main/quick-start.sh | bash

# 方式2: 下载脚本后运行
curl -o quick-start.sh https://raw.githubusercontent.com/LuckyYC/LMeterX/main/quick-start.sh
chmod +x quick-start.sh
./quick-start.sh
```

### 一键部署的优势

- ✅ **无需克隆仓库**：直接使用预构建镜像
- ✅ **快速启动**：跳过漫长的构建过程，几分钟内完成部署
- ✅ **自动化配置**：自动下载必要的配置文件
- ✅ **版本稳定**：使用经过测试的稳定版本镜像
- ✅ **简单维护**：一条命令完成部署和更新

### 预构建镜像列表

| 服务 | Docker Hub镜像 | 大小 | 说明 |
|------|---------------|------|------|
| Frontend | `luckyyc/lmeterx-frontend:latest` | ~20MB | React + Nginx |
| Backend | `luckyyc/lmeterx-backend:latest` | ~80MB | FastAPI + Python |
| Engine | `luckyyc/lmeterx-engine:latest` | ~130MB | Locust + Python |
| Database | `mysql:5.7` | ~130MB | MySQL官方镜像 |

### 常用管理命令

```bash
# 查看服务状态
docker-compose -f docker-compose.prod.yml ps

# 查看实时日志
docker-compose -f docker-compose.prod.yml logs -f

# 停止所有服务
docker-compose -f docker-compose.prod.yml down

# 重启服务
docker-compose -f docker-compose.prod.yml restart

# 更新到最新版本
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

## 📦 传统部署方式

如果您需要自定义构建或开发调试，可以使用传统的克隆仓库方式：

## 项目简介

LmeterX 是一个全面的大语言模型性能测试平台，支持对任何实现 OpenAI API 格式的 LLM 服务进行负载测试。通过 Web 界面可以轻松管理测试任务并查看详细的性能指标。

### 核心功能

- **OpenAI 兼容 API 测试**：支持任何实现 OpenAI API 格式的 LLM 服务
- **压测场景支持**：支持纯文本和图文对话类型压测
- **并发用户模拟**：支持自定义负载测试配置：并发用户数、测试持续时间
- **核心性能指标收集**：首Token延迟、每秒请求数(RPS)、Token Throughput、基础错误率统计
- **Web 界面管理**：用户友好的仪表板管理测试任务和查看结果

## 系统架构

LmeterX 由以下四个主要组件构成：

1. **MySQL 数据库**：存储测试任务、结果和配置数据
2. **Backend API**：基于 FastAPI 的 REST API 服务，管理测试任务和结果
3. **Engine 服务**：基于 Locust 的负载测试引擎，执行实际的性能测试
4. **Frontend**：基于 React + Vite 的 Web 界面，提供用户交互

## 前提条件

在开始之前，请确保您的系统上已安装以下软件：

- **Docker** (20.10.0+)
- **Docker Compose** (2.0.0+)
- **Git**
- **至少 4GB 可用内存**
- **至少 5GB 可用磁盘空间**

### 1. 克隆仓库

```bash
git https://github.com/LuckyYC/LMeterX.git
cd lmeterx
```

### 2. 配置环境变量（可选）

如需自定义配置，可以创建 `.env` 文件或直接修改 `docker-compose.yml` 中的环境变量：

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑配置文件
vim .env
```

### 3. 启动服务

使用 Docker Compose 启动所有服务：

```bash
# 后台启动所有服务
docker-compose up -d

# 查看启动日志
docker-compose logs -f
```

### 4. 验证部署

服务启动后，可以通过以下方式验证安装：

- **前端界面**：http://localhost
- **后端 API 文档**：http://localhost/api/docs (Swagger UI)

等待所有服务健康检查通过（通常需要 1-2 分钟）。

## 详细配置说明

### docker-compose.yml 配置详解

#### MySQL 服务配置

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

**配置说明**：
- 使用 MySQL 5.7 版本确保兼容性
- 自动执行数据库初始化脚本
- 配置 UTF8MB4 字符集支持中文和特殊字符
- 数据持久化到 Docker 卷

#### Backend API 服务配置

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

**配置说明**：
- 基于 Python 3.12 构建，使用 FastAPI 框架
- 使用 Uvicorn 作为 ASGI 服务器，支持 2 个工作进程
- 依赖 MySQL 服务健康检查通过后启动
- 支持文件上传功能

#### Engine 服务配置

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

**配置说明**：
- 基于 Locust 2.33.2 构建的负载测试引擎
- 独立的服务架构，可横向扩展

#### Frontend 服务配置

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

**配置说明**：
- 基于 Node.js 18 构建，使用 Vite 打包
- 使用 Nginx Alpine 作为生产环境 Web 服务器
- 支持 SPA 路由和 API 代理
- 集成文件上传功能

### Nginx 配置详解

前端服务使用 Nginx 作为 Web 服务器，配置包括：

#### 主要功能
- **API 代理**：将 `/api/` 请求代理到后端服务
- **静态资源服务**：提供前端静态文件
- **SPA 路由支持**：支持 React Router 的客户端路由
- **Gzip 压缩**：优化传输性能
- **安全头设置**：增强安全性
- **缓存策略**：优化静态资源加载

#### 关键配置
```nginx
# API 请求代理
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

# SPA 路由支持
location / {
    try_files $uri $uri/ /index.html;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
}
```

## 环境变量详解

### 通用环境变量

| 环境变量 | 说明 | 默认值 | 是否必需 |
|---------|------|--------|----------|
| SECRET_KEY | 应用安全密钥 | your_secret_key_here | 是 |

### 数据库环境变量

| 环境变量 | 说明 | 默认值 | 是否必需 |
|---------|------|--------|----------|
| DB_HOST | 数据库主机地址 | mysql | 是 |
| DB_PORT | 数据库端口 | 3306 | 是 |
| DB_USER | 数据库用户名 | lmeterx | 是 |
| DB_PASSWORD | 数据库密码 | lmeterx_password | 是 |
| DB_NAME | 数据库名称 | lmeterx | 是 |

### MySQL 环境变量

| 环境变量 | 说明 | 默认值 | 是否必需 |
|---------|------|--------|----------|
| MYSQL_ROOT_PASSWORD | MySQL root 密码 | lmeterx_root_password | 是 |
| MYSQL_DATABASE | 初始数据库名 | lmeterx | 是 |
| MYSQL_USER | MySQL 用户名 | lmeterx | 是 |
| MYSQL_PASSWORD | MySQL 用户密码 | lmeterx_password | 是 |

### 应用环境变量

| 环境变量 | 说明 | 默认值 | 是否必需 |
|---------|------|--------|----------|
| FLASK_DEBUG | 调试模式 | false | 否 |
| VITE_API_BASE_URL | 前端 API 基础 URL | /api | 是 |

## 常见操作

### 服务管理

#### 启动服务
```bash
# 启动所有服务
docker-compose up -d

# 启动特定服务
docker-compose up -d mysql backend

# 前台启动（查看实时日志）
docker-compose up
```

#### 停止服务
```bash
# 停止所有服务
docker-compose down

# 停止特定服务
docker-compose stop backend

# 停止并删除数据卷（危险操作）
docker-compose down -v
```

#### 重启服务
```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart backend frontend
```

### 日志管理

#### 查看日志
```bash
# 查看所有服务日志
docker-compose logs

# 查看特定服务日志
docker-compose logs backend
docker-compose logs frontend
docker-compose logs mysql
docker-compose logs engine

# 实时跟踪日志
docker-compose logs -f backend

# 查看最近 100 行日志
docker-compose logs --tail=100 backend
```

#### 日志文件位置
- **应用日志**：`./logs/` 目录
- **Nginx 日志**：容器内 `/var/log/nginx/`
- **MySQL 日志**：容器内 `/var/log/mysql/`

### 数据管理

#### 数据备份
```bash
# 备份 MySQL 数据
docker-compose exec mysql mysqldump -u root -plmeterx_root_password lmeterx > backup.sql

# 备份上传文件
docker run --rm -v lmeterx_upload_files:/data -v $(pwd):/backup alpine tar czf /backup/upload_files_backup.tar.gz -C /data .
```

#### 数据恢复
```bash
# 恢复 MySQL 数据
docker-compose exec -T mysql mysql -u root -plmeterx_root_password lmeterx < backup.sql

# 恢复上传文件
docker run --rm -v lmeterx_upload_files:/data -v $(pwd):/backup alpine tar xzf /backup/upload_files_backup.tar.gz -C /data
```

### 服务更新

#### 更新应用代码
```bash
# 拉取最新代码
git pull origin main

# 重新构建并启动服务
docker-compose build --no-cache
docker-compose up -d

# 或者分步执行
docker-compose down
docker-compose build
docker-compose up -d
```

#### 更新特定服务
```bash
# 只更新后端服务
docker-compose build --no-cache backend
docker-compose up -d backend

# 只更新前端服务
docker-compose build --no-cache frontend
docker-compose up -d frontend
```

### 性能监控

#### 查看服务状态
```bash
# 查看服务运行状态
docker-compose ps

# 查看服务资源使用情况
docker-compose top

# 查看详细统计信息
docker stats $(docker-compose ps -q)
```

#### 健康检查
```bash
# 检查服务健康状态
curl -s http://localhost/api/health
curl -s http://localhost:5002/health

# 检查数据库连接
docker-compose exec mysql mysql -u lmeterx -plmeterx_password -e "SELECT 1"
```

## 故障排除

### 常见问题及解决方案

#### 1. 数据库连接失败

**症状**：后端服务无法连接到数据库

**可能原因**：
- 数据库服务未完全启动
- 数据库配置错误
- 网络连接问题

**解决方案**：
```bash
# 检查数据库服务状态
docker-compose ps mysql

# 查看数据库日志
docker-compose logs mysql

# 检查数据库连接
docker-compose exec mysql mysql -u root -plmeterx_root_password -e "SHOW DATABASES;"

# 重启数据库服务
docker-compose restart mysql

# 等待数据库完全启动后重启后端服务
sleep 30
docker-compose restart backend engine
```

#### 2. 前端无法访问

**症状**：浏览器无法打开前端页面或显示 502 错误

**可能原因**：
- 前端服务未启动
- Nginx 配置错误
- 后端服务不可用

**解决方案**：
```bash
# 检查前端服务状态
docker-compose ps frontend

# 查看前端日志
docker-compose logs frontend

# 检查 Nginx 配置
docker-compose exec frontend nginx -t

# 重启前端服务
docker-compose restart frontend

# 检查后端服务是否可访问
curl -s http://localhost:5001/api/health
```

#### 3. API 请求失败

**症状**：前端页面加载但 API 请求失败

**可能原因**：
- 后端服务异常
- 数据库连接问题
- API 路由配置错误

**解决方案**：
```bash
# 检查后端服务日志
docker-compose logs backend

# 检查 API 健康状态
curl -s http://localhost/api/health

# 检查数据库连接
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

# 重启后端服务
docker-compose restart backend
```

#### 4. 引擎服务异常

**症状**：无法创建或执行测试任务

**可能原因**：
- 引擎服务未启动
- 数据库连接问题
- 资源不足

**解决方案**：
```bash
# 检查引擎服务状态
docker-compose ps engine

# 查看引擎服务日志
docker-compose logs engine

# 检查引擎服务健康状态
curl -s http://localhost:5002/health

# 重启引擎服务
docker-compose restart engine

# 检查系统资源
docker stats $(docker-compose ps -q)
```

#### 5. 端口冲突

**症状**：服务启动失败，提示端口被占用

**解决方案**：
```bash
# 检查端口占用情况
netstat -tlnp | grep -E ':(80|3306|5001|5002)'

# 修改 docker-compose.yml 中的端口映射
# 例如将 80:80 改为 8080:80

# 或者停止占用端口的服务
sudo systemctl stop nginx  # 如果系统 Nginx 占用 80 端口
```

#### 6. 磁盘空间不足

**症状**：服务异常退出，日志显示磁盘空间不足

**解决方案**：
```bash
# 检查磁盘使用情况
df -h

# 清理 Docker 资源
docker system prune -a

# 清理日志文件
docker-compose exec mysql mysql -u root -plmeterx_root_password -e "RESET MASTER;"

# 清理应用日志
rm -rf ./logs/*
```

### 调试技巧

#### 1. 进入容器调试
```bash
# 进入后端容器
docker-compose exec backend bash

# 进入前端容器
docker-compose exec frontend sh

# 进入数据库容器
docker-compose exec mysql bash
```

#### 2. 查看容器详细信息
```bash
# 查看容器配置
docker-compose config

# 查看容器详细信息
docker inspect lmeterx-backend

# 查看网络配置
docker network ls
docker network inspect lmeterx_default
```

#### 3. 性能分析
```bash
# 查看容器资源使用
docker stats --no-stream

# 查看容器进程
docker-compose exec backend ps aux

# 查看网络连接
docker-compose exec backend netstat -tlnp
```

## 生产环境部署建议

### 安全配置

1. **修改默认密码**：
   ```bash
   # 修改数据库密码
   MYSQL_ROOT_PASSWORD=your_strong_password
   MYSQL_PASSWORD=your_strong_password
   DB_PASSWORD=your_strong_password
   
   # 修改应用密钥
   SECRET_KEY=your_random_secret_key
   ```

2. **限制网络访问**：
   ```yaml
   # 仅暴露必要端口
   ports:
     - "127.0.0.1:80:80"  # 仅本地访问
   ```

3. **启用 HTTPS**：
   ```nginx
   # 在 Nginx 配置中添加 SSL 配置
   server {
       listen 443 ssl;
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
   }
   ```

### 性能优化

1. **资源限制**：
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

2. **数据库优化**：
   ```yaml
   command: >
     --default-authentication-plugin=mysql_native_password
     --character-set-server=utf8mb4
     --collation-server=utf8mb4_unicode_ci
     --innodb-buffer-pool-size=1G
     --max-connections=200
   ```

### 监控和日志

1. **日志轮转**：
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

2. **健康检查**：
   ```yaml
   healthcheck:
     test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
     interval: 30s
     timeout: 10s
     retries: 3
     start_period: 40s
   ```

## 总结

LmeterX 通过 Docker Compose 提供了完整的容器化部署方案，支持快速部署和扩展。通过本文档的详细说明，您应该能够：

1. 成功部署 LmeterX 系统
2. 理解各个组件的作用和配置
3. 进行日常的运维操作
4. 解决常见的部署问题
5. 针对生产环境进行优化配置

如果在部署过程中遇到问题，请参考故障排除章节或查看项目的 GitHub Issues。 