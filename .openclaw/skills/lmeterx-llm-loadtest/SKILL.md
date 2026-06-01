---
name: lmeterx-llm-loadtest
emoji: "\U0001F916"
description: |
  LMeterX LLM API Load Test tool. When a user provides an **LLM API endpoint URL**
  (ending with `/v1/chat/completions` or `/v1/messages`) or a curl command targeting
  an LLM API, this skill executes a script to pre-check connectivity and create
  a load testing task. Supports OpenAI-compatible and Claude-compatible APIs.
triggers:
  - 压测这个LLM API
  - 压测这个大模型接口
  - 压测这个模型API
  - 帮我压测 OpenAI
  - 帮我压测 Claude API
  - 压测 chat completions
  - 压测 messages 接口
  - load test this LLM API
  - load test OpenAI endpoint
  - stress test this model API
  - 压测这个AI接口
requires:
  env:
    - LMETERX_BASE_URL
---

# Skill: lmeterx-llm-loadtest

## Intent Routing Rules (Highest Priority)

### When to USE this Skill

- URL ends with `/v1/chat/completions` (OpenAI-compatible)
- URL ends with `/v1/messages` (Claude/Anthropic-compatible)
- User mentions "LLM", "大模型", "模型接口", "OpenAI", "Claude", "chat completions"
- curl command body contains `"model"` and `"messages"` fields

### When NOT to use this Skill

| Condition | Use Instead |
|-----------|------------|
| URL is a webpage (e.g. `https://www.baidu.com`) | `lmeterx-web-loadtest` |
| URL is a regular API without LLM path patterns (e.g. `/api/users`, `/graphql`) | `lmeterx-http-loadtest` |
| User says "网站/网页/页面" | `lmeterx-web-loadtest` |

### Quick Decision Rule

```
URL ends with /v1/chat/completions or /v1/messages → THIS SKILL
URL is a normal webpage                            → lmeterx-web-loadtest
Everything else (REST API, GraphQL, etc.)          → lmeterx-http-loadtest
```

## Execution Rules

1. **Mandatory:** You **must and may only** execute the provided script via Bash.
2. **Prohibition:** Do NOT manually construct HTTP requests using `curl` or `requests` to call LMeterX APIs.
3. **Prohibition:** Do NOT fabricate results. Execute the script and respond based on actual stdout output.

## The Only Correct Way to Execute

### With URL:

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-<YOUR_AUTH_TOKEN>}"
python "${SKILL_DIR}/scripts/run.py" \
  --url "<LLM API URL>" \
  --header "Authorization: Bearer <api-key>"
```

### With curl command:

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-<YOUR_AUTH_TOKEN>}"
python "${SKILL_DIR}/scripts/run.py" \
  --curl '<full curl command>'
```

### With custom load parameters:

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-<YOUR_AUTH_TOKEN>}"
python "${SKILL_DIR}/scripts/run.py" \
  --url "<LLM API URL>" \
  --header "Authorization: Bearer <api-key>" \
  --body '{"model":"gpt-4","messages":[{"role":"user","content":"Hello"}]}' \
  --concurrent-users 50 \
  --duration 300 \
  --spawn-rate 30
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--url` | (required, or use --curl) | LLM API endpoint URL |
| `--curl` | (required, or use --url) | Full curl command string |
| `--header` | [] | Request header (repeatable, format: `Key: Value`) |
| `--body` | "" | Request body JSON string |
| `--model` | (auto-extracted from body) | Model name |
| `--stream` / `--no-stream` | true | Enable/disable streaming |
| `--concurrent-users` | 50 | Concurrent users (1-5000) |
| `--duration` | 300 | Duration in seconds (1-172800) |
| `--spawn-rate` | 30 | User spawn rate |
| `--name` | (auto-generated) | Task name |
| `--test-data` | "" | Dataset: `""` for none, `"default"` for built-in dataset |

## Presenting Results to the User

After execution, present:

1. **API Type:** OpenAI Chat or Claude Chat
2. **Pre-check Result:** Pass/Fail with categorized failure reason
3. **Task ID and Report URL:** `{LMETERX_BASE_URL}/results/{task_id}`

## Exception Handling

| Error Scenario | Output Message |
|---------|---------|
| HTTP 401/403 | LMeterX token is invalid or expired; check `LMETERX_AUTH_TOKEN` |
| HTTP 5xx | LMeterX platform service error; try again later |
| Connection Failure | Cannot connect to LMeterX service; check network |
| Target API 401 | Target LLM API requires auth; check Authorization header |
| Target API timeout | Target LLM API timed out; may be overloaded |
