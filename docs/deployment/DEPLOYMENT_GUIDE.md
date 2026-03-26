# LMeterX 完整部署流程指南

本文档提供了LMeterX从开发到生产的完整部署流程。

## 📋 概述

LMeterX提供了多种部署方式，从简单的一键部署到完整的CI/CD流程：

1. **快速部署**：适合快速体验和测试
2. **开发部署**：适合开发和自定义需求
3. **CI/CD部署**：适合生产环境和持续集成

## 🔧 环境要求

### 最低要求
- **操作系统**：Linux、macOS、Windows
- **Docker**：20.10.0+
- **Docker Compose**：2.0.0+
- **内存**：4GB+
- **磁盘空间**：5GB+

### 推荐配置
- **CPU**：4核心+
- **内存**：8GB+
- **磁盘空间**：20GB+
- **网络**：稳定的互联网连接

## 🚀 快速部署（面向用户）

### 适用场景
- 快速体验LMeterX功能
- 生产环境快速部署
- 不需要修改源码

### 部署步骤

```bash
# 一键部署命令
curl -fsSL https://raw.githubusercontent.com/LuckyYC/LMeterX/main/quick-start.sh | bash
```

### 访问地址
- 前端界面：http://localhost

### 预构建镜像列表

| 服务 | Docker Hub镜像 | 大小 | 说明 |
|------|---------------|------|------|
| Frontend | `luckyyc/lmeterx-frontend:latest` | ~20MB | React + Nginx |
| Backend | `luckyyc/lmeterx-backend:latest` | ~80MB | FastAPI + Python |
| Engine | `luckyyc/lmeterx-engine:latest` | ~130MB | Locust + Python |
| Database | `mysql:5.7` | ~130MB | MySQL官方镜像 |

## ⚙️ 开发部署（面向开发者）

### 适用场景
- 需要修改源码
- 开发和调试
- 自定义配置

### docker-compose部署
参考：[Docker Compose 部署指南](docs/deployment/docker-compose-en.md)

```bash
# 1. 克隆仓库
git clone https://github.com/LuckyYC/LMeterX.git
cd LMeterX

# 2. 启动服务
docker-compose up -d

# 3. 查看状态
docker-compose ps

```

### 手动部署

#### 环境准备

- Python 3.10+
- Node.js 18+ 和 npm
- MySQL 5.7+

```bash
# 克隆仓库
git clone https://github.com/LuckyYC/LMeterX.git
cd LMeterX

```

#### 启动后端服务

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置数据库（MySQL）: 可编辑 .env文件或者config/db_config.py
# 创建数据库: lmeterx
# 导入初始化脚本: backend/db/init_db.sql

# 启动服务
python app.py
```

#### 启动压测引擎

```bash
cd st_engine

# 创建虚拟环境
python -m venv venv  
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置数据库（MySQL）: 可编辑 .env文件或者config/db_config.py
# 创建数据库: lmeterx
# 导入初始化脚本: backend/db/init_db.sql

# 启动服务
python app.py
```

#### 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 或构建生产版本
npm run build:prod
npm run preview
```

## ⚙️ 方式三：CI/CD部署（面向维护者）

### 适用场景
- 项目维护和发布
- 自动化构建和部署
- 版本管理

### 设置步骤

#### 1. 配置GitHub Actions

参考：[GitHub Actions 设置指南](docs/ci/github-actions-setup.md)

1. **创建Docker Hub访问令牌**
2. **配置GitHub Secrets**
3. **更新用户名配置**

#### 2. 构建和发布镜像

##### 自动构建（推荐）
```bash
# 创建版本标签触发自动构建
git tag v1.0.0
git push origin v1.0.0
```

##### 手动构建
1. 进入GitHub仓库的Actions页面
2. 选择"Manual Build and Push"工作流
3. 点击"Run workflow"
4. 输入版本号并执行

#### 3. 发布流程

1. **代码提交**：推送代码到main分支
2. **自动构建**：GitHub Actions自动构建镜像
3. **推送镜像**：自动推送到Docker Hub
4. **创建Release**：自动创建GitHub Release
5. **更新文档**：自动更新部署配置

## 📦 镜像管理

### 镜像命名规范

| 服务 | 镜像名称 | 说明 |
|------|---------|------|
| Backend | `charmy1220/lmeterx-be` | 后端API服务 |
| Engine | `charmy1220/lmeterx-eng` | 压测引擎服务 |
| Frontend | `charmy1220/lmeterx-fe` | 前端Web界面 |

### 标签策略

- `latest`：最新稳定版本
- `v1.0.0`：具体版本号
- `develop`：开发版本

## 🔍 部署验证

### 健康检查

```bash
# 检查服务状态
curl http://localhost:5001/health
curl http://localhost:5002/health

# 检查容器状态
docker-compose ps
```

### 功能测试

1. 访问前端界面：http://localhost
2. 创建测试任务
3. 查看测试结果
4. 检查日志输出

## 🛠️ 故障排除

### 常见问题
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
```

#### 3. 性能分析
```bash
# 查看服务资源使用情况
docker-compose top

# 查看容器资源使用
docker stats --no-stream

# 查看详细统计信息
docker stats $(docker-compose ps -q)
```

## 生产部署建议

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
     - "127.0.0.1:80:80"  
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
## 📊 监控和日志

### 日志管理

```bash
# 查看所有服务日志
docker-compose logs

# 实时跟踪特定服务日志
docker-compose logs -f backend
docker-compose logs frontend

# 查看最近 100 行日志
docker-compose logs --tail=100 engine
```

### 性能监控

```bash
# 查看服务运行状态
docker-compose ps

# 查看服务资源使用情况
docker-compose top

# 查看详细统计信息
docker stats $(docker-compose ps -q)
```

## 🔄 更新和维护

### 版本更新

```bash
# 拉取最新镜像
docker-compose pull

# 重启服务
docker-compose up -d
```

### 更新应用代码
```bash
# 拉取最新代码
git pull origin main

# 重新构建并启动服务
docker-compose build --no-cache
docker-compose up -d
```

### 数据备份

```bash
# 备份数据库
docker-compose exec mysql mysqldump -u root -p lmeterx > backup.sql

# 备份配置文件
tar -czf config-backup.tar.gz docker-compose.prod.yml logs/
```

**选择适合你的部署方式，开始使用LMeterX进行性能测试！** 🚀 