---
name: run-api-loadtest
emoji: 🎯
description: |
  给定一个**具体的 API 端点 URL** 或 **curl 命令**，自动判断 API 类型
  （LLM API 或普通 HTTP API），预检连通性后直接创建 LMeterX 压测任务。
  适用场景：用户已经明确知道要压测哪个 API 接口。
triggers:
  - 帮我压测这个 API
  - 帮我压测这个接口
  - 直接压测这个 API
  - 压测这个 curl
  - 压测这个端点
  - 压测这个 API 接口
  - 压测这个 API 地址
  - load test this API
  - load test this endpoint
  - stress test this curl
requires:
  env:
    - LMETERX_BASE_URL
---

# Skill: run-api-loadtest

## 用途

给定一个**具体的 API 端点 URL**（如 `https://api.example.com/v1/users`）或 **curl 命令**，自动判断 API 类型并直接创建压测任务。

## ⚠️ 本 Skill 与 `run-web-loadtest` 的区别

> **重要**：如果用户提到"网站""网页""页面"或给了一个普通网站 URL（如 `https://www.baidu.com`、`https://example.com`），
> **必须使用 `lmeterx-web-loadtest`，不要使用本 Skill**。

| 判断条件 | 使用本 Skill（run-api-loadtest） ✅ | 使用 lmeterx-web-loadtest ❌ |
|---------|-------------------------------|----------------------|
| 用户给了什么 | 一个具体的 **API 端点 URL** 或 **curl 命令** | 一个**网页/网站 URL**（HTML 页面） |
| 典型 URL | `https://api.example.com/v1/users`、含 `/api/`、`/v1/`、`/graphql` 路径 | `https://www.baidu.com`、`https://example.com`、`https://app.com/dashboard` |
| 用户关键词 | "压测这个 **API/接口/端点**"、"压测这个 **curl**" | "压测这个**网站/网页/页面**" |
| 输入中是否含 curl | ✅ 经常包含 curl 命令 | ❌ 通常不含 |
| 用户意图 | "我知道要压哪个接口，直接压" | "不确定有哪些 API，帮我分析再压测" |

**快速判断规则**：
1. 用户说"压测这个网站/网页/页面" → **使用 `lmeterx-web-loadtest`**
2. URL 看起来是浏览器可打开的普通网页（如 `https://www.baidu.com`）→ **使用 `lmeterx-web-loadtest`**
3. 用户说"压测这个 API/接口" 或给了 curl 命令 → 使用本 Skill
4. URL 含 `/api/`、`/v1/`、`/graphql` 等 API 路径特征 → 使用本 Skill

## API 类型判断规则

根据 URL 路径自动判断：

| URL 路径特征 | API 类型 | api_type 值 | 接口前缀 |
|-------------|---------|-------------|---------|
| 以 `/v1/chat/completions` 结尾 | LLM API | `openai-chat` | `/api/llm-tasks` |
| 以 `/v1/messages` 结尾 | LLM API | `claude-chat` | `/api/llm-tasks` |
| 其他 | 普通 HTTP API | — | `/api/http-tasks` |

### LLM API URL 拆分规则

LLM API 需要将完整 URL 拆分为 `target_host` + `api_path`：

```
https://api.openai.com/v1/chat/completions
  → target_host = "https://api.openai.com/v1"
  → api_path    = "/chat/completions"

https://api.anthropic.com/v1/messages
  → target_host = "https://api.anthropic.com/v1"
  → api_path    = "/messages"
```

## 工作流程（3 步）

> 所有对 LMeterX 后端的 API 调用都需要在请求头中附带 `X-Authorization: <LMETERX_AUTH_TOKEN>`（不加 Bearer 前缀，仅当后端启用 LDAP 认证时需要）。

---

#### 0.1 检查 `LMETERX_BASE_URL`

- 如果环境变量 `LMETERX_BASE_URL` 已设置 → 使用该值
- 如果**未设置** → 立即询问用户：

> ⚙️ 尚未配置 LMeterX 服务地址。请提供你的 LMeterX 后端 URL，例如：`http://localhost:8080`

用户回复后，将其作为 `{LMETERX_BASE_URL}` 用于后续所有请求。

#### 0.2 验证后端连通性

```
GET {LMETERX_BASE_URL}/health
```

- 返回 HTTP 200 → 后端正常，继续
- **连接失败 / 超时 / 非 200** → 告知用户：

> ❌ 无法连接 LMeterX 后端（{LMETERX_BASE_URL}），请检查：
> 1. 地址是否拼写正确（需含协议，如 `https://`）
> 2. LMeterX 服务是否已启动
> 3. 网络 / 防火墙是否放通
>
> 请重新提供正确的地址。

