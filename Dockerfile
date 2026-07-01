FROM python:3.11-slim

# Устанавливаем зависимости для Playwright и Node.js
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Node.js 20.x (альтернативный способ)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    || apt-get install -y nodejs npm

# Если не установился через deb.nodesource, ставим через официальный репозиторий
RUN if ! command -v node &> /dev/null; then \
        curl -fsSL https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.xz | tar -xJ -C /usr/local --strip-components=1; \
    fi

# Устанавливаем Playwright и браузеры
RUN pip install playwright && playwright install chromium && playwright install-deps

# Устанавливаем Goose через npm
RUN npm install -g @block/goose

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем бота
COPY bot.py .

# Команда запуска
CMD ["python", "bot.py"]