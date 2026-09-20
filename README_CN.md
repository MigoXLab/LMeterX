<div align="center">
  <img src="docs/images/logo.png" alt="LMeterX Logo" width="300"/>
  <p>
    <a href="https://github.com/MigoXLab/LMeterX/blob/main/LICENSE"><img src="https://img.shields.io/github/license/MigoXLab/LMeterX" alt="License"></a>
    <a href="https://github.com/MigoXLab/LMeterX/stargazers"><img src="https://img.shields.io/github/stars/MigoXLab/LMeterX" alt="GitHub stars"></a>
  <a href="https://github.com/MigoXLab/LMeterX/network/members"><img src="https://img.shields.io/github/forks/MigoXLab/LMeterX" alt="GitHub forks"></a>
  <a href="https://github.com/MigoXLab/LMeterX/issues"><img src="https://img.shields.io/github/issues/MigoXLab/LMeterX" alt="GitHub issues"></a>
    <a href="https://deepwiki.com/MigoXLab/LMeterX"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
  </p>
  <p>
    <strong>简体中文</strong> |
    <a href="README.md">English</a>
  </p>
</div>

## 📋 项目简介

LMeterX 是一个专业的性能测试平台，覆盖大模型推理服务、通用 HTTP 接口，以及 Agent 协议压测。既支持 LiteLLM、vLLM、TensorRT-LLM、LMDeploy 等推理框架，也支持 Azure OpenAI、AWS Bedrock、Google Vertex AI 等云服务，同时支持 A2A Agent 协作与 MCP 工具调用压测。通过直观的 Web 界面，可以创建和管理测试任务，实时监控过程，并获得详细性能报告，为部署和优化提供数据支撑。


<div align="center">
  <img src="docs/images/images.gif" alt="LMeterX Demo" width="700"/>
</div>

## ✨ 核心特性

