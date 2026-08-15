"""
bot.py - Telegram бот
"""

import os
import json
import time
import asyncio
import signal
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.helpers import escape_markdown

from browser import (
    init_browser,
    close_browser,
    browser_goto,
    browser_get_text,
    browser_inspect,
    browser_screenshot,
    load_cookies_from_json,
    browser_ready,
    browser_page_info,
)
from dspy import init_dspy, run_agent, set_main_event_loop, dspy_agent_instance

logger = logging.getLogger(__name__)

# ============================================================
# GLOBAL STATE
# ============================================================

waiting_for_cookies = set()

# ============================================================
# TELEGRAM COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "🦊 Camoufox + DSPy Browser Agent\n\n"
        "Команды:\n"
        "/check <url>\n"
        "/dspy <задача>\n"
        "/inspect\n"
        "/inspect_map\n"
        "/cookies\n"
        "/cancel\n"
        "/status\n"
        "/screenshot"
    )


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажи URL:\n/check https://example.com"
        )
        return

    msg = await update.message.reply_text("Открываю...")

    try:
        result = await browser_goto(context.args[0])
        text = await browser_get_text()
        await msg.edit_text(f"{result}\n\n{text[:1500]}")
    except Exception as e:
        logger.exception("/check")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1000]}")


async def inspect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "🔎 Глубоко инспектирую страницу..."
    )

    try:
        result = await browser_inspect(
            max_interactive=150,
            max_links=100,
            max_text=15000,
            mode="full",
        )

        if len(result) > 4000:
            result = result[:4000] + "\n\n... [обрезано]"

        await msg.edit_text(result)

    except Exception as e:
        logger.exception("/inspect")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1500]}")


async def inspect_map_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    msg = await update.message.reply_text(
        "🗺️ Строю компактную карту страницы..."
    )

    try:
        result = await browser_inspect(
            max_interactive=120,
            max_links=80,
            max_text=8000,
            mode="map",
        )

        if len(result) > 4000:
            result = result[:4000] + "\n\n... [обрезано]"

        await msg.edit_text(result)

    except Exception as e:
        logger.exception("/inspect_map")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1500]}")


async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📸 Делаю скриншот...")

    try:
        path = await browser_screenshot()

        with open(path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="📸 Текущая страница",
            )

        await msg.delete()

    except Exception as e:
        logger.exception("/screenshot")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1000]}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = "—"
    title = "—"

    if browser_ready:
        try:
            info = await browser_page_info()
            url = info.split("\n")[0].replace("URL: ", "")
            title = info.split("\n")[1].replace("Title: ", "")
        except Exception:
            pass

    status_text = (
        "📦 *Статус системы*\n\n"
        f"🦊 Camoufox: {'✅' if browser_ready else '❌'}\n"
        f"🧠 DSPy: {'✅' if dspy_agent_instance else '❌'}\n\n"
        f"🌐 URL:\n`{escape_markdown(url, version=2)}`\n\n"
        f"📄 Title:\n{escape_markdown(title, version=2)}"
    )

    await update.message.reply_text(
        status_text,
        parse_mode="MarkdownV2",
    )


async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not browser_ready:
        await update.message.reply_text("Camoufox не запущен")
        return

    user_id = update.effective_user.id
    waiting_for_cookies.add(user_id)

    await update.message.reply_text(
        "🍪 Жду JSON-файл с cookies.\n\n"
        "Отправь файл следующим сообщением.\n\n"
        "Для отмены: /cancel"
    )


async def cancel_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in waiting_for_cookies:
        waiting_for_cookies.discard(user_id)
        await update.message.reply_text("Загрузка cookies отменена.")
    else:
        await update.message.reply_text("Нечего отменять.")


