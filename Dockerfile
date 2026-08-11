
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    libglib2.0-0 \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV BH_DOMAIN_SKILLS=1
ENV BH_AGENT_WORKSPACE=/app/browser-harness/agent-workspace

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /app/browser-harness/agent-workspace

# Устанавливаем browser-harness как Python пакет
RUN pip install --no-cache-dir browser-harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .