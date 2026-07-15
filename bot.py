import os
import logging
import base64
import asyncio
import json
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from browser import Browser
from eval import Eval
from accessibility import Accessibility
from ai import AIAgent

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
        "/analyze <url> — анализ страницы (кнопки, поля, формы)\n"
        "/accessibility <url> — доступность страницы\n"
        "/ai <вопрос> — общение с AI агентом\n"
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
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    try:
        if browser is None:
            browser = await Browser().start()
        await browser.goto(url)
        screenshot_base64 = await browser.screenshot()
        photo_bytes = base64.b64decode(screenshot_base64)
        await update.message.reply_photo(photo=photo_bytes, caption=f"✅ Скриншот {url}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL")
        return
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    await update.message.reply_text(f"🔍 Анализирую {url}...")
    try:
        if browser is None:
            browser = await Browser().start()
        await browser.goto(url)
        await asyncio.sleep(2)
        eval = Eval(browser)
        buttons = await eval.get_all_buttons()
        inputs = await eval.get_all_inputs()
        forms = await eval.get_all_forms()
        response = f"📄 **{await eval.get_title()}**\n\n🔘 Кнопок: {len(buttons)}\n📝 Полей: {len(inputs)}\n📋 Форм: {len(forms)}\n"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def accessibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL")
        return
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    await update.message.reply_text(f"♿ Анализирую доступность {url}...")
    try:
        if browser is None:
            browser = await Browser().start()
        await browser.goto(url)
        await asyncio.sleep(3)
        acc = Accessibility(browser)
        await acc.enable()
        await asyncio.sleep(2)
        summary = await acc.get_summary()
        response = f"♿ **Accessibility Tree**\n\n📊 Всего узлов: {summary['total_nodes']}\n🔘 Кнопок: {summary['buttons']}\n📝 Полей: {summary['inputs']}\n🔗 Ссылок: {summary['links']}\n📌 Заголовков: {summary['headings']}\n🏛️ Landmarks: {summary['landmarks']}"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser
    user_id = update.effective_user.id
    text = ' '.join(context.args) if context.args else ''

    if not text:
        await update.message.reply_text(
            "🧠 **AI Агент**\n\n"
            "Примеры:\n"
            "  /ai проанализируй https://x.com\n"
            "  /ai структура https://x.com\n"
            "  /ai что такое CDP"
        )
        return

    await update.message.reply_text("🧠 Думаю...")

    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")

        eval = Eval(browser)
        acc = Accessibility(browser)
        agent = AIAgent(browser, eval, acc)

        url_match = re.search(r'https?://[^\s]+', text)
        url = url_match.group(0) if url_match else None
        text_lower = text.lower()

        if url and ('анализ' in text_lower or 'структура' in text_lower or 'проанализируй' in text_lower):
            result = await agent.analyze_structure(url)
        elif url:
            await browser.goto(url)
            await asyncio.sleep(2)
            title = await eval.get_title()
            buttons = await eval.get_all_buttons()
            inputs = await eval.get_all_inputs()
            links = await eval.get_all_links()
            prompt = f"Страница: {url}\nЗаголовок: {title}\nКнопок: {len(buttons)}\nПолей: {len(inputs)}\nСсылок: {len(links)}\n\nВопрос: {text}"
            result = await agent.ask(prompt)
        else:
            result = await agent.ask(text)

        if len(result) > 4000:
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])
        else:
            await update.message.reply_text(f"🧠 **AI Агент:**\n\n{result}")

        await agent.close()
        logger.info(f"User {user_id} -> AI: {text[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка AI: {e}")
        if browser:
            await browser.close()
            browser = None
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


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
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("accessibility", accessibility))
    app.add_handler(CommandHandler("ai", ai))
    app.add_handler(CommandHandler("log", log))
    logger.info("🚀 Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()