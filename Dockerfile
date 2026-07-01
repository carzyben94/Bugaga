FROM python:3.11-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    bzip2 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Node.js 20 (нужен для npm и MCP)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Устанавливаем Playwright и браузеры
RUN pip install playwright && playwright install chromium && playwright install-deps

# Скачиваем и устанавливаем Goose вручную
RUN curl -fsSL https://github.com/block/goose/releases/download/stable/goose-x86_64-unknown-linux-gnu.tar.bz2 -o /tmp/goose.tar.bz2 \
    && mkdir -p /tmp/goose_extract \
    && tar -xjf /tmp/goose.tar.bz2 -C /tmp/goose_extract \
    && mkdir -p /root/.local/bin \
    && mv /tmp/goose_extract/goose /root/.local/bin/goose \
    && chmod +x /root/.local/bin/goose \
    && rm -rf /tmp/goose.tar.bz2 /tmp/goose_extract

# Устанавливаем Playwright MCP глобально (ВАЖНО для Goose!)
RUN npm install -g @playwright/mcp

# Добавляем Goose в PATH
ENV PATH="/root/.local/bin:${PATH}"

# Убедись что git установлен
RUN apt-get update && apt-get install -y git

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем бота
COPY bot.py .

# Проверяем установку
RUN goose --version && npx @playwright/mcp --version || echo "Playwright MCP installed"

# Команда запуска
CMD ["python", "bot.py"]