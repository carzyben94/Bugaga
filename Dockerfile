FROM psyb0t/stealthy-auto-browse:latest

ENV DISPLAY=:99 \
    VNC_SERVER=0 \
    NOVNC=0 \
    DISPLAY_WIDTH=1024 \
    DISPLAY_HEIGHT=768 \
    DISPLAY_DEPTH=16

WORKDIR /app
COPY bot.py .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# СКАЧИВАЕМ БРАУЗЕР (ОБЯЗАТЕЛЬНО!)
RUN python3 -c "from camoufox.sync_api import Camoufox; Camoufox()._setup()" || python3 -m camoufox fetch

CMD Xvfb :99 -screen 0 1024x768x16 -ac -noreset & \
    python /app/bot.py