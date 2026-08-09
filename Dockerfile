FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    git \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV PATH="/root/.local/bin:${PATH}"
ENV BH_DOMAIN_SKILLS=1
ENV BH_AGENT_WORKSPACE=/app/browser-harness/agent-workspace

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /root/.prime-agent /root/.prime/agent

RUN pip install --no-cache-dir uv
RUN uv tool install --python 3.12 --upgrade --force browser-harness

RUN curl -fsSL https://app.primeintellect.ai/prime-agent/install.sh | sh

RUN pip install 'fastapi==0.124.4' 'uvicorn==0.34.0' && \
    pip install 'litellm[proxy]==1.83.12'

# ============================================================
# СОЗДАЁМ SETTINGS.JSON
# ============================================================
RUN echo '{' > /root/.prime/agent/settings.json && \
    echo '  "defaultThinkingLevel": "xhigh",' >> /root/.prime/agent/settings.json && \
    echo '  "defaultProvider": "litellm",' >> /root/.prime/agent/settings.json && \
    echo '  "defaultModel": "agnes-2.0-flash",' >> /root/.prime/agent/settings.json && \
    echo '  "compaction": {' >> /root/.prime/agent/settings.json && \
    echo '    "enabled": true,' >> /root/.prime/agent/settings.json && \
    echo '    "reserveTokens": 8192,' >> /root/.prime/agent/settings.json && \
    echo '    "keepRecentTokens": 16384' >> /root/.prime/agent/settings.json && \
    echo '  },' >> /root/.prime/agent/settings.json && \
    echo '  "retry": {' >> /root/.prime/agent/settings.json && \
    echo '    "maxRetries": 3,' >> /root/.prime/agent/settings.json && \
    echo '    "baseDelayMs": 1000,' >> /root/.prime/agent/settings.json && \
    echo '    "provider": {' >> /root/.prime/agent/settings.json && \
    echo '      "timeoutMs": 120000' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '    }' >> /root/.prime/agent/settings.json && \
    echo '  },' >> /root/.prime/agent/settings.json && \
    echo '  "thinkingBudgets": {' >> /root/.prime/agent/settings.json && \
    echo '    "off": 0,' >> /root/.prime/agent/settings.json && \
    echo '    "minimal": 1024,' >> /root/.prime/agent/settings.json && \
    echo '    "low": 4096,' >> /root/.prime/agent/settings.json && \
    echo '    "medium": 8192,' >> /root/.prime/agent/settings.json && \
    echo '    "high": 16384,' >> /root/.prime/agent/settings.json && \
    echo '    "xhigh": 32768' >> /root/.prime/agent/settings.json && \
    echo '  }' >> /root/.prime/agent/settings.json && \
    echo '}' >> /root/.prime/agent/settings.json

# ============================================================
# СОЗДАЁМ APPEND_SYSTEM.md
# ============================================================
RUN echo '## Browser Harness Integration' > /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'Всегда используй browser-harness для работы с браузером.' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '### ВАЖНО: НЕ ИСПОЛЬЗУЙ import !!!' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'Все функции уже доступны в глобальном пространстве.' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'НЕ пиши from browser_harness import ...' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'НЕ пиши browser_harness.new_tab() — просто new_tab()' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'НЕ пиши BrowserHarness()' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '### ВАЖНО: НЕ ИСПОЛЬЗУЙ browser. !!!' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'Все функции вызываются напрямую, без префикса browser.' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '### ВАЖНО: НЕ ИСПОЛЬЗУЙ browser_harness. !!!' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'Все функции вызываются напрямую, без префикса browser_harness.' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '### Уровень мышления:' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'Для сложных многошаговых задач используй высокий уровень мышления.' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'Для простых задач используй низкий уровень.' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '### Основные функции (вызывай напрямую):' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- new_tab(url) — открыть новую вкладку (используй для первого перехода)' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- goto_url(url) — переход по URL' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- wait_for_load() — ждать загрузки' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- click_at_xy(x, y) — клик по координатам (CSS пиксели)' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- type_text(text) — ввод текста' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- press_key(key) — нажать клавишу' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- capture_screenshot(path) — сделать скриншот (НЕ screenshot!)' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- page_info() — информация о странице' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- js(expression) — выполнить JavaScript' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- scroll(x, y) — прокрутка' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '- cdp(command) — доступ к Chrome DevTools Protocol' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '### ПРАВИЛЬНЫЙ ПРИМЕР:' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'new_tab("https://wikipedia.org")' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'wait_for_load()' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'capture_screenshot("page.png")' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'result = js('\''() => { const text = document.body.innerText; const m = text.match(/основан[а]?\\s*в\\s*(\\d{4})/i); return m ? m[1] : null; }'\'')' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo 'print(f"Результат: {result}")' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '### Правила:' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '1. НЕ используй import!' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '2. НЕ используй browser. — вызывай функции напрямую!' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '3. НЕ используй browser_harness. — вызывай функции напрямую!' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '4. Всегда используй new_tab(url) для первого перехода' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '5. После навигации всегда вызывай wait_for_load()' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '6. Используй capture_screenshot() для скриншотов (НЕ screenshot!)' >> /root/.prime/agent/APPEND_SYSTEM.md && \
    echo '7. Для поиска элементов используй js()' >> /root/.prime/agent/APPEND_SYSTEM.md

RUN node --version && prime-agent --version || echo "⚠️ Prime Agent установлен"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY config.yaml /app/config.yaml

CMD sh -c "echo '🚀 Запуск LiteLLM...' && \
    litellm --config /app/config.yaml --port 4000 --host 0.0.0.0 >> /app/logs/litellm.log 2>&1 & \
    sleep 5 && \
    echo '✅ LiteLLM запущен (порт 4000)' && \
    echo '🚀 Запуск Chromium...' && \
    /usr/bin/chromium --headless --no-sandbox --disable-dev-shm-usage --disable-gpu --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 --user-data-dir=/tmp/chrome-profile about:blank >> /app/logs/chromium.log 2>&1 & \
    echo '⏳ Ожидание Chromium...' && \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
        if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then \
            echo '✅ Chromium готов!'; \
            break; \
        fi; \
        echo -n '.'; sleep 1; \
    done && \
    echo '🧠 Проверка LiteLLM...' && \
    if curl -s http://127.0.0.1:4000/health > /dev/null 2>&1; then \
        echo '✅ LiteLLM отвечает на health' >> /app/logs/litellm.log; \
    else \
        echo '⚠️ LiteLLM не отвечает, смотрим лог:' && \
        cat /app/logs/litellm.log; \
    fi && \
    echo '🧠 Проверка Prime Agent...' && \
    if command -v prime-agent > /dev/null 2>&1; then \
        echo '✅ Prime Agent готов!'; \
        prime-agent --version; \
    else \
        echo '⚠️ Prime Agent не найден'; \
    fi && \
    echo '🚀 Запуск бота...' && \
    python -u bot.py >> /app/logs/bot.log 2>&1"