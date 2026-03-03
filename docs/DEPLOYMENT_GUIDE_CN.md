# LMeterX 完整部署流程指南

本文档提供了LMeterX从开发到生产的完整部署流程。

## 📋 概述

LMeterX提供了多种部署方式：

1. **一键部署**：适合快速体验和测试
2. **开发部署**：适合开发和自定义需求

## 🚀 一键部署（面向用户）

### 适用场景
- 快速体验LMeterX功能
- 生产环境一键部署
- 不需要修改源码

### 环境要求

- **操作系统**：Linux、macOS、Windows
- **Docker**：20.10.0+
- **Docker Compose**：2.0.0+
- **内存**：4GB+
- **磁盘空间**：5GB+
-
### 部署步骤

```bash
# 一键部署命令
curl -fsSL https://raw.githubusercontent.com/MigoXLab/LMeterX/main/quick-start.sh | bash
```

### 访问地址
- 前端界面：http://localhost:8080

### 预构建镜像列表

| 服务 | Docker Hub镜像 | 大小 | 说明 |
|------|---------------|------|------|
| Frontend | `charmy1220/lmeterx-frontend:latest` | ~20MB | React + Nginx |
| Backend | `charmy1220/lmeterx-backend:latest` | ~80MB | FastAPI + Python |
| Engine | `charmy1220/lmeterx-engine:latest` | ~130MB | Locust + Python |
| Database | `charmy1220/lmeterx-mysql:latest`  | ~130MB | MySQL官方镜像 + 初始化数据库 |

## ⚙️ 开发部署（面向开发者）

### 适用场景
- 需要修改源码
- 开发和调试
- 自定义配置

### docker-compose部署

#### 环境要求

- **Docker**：20.10.0+
- **Docker Compose**：2.0.0+
-

```bash
# 1. 克隆仓库
git clone https://github.com/MigoXLab/LMeterX.git
cd LMeterX

# 2. 启动服务
docker-compose -f docker-compose.dev.yml up -d

# 3. 查看状态
docker-compose -f docker-compose.dev.yml ps

```

#### 访问地址
- 前端界面：http://localhost:8080

### 手动部署

#### 环境要求
- **Python**：3.10+
- **Node.js**： 18+ 和 **npm**
- **MySQL**： 5.7+
-
```bash
# 克隆仓库
git clone https://github.com/MigoXLab/LMeterX.git
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
# 导入初始化脚本: init_db.sql

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
# 导入初始化脚本: init_db.sql

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
#### 访问地址
- 前端界面：http://localhost:5173

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

1. 访问前端界面：http://localhost:8080 或者 http://localhost:5173
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
curl -s http://localhost:5001/api/health

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
   JWT_SECRET_KEY=your_random_jwt_secret_key
   ```

2. **启用 LDAP/AD 认证**(推荐企业部署)：

   LMeterX 支持企业级 LDAP/Active Directory 认证，实现统一用户管理和单点登录。

   **步骤 1: 配置后端 LDAP 设置**

   在 `docker-compose.yml` 的 `backend` 服务中添加以下环境变量：

   ```yaml
   backend:
     environment:
       # 启用 LDAP 认证
       - LDAP_ENABLED=on

       # LDAP 服务器连接
       - LDAP_SERVER=ldap://ldap.example.com
       - LDAP_PORT=389
       - LDAP_USE_SSL=false          # LDAPS 使用 true
       - LDAP_TIMEOUT=5

       # LDAP 搜索配置
       - LDAP_SEARCH_BASE=dc=example,dc=com
       - LDAP_SEARCH_FILTER=(sAMAccountName={username})

       # 选择一种认证方式:
       # 方式 1: 直接绑定(简单 LDAP)
       - LDAP_USER_DN_TEMPLATE=cn={username},ou=users,dc=example,dc=com

       # 方式 2: 服务账号绑定(Active Directory)
       - LDAP_BIND_DN=cn=service,ou=users,dc=example,dc=com
       - LDAP_BIND_PASSWORD=service_password

       # JWT 配置
       - JWT_SECRET_KEY=请修改为随机字符串
       - JWT_EXPIRE_MINUTES=10080      # 7天
   ```

   **步骤 2: 启用前端登录界面**

   在 `frontend` 服务中添加以下环境变量：

   ```yaml
   frontend:
     environment:
       - VITE_LDAP_ENABLED=on
       - VITE_PERSIST_ACCESS_TOKEN=true
   ```

   **步骤 3: 重启服务**

   ```bash
   docker-compose down
   docker-compose up -d
   ```

   **常见 LDAP 配置示例:**

   <details>
   <summary>Active Directory (微软 AD)</summary>

   ```bash
   LDAP_ENABLED=on
   LDAP_SERVER=ldap://ad.company.com
   LDAP_PORT=389
   LDAP_USE_SSL=false
   LDAP_SEARCH_BASE=dc=company,dc=com
   LDAP_SEARCH_FILTER=(sAMAccountName={username})
   LDAP_BIND_DN=cn=ldapservice,ou=ServiceAccounts,dc=company,dc=com
   LDAP_BIND_PASSWORD=您的服务密码
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
   <summary>LDAPS (安全 LDAP)</summary>

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

   **测试 LDAP 连接:**

   ```bash
   # 查看后端日志中的 LDAP 连接状态
   docker-compose logs backend | grep -i ldap

   # 通过 API 测试登录
   curl -X POST http://localhost:5001/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser","password":"testpass"}'
   ```

3. **限制网络访问**：
   ```yaml
   # 仅暴露必要端口
   ports:
     - "127.0.0.1:80:80"
   ```

4. **启用 HTTPS**：
   ```nginx
   # 在 Nginx 配置中添加 SSL 配置
   server {
       listen 443 ssl;
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
   }
   ```
## 📊 监控和日志

### VictoriaMetrics 配置

LMeterX 内置 [VictoriaMetrics](https://victoriametrics.com/) 作为轻量级高性能时序数据库，用于存储实时性能指标及压测引擎的资源监控数据（CPU 使用率、内存占用、网络带宽收发速率）。

#### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `VICTORIA_METRICS_URL` | `http://victoria-metrics:8428` | VictoriaMetrics 服务地址（后端与引擎服务均需配置） |
| `RESOURCE_COLLECT_INTERVAL` | `2` | 引擎资源采集间隔（秒） |
| `ENGINE_ID` | 自动（取自容器 hostname） | 固定引擎标识，单实例场景可手动指定 |
| `ENGINE_POD_NAME` | — | Kubernetes Pod 名称，优先级高于 hostname |

