---
name: run-web-loadtest
emoji: 🚀
description: |
  输入一个网页 URL，后端自动爬取页面并识别核心业务 API，
  对候选 API 执行连通性预检后创建 LMeterX 压测任务。
triggers:
  - 帮我压测这个网站
  - 对这个 URL 做性能测试
  - load test this page
  - stress test this API page
  - 压测
requires:
  env:
    - LMETERX_BASE_URL
---

# Skill: run-web-loadtest

## 用途

输入一个网页 URL，自动分析页面中的核心业务 API，对候选 API 预检连通性后创建压测任务。

## 工作流程（4 步）

> 所有 API 调用都需要在请求头中附带 `Authorization: Bearer <LMETERX_AUTH_TOKEN>`（如已配置）。

### Step 0 — 环境配置检查与引导

在执行任何业务 API 调用前，**必须**先完成以下检查。如果任何一步失败，**停止后续流程**并引导用户修正。

#### 0.1 检查 `LMETERX_BASE_URL`

- 如果环境变量 `LMETERX_BASE_URL` 已设置 → 使用该值
- 如果**未设置** → 立即询问用户：

> ⚙️ 尚未配置 LMeterX 服务地址。请提供你的 LMeterX 后端 URL，例如：`https://lmeterx.example.com`

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
Authorization: Bearer <LMETERX_AUTH_TOKEN>
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

用户提供 Token 后，在后续所有请求头中附带 `Authorization: Bearer <token>`。

---

### Step 1 — 分析页面，提取 API

```
POST {LMETERX_BASE_URL}/api/skills/analyze-url
Content-Type: application/json
```

**请求体：**

```json
{
  "target_url": "https://example.com",
  "concurrent_users": 50,
  "duration": 300,
  "spawn_rate": 30,
  "wait_seconds": 5,
  "scroll": true
}
```

| 字段 | 必填 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| target_url | ✅ | string | — | 目标网页 URL |
| concurrent_users | — | int | 50 | 并发用户数 (1-5000) |
| duration | — | int | 300 | 持续时间秒 (1-172800) |
| spawn_rate | — | int | 30 | 用户生成速率 (1-10000) |
| wait_seconds | — | int | 5 | 页面加载后等待秒数 (1-30) |
| scroll | — | bool | true | 是否滚动页面触发懒加载 |

**成功响应：**

```json
{
  "status": "success",
  "message": "Successfully analyzed https://example.com",
  "target_url": "https://example.com",
  "analysis_summary": "From example.com detected 3 core business APIs ...",
  "llm_used": false,
  "discovered_apis": [
    {
      "name": "GET /api/users",
      "target_url": "https://example.com/api/users",
      "method": "GET",
      "headers": [{"key": "Authorization", "value": "Bearer xxx"}],
      "request_body": null,
      "http_status": 200,
      "source": "playwright_xhr_fetch",
      "confidence": "high"
    }
  ],
  "loadtest_configs": [
    {
      "temp_task_id": "skills_a1b2c3d4",
      "name": "GET /api/users",
      "method": "GET",
      "target_url": "https://example.com/api/users",
      "headers": [{"key": "Authorization", "value": "Bearer xxx"}],
      "cookies": [],
      "request_body": "",
      "concurrent_users": 50,
      "duration": 300,
      "spawn_rate": 30,
      "load_mode": "fixed"
    }
  ]
}
```

**判断逻辑**：如果 `status != "success"` 或 `loadtest_configs` 为空，终止流程并告知用户。

### Step 2 — 预检连通性

对 Step 1 返回的**每个** `loadtest_configs` 项调用：

```
POST {LMETERX_BASE_URL}/api/http-tasks/test
Content-Type: application/json
```

**请求体**（从 loadtest_config 中提取）：

```json
{
  "method": "GET",
  "target_url": "https://example.com/api/users",
  "headers": [{"key": "Authorization", "value": "Bearer xxx"}],
  "cookies": [],
  "request_body": ""
}
```

**成功响应**：

```json
{
  "status": "success",
  "http_status": 200,
  "response_time": 150
}
```

