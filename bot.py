# test_bot.py - минимальный тест Agnes + browse
import os
import sys
import subprocess
import logging
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== НАСТРОЙКА ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== AGNES (БЕСПЛАТНАЯ LLM) ==========
AGNES_AVAILABLE = False
agnes_llm = None

def init_agnes():
    """Инициализация Agnes через прямой API"""
    global AGNES_AVAILABLE, agnes_llm
    try:
        from langchain_openai import ChatOpenAI
        
        llm = ChatOpenAI(
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",
            temperature=0.7,
            api_key=os.environ.get("AGNES_API_KEY", ""),
        )
        
        # Проверяем
        test_response = llm.invoke("Test")
        if test_response:
            agnes_llm = llm
            AGNES_AVAILABLE = True
            print("✅ Agnes загружена")
            return True
        else:
            print("⚠️ Agnes не отвечает")
            return False
            
    except Exception as e:
        print(f"⚠️ Ошибка Agnes: {e}")
        return False

# Инициализируем
init_agnes()

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_agnes = "✅" if AGNES_AVAILABLE else "❌"
    await update.message.reply_text(
        f"🤖 Бот запущен\n"
        f"Agnes: {status_agnes}\n\n"
        f"/browse <задача> — выполнить задачу\n"
        f"/agnes — проверить статус"
    )

async def agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса Agnes"""
    if AGNES_AVAILABLE:
        await update.message.reply_text(
            "✅ **Agnes готова!**\n\n"
            f"Модель: agnes-2.0-flash\n"
            f"API: https://agnes-ai.com/"
        )
    else:
        await update.message.reply_text(
            "❌ **Agnes не доступна**\n\n"
            "1. Получи ключ на https://agnes-ai.com/\n"
            "2. Добавь AGNES_API_KEY=твой_ключ\n"
            "3. Перезапусти бота"
        )

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить задачу через Agnes"""
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /browse <задача>")
        return
    
    if not AGNES_AVAILABLE:
        await update.message.reply_text("❌ Agnes не доступна. Проверь /agnes")
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🧠 Agnes думает: {task[:100]}...")
    
    try:
        # Простой вызов Agnes
        response = agnes_llm.invoke(f"Ответь кратко: {task}")
        result = response.content
        
        await msg.edit_text(f"✅ **Результат:**\n\n{result[:1500]}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error: {e}", exc_info=True)


# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("agnes", agnes))
    app.add_handler(CommandHandler("browse", browse))
    
    print("✅ Тестовый бот запущен!")
    print(f"🤖 Agnes: {'✅ Доступна' if AGNES_AVAILABLE else '❌ Не доступна'}")
    print("Команды: /start, /agnes, /browse")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()