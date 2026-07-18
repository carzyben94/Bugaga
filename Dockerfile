FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium

WORKDIR /app

# Устанавливаем uv
RUN pip install --no-cache-dir uv

# Устанавливаем browser-harness как CLI-инструмент
RUN uv tool install --python 3.12 --upgrade --force browser-harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["/bin/bash", "-c", \
    "echo '🚀 Запуск Chromium...' && \
    /usr/bin/chromium \
        --headless \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --remote-debugging-port=9222 \
        --remote-debugging-address=0.0.0.0 \
        --user-data-dir=/tmp/chrome-profile \
        about:blank > /tmp/chrome.log 2>&1 & \
    echo '⏳ Ожидание инициализации Chromium...' && \
    for i in {1..30}; do \
        if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then \
            echo '✅ Chromium готов!' && \
            break; \
        fi; \
        echo -n '.' && sleep 1; \
    done && \
    echo '🚀 Запуск бота...' && \
    export PATH="/root/.local/bin:$PATH" && \
    python -u bot.py"]