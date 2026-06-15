import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Flask для Render
app_flask = Flask(__name__)

@app_flask.route('/')
def health():
    return "Bot is running!", 200

# Telegram бот
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENROUTER_KEY = os.environ["OPENROUTER_API_KEY"]

# Список бесплатных моделей
MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "google/gemma-2-2b-it:free",
    "qwen/qwen-2.5-7b-instruct:free"
]

async def start(update: Update, context):
    await update.message.reply_text(
        "🤖 Бот с AI работает!\n\n"
        "Просто напиши любой вопрос, я отвечу через нейросеть.\n\n"
        "Команды:\n"
        "/start - Запуск\n"
        "/help - Помощь\n"
        "/info - Инфо\n"
        "/ping - Проверка"
    )

async def help_command(update: Update, context):
    await update.message.reply_text(
        "📚 Доступные команды:\n"
        "/start - Приветствие\n"
        "/help - Справка\n"
        "/info - Информация\n"
        "/ping - Проверка\n\n"
        "Просто напиши текст - я отвечу AI!"
    )

async def info(update: Update, context):
    await update.message.reply_text(
        "ℹ️ Бот на Python + OpenRouter\n"
        f"Доступно моделей: {len(MODELS)}\n"
        "Автопереключение при лимитах\n"
        "Хостинг: Render.com"
    )

async def ping(update: Update, context):
    await update.message.reply_text("🏓 Pong!")

async def ask_ai(update: Update, context):
    user_message = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    for model in MODELS:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": user_message}],
                    "max_tokens": 500,
                    "temperature": 0.7
                },
                timeout=30
            )
            
            if response.status_code == 200:
                reply = response.json()['choices'][0]['message']['content']
                await update.message.reply_text(f"{reply}\n\n_— {model}_", parse_mode="Markdown")
                return
            else:
                print(f"Модель {model} ошибка: {response.status_code}")
                continue
                
        except Exception as e:
            print(f"Ошибка {model}: {e}")
            continue
    
    await update.message.reply_text("❌ Все AI модели перегружены. Попробуй позже!")

def run_bot():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_ai))
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)
