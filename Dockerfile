FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

RUN uv tool install --python 3.12 --upgrade --force browser-harness

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    PROTOCOLS_DIR=/app/docs

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/docs && \
    curl -L -o /app/docs/browser_protocol.json \
    https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json && \
    curl -L -o /app/docs/js_protocol.json \
    https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/js_protocol.json && \
    curl -L -o /app/docs/vbrief-core.schema.json \
    https://raw.githubusercontent.com/deftai/directive/master/content/vbrief/schemas/xbrief-core-0.8.schema.json && \
    curl -L -o /app/docs/browser-logic.json \
    https://raw.githubusercontent.com/carzyben94/Bugaga/main/browser-logic.json && \
    curl -L -o /app/docs/browser-harness-all.json \
    https://raw.githubusercontent.com/carzyben94/Bugaga/main/browser-harness-all.json

EXPOSE 9222 9223 8080

# Просто запускаем от root
CMD ["sh", "-c", "/root/.local/bin/browser-harness --daemon & python -u bot.py"]