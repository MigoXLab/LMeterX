FROM python:3.11-slim

WORKDIR /app

COPY cluster-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cluster-agent/agent.py .

USER 1000:1000

ENTRYPOINT ["python", "agent.py"]
