# Используем легкий официальный образ Python
FROM python:3.11-slim-bullseye

# Устанавливаем системную зависимость, необходимую для browsy-ai
RUN apt-get update && apt-get install -y \
    libssl1.1 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

# Команда для запуска бота
CMD ["python", "bot.py"]