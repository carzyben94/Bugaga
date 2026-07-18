FROM python:3.12-slim

# Устанавливаем Chromium и необходимые зависимости
RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Настройки окружения
ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV BU_CDP_URL=http://localhost:9222

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

# Скрипт для запуска (исправленный)
CMD ["/bin/bash", "-c", \
    "chromium --headless --no-sandbox \
        --remote-debugging-port=9222 \
        --remote-debugging-address=0.0.0.0 \
        --disable-gpu \
        --disable-dev-shm-usage \
        --disable-software-rasterizer \
        --disable-features=IsolateOrigins,site-per-process \
        & \
     sleep 8 && \
     python -u bot.py"]