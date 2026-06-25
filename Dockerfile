FROM python:3.11-slim

WORKDIR /app

# Устанавливаем минимальные зависимости
RUN apt-get update && apt-get install -y \
    xvfb \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libcups2 \
    libxss1 \
    libxrandr2 \
    libatk1.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1

COPY bot.py .

# Запускаем Xvfb и бота в одной команде
CMD Xvfb :99 -screen 0 1280x1024x24 & sleep 2 && python bot.py