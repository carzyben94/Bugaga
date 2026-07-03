FROM python:3.11-slim

# Установка переменных окружения (ДО установки пакетов)
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROMIUM_PATH=/usr/bin/chromium

# Установка всех необходимых зависимостей для Chromium и Pydoll
RUN apt-get update && apt-get install -y \
    # Базовые утилиты
    wget \
    gnupg \
    unzip \
    curl \
    ca-certificates \
    # Chromium и драйвер
    chromium \
    chromium-driver \
    # Шрифты для корректного отображения
    fonts-liberation \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-thai-tlwg \
    fonts-freefont-ttf \
    # Системные библиотеки для Chromium
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    # Дополнительные библиотеки для стабильности
    libxtst6 \
    libxshmfence1 \
    libxkbcommon0 \
    libxfixes3 \
    && rm -rf /var/lib/apt/lists/*

# Проверка установки Chromium с выводом версии
RUN chromium --version || echo "❌ Chromium не установлен!"

# Создаем директорию для логов
RUN mkdir -p /app/logs

WORKDIR /app

# Копирование и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    # Проверка установки Pydoll
    python -c "import pydoll; print(f'✅ Pydoll version: {pydoll.__version__ if hasattr(pydoll, \"__version__\") else \"unknown\"}')" || echo "⚠️ Pydoll не установлен"

# Установка Playwright браузера (для обратной совместимости)
RUN playwright install chromium || echo "⚠️ Playwright install skipped"

# Копирование бота
COPY bot.py .

# Создаем пользователя для безопасности (опционально)
# RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
# USER appuser

# Проверка наличия файлов
RUN ls -la && echo "✅ Файлы скопированы"

# Команда запуска с перенаправлением вывода в файл и консоль
CMD ["sh", "-c", "python -u bot.py 2>&1 | tee -a /app/logs/bot.log"]