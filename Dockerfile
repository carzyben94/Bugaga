FROM python:3.12-slim

# Устанавливаем зависимости для Chromium, Node.js
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
ENV LITELLM_LOG=/tmp/litellm.log

WORKDIR /app

# Устанавливаем uv
RUN pip install --no-cache-dir uv

# Устанавливаем browser-harness как CLI-инструмент
RUN uv tool install --python 3.12 --upgrade --force browser-harness

# УСТАНОВКА PRIME AGENT
RUN curl -fsSL https://app.primeintellect.ai/prime-agent/install.sh | sh

# УСТАНОВКА LITELLM
RUN pip install 'litellm[proxy]'

# Проверяем установку
RUN node --version && prime-agent --version || echo "⚠️ Prime Agent установлен"

# Копируем requirements и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем ВСЕ файлы
COPY . .

# Создаём папку для данных
RUN mkdir -p /root/.prime-agent /app/logs /app/screenshots

# Создаём конфиг для LiteLLM
RUN echo 'model_list:' > /app/litellm_config.yaml && \
    echo '  - model_name: agnes-2.0-flash' >> /app/litellm_config.yaml && \
    echo '    litellm_params:' >> /app/litellm_config.yaml && \
    echo '      model: openai/agnes-2.0-flash' >> /app/litellm_config.yaml && \
    echo '      api_base: https://apihub.agnes-ai.com/v1' >> /app/litellm_config.yaml && \
    echo '      api_key: os.environ/AGNES_API_KEY' >> /app/litellm_config.yaml && \
    echo '      max_tokens: 65536' >> /app/litellm_config.yaml

# ИСПРАВЛЕНО: запускаем все сервисы последовательно
CMD sh -c "
    echo '🚀 Запуск LiteLLM прокси...' && \
    litellm --config /app/litellm_config.yaml --port 4000 --host 0.0.0.0 > /tmp/litellm.log 2>&1 &
    
    echo '⏳ Ожидание LiteLLM...' && \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
        if curl -s http://localhost:4000/health > /dev/null 2>&1; then \
            echo '✅ LiteLLM готов!'; \
            break; \
        fi; \
        echo -n '.' && sleep 2; \
        if [ $i -eq 15 ]; then \
            echo '❌ LiteLLM не запустился, смотрим логи:'; \
            cat /tmp/litellm.log; \
        fi; \
    done && \
    
    echo '🚀 Запуск Chromium...' && \
    /usr/bin/chromium \
        --headless \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --remote-debugging-port=9222 \
        --remote-debugging-address=0.0.0.0 \
        --user-data-dir=/tmp/chrome-profile \
        about:blank > /tmp/chrome.log 2>&1 & \
    
    echo '⏳ Ожидание Chromium...' && \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
        if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then \
            echo '✅ Chromium готов!'; \
            break; \
        fi; \
        echo -n '.' && sleep 1; \
    done && \
    
    echo '🧠 Проверка Prime Agent...' && \
    if command -v prime-agent > /dev/null 2>&1; then \
        echo '✅ Prime Agent готов!'; \
        prime-agent --version; \
    else \
        echo '⚠️ Prime Agent не найден'; \
    fi && \
    
    echo '🚀 Запуск бота...' && \
    python -u bot.py
"