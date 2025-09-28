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

# LMeterX

## 📋 Project Overview

LMeterX is a professional large language model performance testing platform that can be applied to model inference services based on large model inference frameworks (such as LiteLLM, vLLM, TensorRT-LLM, LMDeploy, and others), and also supports performance testing for cloud services like Azure OpenAI, AWS Bedrock, Google Vertex AI, and other major cloud providers. Through an intuitive Web interface, users can easily create and manage test tasks, monitor testing processes in real-time, and obtain detailed performance analysis reports, providing reliable data support for model deployment and performance optimization.

<div align="center">
  <img src="docs/images/images.gif" alt="LMeterX Demo" width="800"/>
</div>

## ✨ Core Features

- **Universal Framework Support** - Compatible with mainstream inference frameworks (vLLM, LiteLLM, TensorRT-LLM) and cloud services (Azure, AWS, Google Cloud)
- **Full Model Compatibility** - Supports mainstream LLMs like GPT, Claude, and Llama with one-click stress testing
- **High-Load Stress Testing** - Simulates high-concurrency requests to accurately detect model performance limits
- **Multi-Scenario Coverage** - Supports streaming/non-streaming, supports text/multimodal/custom datasets<sup>![NEW](https://img.shields.io/badge/NEW-00C851?style=flat&labelColor=transparent)</sup>
- **Professional Metrics** - Core performance metrics including first token latency, throughput(RPS、TPS), and success rate
- **AI Smart Reports** - AI-powered performance analysis<sup>![NEW](https://img.shields.io/badge/NEW-00C851?style=flat&labelColor=transparent)</sup>, multi-dimensional model comparison and visualization
- **Web Console** - One-stop management for task creation, stopping, status tracking, and full-chain log monitoring
- **Enterprise-level Deployment** - Docker containerization with elastic scaling and distributed deployment support

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

### Environment Requirements
- Docker 20.10.0+
- Docker Compose 2.0.0+
- At least 4GB available memory
- At least 5GB available disk space

### One-Click Deployment (Recommended)

> **Complete Deployment Guide**: See [Complete Deployment Guide](docs/DEPLOYMENT_GUIDE.md) for detailed instructions on all deployment methods

Use pre-built Docker images to start all services with one click:

```bash
# Download and run one-click deployment script
curl -fsSL https://raw.githubusercontent.com/MigoXLab/LMeterX/main/quick-start.sh | bash
```

### Multi-Instance Deployment (Supports Concurrent Testing Tasks)

```bash
# Download the deployment file docker-compose.yml
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/MigoXLab/LMeterX/main/docker-compose.yml
# Start multiple instances using the --scale
# Start 2 backends + 2 engines (the number can be adjusted as needed)
docker compose up -d --scale backend=2 --scale engine=2
```

### Usage Guide

1. **Access Web Interface**: Open http://localhost:8080
2. **Create Test Task**: Navigate to Test Tasks → Create Task, configure LLM API request information, test data, and request-response field mapping
   - 2.1 Basic Information: For `/chat/completions` API, you only need to configure API path, model, and response mode. You can also supplement the complete payload in request parameters.
   - 2.2 Data Payload: Select built-in text datasets/multimodal datasets as needed, or upload custom JSONL data files.
   - 2.3 Field Mapping: Configure the prompt field path in payload, and response data paths for model output content, reasoning_content fields, usage fields, etc. This field mapping is crucial for updating request parameters with datasets and correctly parsing streaming/non-streaming responses.
3. **API Testing**: In Test Tasks → Create Task, click the "Test" button in the Basic Information panel to quickly test API connectivity
   **Note**: For quick API response, it's recommended to use simple prompts when testing API connectivity.
4. **Real-time Monitoring**: Navigate to Test Tasks → Logs/Monitoring Center to view full-chain test logs and troubleshoot exceptions
5. **Result Analysis**: Navigate to Test Tasks → Results to view detailed performance results and export reports
6. **Result Comparison**: Navigate to Model Arena to select multiple models or versions for multi-dimensional performance comparison
7. **AI Analysis**: In Test Tasks → Results/Model Arena, after configuring AI analysis service, support intelligent performance evaluation for single/multiple tasks

## 🔧 Configuration

### Environment Variable Configuration

#### General Configuration
```bash
# ================= Database Configuration =================
DB_HOST=mysql           # Database host (container name or IP)
DB_PORT=3306            # Database port
DB_USER=lmeterx         # Database username
DB_PASSWORD=lmeterx_password  # Database password (use secrets management in production)
DB_NAME=lmeterx         # Database name

# ================= Frontend Configuration =================
VITE_API_BASE_URL=/api  # Base API URL for frontend requests (supports reverse proxy)

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
- [ ] Support for `/v1/embedding` and `/v1/rerank` API stress testing

## 📚 Related Documentation

- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) - Detailed deployment instructions and configuration guide
- [Contributing Guide](docs/CONTRIBUTING.md) - How to participate in project development and contribute code

## 👥 Contributors

Thanks to all developers who have contributed to the LMeterX project:

- [@LuckyYC](https://github.com/LuckyYC) - Project maintainer & Core developer
- [@del-zhenwu](https://github.com/del-zhenwu) - Core developer

## 📄 Open Source License

This project is licensed under the [Apache 2.0 License](LICENSE).

---
<div align="center">
**⭐ If this project helps you, please give us a Star! Your support is our motivation for continuous improvement.**
</div>
