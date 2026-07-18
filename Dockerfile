FROM python:3.12-slim

# Устанавливаем Chromium и зависимости
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запускаем Chromium с CDP и бота
CMD chromium --headless --no-sandbox \
    --remote-debugging-port=9222 \
    --remote-debugging-address=0.0.0.0 \
    --disable-gpu \
    --disable-dev-shm-usage \
    & \
    sleep 5 && \
    python -u bot.py