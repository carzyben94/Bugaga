import os
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from cloakbrowser import launch_async

# Проверяем наличие __version__
try:
    from cloakbrowser import __version__ as pkg_version
except ImportError:
    pkg_version = "неизвестно (старая версия)"

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Используй /check <url> или /version")

async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка версии CloakBrowser без проблемного импорта"""
    try:
        # Проверяем бинарник через командную строку
        result = subprocess.run(
            ['cloakbrowser', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        bin_version = result.stdout.strip() or result.stderr.strip() or 'неизвестно'
        
        # Проверяем, что бинарник работает
        result2 = subprocess.run(
            ['cloakbrowser', '--help'],
            capture_output=True,
            text=True,
            timeout=5
        )
        is_working = "CloakBrowser" in result2.stdout or "CloakBrowser" in result2.stderr
        
        await update.message.reply_text(
            f"📦 **CloakBrowser**\n"
            f"• Пакет: `{pkg_version}`\n"
            f"• Бинарник: `{bin_version}`\n"
            f"• Статус: {'✅ Работает' if is_working else '⚠️ Проблема'}\n"
            f"• Путь: `{subprocess.run(['which', 'cloakbrowser'], capture_output=True, text=True).stdout.strip() or 'не найден'}`"
        )
    except FileNotFoundError:
        await update.message.reply_text(
            f"❌ **CloakBrowser не установлен!**\n\n"
            f"Установите командой:\n"
            f"`python -m cloakbrowser install`"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /check https://example.com")
        return
    
    url = context.args[0]
    msg = await update.message.reply_text("⏳ Загружаю через CloakBrowser...")
    
    try:
        browser = await launch_async(
            headless=True,
            fingerprint=True,
            timeout=30000
        )
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        title = await page.title()
        content = await page.content()
        await browser.close()
        
        response = f"✅ {title}\n\n{content[:500]}..."
        await msg.edit_text(response[:4096])
        
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:200]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("check", check))
    app.run_polling()

if __name__ == "__main__":
    main()