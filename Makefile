.PHONY: help install install-dev format lint type-check security test clean all ci frontend-install frontend-lint frontend-format backend-install backend-dev backend-format backend-lint backend-type-check backend-security backend-test backend-clean backend-all backend-ci st-engine-install st-engine-dev st-engine-format st-engine-lint st-engine-type-check st-engine-security st-engine-test st-engine-clean st-engine-all st-engine-ci docker-base-backend docker-base-engine docker-base-all docker-push-base-backend docker-push-base-engine docker-push-base-all docker-build-backend docker-build-engine docker-build-all

# Docker Hub username (can be overridden via environment variable)
DOCKER_USER ?= charmy1220

# 默认目标
help:
	@echo "LMeterX 项目管理命令:"
	@echo ""
	@echo "全局命令:"
	@echo "  help        - 显示此帮助信息"
	@echo "  install     - 安装所有项目的生产依赖"
	@echo "  install-dev - 安装所有项目的开发依赖"
	@echo "  format      - 格式化所有项目的代码"
	@echo "  lint        - 检查所有项目的代码质量"
	@echo "  test        - 运行所有项目的测试"
	@echo "  clean       - 清理所有项目的缓存文件"
	@echo "  all         - 运行所有项目的完整检查"
	@echo "  ci          - 运行所有项目的 CI/CD 检查"
	@echo ""
	@echo "Docker 镜像构建命令:"
	@echo "  docker-base-backend      - 构建后端基础镜像 (含所有依赖+Playwright)"
	@echo "  docker-base-engine       - 构建引擎基础镜像 (含所有依赖)"
	@echo "  docker-base-all          - 构建所有基础镜像"
	@echo "  docker-push-base-backend - 推送后端基础镜像到 Docker Hub"
	@echo "  docker-push-base-engine  - 推送引擎基础镜像到 Docker Hub"
	@echo "  docker-push-base-all     - 推送所有基础镜像到 Docker Hub"
	@echo "  docker-build-backend     - 构建后端应用镜像 (基于基础镜像，极快)"
	@echo "  docker-build-engine      - 构建引擎应用镜像 (基于基础镜像，极快)"
	@echo "  docker-build-all         - 构建所有应用镜像"
	@echo ""
	@echo "Frontend 命令:"
	@echo "  frontend-install - 安装前端依赖"
	@echo "  frontend-lint    - 检查前端代码质量"
	@echo "  frontend-format  - 格式化前端代码"
	@echo ""
	@echo "Backend 命令:"
	@echo "  backend-install     - 安装后端生产依赖"
	@echo "  backend-dev         - 安装后端开发依赖"
	@echo "  backend-format      - 格式化后端代码"
	@echo "  backend-lint        - 检查后端代码质量"
	@echo "  backend-type-check  - 后端类型检查"
	@echo "  backend-security    - 后端安全检查"
	@echo "  backend-test        - 运行后端测试"
	@echo "  backend-clean       - 清理后端缓存"
	@echo "  backend-all         - 运行后端所有检查"
	@echo "  backend-ci          - 后端 CI/CD 检查"
	@echo ""
	@echo "ST Engine 命令:"
	@echo "  st-engine-install     - 安装引擎生产依赖"
	@echo "  st-engine-dev         - 安装引擎开发依赖"
	@echo "  st-engine-format      - 格式化引擎代码"
	@echo "  st-engine-lint        - 检查引擎代码质量"
	@echo "  st-engine-type-check  - 引擎类型检查"
	@echo "  st-engine-security    - 引擎安全检查"
	@echo "  st-engine-test        - 运行引擎测试"
	@echo "  st-engine-clean       - 清理引擎缓存"
	@echo "  st-engine-all         - 运行引擎所有检查"
	@echo "  st-engine-ci          - 引擎 CI/CD 检查"

# 全局命令
install: frontend-install backend-install st-engine-install
	@echo "所有项目依赖安装完成!"

install-dev: backend-dev st-engine-dev
	@echo "所有项目开发依赖安装完成!"

format: frontend-format backend-format st-engine-format
	@echo "所有项目代码格式化完成!"

lint: frontend-lint backend-lint st-engine-lint
	@echo "所有项目代码质量检查完成!"

type-check: backend-type-check st-engine-type-check
	@echo "所有项目类型检查完成!"

security: backend-security st-engine-security
	@echo "所有项目安全检查完成!"

test: backend-test st-engine-test
	@echo "所有项目测试完成!"

clean: backend-clean st-engine-clean
	@echo "所有项目缓存清理完成!"

all: format lint type-check security test
	@echo "所有项目完整检查完成!"

ci: frontend-lint backend-ci st-engine-ci
	@echo "所有项目 CI/CD 检查完成!"

# Frontend 命令
frontend-install:
	@echo "正在安装前端依赖..."
	cd frontend && npm install

frontend-lint:
	@echo "正在检查前端代码质量..."
	cd frontend && npm run lint

frontend-format:
	@echo "正在格式化前端代码..."
	cd frontend && npm run format

# Backend 命令
backend-install:
	@echo "正在安装后端生产依赖..."
	cd backend && pip install -r requirements.txt

backend-dev:
	@echo "正在安装后端开发依赖..."
	cd backend && pip install -r requirements-dev.txt

backend-format:
	@echo "正在格式化后端代码..."
	cd backend && isort . && black .

backend-lint:
	@echo "正在检查后端代码质量..."
	cd backend && flake8 .

backend-type-check:
	@echo "正在进行后端类型检查..."
	cd backend && mypy .

