---
name: lmeterx-web-loadtest
description: "对网站/网页执行压力测试，自动分析页面 API、预检连通性并批量创建 LMeterX 压测任务。输入浏览器可访问的网页 URL 即可。"
allowed_tools:
  - Bash
  - Read
triggers:
  - /web-loadtest
  - /lmeterx-web
  - /压测网站
---

# 网站压测 (lmeterx-web-loadtest)

对网站/网页执行负载测试。自动分析页面发现 API 接口，批量预检并创建压测任务。

## 路由规则

### 使用本 Skill：
- 用户提供网站/网页 URL（如 `https://www.baidu.com`、`https://example.com/dashboard`）
- 用户提到 "网站"、"网页"、"页面"、"website"、"webpage"
- URL 是浏览器可直接访问的 HTML 页面

### 不要使用本 Skill：
| 场景 | 应使用 |
|------|--------|
| URL 以 `/v1/chat/completions` 或 `/v1/messages` 结尾 | `/llm-loadtest` |
| URL 是具体 API 端点（如 `/api/users`） | `/http-loadtest` |
| 用户提供 curl 命令 | `/http-loadtest` 或 `/llm-loadtest` |

## 执行方式

**必须通过 Bash 执行脚本，禁止手动构造 HTTP 请求。**

### 基本用法：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-web-loadtest/scripts/run.py \
  --url "<网页 URL>"
```

### 自定义参数：

```bash
export LMETERX_AUTH_TOKEN="${LMETERX_AUTH_TOKEN:-lmeterx}"
python ~/.claude/skills/lmeterx-web-loadtest/scripts/run.py \
  --url "<网页 URL>" \
  --concurrent-users 80 \
  --duration 600 \
  --spawn-rate 80
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--url` | (必填) | 目标网页 URL |
| `--concurrent-users` | 10 | 并发用户数 (1-5000) |
| `--duration` | 300 | 持续时间/秒 |
| `--spawn-rate` | 10 | 用户生成速率 |

## 内部工作流（自动执行，无需手动干预）

脚本自动完成 3 个步骤：
1. **页面分析** — `POST /api/skills/analyze-url` 发现页面中的 API
2. **连通性预检** — `POST /api/http-tasks/test` 检查每个 API
3. **创建任务** — `POST /api/http-tasks` 批量创建压测任务

## 结果输出

执行完成后向用户报告：
1. **概览**：发现的 API 数量、预检通过/失败数
2. **失败分类**：按原因分类（401、404、5xx 等）
3. **Task ID 及报告地址**：每个任务的 `{LMETERX_BASE_URL}/http-results/{task_id}`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LMETERX_BASE_URL` | `https://lmeterx.openxlab.org.cn` | LMeterX 后端地址 |
| `LMETERX_AUTH_TOKEN` | `lmeterx` | Service Token（X-Authorization 头） |