async def cookies_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in waiting_for_cookies:
        return

    document = update.message.document
    if not document:
        return

    filename = (document.file_name or "").lower()

    if not filename.endswith(".json"):
        await update.message.reply_text("Нужен именно JSON-файл.")
        return

    waiting_for_cookies.discard(user_id)

    msg = await update.message.reply_text("Загружаю cookies...")

    temp_path = (
        f"/tmp/cookies_{user_id}_{int(time.time())}.json"
    )

    try:
        telegram_file = await context.bot.get_file(document.file_id)
        await telegram_file.download_to_drive(temp_path)

        with open(temp_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = await load_cookies_from_json(data)

        loaded = result["loaded"]
        total = result["total"]
        errors = result["errors"]

        if loaded == 0:
            response = (
                "Не удалось загрузить ни одной cookie.\n\n"
                + "\n".join(f"• {e}" for e in errors[:15])
            )
        else:
            response = (
                "🍪 *Cookies обработаны!*\n\n"
                f"✅ Загружено: `{loaded}`\n"
                f"📦 Всего в файле: `{total}`"
            )

            if errors:
                response += "\n\n⚠️ Ошибки:\n"
                response += "\n".join(f"• {e}" for e in errors[:10])

        await msg.edit_text(response, parse_mode="Markdown")

    except json.JSONDecodeError:
        await msg.edit_text("Файл не является корректным JSON.")

    except Exception as e:
        logger.exception("Ошибка загрузки cookies")
        await msg.edit_text(
            "Ошибка загрузки cookies:\n\n"
            f"{str(e)[:2000]}"
        )

    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧠 DSPy Browser Agent\n\n"
            "Примеры:\n\n"
            "/dspy открой https://example.com и покажи заголовок\n\n"
            "/dspy найди Python на Google\n\n"
            "/dspy открой сайт и найди форму входа"
        )
        return

    if not dspy_agent_instance:
        await update.message.reply_text("DSPy не инициализирован")
        return

    if not browser_ready:
        await update.message.reply_text("Camoufox не запущен")
        return

    query = " ".join(context.args)
    msg = await update.message.reply_text(
        "🧠 DSPy управляет Camoufox..."
    )

    try:
        loop = asyncio.get_running_loop()

        answer = await loop.run_in_executor(
            None,
            run_agent,
            query,
        )

        answer = answer[:4000]
        safe_answer = escape_markdown(answer, version=2)

        await msg.edit_text(
            "✅ *Результат:*\n\n" + safe_answer,
            parse_mode="MarkdownV2",
        )

    except Exception as e:
        logger.exception("/dspy")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1000]}")


async def telegram_error_handler(update, context):
    logger.error("Telegram error", exc_info=context.error)

# ============================================================
# MAIN
# ============================================================

async def main():
    global main_event_loop

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

    main_event_loop = asyncio.get_running_loop()
    set_main_event_loop(main_event_loop)

    logger.info("Инициализация...")

    browser_ok = await init_browser()
    dspy_ok = init_dspy()

    app = (
        Application
        .builder()
        .token(token)
        .build()
    )

    app.add_error_handler(telegram_error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("inspect", inspect_command))
    app.add_handler(CommandHandler("inspect_map", inspect_map_command))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("cancel", cancel_cookies))

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            cookies_file,
        )
    )

    logger.info("Camoufox: %s", "OK" if browser_ok else "FAIL")
    logger.info("DSPy: %s", "OK" if dspy_ok else "FAIL")

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        logger.info("Telegram бот запущен!")

        stop_signal = asyncio.Event()

        def signal_handler():
            logger.info("Получен сигнал остановки")
            stop_signal.set()

        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)
        except (NotImplementedError, RuntimeError):
            pass

        while not stop_signal.is_set():
            await asyncio.sleep(60)
            logger.info("Bot alive")

    except Exception:
        logger.exception("Main error")

    finally:
        logger.info("Завершение...")

        try:
            await app.updater.stop()
        except Exception:
            pass

        try:
            await app.stop()
        except Exception:
            pass

        try:
            await app.shutdown()
        except Exception:
            pass

        await close_browser()


if __name__ == "__main__":
    asyncio.run(main())