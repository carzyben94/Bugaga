import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydantic import BaseModel
# from pydoll.browser import Browser  # раскомментируй когда понадобится

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Пример Pydantic модели
class UserData(BaseModel):
    user_id: int
    username: str | None = None
    first_name: str

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Валидация через Pydantic
    user_data = UserData(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    await update.message.reply_text(
        f"Привет, {user_data.first_name}! 👋\n"
        f"ID: {user_data.user_id}\n"
        "Я работаю на Railway!"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()