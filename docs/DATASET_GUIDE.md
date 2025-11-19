# ShareGPT 数据集使用指南 / ShareGPT Dataset Usage Guide

[中文](#中文) | [English](#english)

---

## 中文

### 概述

LMeterX 现已支持 ShareGPT 格式的图文数据集进行压力测试。除了原有的 JSONL 格式，您现在可以使用标准的 ShareGPT JSON 格式来组织测试数据。

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

#### 2. ShareGPT JSON 格式（新增支持）

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

### 图片支持

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

### 使用步骤

1. **准备数据集文件**
   - 准备符合要求的 `.json`（ShareGPT 格式）或 `.jsonl` 格式的数据集文件
   - 如果包含图片，准备好图片文件

2. **配置图片挂载**
   - 将准备的图片放在./data目录下，注意目录层级和图片命名需要和jsonl/json文件中image字段保持一致。
   - 重启服务：`docker-compose down && docker-compose up -d`

3. **创建测试任务**
   - 在 LMeterX 界面中创建新任务
   - 在"数据集来源"中选择"上传 JSONL 文件"
   - 上传您的 `.json` 或 `.jsonl` 文件
   - 完成其他配置并开始测试

### 注意事项

- ⚠️ 对于本地图片路径，必须先配置 Docker 挂载后才能正常访问
- 系统会自动检测上传的文件格式（JSON 或 JSONL）
- ShareGPT 格式会自动提取所有 `human` 角色的对话作为提示词
- 大型图片或大量图片可能会影响性能，建议使用适当大小的图片

### 示例文件

参考示例文件：
- JSONL 格式：`vision_self-built.jsonl`
- ShareGPT 格式：`ShareGPT_V3_partial.json`

---

## English

### Overview

LMeterX now supports ShareGPT format datasets with images for stress testing. In addition to the original JSONL format, you can now use standard ShareGPT JSON format to organize your test data.

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

#### 2. ShareGPT JSON Format (Newly Added)

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

### Image Support

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

### Usage Steps

1. **Prepare Dataset File**
   - Prepare `.json` (ShareGPT format) or `.jsonl` format dataset file
   - Prepare image files if needed

2. **Configure Image Mount** (if needed)
   - Place the prepared images in the ./data directory. Note that the directory hierarchy and image names must be consistent with the image field in the jsonl/json file.
   - Restart services: `docker-compose down && docker-compose up -d`

3. **Create Test Task**
   - Create a new task in LMeterX interface
   - Select "Upload JSONL File" in "Dataset Source"
   - Upload your `.json` or `.jsonl` file
   - Complete other configurations and start test

### Important Notes

- ⚠️ For local image paths, Docker mount must be configured first for proper access
- System automatically detects uploaded file format (JSON or JSONL)
- ShareGPT format automatically extracts all `human` role conversations as prompts
- Large images or many images may affect performance, use appropriately sized images

### Example Files

Reference example files:
- JSONL format:：`vision_self-built.jsonl`
- ShareGPT format:`ShareGPT_V3_partial.json`

## 问题排查 / Troubleshooting

### 图片无法加载 / Images Not Loading

1. 检查 Docker 挂载配置是否正确
2. 确认图片文件路径与数据集中的路径匹配
3. 检查容器日志：`docker-compose logs engine`

### 数据集格式错误 / Dataset Format Error

1. 验证 JSON 格式是否正确（使用 JSON 验证工具）
2. 确保必需字段存在（`id`、`prompt` 或 `conversations`）
3. 检查引擎日志中的详细错误信息

### 性能问题 / Performance Issues

1. 考虑使用较小尺寸的图片
2. 使用图片 URL 代替本地路径（如果可能）
3. 调整并发用户数和测试持续时间

---

如有其他问题，请查看项目文档或提交 Issue。

For other questions, please check the project documentation or submit an Issue.
