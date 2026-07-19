FROM python:3.12-slim   

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Устанавливаем uv
RUN pip install --no-cache-dir uv

# Устанавливаем browser-harness как CLI-инструмент
RUN uv tool install --python 3.12 --upgrade --force browser-harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Правильный синтаксис CMD
CMD sh -c "echo '🚀 Запуск Chromium...' && \
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
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
        if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then \
            echo '✅ Chromium готов!' && \
            break; \
        fi; \
        echo -n '.' && sleep 1; \
    done && \
    echo '🚀 Запуск бота...' && \
    python -u bot.py"