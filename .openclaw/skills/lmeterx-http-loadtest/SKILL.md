---
name: lmeterx-http-loadtest
emoji: "\U0001F310"
description: |
  LMeterX HTTP API Load Test tool. When a user provides a **business/regular API endpoint URL**
  or a curl command targeting a non-LLM HTTP API, this skill executes a script to pre-check
  connectivity and create a load testing task. For REST APIs, GraphQL, and any HTTP endpoints
  that are NOT LLM model APIs.
triggers:
  - 压测这个API
  - 压测这个接口
  - 压测这个端点
  - 帮我压测这个API接口
  - 压测这个 curl
  - 帮我压测这个HTTP接口
  - 压测这个REST API
  - 帮我压测这个业务接口
  - load test this API
  - load test this endpoint
  - stress test this curl
  - load test this HTTP API
requires:
  env:
    - LMETERX_BASE_URL
---

# Skill: lmeterx-http-loadtest

## Intent Routing Rules (Highest Priority)

### When to USE this Skill

- User provides a regular HTTP API URL (e.g. `https://api.example.com/users`, `https://app.com/api/orders`)
- User provides a curl command targeting a business API
- URL contains paths like `/api/`, `/graphql`, `/v2/`, `/rest/` etc. (but NOT `/v1/chat/completions` or `/v1/messages`)
- User says "压测这个API/接口/端点" and the URL is NOT an LLM endpoint

### When NOT to use this Skill

| Condition | Use Instead |
|-----------|------------|
| URL ends with `/v1/chat/completions` or `/v1/messages` | `lmeterx-llm-loadtest` |
| User mentions "LLM", "大模型", "OpenAI", "Claude" | `lmeterx-llm-loadtest` |
| URL is a webpage (e.g. `https://www.baidu.com`) | `lmeterx-web-loadtest` |
| User says "网站/网页/页面" | `lmeterx-web-loadtest` |

### Quick Decision Rule

```
URL ends with /v1/chat/completions or /v1/messages → lmeterx-llm-loadtest
URL is a normal webpage (HTML page for browsers)   → lmeterx-web-loadtest
Everything else (REST/GraphQL/business API)        → THIS SKILL
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
  --url "<API URL>" \
  --method GET
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
  --url "<API URL>" \
  --method POST \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --body '{"key": "value"}' \
  --concurrent-users 100 \
  --duration 600 \
  --spawn-rate 50
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--url` | (required, or use --curl) | API endpoint URL |
| `--curl` | (required, or use --url) | Full curl command string |
| `--method` | POST (auto: POST if body, else GET) | HTTP method |
| `--header` | [] | Request header (repeatable, format: `Key: Value`) |
| `--body` | "" | Request body string |
| `--cookie` | [] | Cookie (repeatable, format: `Key=Value`) |
| `--concurrent-users` | 50 | Concurrent users (1-5000) |
| `--duration` | 300 | Duration in seconds (1-172800) |
| `--spawn-rate` | 30 | User spawn rate |
| `--name` | (auto-generated) | Task name |

## Presenting Results to the User

After execution, present:

1. **Target Info:** Method + URL
2. **Pre-check Result:** Pass/Fail with categorized failure reason
3. **Task ID and Report URL:** `{LMETERX_BASE_URL}/http-results/{task_id}`

## Exception Handling

| Error Scenario | Output Message |
|---------|---------|
| HTTP 401/403 | LMeterX token is invalid or expired; check `LMETERX_AUTH_TOKEN` |
| HTTP 5xx | LMeterX platform service error; try again later |
| Connection Failure | Cannot connect to LMeterX service; check network |
| Target API 401 | Target API requires auth; check Authorization header |
| Target API 404 | Target API path not found; check URL |
| Target API timeout | Target API timed out; check target service status |