backend-security:
	@echo "正在进行后端安全检查..."
	cd backend && bandit -r . -c pyproject.toml -f json -o bandit-report.json || bandit -r . -c pyproject.toml

backend-test:
	@echo "正在运行后端测试..."
	cd backend && TESTING=1 python -m pytest --cov=. --cov-report=html --cov-report=term-missing

backend-clean:
	@echo "正在清理后端缓存..."
	cd backend && find . -type f -name "*.pyc" -delete && \
	find . -type d -name "__pycache__" -delete && \
	find . -type d -name "*.egg-info" -exec rm -rf {} + && \
	find . -type d -name ".pytest_cache" -exec rm -rf {} + && \
	find . -type d -name ".mypy_cache" -exec rm -rf {} + && \
	find . -type f -name ".coverage" -delete && \
	find . -type d -name "htmlcov" -exec rm -rf {} + && \
	find . -type f -name "bandit-report.json" -delete

backend-all: backend-format backend-lint backend-type-check backend-security backend-test
	@echo "后端所有检查完成!"

backend-ci:
	@echo "正在运行后端 CI/CD 检查..."
	cd backend && black --check . && \
	isort --check-only . && \
	flake8 . && \
	mypy . && \
	(bandit -r . -c pyproject.toml -f json -o bandit-report.json || bandit -r . -c pyproject.toml) && \
	TESTING=1 python -m pytest --cov=. --cov-report=term-missing

# ST Engine 命令
st-engine-install:
	@echo "正在安装引擎生产依赖..."
	cd st_engine && pip install -r requirements.txt

st-engine-dev:
	@echo "正在安装引擎开发依赖..."
	cd st_engine && pip install -r requirements.txt && pip install -r requirements-dev.txt

st-engine-format:
	@echo "正在格式化引擎代码..."
	cd st_engine && isort . && black .

st-engine-lint:
	@echo "正在检查引擎代码质量..."
	cd st_engine && flake8 .

st-engine-type-check:
	@echo "正在进行引擎类型检查..."
	cd st_engine && mypy .

st-engine-security:
	@echo "正在进行引擎安全检查..."
	cd st_engine && bandit -r . -c pyproject.toml

st-engine-test:
	@echo "正在运行引擎测试..."
	cd st_engine && python -m pytest

st-engine-clean:
	@echo "正在清理引擎缓存..."
	cd st_engine && find . -type f -name "*.pyc" -delete && \
	find . -type d -name "__pycache__" -delete && \
	find . -type d -name "*.egg-info" -exec rm -rf {} + && \
	find . -type d -name ".pytest_cache" -exec rm -rf {} + && \
	find . -type d -name ".mypy_cache" -exec rm -rf {} + && \
	rm -rf htmlcov/ && \
	rm -rf .coverage && \
	rm -rf coverage.xml

st-engine-all: st-engine-format st-engine-lint st-engine-type-check st-engine-security st-engine-test
	@echo "引擎所有检查完成!"

st-engine-ci:
	@echo "正在运行引擎 CI/CD 检查..."
	cd st_engine && isort --check-only --diff . && \
	black --check --diff . && \
	flake8 . && \
	mypy . && \
	bandit -r . -c pyproject.toml && \
	python -m pytest

# ============================================================
# Docker 镜像构建命令
# ============================================================

# --- 基础镜像构建 (首次 / 依赖变更时执行，较慢但只需偶尔执行) ---
docker-base-backend:
	@echo "正在构建后端基础镜像 (含 Python 依赖 + Playwright)..."
	docker build -t $(DOCKER_USER)/lmeterx-be-base:latest -f backend/Dockerfile.base backend/
	@echo "后端基础镜像构建完成: $(DOCKER_USER)/lmeterx-be-base:latest"

docker-base-engine:
	@echo "正在构建引擎基础镜像 (含 Python 依赖)..."
	docker build -t $(DOCKER_USER)/lmeterx-eng-base:latest -f st_engine/Dockerfile.base st_engine/
	@echo "引擎基础镜像构建完成: $(DOCKER_USER)/lmeterx-eng-base:latest"

docker-base-all: docker-base-backend docker-base-engine
	@echo "所有基础镜像构建完成!"

# --- 推送基础镜像到 Docker Hub ---
docker-push-base-backend:
	@echo "正在推送后端基础镜像到 Docker Hub..."
	docker push $(DOCKER_USER)/lmeterx-be-base:latest
	@echo "后端基础镜像推送完成!"

docker-push-base-engine:
	@echo "正在推送引擎基础镜像到 Docker Hub..."
	docker push $(DOCKER_USER)/lmeterx-eng-base:latest
	@echo "引擎基础镜像推送完成!"

docker-push-base-all: docker-push-base-backend docker-push-base-engine
	@echo "所有基础镜像推送完成!"

# --- 应用镜像构建 (日常开发，基于基础镜像，极快) ---
docker-build-backend:
	@echo "正在构建后端应用镜像 (基于基础镜像)..."
	docker build -t $(DOCKER_USER)/lmeterx-be:latest backend/
	@echo "后端应用镜像构建完成: $(DOCKER_USER)/lmeterx-be:latest"

docker-build-engine:
	@echo "正在构建引擎应用镜像 (基于基础镜像)..."
	docker build -t $(DOCKER_USER)/lmeterx-eng:latest st_engine/
	@echo "引擎应用镜像构建完成: $(DOCKER_USER)/lmeterx-eng:latest"

docker-build-all: docker-build-backend docker-build-engine
	@echo "所有应用镜像构建完成!"
