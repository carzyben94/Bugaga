FROM python:3.12-slim

# Устанавливаем зависимости для работы Chrome в контейнере [citation:1]
RUN apt-get update && apt-get install -y \
    curl \
    chromium \
    xvfb \
    git \
    libglib2.0-0 \
    libnss3 \
    libx11-xcb1 \
    # ... и другие зависимости
    && rm -rf /var/lib/apt/lists/*

FROM cloakhq/cloakbrowser

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /app/browser-harness/agent-workspace

# Устанавливаем browser-harness как Python пакет
RUN pip install --no-cache-dir browser-harness


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]