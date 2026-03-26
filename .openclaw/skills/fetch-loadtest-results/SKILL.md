---
name: fetch-loadtest-results
emoji: 📊
description: |
  获取 LMeterX 压测报告：根据 task_id 和任务类型，
  输出报告页面地址和核心性能指标。
triggers:
  - 获取压测结果
  - 查看压测报告
  - get loadtest results
  - show performance report
  - 压测报告
requires:
  env:
    - LMETERX_BASE_URL
---

# Skill: fetch-loadtest-results

## 用途

根据 task_id 获取压测报告页面地址和核心性能指标。

## 报告地址规则

| 任务类型 | 报告页面 URL |
|---------|-------------|
| 业务 API | `{LMETERX_BASE_URL}/http-results/{task_id}` |
| LLM API | `{LMETERX_BASE_URL}/results/{task_id}` |

## Step 0 — 环境配置检查与引导

在生成报告地址或调用 API 前，**必须**先完成以下检查：

### 0.1 检查 `LMETERX_BASE_URL`

- 如果环境变量 `LMETERX_BASE_URL` 已设置 → 使用该值
- 如果**未设置** → 立即询问用户：

> ⚙️ 尚未配置 LMeterX 服务地址。请提供你的 LMeterX 后端 URL，例如：`https://lmeterx.example.com`

用户回复后，将其作为 `{LMETERX_BASE_URL}` 用于报告地址生成和 API 调用。

### 0.2 验证后端连通性（当需要调用 API 获取性能数据时）

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

### 0.3 检查认证状态（当需要调用 API 获取性能数据时）

```
GET {LMETERX_BASE_URL}/api/auth/profile
Authorization: Bearer <LMETERX_AUTH_TOKEN>
```

| 响应 | 处理 |
|------|------|
| 200 且用户名非 `anonymous` | ✅ 认证通过，继续 |
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

---

## 获取性能数据（可选）

> 以下 API 调用都需要在请求头中附带 `Authorization: Bearer <LMETERX_AUTH_TOKEN>`（如已配置）。

### 查询任务状态

```
GET {LMETERX_BASE_URL}/api/http-tasks/{task_id}       # 普通 HTTP 任务
GET {LMETERX_BASE_URL}/api/llm-tasks/{task_id}               # LLM 任务
```

**响应包含**：`status`（pending / running / completed / failed）、`name`、`target_url`、`concurrent_users`、`duration` 等。

### 获取性能结果

```
GET {LMETERX_BASE_URL}/api/http-tasks/{task_id}/results    # 业务API 任务
GET {LMETERX_BASE_URL}/api/llm-tasks/{task_id}/results           # LLM 任务
```

**响应示例**：

```json
{
  "results": [
    {
      "metric_type": "Total",
      "request_count": 15000,
      "failure_count": 12,
      "rps": 50.0,
      "avg_response_time": 180.5,
      "median_response_time": 160.0,
      "percentile_95_response_time": 350.0,
      "min_response_time": 20.0,
      "max_response_time": 1200.0
    }
  ]
}
```

**取 `metric_type == "Total"` 的行**作为汇总指标。

### 性能评级参考

| 指标 | 🟢 良好 | 🟡 一般 | 🔴 偏低/偏高 |
|------|---------|---------|-------------|
| TPS/QPS | ≥ 100 | 10–100 | < 10 |
| 平均响应 | ≤ 200ms | 200–1000ms | > 1000ms |
| 错误率 | 0% | < 1% | ≥ 1% |

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| task_id | ✅ | 压测任务 ID |
| task_type | — | `http`（默认）或 `llm`，决定 API 路径前缀 |

## 错误处理与用户引导

在 API 调用返回异常时，根据错误类型引导用户排查：

| 错误场景 | 引导提示 |
|---------|---------|
| 连接失败 / 超时 | `LMETERX_BASE_URL` 可能不正确或服务未启动，请用户重新确认地址 |
| HTTP 401 | 认证失效，引导用户重新提供 `LMETERX_AUTH_TOKEN`（参考 Step 0.3） |
| HTTP 404 | task_id 不存在或任务类型（http/llm）不匹配，引导用户确认 |
| HTTP 5xx | 后端服务异常，建议稍后重试 |

## 脚本调用（可选）

```bash
python "${SKILL_DIR}/scripts/fetch.py" --task-id "your-task-id"
```

```bash
python "${SKILL_DIR}/scripts/fetch.py" --task-id "your-task-id" --task-type llm
```

```bash
python "${SKILL_DIR}/scripts/fetch.py" --batch-id "batch_xxx"
```

## 环境变量

- `LMETERX_BASE_URL`（必须）— LMeterX 后端地址，例如 `https://lmeterx.example.com`
- `LMETERX_AUTH_TOKEN`（可选）— Bearer token（启用 LDAP 认证时需要）

> 如果环境变量未配置，Agent 会在对话中引导用户提供（参见 Step 0）。
