FROM python:3.11-slim

# Устанавливаем системные зависимости для Pillow
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py browser.py .

CMD ["python", "bot.py"]