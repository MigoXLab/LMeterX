# ============================================================
# ST Engine Application Image (based on base image)
#
# Usage:
#   1. First time / dependency changes: build and push base image
#      make docker-base-engine
#      make docker-push-base-engine
#   2. Daily development build (only COPY code, very fast):
#      docker build -t charmy1220/lmeterx-eng:latest st_engine/
# ============================================================
ARG BASE_IMAGE=charmy1220/lmeterx-eng-base:latest
FROM ${BASE_IMAGE}

WORKDIR /app

# Only reinstall dependencies when requirements.txt changes (usually base image already contains)
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt 2>/dev/null || true

# Copy application code (this is the only layer that changes frequently)
COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5002"]
