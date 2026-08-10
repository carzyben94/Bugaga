FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    libglib2.0-0 \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV BH_DOMAIN_SKILLS=1
ENV BH_AGENT_WORKSPACE=/app/browser-harness/agent-workspace

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /app/browser-harness/agent-workspace

RUN pip install --no-cache-dir browser-harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD sh -c "echo '🚀 Запуск Chromium...' && \
    /usr/bin/chromium \
        --headless=new \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --disable-software-rasterizer \
        --disable-dev-tools \
        --disable-extensions \
        --disable-component-extensions-with-background-pages \
        --disable-default-apps \
        --disable-sync \
        --disable-domain-reliability \
        --disable-client-side-phishing-detection \
        --disable-crash-reporter \
        --disable-component-update \
        --disable-logging \
        --disable-prompt-on-repost \
        --disable-background-networking \
        --disable-background-timer-throttling \
        --disable-backgrounding-occluded-windows \
        --disable-breakpad \
        --disable-ipc-flooding-protection \
        --disable-renderer-backgrounding \
        --disable-features=ChromeWhatsNewUI,ChromeTips,AudioServiceOutOfProcess,IsolateOrigins,site-per-process,TranslateUI,MediaRouter \
        --disable-site-isolation-trials \
        --disable-blink-features=AutomationControlled \
        --disable-automation \
        --no-default-browser-check \
        --no-first-run \
        --no-experiments \
        --no-pings \
        --no-service-autorun \
        --force-color-profile=srgb \
        --metrics-recording-only \
        --password-store=basic \
        --use-mock-keychain \
        --export-tagged-pdf \
        --enable-features=NetworkService,NetworkServiceInProcess \
        --window-position=100,100 \
        --window-size=1280,800 \
        --remote-debugging-port=9222 \
        --remote-debugging-address=127.0.0.1 \
        --user-data-dir=/tmp/chrome-profile \
        --user-agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' \
        about:blank > /app/logs/chromium.log 2>&1 & \
    echo '⏳ Ожидание Chromium...' && \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
        if curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then \
            echo '✅ Chromium готов!'; \
            break; \
        fi; \
        echo -n '.'; \
        sleep 1; \
    done && \
    echo '🚀 Запуск бота...' && \
    python -u bot.py 2>&1 | tee /app/logs/bot.log"