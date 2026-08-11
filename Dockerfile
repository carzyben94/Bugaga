FROM python:3.12-slim

# Устанавливаем Plasmate бинарник (вместо Chromium)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Скачиваем и устанавливаем Plasmate
RUN curl -fsSL https://plasmate.app/install.sh | sh

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Plasmate будет работать как отдельный сервер + ваш бот
CMD ["python", "bot.py"]