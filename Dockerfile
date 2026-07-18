FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ===== УКАЗЫВАЕМ ПУТЬ К CHROMIUM =====
ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    CHROME_PATH=/usr/bin/chromium \
    BROWSER_EXECUTABLE=/usr/bin/chromium

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "bot.py"]