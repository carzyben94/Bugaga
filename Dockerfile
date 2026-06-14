FROM lightpanda/browser:nightly
WORKDIR /app
RUN apt-get update && apt-get install -y python3 python3-pip
COPY requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages
COPY bot.py .
CMD lightpanda serve --host 0.0.0.0 --port 9222 & sleep 3 && python3 bot.py
