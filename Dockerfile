FROM python:3.11-slim

# Устанавливаем Chrome для CDP
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем бота
COPY bot.py .

# Переменная для Chrome
ENV CHROME_PATH=/usr/bin/chromium

CMD ["python", "bot.py"]