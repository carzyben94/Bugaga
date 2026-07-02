FROM python:3.11-slim

# Установка зависимостей для Chrome/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Установка Chromium
RUN apt-get update && apt-get install -y chromium \
    && rm -rf /var/lib/apt/lists/*

# Установка переменной для Chromium
ENV CHROME_PATH=/usr/bin/chromium

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Установка прав на выполнение
RUN chmod +x bot.py

CMD ["python", "bot.py"]