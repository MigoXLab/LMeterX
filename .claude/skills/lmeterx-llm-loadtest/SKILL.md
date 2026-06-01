---
name: lmeterx-llm-loadtest
description: "对 LLM API（OpenAI/Claude 兼容接口）执行压力测试，自动预检连通性并创建 LMeterX 压测任务。URL 必须以 /v1/chat/completions 或 /v1/messages 结尾。"
allowed_tools:
  - Bash
  - Read
triggers:
  - /llm-loadtest
  - /lmeterx-llm
  - /压测LLM
---

# LLM API 压测 (lmeterx-llm-loadtest)

对 LLM API 端点执行负载测试。支持 OpenAI 兼容 (`/v1/chat/completions`) 和 Claude 兼容 (`/v1/messages`) 接口。

## 路由规则

### 使用本 Skill：
- URL 以 `/v1/chat/completions` 结尾（OpenAI 兼容）
- URL 以 `/v1/messages` 结尾（Claude/Anthropic 兼容）
- 用户提到 "LLM"、"大模型"、"OpenAI"、"Claude"、"chat completions"

### 不要使用本 Skill：
| 场景 | 应使用 |
|------|--------|
| URL 是网页（如 `https://www.baidu.com`） | `/web-loadtest` |
| URL 是普通 API（如 `/api/users`、`/graphql`） | `/http-loadtest` |
| 用户说 "网站/网页/页面" | `/web-loadtest` |

## 执行方式

**必须通过 Bash 执行脚本，禁止手动构造 HTTP 请求。**

获取用户提供的 LLM API URL 或 curl 命令后，在 Bash 中执行：

### URL 模式：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-llm-loadtest/scripts/run.py \
  --url "<LLM API URL>" \
  --header "Authorization: Bearer <api-key>" \
  --body '{"model":"gpt-4","messages":[{"role":"user","content":"Hello"}]}'
```

### curl 模式：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-llm-loadtest/scripts/run.py \
  --curl '<完整 curl 命令>'
```

### 自定义负载参数：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-llm-loadtest/scripts/run.py \
  --url "<LLM API URL>" \
  --header "Authorization: Bearer <api-key>" \
  --body '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}' \
  --concurrent-users 50 \
  --duration 300 \
  --spawn-rate 30
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--url` | (必填，或用 --curl) | LLM API 端点 URL |
| `--curl` | (必填，或用 --url) | 完整 curl 命令字符串 |
| `--header` | [] | 请求头（可重复，格式 `Key: Value`） |
| `--body` | "" | 请求体 JSON 字符串 |
| `--model` | (自动从 body 提取) | 模型名称 |
| `--stream` / `--no-stream` | true | 流式模式 |
| `--concurrent-users` | 50 | 并发用户数 (1-5000) |
| `--duration` | 300 | 持续时间/秒 (1-172800) |
| `--spawn-rate` | 30 | 用户生成速率 |
| `--name` | (自动生成) | 任务名称 |
| `--test-data` | "" | 数据集：`""` 不使用数据集，`"default"` 使用内置默认数据集 |

## 结果输出

执行完成后向用户报告：
1. **API 类型**：OpenAI Chat 或 Claude Chat
2. **预检结果**：通过/失败及分类原因
3. **Task ID 及报告地址**：`{LMETERX_BASE_URL}/results/{task_id}`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LMETERX_BASE_URL` | `https://lmeterx.openxlab.org.cn` | LMeterX 后端地址 |
| `LMETERX_AUTH_TOKEN` | `lmeterx` | Service Token（X-Authorization 头） |
