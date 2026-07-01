FROM python:3.11-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Node.js 20 из официального архива
RUN curl -fsSL https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.xz | tar -xJ -C /usr/local --strip-components=1

# Устанавливаем Playwright и браузеры
RUN pip install playwright && playwright install chromium && playwright install-deps

# Устанавливаем Goose
RUN npm install -g @block/goose

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем бота
COPY bot.py .

# Команда запуска
CMD ["python", "bot.py"]