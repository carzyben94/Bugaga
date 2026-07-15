import os
import logging
import base64
import asyncio
import json
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
        "/ai <url> — AI анализ страницы\n"
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
        await asyncio.sleep(2)
        
        eval = Eval(browser)
        
        buttons = await eval.get_all_buttons()
        inputs = await eval.get_all_inputs()
        forms = await eval.get_all_forms()
        checkboxes = await eval.get_all_checkboxes()
        selects = await eval.get_all_selects()
        
        response = (
            f"🔄 Кнопок: {len(buttons)}\n"
            f"📝 Полей ввода: {len(inputs)}\n"
            f"📋 Форм: {len(forms)}\n"
            f"☑️ Checkbox/Radio: {len(checkboxes)}\n"
            f"📋 Select: {len(selects)}\n\n"
        )
        
        if buttons:
            response += "🔘 **Кнопки:**\n"
            for i, btn in enumerate(buttons, 1):
                text = btn['text'][:40] if btn['text'] else '[без текста]'
                test_id = btn.get('testId', '')
                if test_id:
                    response += f"  {i}. {text} (testid: {test_id})\n"
                else:
                    response += f"  {i}. {text}\n"
            response += "\n"
        
        if inputs:
            response += "✏️ **Поля ввода:**\n"
            for i, inp in enumerate(inputs, 1):
                desc = (
                    inp.get('ariaLabel') or 
                    inp.get('placeholder') or 
                    inp.get('title') or 
                    inp.get('name') or 
                    inp.get('id') or 
                    '[без имени]'
                )
                desc = desc[:35]
                test_id = inp.get('testId', '')
                
                field_type = inp.get('type', '')
                type_icon = {
                    'text': '📝',
                    'password': '🔒',
                    'email': '📧',
                    'number': '🔢',
                    'tel': '📞',
                    'url': '🔗',
                    'search': '🔍',
                    'textarea': '📄',
                }.get(field_type, '')
                
                if test_id:
                    response += f"  {i}. {type_icon} {desc} (testid: {test_id})\n"
                else:
                    response += f"  {i}. {type_icon} {desc}\n"
            response += "\n"
        
        if forms:
            response += f"📋 **Формы:** {len(forms)}\n"
            for i, form in enumerate(forms[:5], 1):
                action = form.get('action', '')[:40]
                method = form.get('method', 'GET')
                if action:
                    response += f"  {i}. {method} → {action}\n"
                else:
                    response += f"  {i}. {method}\n"
        
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


async def accessibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /accessibility https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"♿ Собираю Accessibility Tree для {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        await browser.goto(url)
        
        # Ждём загрузки страницы
        logger.info("⏳ Ожидание загрузки страницы...")
        for _ in range(30):
            try:
                response = await asyncio.wait_for(browser.ws.recv(), timeout=1)
                data = json.loads(response)
                if data.get("method") == "Page.loadEventFired":
                    logger.info("✅ Страница загружена")
                    break
            except asyncio.TimeoutError:
                continue
        else:
            logger.warning("⏱️ Таймаут ожидания загрузки")
        
        await asyncio.sleep(2)
        
        acc = Accessibility(browser)
        await acc.enable()
        await asyncio.sleep(2)
        
        summary = await acc.get_summary()
        
        response = (
            f"♿ **Accessibility Tree**\n\n"
            f"📊 **Всего узлов:** {summary['total_nodes']}\n"
            f"─────────────────\n"
            f"🔘 Кнопок: {summary['buttons']}\n"
            f"📝 Полей ввода: {summary['inputs']}\n"
            f"🔗 Ссылок: {summary['links']}\n"
            f"📌 Заголовков: {summary['headings']}\n"
            f"🏛️ Landmarks: {summary['landmarks']}\n"
            f"🖼️ Изображений: {summary['images']}\n"
            f"📋 Списков: {summary['lists']}\n"
            f"📊 Таблиц: {summary['tables']}\n"
        )
        
        if summary.get('roles'):
            response += "\n📋 **Роли (топ 10):**\n"
            sorted_roles = sorted(summary['roles'].items(), key=lambda x: x[1], reverse=True)[:10]
            for role, count in sorted_roles:
                response += f"  {role}: {count}\n"
        
        if len(response) > 4000:
            response = response[:4000] + "\n\n... (обрезано)"
        
        await update.message.reply_text(response)
        
        logger.info(f"User {user_id} запросил accessibility для {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка Accessibility: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI анализ страницы"""
    global browser
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /ai https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"🧠 Запускаю AI анализ для {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        await browser.goto(url)
        await asyncio.sleep(2)
        
        eval = Eval(browser)
        acc = Accessibility(browser)
        agent = AIAgent(browser, eval, acc)
        
        result = await agent.analyze_page(url)
        
        if len(result) > 4000:
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])
        else:
            await update.message.reply_text(f"🧠 **AI Анализ:**\n\n{result}")
        
        await agent.close()
        
        logger.info(f"User {user_id} выполнил AI анализ {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка AI анализа: {error_msg}")
        
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
    app.add_handler(CommandHandler("accessibility", accessibility))
    app.add_handler(CommandHandler("ai", ai))
    app.add_handler(CommandHandler("log", log))
    
    logger.info("🚀 Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()