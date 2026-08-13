FROM python:3.12-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    curl \
    xvfb \
    libglib2.0-0 \
    libnss3 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# КЛЮЧЕВОЙ МОМЕНТ: устанавливаем banana-browser и принудительно скачиваем Chrome
RUN npm install -g banana-browser && \
    banana-browser install --with-deps --force

# Проверяем, что адаптер скачался
RUN find /usr/local/lib/node_modules -name "patchright*" -type d 2>/dev/null || echo "⚠️ patchright не найден"

ENV PYTHONUNBUFFERED=1
ENV AGENT_BROWSER_ENGINE=patchright
ENV CHROMIUM_PATH=/root/.agent-browser/browsers/chrome-152.0.7977.42/chrome

WORKDIR /app

RUN pip install --no-cache-dir browser-harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "-c", "xvfb-run"]

CMD ["python", "bot.py"]