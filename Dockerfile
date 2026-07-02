FROM python:3.11-slim

# Установка зависимостей
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Проверка установки
RUN chromium --version

# Установка переменных окружения
ENV CHROME_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование бота
COPY bot.py .

# Команда запуска
CMD ["python", "-u", "bot.py"]