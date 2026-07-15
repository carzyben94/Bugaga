import os
import logging
import base64
import asyncio
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
        await asyncio.sleep(2)
        
        eval = Eval(browser)
        
        # ===== ОСНОВНЫЕ ДАННЫЕ =====
        title = await eval.get_title()
        links = await eval.get_all_links()
        images = await eval.get_all_images()
        forms = await eval.get_all_forms()
        page_info = await eval.get_page_info()
        
        # ===== ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ =====
        buttons = await eval.get_all_buttons()
        inputs = await eval.get_all_inputs()
        checkboxes = await eval.get_all_checkboxes()
        selects = await eval.get_all_selects()
        
        # ===== ФОРМИРУЕМ ОТВЕТ =====
        response = (
            f"📄 **{title}**\n\n"
            f"🔗 Ссылок: {len(links)}\n"
            f"🖼️ Изображений: {len(images)}\n"
            f"📝 Форм: {len(forms)}\n"
            f"📏 Длина текста: {len(page_info.get('innerText', ''))} символов\n"
            f"🌐 Язык: {page_info.get('language', 'не определен')}\n"
            f"─────────────────\n"
            f"🔄 Кнопок: {len(buttons)}\n"
            f"📝 Полей ввода: {len(inputs)}\n"
            f"☑️ Checkbox/Radio: {len(checkboxes)}\n"
            f"📋 Select: {len(selects)}\n"
        )
        
        # ===== ПЕРВЫЕ 5 ССЫЛОК =====
        if links:
            response += "\n📌 **Первые 5 ссылок:**\n"
            for i, link in enumerate(links[:5], 1):
                text = link['text'][:30] if link['text'] else '[без текста]'
                href = link['href'][:50] if link['href'] else '#'
                response += f"  {i}. {text} → {href}\n"
        
        # ===== ПЕРВЫЕ 5 КНОПОК =====
        if buttons:
            response += "\n🔘 **Первые 5 кнопок:**\n"
            for i, btn in enumerate(buttons[:5], 1):
                text = btn['text'][:30] if btn['text'] else '[без текста]'
                identifier = btn['id'] or btn['name'] or ''
                if identifier:
                    response += f"  {i}. {text} (id: {identifier})\n"
                else:
                    response += f"  {i}. {text}\n"
        
        # ===== ПЕРВЫЕ 5 ПОЛЕЙ (С ОПИСАНИЕМ) =====
        if inputs:
            response += "\n✏️ **Первые 5 полей:**\n"
            for i, inp in enumerate(inputs[:5], 1):
                # Собираем описание поля из всех возможных атрибутов
                desc = (
                    inp.get('ariaLabel') or 
                    inp.get('placeholder') or 
                    inp.get('title') or 
                    inp.get('name') or 
                    inp.get('id') or 
                    ''
                )
                
                # Если есть и name и описание — показываем оба
                name = inp.get('name', '')
                if name and desc and name != desc:
                    display = f"{desc} ({name})"
                elif desc:
                    display = desc
                elif name:
                    display = name
                else:
                    display = '[без имени]'
                
                display = display[:35]  # обрезаем длинные
                
                # Добавляем тип поля
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
                    'select': '📋'
                }.get(field_type, '')
                
                if type_icon:
                    response += f"  {i}. {type_icon} {display}\n"
                else:
                    response += f"  {i}. {display}\n"
        
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