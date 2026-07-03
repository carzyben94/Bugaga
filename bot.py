import os
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from pydoll.browser import Chrome
from pydoll_page_objects import PageObject
from pydantic import BaseModel, Field

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# --- Pydantic модели ---
class UserData(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)
    parsed_count: int = 0
    last_parse: Optional[datetime] = None
    registered_at: datetime = Field(default_factory=datetime.now)

class ParseResult(BaseModel):
    url: str
    title: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None

# --- Pydoll Page Object ---
class ExamplePage(PageObject):
    """Пример Page Object для парсинга"""
    
    def __init__(self, browser: Chrome):
        super().__init__(browser)
        self.url = "https://example.com"
    
    async def get_page_info(self) -> Dict[str, str]:
        """Получить информацию со страницы"""
        title = await self.browser.execute_script("return document.title")
        
        try:
            content_element = await self.browser.find_element("p")
            text = await content_element.text if content_element else "Контент не найден"
        except Exception:
            text = "Не удалось получить контент"
        
        return {
            "title": title,
            "content": text[:300]
        }

# --- Утилиты ---
async def parse_website(url: str = "https://example.com") -> ParseResult:
    """Асинхронная функция парсинга"""
    browser = None
    try:
        browser = Chrome()
        await browser.start()
        
        page = ExamplePage(browser)
        if url != page.url:
            page.url = url
        
        await browser.go_to(page.url)
        data = await page.get_page_info()
        
        return ParseResult(
            url=page.url,
            title=data['title'],
            content=data['content'],
            success=True
        )
        
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return ParseResult(
            url=url,
            title="Ошибка",
            content="",
            success=False,
            error=str(e)
        )
    finally:
        if browser:
            await browser.close()

# --- Команды бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    
    # Сохраняем данные пользователя
    if "user_data" not in context.user_data:
        user_data = UserData(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        context.user_data["user_data"] = user_data.model_dump()
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я бот для парсинга веб-страниц.\n"
        f"Использую Pydoll для асинхронного парсинга.\n\n"
        f"📌 Введите /menu для просмотра всех команд",
        parse_mode="Markdown"
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /menu - показать меню"""
    await update.message.reply_text(
        "📋 *Меню бота*\n\n"
        "Выберите действие:\n\n"
        "/start - Начать работу\n"
        "/parse - Запустить парсинг сайта\n"
        "/stats - Моя статистика\n"
        "/menu - Показать это меню\n\n"
        "─────────────────\n\n"
        "🤖 Версия: 1.0.0\n"
        "📦 Технологии: Python, Pydoll, asyncio",
        parse_mode="Markdown"
    )

async def parse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /parse - запуск парсинга"""
    message = await update.message.reply_text("⏳ Запускаю асинхронный парсинг...")
    
    try:
        # Выполняем парсинг
        result = await parse_website()
        
        # Обновляем статистику пользователя
        if "user_data" in context.user_data:
            user_data = context.user_data["user_data"]
            user_data["parsed_count"] += 1
            user_data["last_parse"] = datetime.now().isoformat()
            context.user_data["user_data"] = user_data
        
        if result.success:
            await message.edit_text(
                f"✅ *Парсинг завершен успешно!*\n\n"
                f"📌 *Заголовок:* {result.title}\n"
                f"📝 *Контент:*\n{result.content}...\n\n"
                f"🔗 Источник: {result.url}\n"
                f"🕐 Время: {result.timestamp.strftime('%H:%M:%S')}\n\n"
                f"📋 Введите /menu для других команд",
                parse_mode="Markdown"
            )
        else:
            await message.edit_text(
                f"❌ *Ошибка при парсинге:*\n```\n{result.error}\n```\n"
                f"Попробуйте позже.\n\n"
                f"📋 Введите /menu для других команд",
                parse_mode="Markdown"
            )
        
    except asyncio.TimeoutError:
        await message.edit_text(
            "⏰ *Таймаут при парсинге*\n"
            "Сайт не ответил вовремя. Попробуйте позже.\n\n"
            "📋 Введите /menu для других команд",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        await message.edit_text(
            f"⚠️ *Произошла ошибка:*\n```\n{str(e)}\n```\n"
            f"📋 Введите /menu для других команд",
            parse_mode="Markdown"
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /stats - статистика"""
    user_data = context.user_data.get("user_data", {})
    
    parsed_count = user_data.get("parsed_count", 0)
    registered = user_data.get("registered_at")
    last_parse = user_data.get("last_parse")
    
    if registered:
        try:
            registered = datetime.fromisoformat(registered).strftime("%d.%m.%Y %H:%M")
        except:
            registered = "Неизвестно"
    
    if last_parse:
        try:
            last_parse = datetime.fromisoformat(last_parse).strftime("%d.%m.%Y %H:%M:%S")
        except:
            last_parse = "Никогда"
    
    await update.message.reply_text(
        f"📊 *Ваша статистика:*\n\n"
        f"👤 Пользователь: {user_data.get('first_name', 'Unknown')}\n"
        f"🆔 ID: {user_data.get('user_id')}\n"
        f"📅 Зарегистрирован: {registered}\n"
        f"📊 Выполнено парсингов: {parsed_count}\n"
        f"⏱ Последний парсинг: {last_parse}\n\n"
        f"📋 Введите /menu для других команд",
        parse_mode="Markdown"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    await update.message.reply_text(
        f"💬 Вы написали: *{update.message.text}*\n\n"
        f"Используйте /menu для списка команд.",
        parse_mode="Markdown"
    )

# --- Обработчик ошибок ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ *Произошла ошибка*\n"
            "Попробуйте позже.\n\n"
            "📋 Введите /menu для других команд",
            parse_mode="Markdown"
        )

# --- Установка команд меню в Telegram ---
async def set_commands(application: Application) -> None:
    """Установка команд для меню Telegram"""
    commands = [
        BotCommand("start", "Начать работу"),
        BotCommand("menu", "Показать меню"),
        BotCommand("parse", "Запустить парсинг"),
        BotCommand("stats", "Моя статистика"),
    ]
    await application.bot.set_my_commands(commands)

# --- Запуск бота ---
def main():
    """Главная функция запуска"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("parse", parse_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Устанавливаем команды для меню Telegram
    application.job_queue.run_once(set_commands, 0, chat_id=0)
    
    # Запускаем бота
    print("🚀 Бот запущен!")
    print("📋 Команды: /start, /menu, /parse, /stats")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()