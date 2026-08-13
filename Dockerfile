
FROM python:3.12-slim

RUN apt-get update && apt-get install -y libgtk-3-0 libx11-xcb1 libasound2 xvfb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "playwright==1.53.0" "camoufox[geoip]==0.4.11"
RUN python -m camoufox fetch

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /app/browser-harness/agent-workspace

# Устанавливаем browser-harness как Python пакет
RUN pip install --no-cache-dir browser-harness


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]