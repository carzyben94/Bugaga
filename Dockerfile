FROM python:3.11-slim

# Системные зависимости для Camoufox
RUN apt-get update && apt-get install -y \
    libgtk-3-0 \
    libx11-xcb1 \
    libasound2 \
    libxtst6 \
    libxss1 \
    libnss3 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libpango-1.0-0 \
    libatk-bridge2.0-0 \
    --no-install-recommends

WORKDIR /app
COPY requirements.txt .
RUN pip install -U "camoufox[geoip]"
RUN python3 -m camoufox fetch  # Скачиваем браузер при сборке

COPY . .
CMD ["python", "bot.py"]