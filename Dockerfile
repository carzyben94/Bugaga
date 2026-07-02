FROM mcr.microsoft.com/playwright/python:v1.40.0

WORKDIR /app

# Устанавливаем зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузеры Playwright
RUN playwright install chromium

# Копируем код
COPY . .

# Запускаем
CMD ["python", "app.py"]