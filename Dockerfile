FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

# Устанавливаем шрифты
RUN apt-get update && apt-get install -y \
    fonts-liberation \
    fonts-dejavu-core \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    fonts-noto-color-emoji \
    fonts-roboto \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости с принудительной переустановкой
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --force-reinstall openai

# Копируем весь проект
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]