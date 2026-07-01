FROM python:3.11-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    nodejs \
    npm \
    git \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Playwright и браузеры
RUN pip install playwright && playwright install chromium && playwright install-deps

# Устанавливаем Goose через pip (правильный способ)
RUN pip install goose-ai

# ИЛИ устанавливаем через npm (если есть официальный пакет)
# RUN npm install -g goose-ai

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем бота
COPY bot.py .

# Команда запуска
CMD ["python", "bot.py"]