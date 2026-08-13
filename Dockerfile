FROM python:3.12-slim

# Устанавливаем зависимости для Firefox и Camoufox
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    unzip \
    libxtst6 \
    libxrandr2 \
    libxrender1 \
    libcups2 \
    libdbus-glib-1-2 \
    libx11-xcb1 \
    libxcb-shm0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libasound2 \
    libpulse0 \
    libvdpau1 \
    libva2 \
    libgl1-mesa-dri \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Camoufox (специальная сборка Firefox)
RUN wget -O camoufox.tar.bz2 "https://github.com/comex/camoufox/releases/latest/download/camoufox-linux-x86_64.tar.bz2" && \
    tar -xjf camoufox.tar.bz2 -C /opt/ && \
    rm camoufox.tar.bz2 && \
    ln -s /opt/camoufox/camoufox /usr/local/bin/camoufox

# Устанавливаем Playwright для управления Camoufox
RUN pip install playwright && \
    playwright install firefox

WORKDIR /app

RUN mkdir -p /app/logs /app/screenshots /app/browser-harness/agent-workspace

# Устанавливаем browser-harness как Python пакет
RUN pip install --no-cache-dir browser-harness


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]