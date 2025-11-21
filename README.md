<div align="center">
  <img src="docs/images/logo.png" alt="LMeterX Logo" width="400"/>
  <p>
    <a href="https://github.com/MigoXLab/LMeterX/blob/main/LICENSE"><img src="https://img.shields.io/github/license/MigoXLab/LMeterX" alt="License"></a>
    <a href="https://github.com/MigoXLab/LMeterX/stargazers"><img src="https://img.shields.io/github/stars/MigoXLab/LMeterX" alt="GitHub stars"></a>
    <a href="https://github.com/MigoXLab/LMeterX/network/members"><img src="https://img.shields.io/github/forks/MigoXLab/LMeterX" alt="GitHub forks"></a>
    <a href="https://github.com/MigoXLab/LMeterX/issues"><img src="https://img.shields.io/github/issues/MigoXLab/LMeterX" alt="GitHub issues"></a>
    <a href="https://deepwiki.com/MigoXLab/LMeterX"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
  </p>
  <p>
    <a href="README_CN.md">简体中文</a> |
    <strong>English</strong>
  </p>
</div>

⭐ If you like this project, please click the "Star" button in the upper right corner to support us. Your support is our motivation to move forward!

## Contents
- [Contents](#contents)
- [📋 Project Overview](#-project-overview)
- [✨ Core Features](#-core-features)
  - [Feature Comparison](#feature-comparison)
- [🏗️ System Architecture](#️-system-architecture)
- [🚀 Quick Start](#-quick-start)
  - [Environment Checklist](#environment-checklist)
  - [One-Click Deployment (Recommended)](#one-click-deployment-recommended)
  - [Data \& Volume Layout](#data--volume-layout)
  - [Usage Guide](#usage-guide)
- [🔧 Configuration](#-configuration)
  - [Database Configuration](#database-configuration)
  - [Resource Configuration](#resource-configuration)
- [🤝 Development Guide](#-development-guide)
  - [Technology Stack](#technology-stack)
  - [Project Structure](#project-structure)
  - [Development Environment Setup](#development-environment-setup)
- [🗺️ Development Roadmap](#️-development-roadmap)
  - [In Development](#in-development)
  - [Planned](#planned)
- [🗂️ Dataset Reference Notes](#️-dataset-reference-notes)
- [👥 Contributing](#-contributing)
- [📝 Citation](#-citation)
- [📄 Open Source License](#-open-source-license)

## 📋 Project Overview

LMeterX is a professional large language model performance testing platform that can be applied to model inference services based on large model inference frameworks (such as LiteLLM, vLLM, TensorRT-LLM, LMDeploy, and others), and also supports performance testing for cloud services like Azure OpenAI, AWS Bedrock, Google Vertex AI, and other major cloud providers. Through an intuitive Web interface, users can easily create and manage test tasks, monitor testing processes in real-time, and obtain detailed performance analysis reports, providing reliable data support for model deployment and performance optimization.

<div align="center">
  <img src="docs/images/images.gif" alt="LMeterX Demo" width="800"/>
</div>

## ✨ Core Features

- **Universal Framework Support** - Compatible with mainstream inference frameworks (vLLM, LiteLLM, TensorRT-LLM) and cloud services (Azure, AWS, Google Cloud)
- **Full Model Compatibility** - Supports mainstream LLMs like GPT, Claude, and Llama, also supports large document parsing models such as [MinerU](https://github.com/opendatalab/MinerU) and [dots.ocr](https://github.com/rednote-hilab/dots.ocr).
- **High-Load Stress Testing** - Simulates high-concurrency requests to accurately detect model performance limits
- **Multi-Scenario Coverage** &nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" /> - Supports streaming/non-streaming, supports text/multimodal/custom datasets
- **Professional Metrics**  - Core performance metrics including first token latency, throughput(RPS、TPS), and success rate
- **AI Smart Reports** &nbsp;<img src="docs/images/badge-new.svg" alt="NEW" height="16" /> - AI-powered performance analysis, multi-dimensional model comparison and visualization
- **Web Console** - One-stop management for task creation, stopping, status tracking, and full-chain log monitoring
- **Enterprise-level Deployment** - Docker containerization with elastic scaling and distributed deployment support

### Feature Comparison
| Dimension            | LMeterX                                                                 | EvalScope                                                                 | llmperf                                                  |
|----------------------|-------------------------------------------------------------------------|---------------------------------------------------------------------------|----------------------------------------------------------|
| Usage                | Web UI for full-lifecycle task creation, monitoring & stop (load-test) | CLI for ModelScope ecosystem (eval & load-test)                          | CLI, Ray-based (load-test)                              |
| Concurrency & Stress | Multi-process / multi-task, enterprise-scale load testing               | Command-line concurrency (`--parallel`, `--rate`)                        | Command-line concurrency                                 |
| Test Report          | Multi-model / multi-version comparison, AI analysis, visual dashboard   | Basic report + visual charts (requires gradio, plotly, etc.)             | Simple report                                            |
| Model & Data Support | OpenAI-compatible, custom data & model interfaces                       | OpenAI-compatible by default; extending APIs needs custom code           | OpenAI-compatible                                        |
| Deployment & Scaling | Docker / K8s ready, easy horizontal scaling                             | `pip` install or source code                                             | Source code only                                         |

## 🏗️ System Architecture

LMeterX adopts a microservices architecture design, consisting of four core components:

1. **Backend Service**: FastAPI-based REST API service responsible for task management and result storage
2. **Load Testing Engine**: Locust-based load testing engine that executes actual performance testing tasks
3. **Frontend Interface**: Modern Web interface based on React + TypeScript + Ant Design
4. **MySQL Database**: Stores test tasks, result data, and configuration information

<div align="center">
  <img src="docs/images/tech-arch.png" alt="LMeterX tech arch" width="700"/>
</div>

## 🚀 Quick Start

### Environment Checklist
- Docker 20.10.0+ with the daemon running
- Docker Compose 2.0.0+ (`docker compose` plugin or standalone `docker-compose`)
- At least 4GB free memory and 5GB disk space

> **Need more deployment options?** See the [Complete Deployment Guide](docs/DEPLOYMENT_GUIDE.md) for Kubernetes, air-gapped installs, and advanced tuning.

### One-Click Deployment (Recommended)

```bash
# Download and run the one-click deployment script
curl -fsSL https://raw.githubusercontent.com/MigoXLab/LMeterX/main/quick-start.sh | bash
```

After the script finishes:
- Check container health: `docker compose ps`
- Tail logs if needed: `docker compose logs -f`
- Scale services (if needed): `docker compose up -d --scale backend=2 --scale engine=2`
- Open the web UI at http://localhost:8080 (see [Usage Guide](#usage-guide))

### Data & Volume Layout
- `./data` → mounted to `/app/data` in the `engine` service (large datasets are **not** baked into the image)
- `./logs` → shared log output for backend and engine
- `./upload_files` → user-supplied payloads and exported reports

For custom data, please refer to the [Dataset Usage Guide](docs/DATASET_GUIDE.md).

### Usage Guide

1. **Access Web Interface**: Open http://localhost:8080
2. **Create Test Task**: Navigate to Test Tasks → Create Task, configure API request information, test data, and request/response field mappings.
   - 2.1 Basic Information: For OpenAI-like and Claude-like APIs, you only need to configure API path, model, and response mode. You can also supplement the complete payload in request parameters.
   - 2.2 Data & load: Select the dataset type, concurrency, load testing time, etc., as needed.
   - 2.3 Field Mapping: For custom APIs, you need to configure the prompt field path in payload, and response data paths for model output fields, usage fields, etc. This field mapping is crucial for updating request parameters with datasets and correctly parsing streaming/non-streaming responses.
   > 💡 **Tip**: For custom multimodal dataset load tests, follow the [Dataset Guide](docs/DATASET_GUIDE.md) for data preparation, mounting, and troubleshooting.
3. **API Testing**: In Test Tasks → Create Task, click the "Test" button in the Basic Information panel to quickly test API connectivity (use a lightweight prompt for faster feedback).
4. **Real-time Monitoring**: Navigate to Test Tasks → Logs/Monitoring Center to view full-chain test logs and troubleshoot exceptions
5. **Result Analysis**: Navigate to Test Tasks → Results to view detailed performance results and export reports
6. **Result Comparison**: Navigate to Model Arena to select multiple models or versions for multi-dimensional performance comparison
7. **AI Analysis**: In Test Tasks → Results/Model Arena, after configuring AI analysis service, support intelligent performance evaluation for single/multiple tasks

## 🔧 Configuration

### Database Configuration

```bash
# ================= Database Configuration =================
DB_HOST=mysql           # Database host (container name or IP)
DB_PORT=3306            # Database port
DB_USER=lmeterx         # Database username
DB_PASSWORD=lmeterx_password  # Database password (use secrets management in production)
DB_NAME=lmeterx         # Database name
```

### Resource Configuration
```bash
# ================= High-Concurrency Load Testing Deployment Requirements =================
# When concurrent users exceed this threshold, the system will automatically enable multi-process mode (requires multi-core CPU support)
MULTIPROCESS_THRESHOLD=1000

# Minimum number of concurrent users each child process should handle (prevents excessive processes and resource waste)
MIN_USERS_PER_PROCESS=500

# ⚠️ IMPORTANT NOTES:
#   - When concurrency ≥ 1000, enabling multi-process mode is strongly recommended for performance.
#   - Multi-process mode requires multi-core CPU resources — ensure your deployment environment meets these requirements.

# ================= Deployment Resource Limits =================
deploy:
  resources:
    limits:
      cpus: '2.0'       # Recommended minimum: 2 CPU cores (4+ cores recommended for high-concurrency scenarios)
      memory: 2G        # Memory limit — adjust based on actual load (minimum recommended: 2G)
```

## 🤝 Development Guide

> We welcome all forms of contributions! Please read our [Contributing Guide](docs/CONTRIBUTING.md) for details.

### Technology Stack

LMeterX adopts a modern technology stack to ensure system reliability and maintainability:

- **Backend Service**: Python + FastAPI + SQLAlchemy + MySQL
- **Load Testing Engine**: Python + Locust + Custom Extensions
- **Frontend Interface**: React + TypeScript + Ant Design + Vite
- **Deployment & Operations**: Docker + Docker Compose + Nginx

### Project Structure

```
LMeterX/
├── backend/                  # Backend service
├── st_engine/                # Load testing engine service
├── frontend/                 # Frontend service
├── docs/                     # Documentation directory
├── docker-compose.yml        # Docker Compose configuration
├── Makefile                  # Run complete code checks
├── README.md                 # English README
```

### Development Environment Setup

1. **Fork the Project** to your GitHub account
2. **Clone Your Fork**, create a development branch for development
3. **Follow Code Standards**, use clear commit messages (follow conventional commit standards)
4. **Run Code Checks**: Before submitting PR, ensure code checks, formatting, and tests all pass, you can run `make all`
5. **Write Clear Documentation**: Write corresponding documentation for new features or changes
6. **Actively Participate in Review**: Actively respond to feedback during the review process

## 🗺️ Development Roadmap

### In Development
- [ ] Support for client resource monitoring

### Planned
- [ ] CLI command-line tool

## 🗂️ Dataset Reference Notes

> LMeterX builds test samples based on the open-source ShareGPT dataset, strictly adhering to the original license requirements.

- **Data Source**: Uses the [ShareGPT dataset](https://huggingface.co/datasets/learnanything/sharegpt_v3_unfiltered_cleaned_split) as the original dialogue corpus.

- **Adjustment Scope**:
- Filtered high-quality dialogue samples, removing low-quality or irrelevant data for the load testing scenario.
- Random sampling was performed to reduce the data size while preserving diverse dialogues.

## 👥 Contributing

We welcome any contributions from the community! Please refer to our [Contributing Guide](docs/CONTRIBUTING.md)
Thanks to all developers who have contributed to the LMeterX project!

<a href="https://github.com/MigoXLab/LMeterX/graphs/contributors" target="_blank">
  <table>
    <tr>
      <th colspan="2">
        <br><img src="https://contrib.rocks/image?repo=MigoXLab/LMeterX"><br><br>
      </th>
    </tr>
  </table>
</a>

## 📝 Citation
If you use EvalScope in your research, please cite our work:

```bibtex
@software{LMeterX2025,
  author  = {LMeterX Team},
  title   = {LMeterX: Enterprise-Grade Performance Benchmarking Platform for Large Language Models},
  year    = {2025},
  url     = {https://github.com/MigoXLab/LMeterX},
}
```

## 📄 Open Source License

This project is licensed under the [Apache 2.0 License](LICENSE).

---
<div align="center">
**⭐ If this project helps you, please give us a Star! Your support is our motivation for continuous improvement.**
</div>
