# LMeterX Skills — MCP Server

薄层 MCP 集成，核心逻辑由 LMeterX Backend 提供。

## 架构

```
skills/              ← MCP Server（Claude Code / OpenClaw 集成）
  mcp_server.py      ← JSON-RPC stdio server，调用 Backend API

.openclaw/skills/    ← OpenClaw 标准技能目录
  run-web-loadtest/
  fetch-loadtest-results/

backend/             ← 核心逻辑
  api/api_skill.py   ← POST /api/skills/analyze-url
  service/skill_service.py ← Playwright 分析 + LLM 配置生成
```

## 依赖的 Backend API

| API | 用途 |
|-----|------|
| `POST /api/skills/analyze-url` | 分析网页 URL，发现 API，生成压测配置 |
| `POST /api/common-tasks/test` | 测试 API 连通性 |
| `POST /api/common-tasks` | 创建压测任务 |

## 环境变量

- `LMETERX_BASE_URL` — Backend 地址（默认 `http://localhost:5001`）
- `LMETERX_AUTH_TOKEN` — Bearer token（LDAP 环境需要）