#### Docker Compose 服务配置

```yaml
victoria-metrics:
  image: victoriametrics/victoria-metrics:v1.106.1
  container_name: lmeterx-victoria-metrics
  restart: unless-stopped
  ports:
    - "8428:8428"             # HTTP API、Prometheus 远程写入及内置 UI 端口
  volumes:
    - vm_data:/victoria-metrics-data   # 时序数据持久化存储
  command:
    - "-retentionPeriod=7d"               # 数据保留周期（默认 7 天）
    - "-search.maxUniqueTimeseries=50000" # 查询允许的最大唯一时间序列数
    - "-memory.allowedPercent=60"         # 允许使用的内存占比（%）
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 2G
      reservations:
        cpus: '0.5'
        memory: 1G
  healthcheck:
    test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8428/health"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 10s
```

#### 关键调优参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `-retentionPeriod` | `7d` – `30d` | 原始数据保留时长，长期趋势分析可适当延长 |
| `-search.maxUniqueTimeseries` | `50000` | 并行压测任务较多时可适当调大 |
| `-memory.allowedPercent` | `40` – `70` | 内存紧张时降至 `40`；查询密集时可升至 `70` |

#### 验证 VictoriaMetrics 服务

```bash
# 健康检查
curl http://localhost:8428/health

# 查询最近 5 分钟的引擎 CPU 指标
curl "http://localhost:8428/api/v1/query_range?query=engine_cpu_percent&start=-5m&step=15s"

# 查看所有可用的指标名称
curl "http://localhost:8428/api/v1/label/__name__/values"
```

#### 指标参考

| 指标名称 | 标签 | 说明 |
|----------|------|------|
| `engine_cpu_percent` | `engine_id` | 引擎 CPU 使用率（%，相对于已分配核数） |
| `engine_cpu_limit_cores` | `engine_id` | 容器 CPU 核数上限 |
| `engine_memory_used_bytes` | `engine_id` | 引擎内存使用量（字节） |
| `engine_memory_total_bytes` | `engine_id` | 引擎内存上限（字节） |
| `engine_memory_percent` | `engine_id` | 引擎内存使用率（%） |
| `engine_network_sent_bytes_per_sec` | `engine_id` | 网络发送带宽（字节/秒） |
| `engine_network_recv_bytes_per_sec` | `engine_id` | 网络接收带宽（字节/秒） |
| `engine_network_sent_bytes_total` | `engine_id` | 累计发送字节数 |
| `engine_network_recv_bytes_total` | `engine_id` | 累计接收字节数 |
| `lmeterx_current_users` | `task_id`, `task_type`, `engine_id` | 当前活跃虚拟用户数 |
| `lmeterx_current_rps` | `task_id`, `task_type`, `engine_id` | 实时请求速率（RPS） |
| `lmeterx_avg_response_time` | `task_id`, `task_type`, `engine_id` | 平均响应时间（ms） |
| `lmeterx_p95_response_time` | `task_id`, `task_type`, `engine_id` | P95 响应时间（ms） |
| `lmeterx_total_requests` | `task_id`, `task_type`, `engine_id` | 累计请求总数 |
| `lmeterx_total_failures` | `task_id`, `task_type`, `engine_id` | 累计失败总数 |

> **多引擎部署说明**：每个引擎实例自动从容器 hostname 派生唯一 `engine_id`。可通过 `ENGINE_ID`（Docker Compose）或 `ENGINE_POD_NAME`（Kubernetes）环境变量显式指定固定、易读的标识符。

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
docker-compose -f docker-compose.yml pull

# 重启服务
docker-compose -f docker-compose.yml up -d
```

### 更新应用代码
```bash
# 拉取最新代码
git pull origin main

# 重新构建并启动服务
docker-compose -f docker-compose.yml build --no-cache
docker-compose -f docker-compose.yml up -d
```

**选择适合你的部署方式，开始使用LMeterX进行性能测试！** 🚀
