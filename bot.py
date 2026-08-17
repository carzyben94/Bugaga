import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Конфигурация ───────────────────────────────────────────────
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Ключ TokenRouter API (вшит прямо в код)
TOKENROUTER_API_KEY = "sk-38bccoegrP4tGuLq7GgO7BT1b61oAaoQnZxUw7MkDbuEuycN"
MODEL_NAME = "qwen/qwen3.8-max-free"  # ← Обновлено

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

# ─── Клиент TokenRouter (OpenAI-совместимый) ───────────────────
client = AsyncOpenAI(
    base_url="https://api.tokenrouter.com/v1",
    api_key=TOKENROUTER_API_KEY,
)

SYSTEM_PROMPT = "Ты полезный и дружелюбный ассистент в Telegram. Отвечай кратко и по делу."


# ─── Хендлеры ──────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Привет! Я работаю на модели *{MODEL_NAME}* через TokenRouter.\n\n"
        "Просто напиши мне сообщение!\n"
        "/models — список доступных моделей",
        parse_mode="Markdown"
    )


async def models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все доступные Qwen-модели"""
    await update.message.chat.send_action("typing")
    try:
        resp = await client.models.list()
        qwen_models = sorted([m.id for m in resp.data if "qwen" in m.id.lower()])

        if not qwen_models:
            await update.message.reply_text("Модели Qwen не найдены.")
            return

        text = "📋 *Доступные Qwen модели:*\n\n" + "\n".join(
            f"• `{m}`" for m in qwen_models
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка получения списка моделей: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений через TokenRouter"""
    user_text = update.message.text.strip()
    if not user_text:
        return

    await update.message.chat.send_action("typing")

    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )

        reply = response.choices[0].message.content
        if not reply:
            reply = "⚠️ Модель вернула пустой ответ."

        # Telegram ограничивает сообщения 4096 символами
        max_len = 4000
        while reply:
            chunk = reply[:max_len]
            reply = reply[max_len:]
            await update.message.reply_text(chunk)

    except Exception as e:
        logger.error(f"Ошибка TokenRouter API: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка при генерации ответа:\n{e}")


# ─── Запуск ────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("models", models))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()