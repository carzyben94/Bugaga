import asyncio
import logging
import os
import base64
import requests
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

# Получаем токены из переменных окружения
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    logger.warning("⚠️ AGNES_API_KEY не установлен! Функция замены фона не будет работать.")

# Путь к браузеру Google Chrome
CHROME_PATH = "/usr/bin/google-chrome"
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"

# Глобальная переменная для хранения экземпляра браузера
browser_instance = None
tab_instance = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def normalize_url(url: str) -> str:
    """Добавляет https:// если протокол не указан"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 2):
    """Удаляет сообщение через указанную задержку"""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")

async def send_and_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, delay: int = 2):
    """Отправляет сообщение и удаляет его через delay секунд"""
    message = await update.message.reply_text(text)
    asyncio.create_task(delete_message_after_delay(context, update.effective_chat.id, message.message_id, delay))
    return message

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С AGNES AI ---

def replace_background(image_data, new_background_prompt: str) -> str:
    """
    Заменяет фон на изображении через Agnes AI
    
    Args:
        image_data: байты изображения
        new_background_prompt: описание нового фона
    
    Returns:
        str: URL сгенерированного изображения
    """
    if not AGNES_API_KEY:
        raise ValueError("AGNES_API_KEY не установлен!")
    
    try:
        # Кодируем изображение в base64
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Формируем запрос к Agnes AI
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "agnes-image-2.1-flash",
            "prompt": f"Replace the background with: {new_background_prompt}. Keep the main subject unchanged.",
            "image": [f"data:image/jpeg;base64,{img_b64}"],
            "size": "1024x1024",
            "extra_body": {"response_format": "url"}
        }
        
        logger.info(f"📤 Отправка запроса к Agnes AI...")
        response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=60)
        
        # Проверяем статус ответа
        if response.status_code == 404:
            logger.error("❌ Эндпоинт не найден. Проверьте URL API.")
            return None
        
        response.raise_for_status()
        
        # Парсим ответ
        result = response.json()
        logger.info("✅ Изображение успешно сгенерировано")
        
        return result['data'][0]['url']
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка запроса к Agnes AI: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при замене фона: {e}")
        return None

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С БРАУЗЕРОМ ---

def get_browser_options():
    """Создает и возвращает настроенный объект ChromiumOptions"""
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.start_timeout = 30
    return options

async def open_browser():
    """Открывает браузер и создает новую вкладку"""
    global browser_instance, tab_instance
    
    try:
        if browser_instance is None:
            options = get_browser_options()
            browser_instance = Chrome(options=options)
            await browser_instance.start()
            tab_instance = await browser_instance.start()
            logger.info("✅ Браузер успешно открыт")
            return True
        else:
            logger.info("ℹ️ Браузер уже открыт")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка при открытии браузера: {e}")
        return False

async def close_browser():
    """Закрывает браузер"""
    global browser_instance, tab_instance
    
    try:
        if browser_instance is not None:
            await browser_instance.stop()
            browser_instance = None
            tab_instance = None
            logger.info("✅ Браузер успешно закрыт")
            return True
        else:
            logger.info("ℹ️ Браузер уже закрыт")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии браузера: {e}")
        return False

async def take_screenshot():
    """Делает скриншот всей страницы"""
    global tab_instance
    
    try:
        if tab_instance is None:
            return None, "❌ Браузер не открыт. Используйте /open_bw"
        
        screenshot_data = await tab_instance.take_screenshot(
            beyond_viewport=True,
            as_base64=True
        )
        
        logger.info("📸 Скриншот всей страницы сделан")
        return screenshot_data, None
    except Exception as e:
        logger.error(f"❌ Ошибка при создании скриншота: {e}")
        return None, str(e)

def get_browser_status():
    """Возвращает статус браузера"""
    global browser_instance, tab_instance
    
    if browser_instance is not None and tab_instance is not None:
        return "🟢 Включен"
    else:
        return "🔴 Выключен"

# --- КОМАНДЫ БОТА ---

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список команд"""
    await update.message.reply_text(
        "/status - Статус браузера\n"
        "/open_bw - Открыть браузер\n"
        "/close_bw - Закрыть браузер\n"
        "/screen - Скриншот\n"
        "/go <URL> - Перейти на сайт\n\n"
        "📸 Для замены фона:\n"
        "1. Отправьте фото\n"
        "2. Напишите /bg <описание фона>\n"
        "3. Получите результат!"
    )

# Команда /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус браузера"""
    status = get_browser_status()
    await update.message.reply_text(f"📊 Статус браузера: {status}")

