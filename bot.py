import os
import logging
import base64
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт браузера с обработкой ошибок
try:
    from browser import cdp_client
    BROWSER_AVAILABLE = True
except ImportError as e:
    BROWSER_AVAILABLE = False
    print(f"⚠️ Браузер не доступен: {e}")

# Импорт Accessibility
try:
    from accessibility import accessibility
    ACCESSIBILITY_AVAILABLE = True
except ImportError as e:
    ACCESSIBILITY_AVAILABLE = False
    print(f"⚠️ Accessibility не доступен: {e}")

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "🌐 /browser <url> - Открыть сайт\n"
        "📸 /screen - Сделать скриншот\n"
        "🔒 /close - Закрыть браузер\n\n"
        "🔍 /find - Найти элементы на странице\n"
        "🖱️ /click <название> - Клик по кнопке\n"
        "⌨️ /type <поле> <текст> - Ввести текст\n"
        "📄 /gettext <название> - Получить текст элемента"
    )

async def browser_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /browser - запуск браузера и переход по URL"""
    if not BROWSER_AVAILABLE:
        await update.message.reply_text("❌ Модуль браузера недоступен")
        return
    
    # Получаем URL из аргументов
    url = context.args[0] if context.args else None
    
    if not url:
        await update.message.reply_text(
            "❌ Укажи URL.\n\n"
            "Пример: /browser https://x.com"
        )
        return
    
    # Добавляем https:// если нет протокола
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    await update.message.reply_text(f"🌐 Открываю {url}...")
    
    try:
        # Проверяем, запущен ли браузер
        if not cdp_client.ws:
            # Запускаем браузер (куки установятся автоматически)
            await cdp_client.connect_cdp(navigate_to_x=False)
        
        # Переходим по URL
        await cdp_client.navigate_to(url)
        
        # Включаем Accessibility если доступен
        if ACCESSIBILITY_AVAILABLE:
            try:
                await accessibility.enable()
            except:
                pass
        
        await update.message.reply_text(f"✅ Страница загружена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /screen - скриншот"""
    if not BROWSER_AVAILABLE:
        await update.message.reply_text("❌ Модуль браузера недоступен")
        return
    
    await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        # Проверяем, запущен ли браузер
        if not cdp_client.ws:
            await update.message.reply_text("⚠️ Браузер не запущен. Используй /browser <url>")
            return
        
        # Делаем скриншот
        screenshot_b64 = await cdp_client.take_screenshot()
        
        # Декодируем base64 в байты
        screenshot_bytes = base64.b64decode(screenshot_b64)
        
        # Создаем BytesIO объект
        photo_file = io.BytesIO(screenshot_bytes)
        photo_file.name = "screenshot.png"
        
        # Отправляем в чат
        await update.message.reply_photo(
            photo=photo_file,
            caption="📸 Скриншот"
        )
        
        logger.info(f"✅ Скриншот отправлен пользователю {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании скриншота: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def browser_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /close - закрыть браузер"""
    if not BROWSER_AVAILABLE:
        await update.message.reply_text("❌ Модуль браузера недоступен")
        return
    
    await update.message.reply_text("🔒 Закрываю браузер...")
    
    try:
        # Отключаем Accessibility если доступен
        if ACCESSIBILITY_AVAILABLE:
            try:
                await accessibility.disable()
            except:
                pass
        
        await cdp_client.close()
        await update.message.reply_text("✅ Браузер закрыт")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def find_elements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /find - найти элементы на странице"""
    if not BROWSER_AVAILABLE or not ACCESSIBILITY_AVAILABLE:
        await update.message.reply_text("❌ Модуль Accessibility недоступен")
        return
    
    if not cdp_client.ws:
        await update.message.reply_text("⚠️ Браузер не запущен. Используй /browser <url>")
        return
    
    await update.message.reply_text("🔍 Ищу элементы на странице...")
    
    try:
        # Получаем корневой узел
        root = await accessibility.get_root_node()
        if not root:
            await update.message.reply_text("❌ Не удалось получить Accessibility Tree")
            return
        
        # Ищем разные элементы
        buttons = await accessibility.get_all_buttons()
        inputs = await accessibility.get_all_inputs()
        links = await accessibility.get_all_links()
        headings = await accessibility.get_all_headings()
        
        # Формируем ответ
        response = f"📊 Найдено элементов:\n\n"
        response += f"🔄 Кнопки: {len(buttons)}\n"
        response += f"📝 Поля ввода: {len(inputs)}\n"
        response += f"🔗 Ссылки: {len(links)}\n"
        response += f"📌 Заголовки: {len(headings)}\n\n"
        
        # Показываем первые 5 кнопок
        if buttons:
            response += "🔄 Кнопки (первые 5):\n"
            for i, btn in enumerate(buttons[:5]):
                status = "✅" if await btn.is_enabled() else "❌"
                name = btn.name if btn.name else "[без названия]"
                response += f"  {i+1}. {status} {name}\n"
        
        # Показываем первые 5 полей ввода
        if inputs and len(buttons) < 5:
            response += "\n📝 Поля ввода (первые 5):\n"
            for i, inp in enumerate(inputs[:5]):
                status = "✅" if await inp.is_enabled() else "❌"
                name = inp.name if inp.name else "[без названия]"
                response += f"  {i+1}. {status} {name}\n"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска элементов: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def click_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /click - клик по кнопке"""
    if not BROWSER_AVAILABLE or not ACCESSIBILITY_AVAILABLE:
        await update.message.reply_text("❌ Модуль Accessibility недоступен")
        return
    
    if not cdp_client.ws:
        await update.message.reply_text("⚠️ Браузер не запущен. Используй /browser <url>")
        return
    
    # Получаем имя кнопки из аргументов
    button_name = " ".join(context.args) if context.args else None
    
    if not button_name:
        await update.message.reply_text(
            "❌ Укажи название кнопки.\n\n"
            "Пример: /click Войти\n"
            "Пример: /click Отправить"
        )
        return
    
    await update.message.reply_text(f"🖱️ Ищу кнопку '{button_name}'...")
    
    try:
        # Ищем кнопку по имени
        button = await accessibility.find_button(button_name)
        
        if not button:
            await update.message.reply_text(f"❌ Кнопка '{button_name}' не найдена")
            return
        
        # Проверяем, активна ли кнопка
        if not await button.is_enabled():
            await update.message.reply_text(f"❌ Кнопка '{button_name}' неактивна")
            return
        
        # Кликаем
        await button.click()
        await update.message.reply_text(f"✅ Клик по кнопке '{button_name}' выполнен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка клика: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /type - ввод текста в поле"""
    if not BROWSER_AVAILABLE or not ACCESSIBILITY_AVAILABLE:
        await update.message.reply_text("❌ Модуль Accessibility недоступен")
        return
    
    if not cdp_client.ws:
        await update.message.reply_text("⚠️ Браузер не запущен. Используй /browser <url>")
        return
    
    # Парсим аргументы: /type "поле" "текст"
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Укажи поле и текст.\n\n"
            "Пример: /type Поиск запрос\n"
            "Пример: /type Логин user@mail.com"
        )
        return
    
    # Собираем название поля и текст
    field_name = args[0]
    text = " ".join(args[1:])
    
    await update.message.reply_text(f"⌨️ Ищу поле '{field_name}'...")
    
    try:
        # Ищем поле ввода по имени
        input_field = await accessibility.find_input(field_name)
        
        if not input_field:
            await update.message.reply_text(f"❌ Поле '{field_name}' не найдено")
            return
        
        # Проверяем, активно ли поле
        if not await input_field.is_enabled():
            await update.message.reply_text(f"❌ Поле '{field_name}' неактивно")
            return
        
        # Вводим текст
        await input_field.type(text)
        await update.message.reply_text(f"✅ Текст введен в поле '{field_name}'")
        
    except Exception as e:
        logger.error(f"❌ Ошибка ввода: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def get_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /gettext - получить текст элемента"""
    if not BROWSER_AVAILABLE or not ACCESSIBILITY_AVAILABLE:
        await update.message.reply_text("❌ Модуль Accessibility недоступен")
        return
    
    if not cdp_client.ws:
        await update.message.reply_text("⚠️ Браузер не запущен. Используй /browser <url>")
        return
    
    # Получаем имя элемента из аргументов
    element_name = " ".join(context.args) if context.args else None
    
    if not element_name:
        await update.message.reply_text(
            "❌ Укажи название элемента.\n\n"
            "Пример: /gettext Заголовок"
        )
        return
    
    await update.message.reply_text(f"🔍 Ищу текст элемента '{element_name}'...")
    
    try:
        # Ищем элемент по имени
        elements = await accessibility.find_by_name(element_name)
        
        if not elements:
            await update.message.reply_text(f"❌ Элемент '{element_name}' не найден")
            return
        
        # Берем первый найденный
        element = elements[0]
        text = await element.get_text()
        
        # Обрезаем длинный текст
        if len(text) > 1000:
            text = text[:1000] + "..."
        
        await update.message.reply_text(
            f"📝 Элемент: {element.role}\n"
            f"📌 Имя: {element.name}\n"
            f"📄 Текст: {text}"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения текста: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def post_init(application: Application):
    """Запуск браузера при старте бота с куками"""
    if not BROWSER_AVAILABLE:
        logger.warning("⚠️ Браузер недоступен, пропускаем запуск")
        return
    
    logger.info("🚀 Запуск браузера при старте бота...")
    try:
        # Запускаем браузер и сразу устанавливаем куки
        await cdp_client.connect_cdp(navigate_to_x=False)
        
        # Включаем Accessibility если доступен
        if ACCESSIBILITY_AVAILABLE:
            try:
                await accessibility.enable()
            except Exception as e:
                logger.warning(f"⚠️ Ошибка включения Accessibility: {e}")
        
        logger.info("✅ Браузер успешно запущен, куки установлены")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")

def main():
    """Запуск бота"""
    logger.info("Запуск бота...")
    
    # Проверяем доступность браузера
    if not BROWSER_AVAILABLE:
        logger.warning("⚠️ Браузер не доступен, некоторые функции будут отключены")
    
    if not ACCESSIBILITY_AVAILABLE:
        logger.warning("⚠️ Accessibility не доступен, некоторые функции будут отключены")
    
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser", browser_start))
    app.add_handler(CommandHandler("screen", screenshot))
    app.add_handler(CommandHandler("close", browser_close))
    app.add_handler(CommandHandler("find", find_elements))
    app.add_handler(CommandHandler("click", click_button))
    app.add_handler(CommandHandler("type", type_text))
    app.add_handler(CommandHandler("gettext", get_text))
    
    # Запускаем браузер при старте
    app.post_init = post_init
    
    # Запускаем поллинг
    logger.info("Бот запущен, ожидаем сообщения...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()