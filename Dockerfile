FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости для Chrome и Nodriver
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    unzip \
    xvfb \
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
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libpangocairo-1.0-0 \
    libx11-xcb-dev \
    libxcb-dri3-0 \
    libdrm2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Chrome (Nodriver использует его)
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Добавляем Xvfb для виртуального экрана (важно для сервера)
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1

COPY bot.py .
COPY xvfb_start.sh .
RUN chmod +x xvfb_start.sh

CMD ["./xvfb_start.sh"]