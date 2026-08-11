FROM python:3.12-slim

# Устанавливаем git и curl
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Скачиваем Plasmate v0.5.1 напрямую из GitHub
RUN curl -fsSL -o /usr/local/bin/plasmate \
    https://github.com/plasmate-labs/plasmate/releases/download/v0.5.1/plasmate-x86_64-linux \
    && chmod +x /usr/local/bin/plasmate

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir git+https://github.com/plasmate-labs/dspy-plasmate.git

COPY . .

CMD plasmate serve & sleep 2 && python bot.py