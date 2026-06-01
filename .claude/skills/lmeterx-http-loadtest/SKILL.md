---
name: lmeterx-http-loadtest
description: "对业务 HTTP API（REST/GraphQL 等）执行压力测试，自动预检连通性并创建 LMeterX 压测任务。适用于非 LLM、非网页的普通 API 接口。"
allowed_tools:
  - Bash
  - Read
triggers:
  - /http-loadtest
  - /lmeterx-http
  - /压测API
---

# HTTP 业务 API 压测 (lmeterx-http-loadtest)

对普通业务 HTTP API 端点执行负载测试。支持 REST、GraphQL 和任何非 LLM 的 HTTP 接口。

## 路由规则

### 使用本 Skill：
- 用户提供了普通 HTTP API URL（如 `/api/users`、`/api/orders`、`/graphql`）
- 用户提供了针对业务 API 的 curl 命令
- URL 不是 LLM 端点也不是浏览器网页

### 不要使用本 Skill：
| 场景 | 应使用 |
|------|--------|
| URL 以 `/v1/chat/completions` 或 `/v1/messages` 结尾 | `/llm-loadtest` |
| 用户提到 "LLM"、"大模型"、"OpenAI"、"Claude" | `/llm-loadtest` |
| URL 是网页（如 `https://www.baidu.com`） | `/web-loadtest` |
| 用户说 "网站/网页/页面" | `/web-loadtest` |

## 执行方式

**必须通过 Bash 执行脚本，禁止手动构造 HTTP 请求。**

### URL 模式：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-http-loadtest/scripts/run.py \
  --url "<API URL>" \
  --method GET
```

### curl 模式：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-http-loadtest/scripts/run.py \
  --curl '<完整 curl 命令>'
```

### POST 带请求体：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-http-loadtest/scripts/run.py \
  --url "<API URL>" \
  --method POST \
  --header "Authorization: Bearer <token>" \
  --body '{"key": "value"}' \
  --concurrent-users 100 \
  --duration 600 \
  --spawn-rate 50
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--url` | (必填，或用 --curl) | API 端点 URL |
| `--curl` | (必填，或用 --url) | 完整 curl 命令字符串 |
| `--method` | POST(有body)/GET(无body) | HTTP 方法 |
| `--header` | [] | 请求头（可重复，格式 `Key: Value`） |
| `--body` | "" | 请求体字符串 |
| `--cookie` | [] | Cookie（可重复，格式 `Key=Value`） |
| `--concurrent-users` | 50 | 并发用户数 (1-5000) |
| `--duration` | 300 | 持续时间/秒 (1-172800) |
| `--spawn-rate` | 30 | 用户生成速率 |
| `--name` | (自动生成) | 任务名称 |

## 结果输出

执行完成后向用户报告：
1. **目标信息**：Method + URL
2. **预检结果**：通过/失败及分类原因
3. **Task ID 及报告地址**：`{LMETERX_BASE_URL}/http-results/{task_id}`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LMETERX_BASE_URL` | `<YOUR_LMETERX_BASE_URL>` | LMeterX 后端地址 |
| `LMETERX_AUTH_TOKEN` | `<YOUR_AUTH_TOKEN>` | Service Token（X-Authorization 头） |
