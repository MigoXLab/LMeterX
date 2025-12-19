# ShareGPT 数据集使用指南 / ShareGPT Dataset Usage Guide

[中文](#中文) | [English](#english)

---

## 中文

### 概述

LMeterX 支持两种类型的API压测：**LLM API 压测**和**通用 API 压测**。两种压测类型支持的数据集格式不同，请根据您的压测类型选择合适的数据集格式。

---

## LLM API 压测数据集格式

### 支持的数据集格式

#### 1. JSONL 格式

每行一个 JSON 对象：

```jsonl
{"id": "1", "prompt": "你好，请介绍一下你自己"}
{"id": "2", "prompt": "What is machine learning?"}
{"id": "3", "prompt": "描述这张图片", "image_path": "path/to/image.jpg"}
```

字段说明：
- `id`: 必需，唯一标识符
- `prompt`: 必需，提示词（字符串或字符串数组）
- `image_path`: 可选，图片路径（字符串或字符串数组）
- `image`: 可选，图片 URL 或 base64 编码

#### 2. ShareGPT JSON 格式

JSON 数组格式：

```json
[
  {
    "id": "sharegpt_001",
    "image": "data/pic/image1.jpg",
    "conversations": [
      {"from": "human", "value": "你好"},
      {"from": "gpt", "value": "你好！有什么我可以帮你的吗？"},
      {"from": "human", "value": "描述这个图片"},
      {"from": "gpt", "value": "这是一张美丽的风景照片。"}
    ]
  },
  {
    "id": "sharegpt_002",
    "image": "http://example.com/image2.jpg",
    "conversations": [
      {"from": "human", "value": "这张图片里有什么？"},
      {"from": "gpt", "value": "这是一张城市夜景照片。"}
    ]
  },
  {
    "id": "sharegpt_003",
    "conversations": [
      {"from": "human", "value": "今天天气怎么样？"},
      {"from": "gpt", "value": "今天天气晴朗，适合外出。"}
    ]
  }
]
```

字段说明：
- `id`: 必需，唯一标识符
- `conversations`: 必需，对话数组
  - `from`: 必需，`"human"` 或 `"gpt"`
  - `value`: 必需，对话内容
- `image`: 可选，图片路径或 URL

**注意**：系统会自动提取 `conversations` 中所有 `"human"` 角色的内容作为提示词。


#### 3. 图片支持

当数据集包含图片路径时，您需要将图片文件挂载到容器./data对应目录下。

#### Docker Compose 配置

在 `docker-compose.yml` 或 `docker-compose.dev.yml` 中配置图片目录挂载：

```yaml
services:
  engine:
    volumes:
      - ./logs:/logs
      - ./upload_files:/app/upload_files
      - ./data:/app/data
```
### 压测使用步骤

1. **准备数据集文件**
   - 准备符合要求的 `.json`（ShareGPT 格式）或 `.jsonl` 格式的数据集文件
   - 如果包含图片，准备好图片文件

2. **配置图片挂载**（如需要）
   - 将准备的图片放在 `./data` 目录下，注意目录层级和图片命名需要和 jsonl/json 文件中 image 字段保持一致
   - 重启服务：`docker-compose down && docker-compose up -d`

3. **创建测试任务**
   - 在 LMeterX 界面中切换到「LLM API」标签页
   - 创建新任务，在"数据集来源"中选择"上传 JSONL 文件"
   - 上传您的 `.json` 或 `.jsonl` 文件
   - 完成其他配置并开始测试
---

## 通用 API 压测数据集格式

### 数据集格式说明

通用 API 压测**仅支持 JSONL 格式**

#### JSONL 格式要求

每行必须是一个**完整的 payload JSON 对象**，该对象将直接作为 HTTP 请求的请求体（request body）发送。

```jsonl
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "你好"}], "max_tokens": 128}
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "介绍一下机器学习"}], "max_tokens": 256}
```

**重要说明**：
- ✅ 每行必须是一个有效的 JSON 对象
- ✅ 每行的 JSON 对象将直接作为请求体发送给目标 API
- ✅ 支持任意结构的 JSON 对象，根据您的 API 需求自定义
- ❌ 不支持 JSON 格式（JSON 数组格式）
- ❌ 不支持图片字段（通用 API 压测不涉及图片处理）

**使用场景**：
- RESTful API 压测
- 自定义业务 API 压测
- 需要批量不同请求体的场景

### 压测使用步骤

1. **准备数据集文件**
   - 准备 JSONL 格式的数据集文件
   - 每行必须是一个完整的 payload JSON 对象
   - 确保每行的 JSON 格式正确（可使用 JSON 验证工具检查）

2. **创建测试任务**
   - 在 LMeterX 界面中切换到「通用API」标签页
   - 创建新任务，填写 API 请求信息（URL、方法、Headers 等）
   - 在"数据集来源"中选择"上传"
   - 上传您的 `.jsonl` 文件
   - 完成其他配置（并发数、压测时长等）并开始测试

## 注意事项

### LLM API 压测
- ⚠️ 对于本地图片路径，必须先配置 Docker 挂载后才能正常访问
- 系统会自动检测上传的文件格式（JSON 或 JSONL）
- ShareGPT 格式会自动提取所有 `human` 角色的对话作为提示词
- 大型图片或大量图片可能会影响性能，建议使用适当大小的图片

### 通用 API 压测
- ⚠️ **仅支持 JSONL 格式**，不支持 JSON 格式
- ⚠️ 每行必须是一个有效的 JSON 对象，格式错误会导致该行被跳过
- ⚠️ 每行的 JSON 对象将直接作为请求体发送，请确保格式符合目标 API 的要求
- 系统会按行顺序轮询使用数据集中的请求体
- 如果某行 JSON 解析失败，系统会尝试将其作为纯文本发送

## 示例文件

### LLM API 压测示例
- JSONL 格式：`vision_self-built.jsonl`
- ShareGPT 格式：`ShareGPT_V3_partial.json`

### 通用 API 压测示例

创建一个 `common_api_dataset.jsonl` 文件，示例内容：

```jsonl
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "你好"}], "max_tokens": 128, "stream": false}
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "介绍一下机器学习"}], "max_tokens": 256, "stream": false}
```

---
## 问题排查

### 图片无法加载

1. 检查 Docker 挂载配置是否正确
2. 确认图片文件路径与数据集中的路径匹配
3. 检查容器日志：`docker-compose logs engine`

### 数据集未生效

#### LLM API 压测
1. 验证 JSON 格式是否正确（使用 JSON 验证工具）
2. 确保必需字段存在（`id`、`prompt` 或 `conversations`）
3. 检查引擎日志中的详细错误信息

#### 通用 API 压测
1. 验证每行的 JSON 格式是否正确（使用 JSON 验证工具）
2. 确保每行都是一个完整的 JSON 对象
3. 检查引擎日志中的详细错误信息

---
## English

### Overview

LMeterX supports two types of API load testing: **LLM API Load Testing** and **General API Load Testing**. The supported dataset formats differ between these two types. Please choose the appropriate dataset format based on your testing type.

---

## LLM API Load Testing Dataset Formats

### Supported Dataset Formats

#### 1. JSONL Format

One JSON object per line:

```jsonl
{"id": "1", "prompt": "Hello, please introduce yourself"}
{"id": "2", "prompt": "What is machine learning?"}
{"id": "3", "prompt": "Describe this image", "image_path": "path/to/image.jpg"}
```

Fields:
- `id`: Required, unique identifier
- `prompt`: Required, prompt text (string or array of strings)
- `image_path`: Optional, image path (string or array of strings)
- `image`: Optional, image URL or base64 encoded data

#### 2. ShareGPT JSON Format

JSON array format:

```json
[
  {
    "id": "sharegpt_001",
    "image": "data/pic/image1.jpg",
    "conversations": [
      {"from": "human", "value": "Hello"},
      {"from": "gpt", "value": "Hello! How can I help you?"},
      {"from": "human", "value": "Describe this image"},
      {"from": "gpt", "value": "This is a beautiful landscape photo."}
    ]
  },
  {
    "id": "sharegpt_002",
    "image": "http://example.com/image2.jpg",
    "conversations": [
      {"from": "human", "value": "What's in this image?"},
      {"from": "gpt", "value": "This is a city night scene photo."}
    ]
  },
  {
    "id": "sharegpt_003",
    "conversations": [
      {"from": "human", "value": "How's the weather today?"},
      {"from": "gpt", "value": "It's sunny today, perfect for going out."}
    ]
  }
]
```

Fields:
- `id`: Required, unique identifier
- `conversations`: Required, array of conversation turns
  - `from`: Required, either `"human"` or `"gpt"`
  - `value`: Required, conversation content
- `image`: Optional, image path or URL

**Note**: The system automatically extracts all `"human"` role content from `conversations` as prompts.

#### 3. Image Support

When your dataset contains images, you need to mount the image files into the container.

#### Docker Compose Configuration

Configure image directory mount in `docker-compose.yml` or `docker-compose.dev.yml`:

```yaml
services:
  engine:
    volumes:
      - ./logs:/logs
      - ./upload_files:/app/upload_files
      - ./data:/app/data
```

### Load Testing Usage Steps

1. **Prepare Dataset File**
   - Prepare `.json` (ShareGPT format) or `.jsonl` format dataset file
   - Prepare image files if needed

2. **Configure Image Mount** (if needed)
   - Place the prepared images in the `./data` directory. Note that the directory hierarchy and image names must be consistent with the image field in the jsonl/json file
   - Restart services: `docker-compose down && docker-compose up -d`

3. **Create Test Task**
   - Switch to the "LLM API" tab in the LMeterX interface
   - Create a new task, select "Upload JSONL File" in "Dataset Source"
   - Upload your `.json` or `.jsonl` file
   - Complete other configurations and start test

---

## General API Load Testing Dataset Formats

### Dataset Format Description

General API load testing **only supports JSONL format**

#### JSONL Format Requirements

Each line must be a **complete payload JSON object** that will be sent directly as the HTTP request body.

```jsonl
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 128}
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "Introduce machine learning"}], "max_tokens": 256}
```

**Important Notes**:
- ✅ Each line must be a valid JSON object
- ✅ Each line's JSON object will be sent directly as the request body to the target API
- ✅ Supports any JSON object structure, customize according to your API requirements
- ❌ Does not support JSON format
- ❌ Does not support image fields (General API load testing does not involve image processing)

**Use Cases**:
- RESTful API load testing
- Custom business API load testing
- Scenarios requiring batch requests with different request bodies

### Load Testing Usage Steps

1. **Prepare Dataset File**
   - Prepare a JSONL format dataset file
   - Each line must be a complete payload JSON object
   - Ensure each line's JSON format is correct (use JSON validation tools to check)

2. **Create Test Task**
   - Switch to the "General API" tab in the LMeterX interface
   - Create a new task, fill in API request information (URL, method, headers, etc.)
   - Select "Upload" in "Dataset Source"
   - Upload your `.jsonl` file
   - Complete other configurations (concurrency, test duration, etc.) and start test

## Important Notes

### LLM API Load Testing
- ⚠️ For local image paths, Docker mount must be configured first for proper access
- System automatically detects uploaded file format (JSON or JSONL)
- ShareGPT format automatically extracts all `human` role conversations as prompts
- Large images or many images may affect performance, use appropriately sized images

### General API Load Testing
- ⚠️ **Only supports JSONL format**
- ⚠️ Each line must be a valid JSON object, format errors will cause that line to be skipped
- ⚠️ Each line's JSON object will be sent directly as the request body, ensure the format meets your target API requirements
- System will use dataset request bodies in round-robin order
- If a line's JSON parsing fails, the system will attempt to send it as plain text

## Example Files

### LLM API Load Testing Examples
- JSONL format: `vision_self-built.jsonl`
- ShareGPT format: `ShareGPT_V3_partial.json`

### General API Load Testing Example

Create a `common_api_dataset.jsonl` file with example content:

```jsonl
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 128, "stream": false}
{"model": "gpt-5.2", "messages": [{"role": "user", "content": "Introduce machine learning"}], "max_tokens": 256, "stream": false}
```

## Troubleshooting

### Images Not Loading

1. Check if the Docker mount configuration is correct.
2. Confirm that the image file paths match the paths in the dataset.
3. Check the container logs: `docker-compose logs engine`

### Dataset not working

#### LLM API Load Testing

1. Verify that the JSON format is correct (using a JSON validator).
2. Ensure that required fields exist (`id`, `prompt`, or `conversations`).
3. Check the engine logs for detailed error information.

#### General API Load Testing

1. Verify that the JSON format of each line is correct (using a JSON validator).
2. Ensure that each line is a complete JSON object.
3. Check the engine logs for detailed error information.

---

如有其他问题，请查看项目文档或提交 Issue。

For other questions, please check the project documentation or submit an Issue.
