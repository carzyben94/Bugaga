FROM python:3.12-slim

# Устанавливаем git, curl и очищаем кэш
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Устанавливаем Plasmate бинарник
RUN curl -fsSL https://plasmate.app/install.sh | sh

WORKDIR /app

# Обновляем pip для стабильности
RUN pip install --no-cache-dir --upgrade pip

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем ПОСЛЕДНЮЮ версию dspy-plasmate из Git
RUN pip install --no-cache-dir git+https://github.com/plasmate-labs/dspy-plasmate.git

COPY . .

# Запускаем Plasmate в фоне и бота
CMD plasmate serve & sleep 2 && python bot.py