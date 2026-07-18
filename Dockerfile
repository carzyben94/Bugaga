FROM python:3.12-slim

# Установка Chromium и системных зависимостей
RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Установка uv (быстрый менеджер пакетов)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Установка browser-harness для ВСЕХ пользователей
RUN uv tool install --python 3.12 --upgrade --force browser-harness && \
    cp /root/.local/bin/browser-harness /usr/local/bin/ && \
    chmod +x /usr/local/bin/browser-harness

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    PROTOCOLS_DIR=/app/docs

WORKDIR /app

# Установка Python-зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Скачивание протоколов
RUN mkdir -p /app/docs && \
    curl -L -o /app/docs/browser_protocol.json \
    https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json && \
    curl -L -o /app/docs/js_protocol.json \
    https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/js_protocol.json && \
    curl -L -o /app/docs/vbrief-core.schema.json \
    https://raw.githubusercontent.com/deftai/directive/master/content/vbrief/schemas/xbrief-core-0.8.schema.json && \
    curl -L -o /app/docs/browser-logic.json \
    https://raw.githubusercontent.com/carzyben94/Bugaga/main/browser-logic.json && \
    curl -L -o /app/docs/browser-harness-all.json \
    https://raw.githubusercontent.com/carzyben94/Bugaga/main/browser-harness-all.json

# Создание пользователя для безопасного запуска
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

# Порты
EXPOSE 9222 9223 8080

# Запуск демона browser-harness и бота
CMD ["sh", "-c", "/usr/local/bin/browser-harness --daemon & python -u bot.py"]