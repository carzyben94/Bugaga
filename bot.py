import os
import sys
import time
import logging
import base64
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# 1. ДОБАВЛЯЕМ ПУТЬ К BROWSER-HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

# ============================================================
# 2. ИМПОРТ ХЕЛПЕРОВ
# ============================================================

try:
    from browser_harness.helpers import *
    from browser_harness.admin import ensure_daemon, daemon_alive, restart_daemon
    print("✅ Импорт успешен!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

# ============================================================
# 3. НАСТРОЙКА
# ============================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

# Подключаемся к браузеру
os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

# ============================================================
# 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def attach_to_tab_by_url(url_part: str):
    """Находит вкладку по URL и принудительно привязывается к ней"""
    try:
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        
        for page in pages:
            if url_part in page.get("url", ""):
                target_id = page["id"]
                
                # ПРИНУДИТЕЛЬНО ПРИВЯЗЫВАЕМСЯ К ВКЛАДКЕ
                cdp("Target.attachToTarget", {
                    "targetId": target_id,
                    "flatten": True
                })
                
                logger.info(f"✅ Привязались к вкладке: {target_id}")
                logger.info(f"   URL: {page.get('url')}")
                return target_id
        
        # Если не найдено — берём последнюю
        if pages:
            target_id = pages[-1]["id"]
            cdp("Target.attachToTarget", {
                "targetId": target_id,
                "flatten": True
            })
            logger.warning(f"⚠️ {url_part} не найдена, привязались к последней: {target_id}")
            return target_id
        
        return None
    except Exception as e:
        logger.error(f"Ошибка привязки: {e}")
        return None

# ============================================================
# 5. КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Бот с browser-harness**\n\n"
        "Команды:\n"
        "/ping - проверка\n"
        "/info - информация о странице\n"
        "/screenshot - скриншот google.com\n"
        "/tabs - показать активные вкладки\n"
        "/restart - перезапустить браузер"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_tab("https://httpbin.org/html")
        wait_for_load()
        info = page_info()
        await update.message.reply_text(
            f"📄 **Страница:**\n"
            f"• Заголовок: {info.get('title', 'нет')}\n"
            f"• URL: {info.get('url', 'нет')}"
        )
    except Exception as e:
        logger.error(f"Ошибка /info: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("📸 Делаю скриншот...")
    try:
        # 1. Открываем НОВУЮ вкладку
        new_tab("https://google.com")
        wait_for_load()
        time.sleep(2)
        
        # 2. Принудительно привязываемся к вкладке с google.com
        session_id = attach_to_tab_by_url("google.com")
        
        if not session_id:
            raise ValueError("Не удалось привязаться к вкладке")
        
        logger.info(f"Session ID: {session_id}")
        
        # 3. Устанавливаем разрешение через CDP с sessionId
        cdp(
            "Emulation.setDeviceMetricsOverride",
            width=1280,
            height=720,
            deviceScaleFactor=1,
            mobile=False,
            session_id=session_id
        )
        time.sleep(1)
        
        # 4. Делаем скриншот через CDP с sessionId
        result = cdp(
            "Page.captureScreenshot",
            format="png",
            quality=80,
            captureBeyondViewport=False,
            session_id=session_id
        )
        screenshot_b64 = result.get("data")
        
        if not screenshot_b64:
            raise ValueError("Скриншот пустой")
        
        # Очищаем base64
        if ',' in screenshot_b64:
            screenshot_b64 = screenshot_b64.split(',', 1)[1]
        screenshot_b64 = screenshot_b64.strip()
        
        missing_padding = len(screenshot_b64) % 4
        if missing_padding:
            screenshot_b64 += '=' * (4 - missing_padding)
        
        img_bytes = base64.b64decode(screenshot_b64)
        
        if len(img_bytes) < 1000:
            raise ValueError("Скриншот слишком маленький")
        
        await update.message.reply_photo(
            photo=img_bytes,
            caption="📸 Скриншот google.com (1280x720)"
        )
        await status_msg.edit_text("✅ Скриншот отправлен!")
        
    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def tabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает активные вкладки"""
    try:
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        
        if not pages:
            await update.message.reply_text("📭 Нет активных вкладок")
            return
        
        msg = "📑 **Активные вкладки:**\n\n"
        for i, page in enumerate(pages[:10]):
            title = page.get("title", "Без названия")[:50]
            url = page.get("url", "unknown")[:60]
            session_id = page.get("id", "нет")[:20]
            msg += f"{i+1}. **{title}**\n   `{url}`\n   🆔 `{session_id}`\n\n"
        
        await update.message.reply_text(msg[:4000], parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапуск браузера"""
    status_msg = await update.message.reply_text("🔄 Перезапускаю браузер...")
    try:
        restart_daemon()
        time.sleep(2)
        ensure_daemon()
        await status_msg.edit_text("✅ Браузер перезапущен!")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 6. ЗАПУСК
# ============================================================

def main():
    print("🚀 Запуск бота...")
    
    if daemon_alive():
        print("✅ Daemon уже запущен")
    else:
        print("⚠️ Daemon не запущен, запускаем...")
        ensure_daemon()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("restart", restart))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()