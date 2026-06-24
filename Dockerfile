FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip xvfb \
    libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 \
    libxdamage1 libxi6 libxtst6 libnss3 libcups2 \
    libxss1 libxrandr2 libasound2 libatk-bridge2.0-0 \
    libgtk-3-0 libgbm1 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем ВСЕ .py файлы
COPY *.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]