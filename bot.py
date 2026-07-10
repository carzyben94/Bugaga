import asyncio
import logging
import os
import base64
import requests
from PIL import Image
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    logger.warning("⚠️ AGNES_API_KEY не установлен!")

CHROME_PATH = "/usr/bin/google-chrome"
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
browser_instance = None
tab_instance = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

async def delete_message_after_delay(context, chat_id, message_id, delay=2):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Ошибка при удалении: {e}")

async def send_and_delete(update, context, text, delay=2):
    message = await update.message.reply_text(text)
    asyncio.create_task(delete_message_after_delay(context, update.effective_chat.id, message.message_id, delay))
    return message

def get_image_size(image_data):
    try:
        img = Image.open(io.BytesIO(image_data))
        width, height = img.size
        logger.info(f"📐 Размер изображения: {width}x{height}")
        return width, height
    except Exception as e:
        logger.error(f"Ошибка при определении размера: {e}")
        return None, None

# --- ФУНКЦИЯ ЗАМЕНЫ ФОНА (AGNES AI) ---
def replace_background(image_data, new_background_prompt: str):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен!"
    
    try:
        width, height = get_image_size(image_data)
        
        if width is None or height is None:
            size = "1024x1024"
            logger.info("⚠️ Использую стандартный размер: 1024x1024")
        else:
            max_size = 2048
            if width > max_size or height > max_size:
                ratio = min(max_size / width, max_size / height)
                width = int(width * ratio)
                height = int(height * ratio)
                logger.info(f"📐 Изменен размер для API: {width}x{height}")
            
            size = f"{width}x{height}"
            logger.info(f"📐 Использую размер: {size}")
        
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{img_b64}"
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "agnes-image-2.0-flash",
            "prompt": f"Replace the background with: {new_background_prompt}. Keep the main subject unchanged.",
            "size": size,
            "extra_body": {
                "image": [data_uri],
                "response_format": "url"
            }
        }
        
        logger.info(f"📤 Отправка запроса к Agnes AI...")
        response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        logger.info("✅ Изображение сгенерировано")
        
        if 'data' in result and len(result['data']) > 0 and 'url' in result['data'][0]:
            return result['data'][0]['url'], None
        else:
            logger.error(f"❌ Неожиданный ответ от API: {result}")
            return None, "Неожиданный ответ от API"
        
    except requests.exceptions.Timeout:
        return None, "Таймаут запроса к Agnes AI"
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return None, f"Ошибка запроса: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return None, str(e)

# --- ФУНКЦИИ БРАУЗЕРА ---
def get_browser_options():
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.start_timeout = 30
    return options

async def open_browser():
    global browser_instance, tab_instance
    try:
        if browser_instance is None:
            options = get_browser_options()
            browser_instance = Chrome(options=options)
            await browser_instance.start()
            tab_instance = await browser_instance.start()
            logger.info("✅ Браузер открыт")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def close_browser():
    global browser_instance, tab_instance
    try:
        if browser_instance is not None:
            await browser_instance.stop()
            browser_instance = None
            tab_instance = None
            logger.info("✅ Браузер закрыт")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def take_screenshot():
    global tab_instance
    try:
        if tab_instance is None:
            return None, "❌ Браузер не открыт."
        screenshot_data = await tab_instance.take_screenshot(beyond_viewport=True, as_base64=True)
        return screenshot_data, None
    except Exception as e:
        return None, str(e)

def get_browser_status():
    if browser_instance is not None and tab_instance is not None:
        return "🟢 Включен"
    return "🔴 Выключен"

# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/status - Статус браузера\n"
        "/open_bw - Открыть браузер\n"
        "/close_bw - Закрыть браузер\n"
        "/screen - Скриншот\n"
        "/go <URL> - Перейти на сайт\n"
        "/bg - Замена фона"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 Статус браузера: {get_browser_status()}")

async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success = await open_browser()
    if success:
        await send_and_delete(update, context, "🌐 Браузер открыт ✅", delay=2)
    else:
        await update.message.reply_text("❌ Не удалось открыть браузер")

async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success = await close_browser()
    if success:
        await send_and_delete(update, context, "❌ Браузер закрыт ✅", delay=2)
    else:
        await update.message.reply_text("❌ Не удалось закрыть браузер")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_and_delete(update, context, "📸 Делаю скриншот...", delay=2)
    screenshot_data, error = await take_screenshot()
    if error:
        await update.message.reply_text(f"❌ {error}")
    elif screenshot_data:
        try:
            screenshot_bytes = base64.b64decode(screenshot_data)
            context.user_data['last_image'] = screenshot_bytes
            await update.message.reply_photo(
                screenshot_bytes,
                caption="📸 Скриншот сохранен!\nКакой фон? /bg <пишите сюда фон>"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tab_instance
    if not context.args:
        await update.message.reply_text("❌ Укажите URL. Пример: /go https://example.com")
        return
    url = normalize_url(context.args[0])
    try:
        if tab_instance is None:
            await update.message.reply_text("❌ Браузер не открыт.")
            return
        await tab_instance.go_to(url)
        title = await tab_instance.title
        await update.message.reply_text(f"✅ Перешел на {url}\n📄 {title}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        context.user_data['last_image'] = bytes(photo_bytes)
        
        width, height = get_image_size(photo_bytes)
        size_info = f" ({width}x{height})" if width and height else ""
        
        await update.message.reply_text(
            f"📸 Фото сохранено{size_info}!\nКакой фон? /bg <пишите сюда фон>"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# --- ГЛАВНАЯ КОМАНДА /bg ---
async def bg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return

    # Проверяем, есть ли сохраненное изображение
    if 'last_image' not in context.user_data:
        await update.message.reply_text("📸 Сначала загрузите картинку!")
        return

    # Если нет описания
    if not context.args:
        await update.message.reply_text(
            "✏️ Напишите описание нового фона.\n"
            "Пример: /bg beach \n"
            "Пример: /bg water"
        )
        return

    prompt = ' '.join(context.args)
    waiting_msg = await update.message.reply_text(f"🎨 Заменяю фон: {prompt}\n⏳ Ожидайте...")

    try:
        image_data = context.user_data['last_image']
        loop = asyncio.get_event_loop()
        result_url, error = await loop.run_in_executor(None, replace_background, image_data, prompt)

        try:
            await waiting_msg.delete()
        except:
            pass

        if error:
            await update.message.reply_text(f"❌ Ошибка: {error}")
            return

        if result_url:
            try:
                response = requests.get(result_url, timeout=30)
                
                if response.status_code == 200:
                    await update.message.reply_photo(
                        response.content,
                        caption="🖼️ Готово!"
                    )
                else:
                    await update.message.reply_text(f"❌ Ошибка {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Ошибка скачивания: {e}")
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        else:
            await update.message.reply_text("❌ Не удалось заменить фон")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# --- ОБРАБОТЧИК ОШИБОК ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    try:
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("open_bw", open_browser_command))
        application.add_handler(CommandHandler("close_bw", close_browser_command))
        application.add_handler(CommandHandler("screen", screenshot_command))
        application.add_handler(CommandHandler("go", go_command))
        application.add_handler(CommandHandler("bg", bg_command))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()