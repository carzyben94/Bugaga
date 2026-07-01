FROM python:3.11-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Playwright и браузеры
RUN pip install playwright && playwright install chromium && playwright install-deps

# Устанавливаем Goose через официальный скрипт с GitHub
RUN curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | bash

# Добавляем Goose в PATH (если скрипт не сделал это автоматически)
ENV PATH="/root/.goose/bin:${PATH}"

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем бота
COPY bot.py .

# Проверяем установку Goose (опционально)
RUN goose --version || echo "Goose installed but version check failed"

# Команда запуска
CMD ["python", "bot.py"]