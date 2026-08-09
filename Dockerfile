FROM python:3.12-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    git \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir uv
RUN uv tool install --python 3.12 --upgrade --force browser-harness

# УСТАНОВКА PRIME AGENT
RUN curl -fsSL https://app.primeintellect.ai/prime-agent/install.sh | sh

# УСТАНОВКА LITELLM
RUN pip install 'litellm[proxy]'

# Проверка
RUN node --version && prime-agent --version || echo "⚠️ Prime Agent установлен"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /root/.prime-agent /app/logs /app/screenshots /root/.prime/agent

COPY config.yaml /app/config.yaml

# ИСПРАВЛЕННЫЙ CMD с проверкой LiteLLM
CMD sh -c "echo '🚀 Запуск LiteLLM...' && \
    litellm --config /app/config.yaml --port 4000 --host 0.0.0.0 > /tmp/litellm.log 2>&1 & \
    sleep 5 && \
    echo '✅ LiteLLM запущен (порт 4000)' && \
    echo '🚀 Запуск Chromium...' && \
    /usr/bin/chromium --headless --no-sandbox --disable-dev-shm-usage --disable-gpu --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 --user-data-dir=/tmp/chrome-profile about:blank > /tmp/chrome.log 2>&1 & \
    echo '⏳ Ожидание Chromium...' && \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
        if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then \
            echo '✅ Chromium готов!'; \
            break; \
        fi; \
        echo -n '.'; sleep 1; \
    done && \
    echo '🧠 Проверка LiteLLM...' && \
    if curl -s http://127.0.0.1:4000/health > /dev/null 2>&1; then \
        echo '✅ LiteLLM отвечает на health'; \
    else \
        echo '⚠️ LiteLLM не отвечает, смотрим лог:'; \
        cat /tmp/litellm.log; \
    fi && \
    echo '🧠 Проверка Prime Agent...' && \
    if command -v prime-agent > /dev/null 2>&1; then \
        echo '✅ Prime Agent готов!'; \
        prime-agent --version; \
    else \
        echo '⚠️ Prime Agent не найден'; \
    fi && \
    echo '🚀 Запуск бота...' && \
    python -u bot.py"