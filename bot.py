```python
import os
import time
import logging
import json
import requests
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from flask import Flask, request
import telebot
from bs4 import BeautifulSoup
from datetime import datetime
from super_agent import SuperAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("start_time.txt", "w") as f:
    f.write(str(time.time()))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== СУПЕР-АГЕНТ =====
super_agent = SuperAgent({
    'GITHUB_TOKEN': GITHUB_TOKEN,
    'RENDER_API_KEY': RENDER_API_KEY,
    'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
    'OPENROUTER_API_KEY': OPENROUTER_API_KEY,
    'GITHUB_REPO': GITHUB_REPO,
    'RENDER_SERVICE_ID': RENDER_SERVICE_ID
})

# ===== СТАТУС МОДУЛЬ =====
try:
    from status import register_status_full
    register_status_full(bot)
    print("Status module loaded")
except Exception as e:
    print(f"Status not loaded: {e}")

# ===== ЛОГИ В ЧАТ =====
def send_log_to_admin(action, details=None, status="info"):
    if not ADMIN_CHAT_ID:
        return
    emoji = "✅" if status == "success" else "🔴" if status == "error" else "ℹ️"
    timestamp = time.strftime("%H:%M:%S")
    try:
        bot.send_message(ADMIN_CHAT_ID, f"{emoji} [{timestamp}] {action}: {details}")
    except:
        pass

def log_action(action, details=None, status="info", send=True):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "action": action, "status": status, "details": details}
    try:
        with open("agent_actions.log", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except:
        pass
    if send:
        send_log_to_admin(action, details, status)

def get_last_errors(limit=5):
    try:
        if not os.path.exists("agent_actions.log"):
            return []
        with open("agent_actions.log", "r") as f:
            lines = f.readlines()
        errors = []
        for line in reversed(lines[-100:]):
            try:
                log = json.loads(line)
                if log.get("status") == "error":
                    errors.append(log.get("details", ""))
                    if len(errors) >= limit:
                        break
