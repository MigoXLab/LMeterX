.PHONY: help install install-dev format lint type-check security test clean all ci frontend-install frontend-lint frontend-format backend-install backend-dev backend-format backend-lint backend-type-check backend-security backend-test backend-clean backend-all backend-ci st-engine-install st-engine-dev st-engine-format st-engine-lint st-engine-type-check st-engine-security st-engine-test st-engine-clean st-engine-all st-engine-ci

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
