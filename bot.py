import os, requests, json, threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Flask приложение
app_flask = Flask(__name__)

@app_flask.route('/')
def health_check():
    return "Бот работает!", 200

# Модели OpenRouter
MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "google/gemma-2-2b-it:free"
]

# Переменные окружения (правильные имена)
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]  # ← изменил
OPENROUTER_KEY = os.environ["OPENROUTER_API_KEY"]

async def start(update, context):
    await update.message.reply_text("Я жив! Отвечаю через OpenRouter")

async def chat(update, context):
    user_msg = update.message.text
    
    for model in MODELS:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": user_msg}]},
                timeout=30
            )
            if resp.status_code == 200:
                reply = resp.json()['choices'][0]['message']['content']
                await update.message.reply_text(f"{reply}\n\n— {model}")
                return
        except:
            continue
    
    await update.message.reply_text("Все модели перегружены, попробуй позже")

def run_telegram():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_telegram)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)
