FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y curl procps && apt-get clean

COPY requirements.txt .
RUN pip config set global.index-url https://pypi.org/simple && \
    pip install --no-cache-dir --default-timeout=300 -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5002"]
