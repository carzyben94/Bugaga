import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем все функции из pydoll_handlers
from pydoll_handlers import (
    search_and_screenshot,
    get_page_title,
    execute_javascript,
    take_screenshot_of_element,
    find_in_shadow_dom,
    find_all_shadow_roots,
    load_page_without_images,
    record_har,
    hybrid_automation_example,
    save_page_bundle,
    human_click_example,
    concurrent_scraping,
    extract_quotes
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

# ============================================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение со списком команд"""
    await update.message.reply_text(
        "👋 Привет! Я бот с **полным функционалом Pydoll**.\n\n"
        "📌 **Основные команды:**\n"
        "/start - Показать это сообщение\n"
        "/search <запрос> - Поиск в Google со скриншотом\n"
        "/title <url> - Получить заголовок страницы\n"
        "/js <url> <script> - Выполнить JavaScript\n"
        "/element <url> <селектор> - Скриншот элемента\n\n"
        "📌 **Расширенные команды:**\n"
        "/shadow <url> <хост> <внутренний> - Поиск в Shadow DOM\n"
        "/shadows <url> - Найти все Shadow Roots\n"
        "/block <url> - Загрузить страницу без картинок\n"
        "/har <url> - Записать HAR-лог\n"
        "/bundle <url> - Сохранить страницу в ZIP\n"
        "/human <url> <селектор> - Клик с humanize=True\n"
        "/concurrent <url1> <url2> ... - Параллельная загрузка\n"
        "/parse <url> - Парсинг цитат (ExtractionModel)\n"
        "/hybrid <login_url> <user> <pass> <api_url> - Гибридная автоматизация"
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск в Google со скриншотом"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /search <запрос>")
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        screenshot_path = await search_and_screenshot(query)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption=f"✅ Результат поиска: {query}"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в search: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить заголовок страницы"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /title <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📄 Загружаю: {url}...")
    
    try:
        page_title = await get_page_title(url)
        await update.message.reply_text(f"📌 Заголовок: {page_title}")
    except Exception as e:
        logger.error(f"Ошибка в title: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить JavaScript на странице"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /js <url> <script>")
        return
    
    url = context.args[0]
    script = " ".join(context.args[1:])
    
    try:
        result = await execute_javascript(url, script)
        await update.message.reply_text(f"✅ Результат JS:\n{result[:500]}")
    except Exception as e:
        logger.error(f"Ошибка в js: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def element_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот элемента по CSS-селектору"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /element <url> <css_selector>")
        return
    
    url = context.args[0]
    selector = context.args[1]
    
    try:
        screenshot_path = await take_screenshot_of_element(url, selector)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption=f"✅ Элемент: {selector}"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в element_screenshot: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def shadow_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск элемента внутри Shadow DOM"""
    if len(context.args) < 3:
        await update.message.reply_text("❌ Использование: /shadow <url> <host_selector> <inner_selector>")
        return
    
    url = context.args[0]
    host_selector = context.args[1]
    inner_selector = context.args[2]
    
    try:
        text = await find_in_shadow_dom(url, host_selector, inner_selector)
        await update.message.reply_text(f"✅ Найдено в Shadow DOM:\n{text[:500]}")
    except Exception as e:
        logger.error(f"Ошибка в shadow_dom: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def all_shadows(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Найти все Shadow Roots на странице"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /shadows <url>")
        return
    
    url = context.args[0]
    
    try:
        results = await find_all_shadow_roots(url)
        await update.message.reply_text(f"✅ Найдено Shadow Roots: {len(results)}")
    except Exception as e:
        logger.error(f"Ошибка в all_shadows: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def block_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загрузить страницу без картинок"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /block <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🚫 Загружаю без картинок: {url}...")
    
    try:
        screenshot_path = await load_page_without_images(url)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption="✅ Страница загружена без картинок и стилей"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в block_images: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def har_recording(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Записать HAR-лог"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /har <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📊 Записываю HAR для: {url}...")
    
    try:
        result = await record_har(url)
        await update.message.reply_text(
            f"✅ Записано {result['entries_count']} запросов\n"
            f"📁 Файл: {result['file_path']}"
        )
    except Exception as e:
        logger.error(f"Ошибка в har_recording: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def page_bundle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить страницу в ZIP"""
    if not context.args:
        await update.message.reply_text(
            "❌ Использование: /bundle <url>\n"
            "Добавьте --inline для встраивания ресурсов"
        )
        return
    
    inline = "--inline" in context.args
    url = context.args[0] if not context.args[0].startswith("--") else context.args[1]
    
    await update.message.reply_text(f"📦 Сохраняю страницу: {url}...")
    
    try:
        bundle_path = await save_page_bundle(url, inline=inline)
        await update.message.reply_text(
            f"✅ Страница сохранена\n"
            f"📁 Файл: {bundle_path}"
        )
    except Exception as e:
        logger.error(f"Ошибка в page_bundle: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def human_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Клик с человеко-подобным движением мыши"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /human <url> <css_selector>")
        return
    
    url = context.args[0]
    selector = context.args[1]
    
    try:
        screenshot_path = await human_click_example(url, selector)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption=f"✅ Клик с humanize=True на {selector}"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в human_click: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def concurrent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Параллельная загрузка нескольких страниц"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /concurrent <url1> <url2> ...")
        return
    
    urls = context.args
    await update.message.reply_text(f"🔄 Загружаю {len(urls)} страниц параллельно...")
    
    try:
        results = await concurrent_scraping(urls)
        
        message = "📌 Результаты:\n\n"
        for i, (url, title) in enumerate(zip(urls, results), 1):
            message += f"{i}. {title[:50]}\n"
        
        await update.message.reply_text(message[:4000])
        
    except Exception as e:
        logger.error(f"Ошибка в concurrent: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсинг цитат с использованием ExtractionModel"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /parse <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔍 Парсинг цитат: {url}...")
    
    try:
        quotes = await extract_quotes(url)
        
        if not quotes:
            await update.message.reply_text("❌ Цитаты не найдены")
            return
        
        message = f"📚 Найдено цитат: {len(quotes)}\n\n"
        for i, q in enumerate(quotes[:5], 1):
            text = q['text'][:50] + "..." if len(q['text']) > 50 else q['text']
            message += f"{i}. \"{text}\" — {q['author']}\n"
        
        if len(quotes) > 5:
            message += f"\n... и ещё {len(quotes) - 5} цитат"
        
        await update.message.reply_text(message[:4000])
        
    except Exception as e:
        logger.error(f"Ошибка в parse: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def hybrid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Гибридная автоматизация (UI + API)"""
    if len(context.args) < 4:
        await update.message.reply_text(
            "❌ Использование: /hybrid <login_url> <username> <password> <api_url>"
        )
        return
    
    login_url = context.args[0]
    username = context.args[1]
    password = context.args[2]
    api_url = context.args[3]
    
    await update.message.reply_text("🔄 Выполняю гибридную автоматизацию...")
    
    try:
        result = await hybrid_automation_example(login_url, username, password, api_url)
        
        await update.message.reply_text(
            f"✅ Статус: {result['status']}\n"
            f"📊 Данные:\n{result['data'][:500]}"
        )
    except Exception as e:
        logger.error(f"Ошибка в hybrid: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

# ============================================================
# ЗАПУСК БОТА
# ============================================================

def main():
    """Запуск бота"""
    logger.info("🚀 Запуск бота с полным функционалом Pydoll...")
    
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("title", title))
    app.add_handler(CommandHandler("js", js))
    app.add_handler(CommandHandler("element", element_screenshot))
    app.add_handler(CommandHandler("shadow", shadow_dom))
    app.add_handler(CommandHandler("shadows", all_shadows))
    app.add_handler(CommandHandler("block", block_images))
    app.add_handler(CommandHandler("har", har_recording))
    app.add_handler(CommandHandler("bundle", page_bundle))
    app.add_handler(CommandHandler("human", human_click))
    app.add_handler(CommandHandler("concurrent", concurrent))
    app.add_handler(CommandHandler("parse", parse))
    app.add_handler(CommandHandler("hybrid", hybrid))
    
    # Запускаем поллинг
    logger.info("✅ Бот запущен, ожидаем сообщения...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()