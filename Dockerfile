FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    xvfb \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем файлы
COPY bot.py .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir python-telegram-bot playwright cloakbrowser python-dotenv
RUN playwright install chromium

ENV DISPLAY=:99
ENV HEADLESS=false

CMD ["/usr/bin/supervisord"]