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
# СОЗДАЁМ APPEND_SYSTEM.md ДЛЯ PRIME AGENT
# ============================================================
RUN echo '## Browser Harness Integration

Всегда используй browser-harness для работы с браузером.

### Основные функции:
- new_tab(url) — открыть новую вкладку (используй для первого перехода)
- goto_url(url) — переход по URL
- wait_for_load() — ждать загрузки
- click_at_xy(x, y) — клик по координатам (CSS пиксели)
- type_text(text) — ввод текста
- press_key(key) — нажать клавишу
- capture_screenshot(path) — скриншот
- page_info() — информация о странице
- js(expression) — выполнить JavaScript
- scroll(x, y) — прокрутка
- cdp(command) — доступ к Chrome DevTools Protocol

### Правила:
1. Всегда используй new_tab(url) для первого перехода
2. После навигации всегда вызывай wait_for_load()
3. После каждого действия делай скриншот
4. Для поиска элементов используй js() или cdp("Accessibility.getFullAXTree")
5. Для клика по элементу: найди координаты через DOM.getBoxModel и используй click_at_xy()

### Пример:
new_tab("https://wikipedia.org")
wait_for_load()
capture_screenshot("page.png")
' > /root/.prime/agent/APPEND_SYSTEM.md

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