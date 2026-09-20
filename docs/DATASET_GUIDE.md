# 数据集使用指南 / Dataset Usage Guide

[中文](#中文) | [English](#english)

---

## 中文

### 概述

LMeterX 的压测任务通过 **UTF-8 JSONL**（每行一个 JSON 对象）提供测试数据。数据集可在「数据集」库中复用，也可在创建任务时上传或粘贴。

任务类型与数据集类型必须匹配：

| 任务类型 | 数据集类型 | 每行含义 |
| --- | --- | --- |
| LLM API | `llm` | 提示词 / 消息列表，或完整请求体（取决于 API 类型） |
| 通用 HTTP API | `business` | 完整 HTTP 请求体 |
| Agent A2A | `a2a` | 绑定到已配置场景的 A2A `message` |
| Agent MCP | `mcp` | 绑定到已配置场景的工具 `arguments` |


创建任务时的数据来源：

- **系统数据集**：从数据集库选择（公开或本人私有）
- **上传数据集**：本次任务专用文件
- **自定义 JSONL 数据**（仅 LLM）：在表单中直接粘贴若干行
- **不使用数据集**：全程使用任务里配置的原始请求体 / 场景

系统预置公开数据集 **ShareGPT V3 Partial**（`ShareGPT_V3_partial.jsonl`）可用于 LLM 文本压测。

---

## LLM API 压测数据集

统一要求：UTF-8，每行一个 JSON 对象；空行忽略。`id` 建议填写；省略时引擎用行号。字段优先级（解析提示词时）：`prompt` > `messages` > Responses 的 `input`。

构造实际请求时：

- 存在 `messages`：用该数组**整体替换**请求中的 `messages`（Responses 则写入 `input`）
- 否则用 `prompt` **替换**模板里的用户消息（Responses 写入 `input`）
- 可选 `system_prompt`（字符串）：OpenAI Chat 替换 / 插入 `role=system` 消息；Claude Chat 写入顶层 `system`
- `prompt` 与 `messages` 同时存在时，**请求以 `messages` 为准**，`prompt` 仍可用于指标展示

### OpenAI Chat / Claude Chat

推荐两种行格式（可在同一文件中混用）：

```jsonl
{"id":"00132c2b","system_prompt":"You are PR-Reviewer.","prompt":"You are given a Pull Request (PR) code diff:"}
{"id":"2","system_prompt":"Review the follow-up","messages":[{"role":"user","content":"Check this code"},{"role":"assistant","content":"Please send the diff"},{"role":"user","content":"Here is the diff"}]}
```

字段说明：

- `id`：建议填写
- `prompt`：无 `messages` 时作为用户提示词；可为字符串、字符串数组（取首项）或对象（序列化为 JSON 字符串）
- `messages`：OpenAI 风格消息数组，替换整个对话
- `system_prompt`：可选，单独替换 system
- `image` / `image_path`：可选，图片 URL、本地路径，或路径数组（取第一项）

### OpenAI Responses

继续使用 `prompt`，或提供字符串 `input`、`messages` 列表：

```jsonl
{"id":"1","prompt":"解释什么是 TTFT"}
{"id":"2","input":"给出三个性能优化建议"}
{"id":"3","messages":[{"role":"user","content":"Hello!"}]}
```

引擎把每行内容写入请求的 `input`，并保留任务里的 `model`、`stream` 等参数。`messages` 会原样写入 `input`；ShareGPT 行只会抽出用户提示词。Responses **不会**应用 `system_prompt`。

### 自定义 Chat / Embeddings

每行必须是**完整请求体**，将替换任务中填写的请求 JSON（不再按 `prompt` 局部改写）：

```jsonl
{"model":"custom-chat-model","stream":true,"messages":[{"role":"user","content":"Hello, how are you?"}]}
{"model":"text-embedding-3-small","input":"What is artificial intelligence?"}
```

### 图片

Chat / Responses 数据集可通过 `image` 或 `image_path` 携带图片。本地路径需在引擎容器内可读。Embeddings、自定义 Chat 不处理图片字段。

在 `docker-compose.yml` 中挂载图片目录，例如：

```yaml
services:
  engine:
    volumes:
      - ./logs:/logs
      - ./upload_files:/app/upload_files
      - ./data:/app/data
```

将图片放到 `./data`，路径需与数据集字段一致，然后重启服务。图片在发请求时按路径懒加载编码，过大或过多会影响性能。

### 使用步骤

1. 准备 `.jsonl`（或 LLM 任务临时上传的 ShareGPT `.json` 数组）
2. 如需本地图片，配置挂载后重启
3. 打开「LLM API」创建任务，数据集来源选择库内数据集、上传或粘贴 JSONL
4. 数据集类型须为 LLM；完成其余配置后启动

---

## 通用 HTTP API 压测数据集

仅支持 JSONL。每行是一个**完整 payload 对象**，直接作为 HTTP 请求体；任务中填写的 body 仅在不使用数据集时生效。

```jsonl
{"model":"gpt-5.2","messages":[{"role":"user","content":"你好"}],"max_tokens":128}
{"model":"gpt-5.2","messages":[{"role":"user","content":"介绍一下机器学习"}],"max_tokens":256}
```

说明：

- 结构由目标 API 决定，系统不做业务字段校验
- 不支持 JSON 数组文件，不处理图片字段
- 按行轮询使用
- 某行 JSON 解析失败时，引擎会尝试把该行当纯文本发送

使用步骤：在「通用 API」填写 URL、方法、Headers；需要变化请求体时选择数据集并上传 / 选用 `business` 类型 JSONL。

---

## Agent A2A 数据集

每行绑定一个已在任务中配置的场景。**禁止**出现未声明字段；权重写在场景上，不要写在数据集行里。

必填：`id`、`scenario_id`、`message`。

- `scenario_id` 必须等于某个已配置场景的 `id`
- `message.role` 必须为 `ROLE_USER`（可省略，默认即此值）
- `message.parts` 非空；每个 part 有且仅有 `text`、`data`、`raw`、`url` 之一
- 数据集必须覆盖任务里**全部**已配置场景，至少各有一行

```jsonl
{"id":"order-10001","scenario_id":"order","message":{"role":"ROLE_USER","parts":[{"text":"处理订单 10001"}]}}
{"id":"order-10002","scenario_id":"order","message":{"role":"ROLE_USER","parts":[{"text":"处理订单 10002"}]}}
```

同一 `scenario_id` 的多行会在该场景被抽中时轮询。

---

## Agent MCP 数据集

每行绑定一个已配置的 `tools/call` 场景。**禁止**未声明字段；不要在行内写 `weight`。

必填：`id`、`scenario_id`；`arguments` 为对象，可为 `{}`。

- `scenario_id` 必须等于某个已配置场景的 `id`
- 必须覆盖任务里全部场景

```jsonl
{"id":"weather-shanghai","scenario_id":"weather","arguments":{"city":"上海"}}
{"id":"weather-beijing","scenario_id":"weather","arguments":{"city":"北京"}}
```

---

## 注意事项

### 数据集库

- 仅 `.jsonl`；入库时校验每行是 JSON 对象，**不**按任务类型校验业务字段
- 类型（LLM / 业务 / A2A / MCP）决定哪些任务能选用
- 私有仅创建人可见；公开可供他人创建任务；系统预置集不可改、不可删、不可下载

### LLM

- Chat：有 `messages` 替换整段对话，否则用 `prompt` 替换用户消息；`system_prompt` 单独替换 system
- 自定义 Chat / Embeddings：每行即完整请求体
- 本地图片必须先挂载

### 通用 HTTP

- 仅 JSONL；每行完整请求体；解析失败则尝试纯文本

### Agent

- 行内字段集合固定，多写即校验失败
- `scenario_id` 未知或有场景未被覆盖时，任务无法创建

---

## 示例文件

- LLM 文本：系统预置 `ShareGPT_V3_partial.jsonl`（`id` + `prompt`）
- HTTP：见上文完整请求体示例
- A2A / MCP：见上文场景绑定示例

---

## 问题排查

### 图片无法加载

1. 检查 Docker 挂载
2. 确认路径与 `image` / `image_path` 一致，且容器内文件存在
3. 查看引擎日志：`docker-compose logs engine`

### 数据集未生效

**LLM**：检查 JSONL；Chat 行需有 `prompt` 或 `messages`；自定义 / Embeddings 行须为完整对象。

**HTTP**：检查每行是否为对象；确认任务选用了数据集且方法带 body。

**A2A / MCP**：检查必填字段、`ROLE_USER` / `parts`、`arguments` 为对象、`scenario_id` 覆盖全部场景、无多余字段。

---

## English

### Overview

LMeterX load-test tasks consume **UTF-8 JSONL** (one JSON object per line). Datasets can live in the dataset library or be uploaded / pasted when creating a task.

Task type and dataset type must match:

| Task type | Dataset type | Meaning of each row |
| --- | --- | --- |
| LLM API | `llm` | Prompt / messages, or a full request body (depends on API type) |
| General HTTP API | `business` | Full HTTP request body |
| Agent A2A | `a2a` | An A2A `message` bound to a configured scenario |
| Agent MCP | `mcp` | Tool `arguments` bound to a configured scenario |

Dataset sources when creating a task:

- **System dataset**: public or owned private datasets
- **Upload**: task-scoped file
- **Custom JSONL** (LLM only): paste rows in the form
- **No dataset**: use the configured request body / scenarios only

The bundled public dataset **ShareGPT V3 Partial** (`ShareGPT_V3_partial.jsonl`) is LLM text data in `{"id","prompt"}` form.

---

## LLM API datasets

UTF-8, one object per line; blank lines are skipped. `id` is recommended; the engine falls back to the line number. Prompt extraction order: `prompt` > `messages` > Responses `input`.

When building the request:

- If `messages` is present, it **replaces** the request `messages` array (Responses: written to `input`)
- Otherwise `prompt` **replaces** the template user message (Responses: `input`)
- Optional string `system_prompt`: OpenAI Chat replaces/inserts a `system` message; Claude Chat sets top-level `system`
- If both `prompt` and `messages` exist, the **request uses `messages`**; `prompt` may still be used for metrics

### OpenAI Chat / Claude Chat

Two recommended row shapes (they may be mixed in one file):

```jsonl
{"id":"00132c2b","system_prompt":"You are PR-Reviewer.","prompt":"You are given a Pull Request (PR) code diff:"}
{"id":"2","system_prompt":"Review the follow-up","messages":[{"role":"user","content":"Check this code"},{"role":"assistant","content":"Please send the diff"},{"role":"user","content":"Here is the diff"}]}
```

Fields:

- `id`: recommended
- `prompt`: user text when `messages` is absent; string, string array (first item), or object (JSON-serialized)
- `messages`: OpenAI-style array replacing the whole conversation
- `system_prompt`: optional system replacement
- `image` / `image_path`: optional URL, local path, or path array (first item)

### OpenAI Responses

Use `prompt`, a string `input`, or a `messages` list:

```jsonl
{"id":"1","prompt":"Explain what TTFT means."}
{"id":"2","input":"Give three performance tuning tips."}
{"id":"3","messages":[{"role":"user","content":"Hello!"}]}
```

Each row is written to request `input`; task options such as `model` and `stream` are kept. A `messages` list is copied to `input`; ShareGPT rows are reduced to the extracted user prompt. `system_prompt` is **not** applied for Responses.

### Custom Chat / Embeddings

Each line must be a **full request body** and **replaces** the task JSON (no partial `prompt` rewrite):

```jsonl
{"model":"custom-chat-model","stream":true,"messages":[{"role":"user","content":"Hello, how are you?"}]}
{"model":"text-embedding-3-small","input":"What is artificial intelligence?"}
```

### Images

Chat / Responses rows may include `image` or `image_path`. Local files must be readable in the engine container. Embeddings and custom Chat ignore image fields.

Mount image directories in `docker-compose.yml`, for example:

```yaml
services:
  engine:
    volumes:
      - ./logs:/logs
      - ./upload_files:/app/upload_files
      - ./data:/app/data
```

Place files under `./data` so paths match the dataset, then restart. Images are encoded lazily at request time; large or numerous files hurt performance.

### Usage

1. Prepare `.jsonl` (or a temporary ShareGPT `.json` array for LLM upload)
2. Mount local images if needed and restart
3. Create an LLM task; pick a library dataset, upload, or paste JSONL
4. Dataset type must be LLM; configure the rest and start

---

## General HTTP API datasets

JSONL only. Each line is a **complete payload object** sent as the HTTP body. The form body is used only when no dataset is selected.

```jsonl
{"model":"gpt-5.2","messages":[{"role":"user","content":"Hello"}],"max_tokens":128}
{"model":"gpt-5.2","messages":[{"role":"user","content":"Introduce machine learning"}],"max_tokens":256}
```

Notes:

- Any JSON object shape your API needs
- No JSON-array files; no image handling
- Rows are used round-robin
- If a line fails JSON parse, the engine tries sending it as plain text

Usage: on the General API tab, set URL, method, and headers; select a `business` JSONL dataset when the body should vary.

---

## Agent A2A datasets

Each row binds to a scenario already configured on the task. **No extra fields**; put weights on scenarios, not dataset rows.

Required: `id`, `scenario_id`, `message`.

- `scenario_id` must equal a configured scenario `id`
- `message.role` must be `ROLE_USER` (default if omitted)
- `message.parts` must be non-empty; each part has exactly one of `text`, `data`, `raw`, `url`
- The file must cover **every** configured scenario with at least one row

```jsonl
{"id":"order-10001","scenario_id":"order","message":{"role":"ROLE_USER","parts":[{"text":"Process order 10001"}]}}
{"id":"order-10002","scenario_id":"order","message":{"role":"ROLE_USER","parts":[{"text":"Process order 10002"}]}}
```

Multiple rows for the same `scenario_id` rotate when that scenario is selected.

---

## Agent MCP datasets

Each row binds to a configured `tools/call` scenario. **No extra fields**; do not set `weight` on the row.

Required: `id`, `scenario_id`; `arguments` is an object and may be `{}`.

- `scenario_id` must equal a configured scenario `id`
- Every configured scenario must appear at least once

```jsonl
{"id":"weather-shanghai","scenario_id":"weather","arguments":{"city":"Shanghai"}}
{"id":"weather-beijing","scenario_id":"weather","arguments":{"city":"Beijing"}}
```

---

## Important notes

### Dataset library

- `.jsonl` only; upload checks that each line is a JSON object, **not** task-specific schemas
- Type (LLM / business / A2A / MCP) controls which tasks can select the file
- Private datasets are owner-only; public ones can be used by others; the system dataset cannot be edited, deleted, or downloaded

### LLM

- Chat: `messages` replaces the conversation; otherwise `prompt` replaces the user message; `system_prompt` replaces system
- Custom Chat / Embeddings: each line is the full body
- Local images require a Docker mount

### HTTP

- JSONL only; full body per line; parse failures may be sent as text

### Agent

- Closed field sets; unknown keys fail validation
- Unknown `scenario_id` or uncovered scenarios block task creation

---

## Examples

- LLM text: bundled `ShareGPT_V3_partial.jsonl` (`id` + `prompt`)
- HTTP: full-body examples above
- A2A / MCP: scenario-bound examples above

---

## Troubleshooting

### Images not loading

1. Check the Docker mount
2. Confirm paths match `image` / `image_path` and exist in the container
3. Inspect engine logs: `docker-compose logs engine`

### Dataset not applied

**LLM**: Validate JSONL. Chat rows need `prompt` or `messages`. Custom / Embeddings rows must be complete objects.

**HTTP**: Each line must be an object; confirm a dataset is selected and the method has a body.

**A2A / MCP**: Check required fields, `ROLE_USER` / `parts`, object `arguments`, full `scenario_id` coverage, and no extra keys.

---

如有其他问题，请查看项目文档或提交 Issue。

For other questions, please check the project documentation or submit an Issue.
