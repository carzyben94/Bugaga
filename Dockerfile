FROM psyb0t/stealthy-auto-browse:latest

# Отключаем ВСЁ лишнее
ENV DISPLAY=:99 \
    VNC_SERVER=0 \
    NOVNC=0 \
    DISPLAY_WIDTH=1024 \
    DISPLAY_HEIGHT=768 \
    DISPLAY_DEPTH=16

# Копируем бота
WORKDIR /app
COPY bot.py .
COPY requirements.txt .

# Минимальная установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Запускаем с ограничением ресурсов
CMD Xvfb :99 -screen 0 1024x768x16 -ac -noreset & \
    python /app/bot.py