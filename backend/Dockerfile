# ============================================================
# Backend Application Image (based on base image)
#
# Usage:
#   1. First time / dependency changes: build and push base image
#      make docker-base-backend
#      make docker-push-base-backend
#   2. Daily development build (only COPY code, very fast):
#      docker build -t charmy1220/lmeterx-be:latest -f backend/Dockerfile .
# ============================================================
ARG BASE_IMAGE=charmy1220/lmeterx-be-base:latest
FROM ${BASE_IMAGE}

WORKDIR /app

# Only reinstall dependencies when requirements.txt changes (usually base image already contains)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300  -r requirements.txt
# Ensure Playwright browser binary matches the installed package version
# (without --with-deps since system deps are already in base image, very fast if version unchanged)
RUN playwright install chromium

# Copy application code and shared runtime helpers.
COPY backend/ .
COPY common/ /app/common/

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5001", "--workers", "2", "--timeout-keep-alive", "600"]