# Команда /open_bw
async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает браузер"""
    success = await open_browser()
    if success:
        await send_and_delete(update, context, "🌐 Браузер открыт ✅", delay=2)
    else:
        await update.message.reply_text("❌ Не удалось открыть браузер")

# Команда /close_bw
async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    success = await close_browser()
    if success:
        await send_and_delete(update, context, "❌ Браузер закрыт ✅", delay=2)
    else:
        await update.message.reply_text("❌ Не удалось закрыть браузер")

# Команда /screen
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот всей страницы"""
    await send_and_delete(update, context, "📸 Делаю скриншот...", delay=2)
    
    screenshot_data, error = await take_screenshot()
    
    if error:
        await update.message.reply_text(f"❌ {error}")
    elif screenshot_data:
        try:
            if isinstance(screenshot_data, str):
                screenshot_bytes = base64.b64decode(screenshot_data)
            else:
                screenshot_bytes = screenshot_data
            
            # Сохраняем скриншот в контексте
            context.user_data['last_image'] = screenshot_bytes
            
            await update.message.reply_photo(
                screenshot_bytes,
                caption="📸 Скриншот сохранен!\nДля замены фона используйте /bg <описание>"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке скриншота: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    else:
        await update.message.reply_text("❌ Не удалось сделать скриншот")

# Команда /go
async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переходит на указанный URL"""
    global tab_instance
    
    if not context.args:
        await update.message.reply_text("❌ Укажите URL. Пример: /go https://example.com")
        return
    
    url = normalize_url(context.args[0])
    
    try:
        if tab_instance is None:
            await update.message.reply_text("❌ Браузер не открыт. Используйте /open_bw")
            return
        
        await tab_instance.go_to(url)
        title = await tab_instance.title
        await update.message.reply_text(f"✅ Перешел на {url}\n📄 {title}")
    except Exception as e:
        logger.error(f"Ошибка при переходе: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# --- ОБРАБОТКА ФОТО ---

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает загруженное фото"""
    try:
        # Получаем фото
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Сохраняем фото в контексте
        context.user_data['last_image'] = bytes(photo_bytes)
        
        await update.message.reply_text(
            "📸 Фото сохранено!\n"
            "Теперь напишите /bg <описание фона>\n"
            "Пример: /bg beautiful beach sunset"
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await update.message.reply_text(f"❌ Ошибка при загрузке фото: {str(e)}")

# Команда /bg - замена фона
async def bg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заменяет фон на последнем изображении"""
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ AGNES_API_KEY не настроен. Обратитесь к администратору.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите описание нового фона.\n"
            "Пример: /bg beautiful beach sunset"
        )
        return
    
    # Проверяем, есть ли сохраненное изображение
    if 'last_image' not in context.user_data:
        await update.message.reply_text(
            "❌ Сначала загрузите фото или сделайте скриншот командой /screen"
        )
        return
    
    background_prompt = ' '.join(context.args)
    await update.message.reply_text(f"🎨 Заменяю фон на: {background_prompt}\n⏳ Это может занять до 30 секунд...")
    
    try:
        # Получаем изображение из контекста
        image_data = context.user_data['last_image']
        
        # Запускаем замену фона в отдельном потоке, чтобы не блокировать бота
        loop = asyncio.get_event_loop()
        result_url = await loop.run_in_executor(
            None, 
            replace_background, 
            image_data, 
            background_prompt
        )
        
        if result_url:
            # Скачиваем и отправляем изображение
            try:
                response = requests.get(result_url, timeout=30)
                if response.status_code == 200:
                    await update.message.reply_photo(
                        response.content,
                        caption=f"🖼️ Новое изображение\nФон: {background_prompt}"
                    )
                else:
                    await update.message.reply_text(f"✅ Готово! Ссылка: {result_url}")
            except Exception as e:
                logger.error(f"Ошибка при скачивании результата: {e}")
                await update.message.reply_text(f"✅ Готово! Ссылка: {result_url}")
        else:
            await update.message.reply_text(
                "❌ Не удалось заменить фон. Проверьте API ключ или попробуйте позже."
            )
            
    except Exception as e:
        logger.error(f"Ошибка при замене фона: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# --- ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ---

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    """Главная функция запуска бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()

        # Регистрируем команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("open_bw", open_browser_command))
        application.add_handler(CommandHandler("close_bw", close_browser_command))
        application.add_handler(CommandHandler("screen", screenshot_command))
        application.add_handler(CommandHandler("go", go_command))
        application.add_handler(CommandHandler("bg", bg_command))
        
        # Регистрируем обработчик фото
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        logger.info(f"📁 Используемый браузер: {CHROME_PATH}")
        logger.info("ℹ️ Доступные команды: /start, /status, /open_bw, /close_bw, /screen, /go, /bg")
        logger.info("📸 Бот принимает фото для замены фона")
        
        if AGNES_API_KEY:
            logger.info("✅ Agnes AI настроен")
        else:
            logger.warning("⚠️ Agnes AI не настроен (AGNES_API_KEY отсутствует)")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()