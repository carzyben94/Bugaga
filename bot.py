import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Импортируем модуль с Accessibility Tree
from accessibility import UniversalModel, get_accessibility_snapshot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")


# ---------- Тестовая команда ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Бот работает!\n\n"
        "Модуль accessibility.py подключен.\n"
        "UniversalModel доступен."
    )


async def test_ax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки модуля"""
    try:
        # Проверяем, что модуль импортирован
        from accessibility import UniversalModel, UniversalElement, get_accessibility_snapshot
        
        # Создаём тестовую модель
        test_model = UniversalModel()
        test_model.title = "Тестовая страница"
        test_model.url = "https://test.com"
        
        # Добавляем тестовую кнопку
        test_button = UniversalElement(
            role="button",
            name="Тестовая кнопка",
            ref="@e0",
            states={"enabled": True}
        )
        test_model.buttons.append(test_button)
        
        result = "✅ Модуль accessibility.py работает!\n\n"
        result += f"📄 Страница: {test_model.title}\n"
        result += f"🔘 Кнопок: {len(test_model.buttons)}\n"
        result += f"  • {test_model.buttons[0].name} [{test_model.buttons[0].ref}]"
        
        await update.message.reply_text(result)
        
    except ImportError as e:
        await update.message.reply_text(f"❌ Ошибка импорта: {e}")


# ---------- Main ----------

def main():
    print("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_ax))
    
    print("🚀 Бот запущен! Проверь /test")
    app.run_polling()


if __name__ == "__main__":
    main()