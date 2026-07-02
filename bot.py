# test_bot.py - cdp-use с прямой установкой
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

# ========== УСТАНОВКА CDP-USE ПРЯМО СЕЙЧАС ==========

def install_cdp_use():
    """Принудительная установка cdp-use"""
    try:
        print("⏳ Устанавливаю cdp-use...")
        
        # Пробуем через pip
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'cdp-use', '--no-cache-dir'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ cdp-use установлен")
            return True
        else:
            print(f"❌ Ошибка: {result.stderr}")
            
            # Пробуем через git если pip не работает
            print("⏳ Пробую установить через git...")
            result2 = subprocess.run([
                sys.executable, '-m', 'pip', 'install', 
                'git+https://github.com/brilliant-dev/cdp-use.git'
            ], capture_output=True, text=True)
            
            if result2.returncode == 0:
                print("✅ cdp-use установлен через git")
                return True
            else:
                print(f"❌ Ошибка git: {result2.stderr}")
                return False
                
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

# Устанавливаем при запуске
print("⏳ Проверка cdp-use...")
try:
    import cdp_use
    print("✅ cdp-use уже установлен")
    CDP_AVAILABLE = True
except ImportError:
    print("⚠️ cdp-use не найден, устанавливаю...")
    if install_cdp_use():
        CDP_AVAILABLE = True
    else:
        CDP_AVAILABLE = False

# ========== AGNES ==========
AGNES_AVAILABLE = False
agnes_llm = None

def init_agnes():
    global AGNES_AVAILABLE, agnes_llm
    try:
        from langchain_openai import ChatOpenAI
        
        api_key = os.environ.get("AGNES_API_KEY", "")
        if not api_key:
            print("⚠️ AGNES_API_KEY не установлен")
            return False
        
        llm = ChatOpenAI(
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",
            temperature=0.7,
            api_key=api_key,
        )
        
        test_response = llm.invoke("Test")
        if test_response:
            agnes_llm = llm
            AGNES_AVAILABLE = True
            print("✅ Agnes загружена")
            return True
    except Exception as e:
        print(f"⚠️ Ошибка Agnes: {e}")
    return False

init_agnes()

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Бот запущен\n"
        f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
        f"cdp-use: {'✅' if CDP_AVAILABLE else '❌'}\n\n"
        f"/browse <задача> — выполнить в браузере\n"
        f"/agnes — статус Agnes"
    )

async def agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if AGNES_AVAILABLE:
        await update.message.reply_text("✅ Agnes готова!")
    else:
        await update.message.reply_text(
            "❌ Agnes не доступна\n\n"
            "1. Получи ключ на https://agnes-ai.com/\n"
            "2. Добавь AGNES_API_KEY=твой_ключ\n"
            "3. Перезапусти бота"
        )

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить задачу в браузере через cdp-use"""
    if not context.args:
        await update.message.reply_text("ℹ️ /browse <задача>\nПример: /browse открой google.com")
        return
    
    if not AGNES_AVAILABLE:
        await update.message.reply_text("❌ Agnes не доступна. Проверь /agnes")
        return
    
    if not CDP_AVAILABLE:
        await update.message.reply_text(
            "❌ cdp-use не установлен. Перезапусти бота для установки."
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🌐 Выполняю: {task[:100]}...")
    
    try:
        from cdp_use import connect
        from cdp_use.browser import Browser
        
        await msg.edit_text("🔄 Запускаю браузер...")
        
        # Запускаем браузер через cdp-use
        async with connect() as client:
            browser = Browser(client)
            
            # Открываем новую страницу
            page = await browser.new_page()
            
            # Переходим на google.com
            await page.goto('https://google.com')
            await asyncio.sleep(2)
            
            # Делаем скриншот
            screenshot = await page.screenshot()
            
            # Сохраняем
            with open('/tmp/screenshot.png', 'wb') as f:
                f.write(screenshot)
            
            # Закрываем страницу
            await page.close()
        
        # Отправляем скриншот
        await update.message.reply_photo(
            photo=open('/tmp/screenshot.png', 'rb'),
            caption=f"📸 Google.com"
        )
        
        await msg.edit_text(f"✅ **Задача выполнена!**")
        
    except Exception as e:
        error_msg = str(e)
        await msg.edit_text(f"❌ Ошибка: {error_msg[:200]}")
        logger.error(f"Error: {e}", exc_info=True)


# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("agnes", agnes))
    app.add_handler(CommandHandler("browse", browse))
    
    print("✅ Бот запущен!")
    print(f"🤖 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}")
    print(f"🧠 cdp-use: {'✅' if CDP_AVAILABLE else '❌'}")
    print("Команды: /start, /agnes, /browse")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()