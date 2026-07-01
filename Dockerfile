FROM python:3.11-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Node.js 20 (нужен для npm и Goose)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Устанавливаем Playwright и браузеры
RUN pip install playwright && playwright install chromium && playwright install-deps

# Устанавливаем Goose через npm (ПРАВИЛЬНЫЙ СПОСОБ!)
RUN npm install -g @block/goose

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем бота
COPY bot.py .

# Команда запуска
CMD ["python", "bot.py"]