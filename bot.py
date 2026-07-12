import os
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Добавляем текущую папку в путь (чтобы найти accessibility.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем модуль с Accessibility Tree
try:
    from accessibility import UniversalModel, UniversalElement, get_accessibility_snapshot
    print("✅ Модуль accessibility.py найден и импортирован!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print(f"   Файл accessibility.py должен лежать в {os.path.dirname(os.path.abspath(__file__))}")
    UniversalModel = None
    get_accessibility_snapshot = None

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
        "Проверь /test - покажет, найден ли модуль"
    )


async def test_ax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки модуля"""
    try:
        if UniversalModel is None:
            await update.message.reply_text("❌ Модуль accessibility.py НЕ НАЙДЕН!\n\nФайл должен лежать в одной папке с bot.py")
            return
        
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