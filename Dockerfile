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

CMD sh -c "echo '🚀 Запуск Chromium...' && \
    /usr/bin/chromium --headless --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --remote-debugging-port=9222 \
        --remote-debugging-address=0.0.0.0 \
        --user-data-dir=/tmp/chrome-profile \
        about:blank > /app/logs/chromium.log 2>&1 & \
    echo '⏳ Ожидание Chromium...' && \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
        if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then \
            echo '✅ Chromium готов!'; \
            break; \
        fi; \
        echo -n '.'; \
        sleep 1; \
    done && \
    echo '🚀 Запуск бота...' && \
    python -u bot.py 2>&1 | tee /app/logs/bot.log"