**判断逻辑**：`status == "success"` 的视为预检通过，记入通过列表。全部失败则终止流程。

### Step 3 — 创建压测任务

对每个**预检通过**的 config，直接作为 JSON body 提交：

```
POST {LMETERX_BASE_URL}/api/http-tasks
Content-Type: application/json
```

**请求体**（完整的 loadtest_config 对象）：

```json
{
  "temp_task_id": "skills_a1b2c3d4",
  "name": "GET /api/users",
  "method": "GET",
  "target_url": "https://example.com/api/users",
  "headers": [{"key": "Authorization", "value": "Bearer xxx"}],
  "cookies": [],
  "request_body": "",
  "concurrent_users": 50,
  "duration": 300,
  "spawn_rate": 30,
  "load_mode": "fixed"
}
```

**成功响应**：

```json
{
  "task_id": "ct_xxxxxxxx",
  "status": "pending",
  "message": "Task created"
}
```

## 输出

完成后，向用户报告：

1. 发现的 API 数量 及分析摘要
2. 预检通过/失败数
3. **预检失败归类**（如有失败）— 按原因分组展示，帮助用户快速定位问题
4. 每个已创建任务的 `task_id`
5. 报告查看地址：`{LMETERX_BASE_URL}/http-results/{task_id}`

### 预检失败归类

当存在预检未通过的 API 时，脚本会按失败原因分类输出：

| 分类 | 说明 | 建议 |
|------|------|------|
| 🔐 认证失败 (401) | 目标 API 需要认证 | 检查 Headers 中的 Authorization 或 API Key |
| 🚫 权限不足 (403) | 已认证但无访问权限 | 确认账号权限或 IP 白名单 |
| 🔗 地址无效 (404) | API 路径不存在 | 可能是死链或爬虫抓取了无效地址 |
| ⛔ 方法不允许 (405) | HTTP 方法不匹配 | 检查 GET/POST 等是否正确 |
| ⏳ 请求限流 (429) | 目标 API 限流 | 稍后重试或降低并发 |
| 💥 服务端错误 (5xx) | 目标服务内部异常 | 检查目标服务状态 |
| 🌐 连接失败 | 无法连接目标主机 | 检查 URL 和网络 |
| ⏱ 请求超时 | 目标 API 响应超时 | 检查目标服务是否正常 |
| 🔒 SSL/TLS 错误 | 证书验证失败 | 检查证书配置 |

> 注意：预检阶段会过滤掉目标 API 返回 4xx/5xx 的 URL，只有返回 2xx/3xx 的 API 才会进入后续的压测任务创建。

## 错误处理与用户引导

在任何 API 调用（Step 1 / Step 2 / Step 3）返回异常时，**不要直接报错退出**，而是根据错误类型引导用户排查：

| 错误场景 | 引导提示 |
|---------|---------|
| 连接失败 / 超时 | `LMETERX_BASE_URL` 可能不正确或服务未启动，请用户重新确认地址 |
| HTTP 401 | 认证失效，引导用户重新提供 `LMETERX_AUTH_TOKEN`（参考 Step 0.3） |
| HTTP 403 | 账号无权限，建议用户联系管理员 |
| HTTP 404 | 接口不存在，可能 LMeterX 版本不匹配，建议确认后端版本 |
| HTTP 5xx | 后端服务异常，建议稍后重试或联系管理员 |

## 脚本调用（可选）

如需通过脚本执行：

```bash
python "${SKILL_DIR}/scripts/run.py" --url "https://example.com"
```

```bash
python "${SKILL_DIR}/scripts/run.py" \
  --url "https://example.com" \
  --concurrent-users 80 \
  --duration 600 \
  --spawn-rate 80
```

## 环境变量

- `LMETERX_BASE_URL`（必须）— LMeterX 后端地址，例如 `https://lmeterx.example.com`
- `LMETERX_AUTH_TOKEN`（可选）— Bearer token（启用 LDAP 认证时需要）

> 如果环境变量未配置，Agent 会在对话中引导用户提供（参见 Step 0）。
