FROM python:3.12-slim

# Устанавливаем зависимости и banana-browser
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

# Устанавливаем Node.js (нужен для banana-browser)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем banana-browser глобально
RUN npm install -g banana-browser && \
    banana-browser install --with-deps

ENV PYTHONUNBUFFERED=1
ENV BH_DOMAIN_SKILLS=1
ENV BH_AGENT_WORKSPACE=/app/browser-harness/agent-workspace
ENV AGENT_BROWSER_ENGINE=patchright

# Динамически находим реальный путь к Chrome
RUN CHROME_PATH=$(find /root/.cache/banana-browser -name "chrome" -type f 2>/dev/null | head -1) && \
    if [ -n "$CHROME_PATH" ]; then \
        echo "✅ Found Chrome at: $CHROME_PATH" && \
        echo "CHROMIUM_PATH=$CHROME_PATH" >> /etc/environment; \
    else \
        echo "❌ Chrome not found!"; \
    fi

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /app/browser-harness/agent-workspace

# Устанавливаем browser-harness
RUN pip install --no-cache-dir browser-harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ✅ ОДНА КОМАНДА CMD: запускаем xvfb и бота вместе
CMD ["bash", "-c", "xvfb-run --auto-servernum python bot.py"]