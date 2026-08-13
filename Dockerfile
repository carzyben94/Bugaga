FROM python:3.12-slim

# Устанавливаем зависимости для работы Chrome в контейнере [citation:1]
RUN apt-get update && apt-get install -y \
    curl \
    xvfb \
    git \
    libglib2.0-0 \
    libnss3 \
    libx11-xcb1 \
    # ... и другие зависимости
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Veil из GitHub [citation:2]
RUN pip install git+https://github.com/acunningham-ship-it/veilbrowser.git#subdirectory=python

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]