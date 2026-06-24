FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    xvfb \
    xauth \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем bot.py
COPY bot.py .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir python-telegram-bot playwright cloakbrowser python-dotenv

# Устанавливаем Playwright браузер
RUN playwright install chromium

# Переменные окружения
ENV DISPLAY=:99
ENV HEADLESS=false

# Запускаем Xvfb в фоне и бота
CMD Xvfb :99 -screen 0 1920x1080x24 -ac & python bot.py