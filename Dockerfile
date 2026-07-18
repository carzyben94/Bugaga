FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# КЛЮЧЕВОЙ МОМЕНТ: запускаем браузер в фоне
CMD chromium --headless --no-sandbox --remote-debugging-port=9222 --disable-gpu & \
    sleep 3 && \
    python -u bot.py