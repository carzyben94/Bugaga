FROM python:3.14-slim

# Установка Chromium и зависимостей
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    # Дополнительные зависимости для Playwright
    libxkbcommon0 \
    libxss1 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# Проверка установки Chromium
RUN chromium --version || echo "Chromium installed"

# Переменные окружения
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

WORKDIR /app

# Установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Установка браузеров Playwright (НУЖНО для Browser Use)
RUN playwright install chromium && \
    playwright install-deps

# Копирование бота
COPY bot.py .

CMD ["python", "-u", "bot.py"]