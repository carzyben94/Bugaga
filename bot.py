import os
import logging
import base64
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from browser import Browser
from eval import Eval

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

browser = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот.\n\n"
        "Команды:\n"
        "/screen <url> — скриншот страницы\n"
        "/analyze <url> — анализ страницы\n"
        "/log — скачать лог"
    )


async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /screen https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен с маскировкой")
        
        await browser.goto(url)
        screenshot_base64 = await browser.screenshot()
        
        photo_bytes = base64.b64decode(screenshot_base64)
        
        await update.message.reply_photo(
            photo=photo_bytes,
            caption=f"✅ Скриншот {url}\nРазмер: {len(photo_bytes)} байт"
        )
        
        logger.info(f"User {user_id} сделал скриншот {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка скриншота: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /analyze https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"🔍 Анализирую {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        await browser.goto(url)
        
        eval = Eval(browser)
        
        title = await eval.get_title()
        links = await eval.get_all_links()
        images = await eval.get_all_images()
        forms = await eval.get_all_forms()
        page_info = await eval.get_page_info()
        
        response = (
            f"📄 **{title}**\n\n"
            f"🔗 Ссылок: {len(links)}\n"
            f"🖼️ Изображений: {len(images)}\n"
            f"📝 Форм: {len(forms)}\n"
            f"📏 Длина текста: {len(page_info.get('innerText', ''))} символов\n"
            f"🌐 Язык: {page_info.get('language', 'не определен')}\n\n"
            f"📌 Первые 5 ссылок:\n"
        )
        
        for i, link in enumerate(links[:5], 1):
            text = link['text'][:30] if link['text'] else '[без текста]'
            href = link['href'][:50] if link['href'] else '#'
            response += f"  {i}. {text} → {href}\n"
        
        if len(response) > 4000:
            response = response[:4000] + "\n\n... (обрезано)"
        
        await update.message.reply_text(response)
        
        logger.info(f"User {user_id} проанализировал {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка анализа: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        with open("bot.log", "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                caption=f"📋 Лог бота ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
            )
        logger.info(f"User {user_id} скачал лог")
    except FileNotFoundError:
        await update.message.reply_text("❌ Файл лога не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("log", log))
    
    logger.info("🚀 Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()