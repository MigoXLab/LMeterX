# Contributing Guide

Welcome to the LMeterX community! We appreciate your interest in contributing to our OpenAI-compatible API performance testing platform. All kinds of contributions are welcomed, including but not limited to bug fixes, new features, documentation improvements, and community support.

## 📋 Table of Contents

- [Ways to Contribute](#-ways-to-contribute)
- [Development Environment Setup](#-development-environment-setup)
- [Development Workflow](#-development-workflow)
- [Code Standards](#-code-standards)
- [Pull Request Process](#-pull-request-process)
- [Issue Guidelines](#-issue-guidelines)
- [Community Guidelines](#-community-guidelines)

## 🤝 Ways to Contribute

### Bug Fixes

You can directly post a Pull Request to fix typos in code or documents.

For code implementation bugs:
1. If the modification involves significant changes, create an issue first describing the error information and how to trigger the bug
2. Other developers will discuss with you and propose a proper solution
3. Post a pull request after fixing the bug and adding corresponding unit tests

### New Features or Enhancements

1. If the modification involves significant changes, create an issue to discuss with our developers and propose a proper design
2. Post a Pull Request after implementing the new feature or enhancement
3. Add corresponding unit tests for new functionality

### Documentation

- You can directly post a pull request to fix documents
- If you want to add new documentation, create an issue first to check if it is reasonable

### Other Contributions

- Performance optimizations
- Code refactoring
- Community support
- Testing and feedback

## 🛠️ Development Environment Setup

### Prerequisites

- **Python**: 3.10+
- **Node.js**: 18+
- **Docker**: 20.10.0+ (recommended)
- **Docker Compose**: 2.0.0+
- **MySQL**: 5.7+ (if not using Docker)

### Option 1: Docker Development Environment (Recommended)

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/LMeterX.git
cd LMeterX

# 2. Create a development branch
git checkout -b feature/your-feature-name

# 3. Start development environment
docker compose -f docker-compose.dev.yml up -d

# 4. Check service status
docker compose -f docker-compose.dev.yml ps
```

### Option 2: Local Development Environment

#### Database Setup

```bash
# Install and start MySQL
# Ubuntu/Debian:
sudo apt-get install mysql-server
sudo systemctl start mysql

# macOS (using Homebrew):
brew install mysql
brew services start mysql

# Create database and user
mysql -u root -p
CREATE DATABASE lmeterx;
CREATE USER 'lmeterx'@'localhost' IDENTIFIED BY 'lmeterx_password';
GRANT ALL PRIVILEGES ON lmeterx.* TO 'lmeterx'@'localhost';
FLUSH PRIVILEGES;
```

#### Backend Development Environment

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env file to configure database connection

# Start backend service
python app.py
```

#### Load Testing Engine Environment

```bash
cd st_engine

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Use API mode against the local Backend:
# ENGINE_MODE=api
# BACKEND_URL=http://localhost:5001
# CLUSTER_ID=local

# Start load testing engine
python app.py
```

The Engine uses Backend API mode by default. Direct MySQL polling (`ENGINE_MODE=db`) is deprecated. For cross-cluster development, see the [Multi-Cluster Engine Guide](MULTI_CLUSTER_GUIDE.md).

#### Frontend Development Environment

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build:prod
```

## 🔄 Development Workflow

### 1. Start Development

```bash
# 1. Fork the project to your GitHub account
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/LMeterX.git
cd LMeterX

# 3. Add upstream repository
git remote add upstream https://github.com/MigoXLab/LMeterX.git

# 4. Create development branch
git checkout -b feature/your-feature-name
```

### 2. Keep Code Updated

```bash
# Keep local code synchronized with upstream
git fetch upstream
git checkout main
git merge upstream/main
git push origin main

# Switch to development branch and merge latest code
git checkout feature/your-feature-name
git merge main
```

### 3. Commit Code

```bash
# Add modified files
git add .

# Commit code (follow commit conventions)
git commit -m "feat: add new performance metrics collection"

# Push to your fork
git push origin feature/your-feature-name
```

## 📝 Code Standards

### Python Code Standards

Follow [PEP 8](https://pep8.org/) guidelines

### TypeScript/React Code Standards

Follow [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript)

## 🔄 Pull Request Process

### Pull Request Checklist

Before submitting a PR, ensure:

- [ ] Code follows project standards
- [ ] Includes necessary tests
- [ ] All tests pass
- [ ] Documentation is updated
- [ ] Commit messages follow conventions
- [ ] No merge conflicts
- [ ] CHANGELOG.md is updated with notable changes under "Unreleased"

### PR Description Template

When creating a Pull Request, include:

1. **Feature Description**: What does this PR accomplish?
2. **Testing**: How was this tested?
3. **Related Issues**: Link to related issues
4. **Screenshots**: If applicable
5. **Breaking Changes**: Any breaking changes introduced

### Review Process

- **Functionality**: Does the code implement the expected functionality?
- **Code Quality**: Does it follow best practices?
- **Performance**: Does it introduce performance issues?
- **Security**: Are there any security vulnerabilities?
- **Maintainability**: Is the code easy to understand and maintain?

## 📝 Issue Guidelines

### Bug Reports

When reporting bugs, include:

- **Bug Description**: Detailed description of the issue
- **Steps to Reproduce**: How to reproduce the problem
- **Expected Behavior**: What should happen
- **Actual Behavior**: What actually happens
- **Environment**: OS, browser version, etc.
- **Screenshots**: If applicable

### Feature Requests

When suggesting features, include:

- **Feature Description**: Detailed description of the proposed feature
- **Use Case**: When would this feature be needed?
- **Implementation Suggestions**: If you have ideas about implementation
- **Priority**: How important is this feature?

## 👥 Community Guidelines

### Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for everyone:

- **Respect Others**: Respect different viewpoints and experiences
- **Friendly Communication**: Use welcoming and inclusive language
- **Constructive Feedback**: Provide constructive criticism and suggestions
- **Stay On Topic**: Keep discussions technically relevant

### Getting Help

If you need help, you can:

- **GitHub Issues**: For technical questions and bug reports
- **GitHub Discussions**: For general discussions and questions
- **Project Documentation**: Check detailed usage guides

---

Thank you for contributing to LMeterX! If you have any questions or suggestions, please feel free to reach out to us.

**Let's build a better performance testing platform together!** 🚀