等待用户提供新地址后重新验证，直到通过。

#### 0.3 检查认证状态

```
GET {LMETERX_BASE_URL}/api/auth/profile
X-Authorization: <LMETERX_AUTH_TOKEN>
```

| 响应 | 处理 |
|------|------|
| 200 且用户名非 `anonymous` | ✅ 认证通过，告知用户当前身份，继续 |
| 200 且用户名为 `anonymous` | ✅ 该实例未启用认证，继续 |
| 401 且**未配置** `LMETERX_AUTH_TOKEN` | ❌ 引导用户提供 Token（见下方提示） |
| 401 且**已配置** Token | ❌ Token 无效或已过期，引导用户重新提供 |
| 其他状态码 | ⚠️ 警告但不阻断，继续执行 |

**401 时的引导提示：**

> 🔐 该 LMeterX 实例需要登录认证。请提供你的 Auth Token。
>
> **获取方式**：登录 LMeterX 管理页面复制 Token，或执行：
> ```
> curl -X POST {LMETERX_BASE_URL}/api/auth/login \
>   -H 'Content-Type: application/json' \
>   -d '{"username":"<用户名>","password":"<密码>"}'
> ```
> 从返回的 JSON 中复制 `access_token` 值。

用户提供 Token 后，在后续所有请求头中附带 `X-Authorization: <token>`（Service Token 不加 `Bearer` 前缀）。

---

### 路径 A：LLM API 压测

#### Step 1 — 预检 API 连通性

```
POST {LMETERX_BASE_URL}/api/llm-tasks/test
Content-Type: application/json
```

**请求体：**

