FROM python:3.14-slim 

# Только самое необходимое для Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Минимальные переменные
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "bot.py"]