FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright сам установит все зависимости
RUN playwright install chromium
RUN playwright install-deps

COPY . .

CMD ["python", "bot.py"]