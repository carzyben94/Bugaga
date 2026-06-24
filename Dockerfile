FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

RUN pip install cloakbrowser
RUN python -m cloakbrowser install

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-3-0 libx11-xcb1 libasound2 libxtst6 libxss1 \
    libnss3 libxcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxi6 libxrandr2 libxrender1 libatk1.0-0 libcups2 \
    libdrm2 libgbm1 libpango-1.0-0 libatk-bridge2.0-0 \
    xvfb && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /root/.cloakbrowser /root/.cloakbrowser
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "bot.py"]