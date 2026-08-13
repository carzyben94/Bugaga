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
RUN npm install -g banana-browser \
    && banana-browser install

ENV PYTHONUNBUFFERED=1
ENV BH_DOMAIN_SKILLS=1
ENV BH_AGENT_WORKSPACE=/app/browser-harness/agent-workspace
# Указываем banana-browser как движок
ENV AGENT_BROWSER_ENGINE=patchright
# Путь к браузеру banana-browser
ENV CHROMIUM_PATH=/root/.cache/banana-browser/chrome/linux-129.0.6668.89/chrome-linux64/chrome

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /app/browser-harness/agent-workspace

# Устанавливаем browser-harness
RUN pip install --no-cache-dir browser-harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запускаем через xvfb для имитации графического экрана
CMD ["xvfb-run", "--auto-servernum"]

CMD ["python", "bot.py"]