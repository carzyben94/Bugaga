FROM python:3.11-slim-bullseye

# Устанавливаем все зависимости для сборки Rust-пакетов с OpenSSL
RUN apt-get update && apt-get install -y \
    libssl1.1 \
    libssl-dev \
    build-essential \
    curl \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Rust через rustup
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]