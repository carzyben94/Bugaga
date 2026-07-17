FROM python:3.14-slim 

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    PROTOCOLS_DIR=/app/docs

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Скачивание протоколов при сборке
RUN mkdir -p /app/docs && \
    curl -L -o /app/docs/browser_protocol.json \
    https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json && \
    curl -L -o /app/docs/js_protocol.json \
    https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/js_protocol.json

# Создаём папку для данных
RUN mkdir -p /app/data

# В конце (перед CMD)
VOLUME ["/app/data"]

CMD ["python", "-u", "bot.py"]