```json
{
  "target_host": "https://api.openai.com/v1",
  "api_path": "/chat/completions",
  "model": "gpt-4",
  "stream_mode": true,
  "headers": [{"key": "Authorization", "value": "Bearer sk-xxx"}],
  "cookies": [],
  "request_payload": "",
  "api_type": "openai-chat"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| target_host | ✅ | API 主机地址（含 /v1 前缀） |
| api_path | — | API 路径，默认 `/chat/completions` |
| model | — | 模型名称（可从请求体自动提取） |
| stream_mode | — | 流式响应，默认 true |
| headers | — | `[{key, value}]` 格式，需过滤掉 `Content-Type` |
| cookies | — | `[{key, value}]` 格式 |
| request_payload | — | 自定义请求体 JSON 字符串 |
| api_type | — | `openai-chat` 或 `claude-chat` |

**成功响应**：`{"status": "success", "http_status": 200}`

#### Step 2 — 创建 LLM 压测任务（仅在 Step 1 通过后执行）

```
POST {LMETERX_BASE_URL}/api/llm-tasks
Content-Type: application/json
```

**请求体：**

```json
{
  "temp_task_id": "direct_a1b2c3d4",
  "name": "api.openai.com/v1/chat/completions",
  "target_host": "https://api.openai.com/v1",
  "api_path": "/chat/completions",
  "model": "gpt-4",
  "duration": 300,
  "concurrent_users": 50,
  "spawn_rate": 30,
  "stream_mode": true,
  "headers": [{"key": "Authorization", "value": "Bearer sk-xxx"}],
  "cookies": [],
  "request_payload": "",
  "api_type": "openai-chat",
  "chat_type": 0,
  "warmup_enabled": true,
  "warmup_duration": 120,
  "load_mode": "fixed"
}
```

**成功响应**：`{"task_id": "t_xxxxxxxx", "status": "pending", "message": "..."}`
**报告地址**：`{LMETERX_BASE_URL}/results/{task_id}`

---

### 路径 B：普通 HTTP API 压测

#### Step 1 — 预检 API 连通性

```
POST {LMETERX_BASE_URL}/api/http-tasks/test
Content-Type: application/json
```

**请求体：**

```json
{
  "method": "GET",
  "target_url": "https://api.example.com/users",
  "headers": [{"key": "Authorization", "value": "Bearer xxx"}],
  "cookies": [],
  "request_body": ""
}
```

**成功响应**：`{"status": "success", "http_status": 200}`

#### Step 2 — 创建 HTTP 压测任务（仅在 Step 1 通过后执行）

```
POST {LMETERX_BASE_URL}/api/http-tasks
Content-Type: application/json
```

**请求体：**

```json
{
  "temp_task_id": "direct_a1b2c3d4",
  "name": "api.example.com/users",
  "method": "GET",
  "target_url": "https://api.example.com/users",
  "headers": [{"key": "Authorization", "value": "Bearer xxx"}],
  "cookies": [],
  "request_body": "",
  "concurrent_users": 50,
  "duration": 300,
  "spawn_rate": 30,
  "load_mode": "fixed"
}
```

**成功响应**：`{"task_id": "ct_xxxxxxxx", "status": "pending", "message": "..."}`
**报告地址**：`{LMETERX_BASE_URL}/http-results/{task_id}`

---

## 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| url / curl | ✅(二选一) | — | API URL 或完整 curl 命令 |
| method | — | POST | HTTP 方法 |
| headers | — | [] | 请求头 |
| cookies | — | [] | Cookie |
| body | — | "" | 请求体 JSON |
| model | — | (自动提取) | 模型名称（LLM API 专用） |
| stream | — | true | 流式响应（LLM API 专用） |
| concurrent_users | — | 50 | 并发用户数 (1-5000) |
| duration | — | 300 | 持续时间秒 (1-172800) |
| spawn_rate | — | 30 | 用户生成速率 |
| name | — | (自动生成) | 任务名称 |

### curl 解析规则

从 curl 命令中提取：
- URL → 目标地址
- `-X`/`--request` → HTTP 方法（无 `-X` 且有 `-d` 则为 POST，否则 GET）
- `-H`/`--header` → 请求头（格式 `Key: Value`）
- `-d`/`--data`/`--data-raw` → 请求体
- `-b`/`--cookie` → Cookie（格式 `Key=Value;...`）

## 输出

完成后，向用户报告：

1. API 类型识别结果（LLM / 普通 HTTP）
2. 预检结果（通过/失败），失败时给出**分类原因和排查建议**
3. 任务 `task_id`
4. 报告查看地址

### 预检失败分类

当预检未通过时，脚本会输出失败原因分类和排查建议：

| 分类 | 说明 | 建议 |
|------|------|------|
| 🔐 认证失败 (401) | 目标 API 需要认证 | 检查 Headers 中的 Authorization 或 API Key |
| 🚫 权限不足 (403) | 已认证但无访问权限 | 确认账号权限或 IP 白名单 |
| 🔗 地址无效 (404) | API 路径不存在 | 检查 URL 拼写是否正确 |
| ⛔ 方法不允许 (405) | HTTP 方法不匹配 | 检查 GET/POST 等是否正确 |
| ⏳ 请求限流 (429) | 目标 API 限流 | 稍后重试 |
| 💥 服务端错误 (5xx) | 目标服务内部异常 | 检查目标服务状态 |
| 🌐 连接失败 | 无法连接目标主机 | 检查 URL 和网络 |
| ⏱ 请求超时 | 目标 API 响应超时 | 检查目标服务是否正常 |
| 🔒 SSL/TLS 错误 | 证书验证失败 | 检查证书配置 |

## 错误处理与用户引导

在任何 API 调用（Step 1 / Step 2）返回异常时，**不要直接报错退出**，而是根据错误类型引导用户排查：

| 错误场景 | 引导提示 |
|---------|---------|
| 连接失败 / 超时 | `LMETERX_BASE_URL` 可能不正确或服务未启动，请用户重新确认地址 |
| HTTP 401 | Service Token 认证失败，引导用户检查 `LMETERX_AUTH_TOKEN` 是否与后端配置一致（参考 Step 0.3） |
| HTTP 403 | 账号无权限，建议用户联系管理员 |
| HTTP 404 | 接口不存在，可能 LMeterX 版本不匹配，建议确认后端版本 |
| HTTP 5xx | 后端服务异常，建议稍后重试或联系管理员 |

## 脚本调用（可选）

```bash
# curl 命令模式
python "${SKILL_DIR}/scripts/run.py" \
  --curl 'curl https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer sk-xxx" \
    -d "{\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"'

# 参数模式（LLM API）
python "${SKILL_DIR}/scripts/run.py" \
  --url "https://api.openai.com/v1/chat/completions" \
  --header "Authorization: Bearer sk-xxx" \
  --body '{"model":"gpt-4","messages":[{"role":"user","content":"Hello"}]}'

# 参数模式（普通 HTTP API）
python "${SKILL_DIR}/scripts/run.py" \
  --url "https://api.example.com/users" \
  --method GET \
  --concurrent-users 100 \
  --duration 600
```

## 环境变量

- `LMETERX_BASE_URL`（必须）— LMeterX 后端地址，例如 `http://localhost:8080`
- `LMETERX_AUTH_TOKEN`（可选）— Service Token（启用 LDAP 认证时需要，通过 `X-Authorization` 请求头传递，不加 Bearer 前缀）

> 如果环境变量未配置，Agent 会在对话中引导用户提供（参见 Step 0）。
