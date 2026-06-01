# LMeterX Claude Code Skills 安装指南

## 概述

本项目提供三个 Claude Code Skills，用于通过自然语言驱动 LMeterX 平台执行压力测试：

| Skill | 斜杠命令 | 用途 |
|-------|---------|------|
| `lmeterx-llm-loadtest` | `/llm-loadtest` | LLM API 压测（OpenAI/Claude 兼容） |
| `lmeterx-http-loadtest` | `/http-loadtest` | 业务 HTTP API 压测（REST/GraphQL） |
| `lmeterx-web-loadtest` | `/web-loadtest` | 网站/网页压测（自动分析页面 API） |

## 前置条件

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) 已安装
- Python 3.8+（脚本会自动安装 `httpx` 依赖，无需手动安装）

## 安装步骤

### Step 1: 复制 Skills 到全局目录

```bash
# 从项目根目录执行
cp -r .claude/skills/lmeterx-llm-loadtest  ~/.claude/skills/
cp -r .claude/skills/lmeterx-http-loadtest  ~/.claude/skills/
cp -r .claude/skills/lmeterx-web-loadtest   ~/.claude/skills/
```

安装后的目录结构：

```
~/.claude/skills/
├── lmeterx-llm-loadtest/
│   ├── SKILL.md
│   └── scripts/run.py
├── lmeterx-http-loadtest/
│   ├── SKILL.md
│   └── scripts/run.py
└── lmeterx-web-loadtest/
    ├── SKILL.md
    └── scripts/run.py
```

### Step 2: 配置权限

在 `~/.claude/settings.local.json` 的 `permissions.allow` 数组中添加以下条目：

```json
{
  "permissions": {
    "allow": [
      "Bash(python ~/.claude/skills/lmeterx-llm-loadtest/scripts/run.py*)",
      "Bash(python ~/.claude/skills/lmeterx-http-loadtest/scripts/run.py*)",
      "Bash(python ~/.claude/skills/lmeterx-web-loadtest/scripts/run.py*)",
      "Bash(export LMETERX_AUTH_TOKEN*)"
    ]
  }
}
```

> 如果文件已有其他 permissions，将上述条目追加到 `allow` 数组末尾即可。

### Step 3: 配置环境变量（可选）

Skills 内置了默认值，可直接使用。如需自定义，在 shell 配置文件（`~/.bashrc` 或 `~/.zshrc`）中添加：

```bash
export LMETERX_BASE_URL="<YOUR_LMETERX_BASE_URL>"  # LMeterX 后端地址
export LMETERX_AUTH_TOKEN="<YOUR_AUTH_TOKEN>"       # Service Token
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LMETERX_BASE_URL` | `<YOUR_LMETERX_BASE_URL>` | LMeterX 后端地址 |
| `LMETERX_AUTH_TOKEN` | `<YOUR_AUTH_TOKEN>` | Service Token，通过 `X-Authorization` 头传递 |

## 验证安装

重启 Claude Code 后，输入 `/llm-loadtest`、`/http-loadtest` 或 `/web-loadtest` 即可验证 Skills 是否正常加载。

也可以运行以下命令验证脚本（首次运行会自动安装 `httpx` 依赖到脚本本地 `.deps/` 目录）：

```bash
python ~/.claude/skills/lmeterx-llm-loadtest/scripts/run.py --help
python ~/.claude/skills/lmeterx-http-loadtest/scripts/run.py --help
python ~/.claude/skills/lmeterx-web-loadtest/scripts/run.py --help
```

## 使用示例

### LLM API 压测

```
/llm-loadtest 压测这个接口，并发10，持续5分钟：
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}'
```

### 业务 HTTP API 压测

```
/http-loadtest 并发50压测10分钟：
curl -X GET https://api.example.com/users \
  -H "Authorization: Bearer token123"
```

### 网站压测

```
/web-loadtest 帮我压测这个网站，并发20：https://example.com
```

## 路由规则

当用户请求压测时，根据以下规则选择 Skill：

```
URL 以 /v1/chat/completions 或 /v1/messages 结尾 → /llm-loadtest
URL 是浏览器可访问的普通网页                      → /web-loadtest
其他 API 端点（REST/GraphQL/curl 命令）           → /http-loadtest
```

## 卸载

```bash
rm -rf ~/.claude/skills/lmeterx-llm-loadtest
rm -rf ~/.claude/skills/lmeterx-http-loadtest
rm -rf ~/.claude/skills/lmeterx-web-loadtest
```

并从 `~/.claude/settings.local.json` 中移除对应的权限条目。