- **主流框架兼容**：适配 vLLM、LiteLLM、TRT-LLM 等主流推理框架及云平台，实现环境无缝迁移。
- **全模态全场景**：支持 GPT、Claude、Llama 及 [MinerU](https://github.com/opendatalab/MinerU)、[dots.ocr](https://github.com/rednote-hilab/dots.ocr) 等文档解析模型，涵盖文本、多模态与流式交互。
- **多协议模型接口**：原生支持 OpenAI `/v1/chat/completions`、`/v1/responses`&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />、Anthropic `/v1/messages`、Embeddings 与自定义模型接口，同时支持通用 HTTP 业务接口。
- **多模式高并发压测**：支持固定/阶梯式并发&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />策略，支持模拟超高并发，精准定位性能拐点与系统容量上限。
- **系统数据集库**：一次上传，可在 LLM、HTTP、A2A、MCP 任务中按类型选用，系统预置公开 ShareGPT 文本集。
- **智能自动化预热**&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />：支持模型自动预热，消除冷启动干扰，确保测试数据精准可靠。
- **多维指标可视化**：集成 TTFT、RPS、TPS 及吞吐分布等核心指标，支持性能数据实时追踪与可视化&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />。
- **系统资源监控**&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />：支持压测机 CPU、内存与网络带宽的实时监控，精准排除本地资源瓶颈
- **AI 驱动数据洞察**：AI 辅助分析报告&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />，支持多模型多维度结果对比，直观呈现性能优化方向。
- **一站式 Web 控制台**：直观管理任务调度、监控与实时日志，显著降低上手门槛与运维成本。
- **Web 解析和智能压测**&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />：输入网页 URL 自动爬取页面、识别核心业务 API，一键完成连通性预检与压测任务创建，零配置启动压测。
- **AI Agent 集成**&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />：内置 MCP Server 与 [OpenClaw](https://github.com/openclaw) Skills，原生支持 Claude Code、Cursor 等 AI Agent 通过自然语言指令自动生成压测配置并快速启动任务。
- **A2A / MCP 协议压测**&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />：支持对 Agent 协作服务（A2A 1.0，覆盖 JSON-RPC、HTTP+JSON REST、gRPC 三种协议绑定）和 MCP 工具服务压测。可按权重混合多种业务场景，覆盖同步、流式 SSE、异步轮询，并统计耗时、成功率与工具调用指标。
- **跨集群 Engine 调度**&nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" />：一个控制面统一管理多个本地或 Kubernetes 压测集群，任务可按压测环境路由，并支持 Engine 心跳、资源监控与弹性扩缩容。
- **企业级架构安全**：支持分布式部署、LDAP/AD 集成，以及 Engine 与 AI Agent 的独立服务令牌，满足企业级扩展与认证需求。

### 工具对比

| 维度 | LMeterX | EvalScope | llmperf |
|------|---------|---------|-----------|
| 使用 | 提供 Web UI：任务创建、监控、停止全生命周期管理（压测） | CLI 命令行，面向 ModelScope 生态（效果评测和压测）| CLI 命令行，依赖 Ray 框架（压测） |
| 并发与压测 | 支持多进程、多任务、固定和阶梯式并发模式，企业级规模化压测 | 支持命令参数并发 | 支持命令参数并发 |
| 测试报告 | 支持多模型/多版本对比，AI 分析，提供可视化页面 | 基础报告 + 可视化图表（需额外安装 gradio, plotly等） | 简易报告 |
| 模型与数据支持 | 支持 OpenAI Chat/Responses、Claude、A2A（JSON-RPC / HTTP+JSON / gRPC）、MCP、自定义数据和模型接口 | 默认支持 OpenAI 格式，扩展新 API 需自行实现代码 | 支持 OpenAI 格式 |
| 性能与资源监控| 支持实时监控性能指标和压测机资源情况 | - | - |
| 部署与扩展 | 提供 Docker / K8s 部署方案，易于弹性伸缩 | `pip` 或源码 | 源码 |

## 🏗️ 系统架构

LMeterX 采用控制面与执行面分离的微服务架构：

- **控制面**：前端、Backend、MySQL 和 VictoriaMetrics，负责任务、调度、结果与监控。
- **执行面**：一个或多个 Engine 实例，通过 Backend API 注册、心跳并领取所属集群的任务。
- **Cluster Agent（可选）**：部署在远端 Kubernetes 集群，根据控制面期望状态调整 Engine 副本数。

<div align="center">
  <img src="docs/images/tech-arch.png" alt="LMeterX tech arch" width="800"/>
</div>

## 🚀 快速开始

### 环境检查清单
- Docker 20.10.0+（确保 Docker 守护进程已启动）
- Docker Compose 2.0.0+（支持 `docker compose` 或 `docker-compose`）
- 至少 4GB 可用内存、5GB 磁盘空间

> **需要更多部署方式？** 请查阅 [完整部署指南](docs/DEPLOYMENT_GUIDE_CN.md)，获取 Kubernetes、离线环境等高级方案。

> Docker Compose 默认创建 `local` 压测环境。需要接入多个 Engine 集群时，请参考 [跨多集群 Engine 部署指南](docs/MULTI_CLUSTER_GUIDE_CN.md)。

### 一键部署（推荐）

```bash
# 默认使用预构建镜像启动全套服务
curl -fsSL https://raw.githubusercontent.com/MigoXLab/LMeterX/main/quick-start.sh | bash
```

启动完成后可执行：
- `docker compose ps` 查看容器状态
- `docker compose logs -f` 追踪实时日志
- `docker compose up -d --scale backend=2 --scale engine=2` 服务扩容(如需)
- 在浏览器打开 http://localhost:8080（详见下方「使用指南」）

### 数据目录与挂载说明
- `./data` → 挂载到 `engine` 容器的 `/app/data`（预置 ShareGPT 源文件、多模态本地图片；大规模数据不打进镜像）
- `./logs` → 后端与压测引擎的统一日志输出目录
- `./upload_files` → 数据集库文件、任务上传文件及导出报表

数据集统一为 UTF-8 JSONL（每行一个 JSON 对象），类型需与任务匹配：`llm`、`business`（HTTP）、`a2a`、`mcp`。行格式、字段规则与图片挂载见 [数据集使用指南](docs/DATASET_GUIDE.md)。

### 使用指南

任务页提供四个标签：**HTTP API**、**大模型压测**、**A2A Agent 协作**、**MCP 工具调用**。按被测对象切换即可。各类型创建任务时均可粘贴完整 curl 并一键解析，自动填充请求信息。

#### 通用 HTTP 接口压测

1. **访问界面**: 打开 http://localhost:8080，切换到「HTTP API」
2. **创建任务**: 导航至 测试任务 → 创建任务
   - 粘贴完整 curl 命令，点击「一键解析」，自动填充请求方法、URL、请求头和请求体
   - 核对解析结果是否完整、准确
3. **API 测试**: 点击「测试」按钮验证接口连通性，确认请求信息正确后再压测
4. **数据集**（可选）: 从数据集库选择 `business` 类型数据集或上传 JSONL。每行须为完整请求体 JSON 对象，按轮询使用。不使用数据集时，每次发送表单中的请求体。
5. **开始压测**: 配置并发用户数、时长等参数后点击「创建」
6. **实时监控**: 测试过程中点击「日志」查看压测状态与实时日志
7. **结果分析**: 测试完成后点击「结果」，查看 RPS、响应时间、成功率等指标

#### 大模型接口压测

1. **访问界面**: 打开 http://localhost:8080，切换到「大模型压测」
2. **创建任务**: 导航至 测试任务 → 创建任务，配置 API 请求信息、测试数据以及请求响应字段映射
   - 2.1 压测环境: 选择任务要运行的 Engine 集群；单机部署选择默认的 `Local`
   - 2.2 基础信息: 可粘贴完整 curl 并点击「一键解析」，自动填充 API 地址、路径、模型、请求头和请求体；路径含 `/chat/completions`、`/responses`、`/messages`、`/embeddings` 时会自动识别 API 类型。也可手动填写 API 类型、路径、模型与响应模式，或在请求参数中补充完整 payload
   - 2.3 OpenAI Responses: API 类型选择 `OpenAI Responses`，路径填写 `/v1/responses`；请求体使用 `input` 而不是 `messages`
   - 2.4 数据与负载: 从数据集库选择、上传 `.jsonl`、粘贴 JSONL，或不使用数据集而沿用请求体。再配置并发与时长。
     - OpenAI / Claude Chat：每行需有 `prompt` 或 `messages`；可选 `system_prompt` 替换 system 消息 / Claude 顶层 `system`。有 `messages` 时替换整段对话，否则用 `prompt` 替换用户消息。
     - OpenAI Responses：每行使用 `prompt`、`input` 或 `messages`（写入 `input`）。
     - 自定义 Chat / Embeddings：每行是**完整请求体**。
   - 2.5 字段映射: 仅自定义 API 等非标准接口需要配置 prompt、content、reasoning_content、usage 等字段路径
   > 💡 **提示**: 行格式、ShareGPT 兼容说明与本地图片挂载见 [数据集使用指南](docs/DATASET_GUIDE.md)。
3. **API 测试**: 在 测试任务 → 创建任务，点击基础信息面板的「测试」按钮，快速验证接口连通性（建议使用简短 prompt）
4. **实时监控**: 访问 测试任务 → 日志/监控中心，查看全链路测试日志，快速定位异常
5. **结果分析**: 进入 测试任务 → 结果，查看详细性能指标并导出报告
6. **结果对比**: 在 模型擂台 模块选择多个模型/版本，进行多维度性能对比
7. **AI 分析**: 在 测试任务 → 结果/模型擂台 中配置 AI 分析服务后，可对单个或多任务进行智能评估

#### A2A Agent 协作压测

用于压测遵循 A2A 1.0 的 Agent 服务：向对方发送消息，等待任务完成并统计端到端性能。支持三种协议绑定：

| 协议绑定 | 地址填写 | 实际请求 |
|---------|---------|---------|
| **JSON-RPC** | 单端点 URL，如 `https://agent.example.com/a2a` | POST 到该端点，方法写在 JSON-RPC 请求体中（`SendMessage` / `SendStreamingMessage`） |
| **HTTP+JSON (REST)** | 服务基地址，不含路由后缀 | 按执行方式自动拼接 `/message:send`、`/message:stream`；异步轮询时再请求 `GET /tasks/{taskId}` |
| **gRPC** | `host:port`，如 `agent.example.com:443` | 调用 `a2a.A2AService/SendMessage` 或 `SendStreamingMessage` |

1. 打开 http://localhost:8080，切换到 **A2A Agent 协作**
2. 创建任务。可粘贴完整 `curl`（或 gRPC 的 `grpcurl`）并点击「一键解析」，自动识别协议绑定、执行方式，并填充地址、请求头和消息场景
3. 选择协议绑定并填写服务地址（Agent Card 地址可选，留空时自动发现）。JSON-RPC / HTTP+JSON 填 `https://...` 基地址；gRPC 填 `host:port`，不要带 `http://`
4. 点击「测试连接」，确认服务可达
5. 添加消息场景并设置权重，压测时按权重随机发送
6. 选择执行方式：**同步**、**流式 SSE**，或 **异步提交 + 轮询**
7. （可选）选用 `a2a` 类型数据集或上传 `.jsonl`，为同一场景提供不同 `message`。每行必填 `id`、`scenario_id`（须对应已配置场景）、`message`（`role` 为 `ROLE_USER`，`parts` 非空）。禁止多余字段；权重写在场景上。文件须覆盖任务中全部场景。
8. 配置并发与时长后创建任务，在日志和结果中查看耗时与成功率

#### MCP 工具调用压测

用于压测 MCP Streamable HTTP 服务：并发调用工具，统计调用延迟与成功率。

1. 切换到 **MCP 工具调用**
2. 填写 MCP Streamable HTTP 地址，或粘贴 curl 并一键解析以自动填充地址、请求头和工具场景；点击「测试连接」发现可用工具
3. 添加工具调用场景：选择工具名、填写 `arguments`，并设置权重
4. （可选）选用 `mcp` 类型数据集或上传 `.jsonl`，为同一工具提供不同参数。每行必填 `id`、`scenario_id`（须对应已配置场景），`arguments` 为对象（可为 `{}`）。禁止多余字段；文件须覆盖任务中全部场景。
5. 配置并发与时长后创建任务，在结果中查看工具调用延迟与成功率

## 🔧 配置说明

### 数据库配置
```bash
=== 数据库配置 ===
DB_HOST=mysql
DB_PORT=3306
DB_USER=lmeterx
DB_PASSWORD=lmeterx_password
DB_NAME=lmeterx
```

### LDAP/AD 认证配置

```bash
=== LDAP 认证配置 ===
# 启用或禁用 LDAP 认证 (on/off)，默认关闭
LDAP_ENABLED=on

# LDAP 服务器连接配置
LDAP_SERVER=ldap://ldap.example.com    # LDAP 服务器地址
LDAP_PORT=389                          # LDAP 服务器端口 (389为LDAP，636为LDAPS)
LDAP_USE_SSL=false                     # 是否使用 SSL/TLS 连接 (LDAPS使用true)
LDAP_TIMEOUT=5                         # 连接超时时间(秒)

# LDAP 搜索配置
LDAP_SEARCH_BASE=dc=example,dc=com     # 用户搜索基准 DN
LDAP_SEARCH_FILTER=(sAMAccountName={username})  # LDAP 搜索过滤器

# 认证方式 1: 使用 DN 模板直接绑定(适用于简单 LDAP 场景)
LDAP_USER_DN_TEMPLATE=cn={username},ou=users,dc=example,dc=com

# 认证方式 2: 使用服务账号绑定(适用于 Active Directory)
LDAP_BIND_DN=cn=service,ou=users,dc=example,dc=com    # 服务账号 DN
LDAP_BIND_PASSWORD=service_password                   # 服务账号密码

# JWT 配置(可选)
JWT_SECRET_KEY=your-secret-key-here    # JWT 签名密钥(生产环境请修改)
JWT_EXPIRE_MINUTES=10080                 # Token 过期时间(分钟，默认7天)
```

**配置说明:**
- **简单 LDAP 部署**: 使用 `LDAP_USER_DN_TEMPLATE` 进行用户直接绑定
- **Active Directory**: 使用 `LDAP_BIND_DN` + `LDAP_BIND_PASSWORD` 进行服务账号绑定
- **安全性**: 生产环境务必设置 `LDAP_USE_SSL=true`
- **前端配置**: 设置 `VITE_LDAP_ENABLED=on` 以启用登录界面

### AI Agent Service Token 配置

`LMETERX_AUTH_TOKEN` 是专为 AI Agent / Skill 程序化访问（如 Claude Code、Cursor、OpenClaw Skills）设计的静态服务令牌，使 Agent 工具无需经过交互式 LDAP 登录即可调用指定接口。详细配置和白名单API见: [完整部署指南](docs/DEPLOYMENT_GUIDE_CN.md)

```bash
# ================= Service Token 配置 =================
# AI Agent / Skill 程序化访问专用静态令牌。
# 设置后，该令牌绑定内置的 "agent" 用户。
# 仅在 LDAP_ENABLED=on 且需要 AI Agent 集成时才需配置。
LMETERX_AUTH_TOKEN=<your-strong-random-token>
```

### 资源配置
```bash
=== 高并发压测 部署要求 ===
# 当并发用户数超过此阈值，系统将自动启用多进程模式（需多核 CPU 支持）
MULTIPROCESS_THRESHOLD: 1000
# 每个子进程至少承载的并发用户数（避免进程过多导致资源浪费）
MIN_USERS_PER_PROCESS: 500
# ⚠️ 重要提示：
#   - 当并发量 ≥ 1000 时，强烈建议启用多进程以提升性能。
#   - 多进程模式依赖多核 CPU 资源，请确保部署环境满足资源要求
deploy:
  resources:
    limits:
      cpus: '2.0'    # 建议至少分配 2 核 CPU（高并发场景建议 4 核或以上）
      memory: 2G     # 内存限制，可根据实际负载调整（推荐 ≥ 2G）
```

### VictoriaMetrics 配置

LMeterX 使用 [VictoriaMetrics](https://victoriametrics.com/) 作为轻量级高性能时序数据库，用于存储实时性能指标及压测引擎的资源监控数据（CPU、内存、网络带宽）。

```bash
# ================= VictoriaMetrics 配置 =================
# VictoriaMetrics 服务地址（后端与引擎均需配置）
VICTORIA_METRICS_URL=http://victoria-metrics:8428

# 引擎资源采集间隔，单位秒（默认 2s）
RESOURCE_COLLECT_INTERVAL=2
```

`docker-compose.yml` 中的核心参数说明：

```yaml
victoria-metrics:
  image: victoriametrics/victoria-metrics:v1.106.1
  ports:
    - "8428:8428"             # HTTP API 及 UI 端口
  command:
    - "-retentionPeriod=7d"               # 数据保留周期（默认 7 天）
    - "-search.maxUniqueTimeseries=50000" # 查询允许的最大唯一时间序列数
    - "-memory.allowedPercent=60"         # 允许使用的内存占比（%）
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 2G
```

> **说明**：资源采集模块支持 cgroup v1 与 cgroup v2。多引擎部署时，每个实例必须使用全局唯一的 `engine_id`；容器部署可自动使用 hostname，Kubernetes 推荐将 `ENGINE_ID` 设为 Pod UID。

## 🤝 开发指南

> 💡 **欢迎贡献**！查看 [贡献指南](docs/CONTRIBUTING.md) 了解详情

### 技术栈

- **后端** - Python + FastAPI + SQLAlchemy + MySQL
- **压测引擎** - Python + Locust + 自定义扩展
- **前端** - React + TypeScript + Ant Design + Vite
- **部署** - Docker + Docker Compose + Nginx

### 开发环境搭建

1. **Fork项目** → 克隆到本地
2. **创建分支** → 进行功能开发
3. **代码检查** → 运行 `make all` 确保质量
4. **提交PR** → 遵循约定式提交规范
5. **文档更新** → 为新功能撰写文档

## 🗺️ 发展路线图

### 规划中
- [ ] CLI 命令行工具
- [ ] 多接口场景压测

## 📚 相关文档

- [部署指南](docs/DEPLOYMENT_GUIDE_CN.md) - 详细部署说明
- [跨多集群 Engine 部署指南](docs/MULTI_CLUSTER_GUIDE_CN.md) - 集群注册、Engine 接入、扩缩容与排查
- [贡献指南](docs/CONTRIBUTING.md) - 参与开发指南
- [数据集使用指南](docs/DATASET_GUIDE.md) - LLM / HTTP / A2A / MCP 的 JSONL 格式与使用说明

## 👥 贡献者

感谢所有为 LMeterX 做出贡献的开发者：

- [@LuckyYC](https://github.com/LuckyYC) - 项目维护者 & 核心开发者
- [@del-zhenwu](https://github.com/del-zhenwu) - 核心开发者

## 🗂️ 数据集引用说明

> 系统预置公开数据集 **ShareGPT V3 Partial**（`ShareGPT_V3_partial.jsonl`）会挂入数据集库，类型为 LLM 文本，每行为 `{"id","prompt"}`。样本来自开源 ShareGPT，遵循原始许可。

- **数据来源**：[ShareGPT 数据集](https://huggingface.co/datasets/learnanything/sharegpt_v3_unfiltered_cleaned_split) 对话语料
- **调整范围**：
  - 筛选高质量对话样本，剔除低质量或与压测场景无关的数据
  - 进行随机抽样，减轻数据规模的同时保留多样化对话

## 📄 开源许可

本项目采用 [Apache 2.0 许可证](LICENSE)。

<div align="center">

**⭐ 如果这个项目对您有帮助，请给我们一个 Star！您的支持是我们持续改进的动力。**

</div>
