FROM python:3.11-slim

# Устанавливаем системные зависимости для Playwright
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем и устанавливаем Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Playwright с браузером, но БЕЗ install-deps
RUN playwright install chromium

# Устанавливаем зависимости вручную для новых версий Debian
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm-dev \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libcups2 \
    libxss1 \
    libxrandr2 \
    libgdk-pixbuf-2.0-0 \
    libgtk-3-0 \
    libglib2.0-0 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

# Дополнительно: устанавливаем отсутствующие пакеты (новые имена)
RUN apt-get update && apt-get install -y \
    fonts-unifont \
    fonts-ubuntu \
    libjpeg62-turbo \
    libwebp7 \
    libvpx9 \
    libenchant-2-2 \
    libicu72 \
    libx264-164 \
    libx265-209 \
    && rm -rf /var/lib/apt/lists/*

COPY bot.py .

ENV TELEGRAM_TOKEN_BOT=""
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]