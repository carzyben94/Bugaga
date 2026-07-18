FROM python:3.12-slim

# Устанавливаем git и chromium
RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запускаем браузер и бота
CMD chromium --headless --no-sandbox --remote-debugging-port=9222 --disable-gpu & \
    sleep 3 && \
    python -u bot.py