import os
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# Модели (оставляем твой список)
MODELS = [
    "openrouter/free",
    "openai/gpt-oss-120b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a9b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

# Кнопки меню
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="🤖 Спросить ИИ")],
        [types.KeyboardButton(text="📋 О боте"), types.KeyboardButton(text="🔄 Сменить модель")]
    ],
    resize_keyboard=True
)

bot = Bot(token=TOKEN)
dp = Dispatcher()
current_model = 0

# Webhook URL (Render сам подставит)
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL") + WEBHOOK_PATH

# --- Все твои старые хендлеры ---
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"Бот работает (webhook). Модель: {MODELS[current_model]}",
        reply_markup=menu_keyboard
    )

@dp.message()
async def handle_menu(message: Message):
    global current_model
    text = message.text
    
    if text == "🤖 Спросить ИИ":
        await message.answer("Напиши свой вопрос")
    elif text == "📋 О боте":
        await message.answer(f"Модель: {MODELS[current_model]}\nДоступно: {len(MODELS)}")
    elif text == "🔄 Сменить модель":
        current_model = (current_model + 1) % len(MODELS)
        await message.answer(f"Модель: {MODELS[current_model]}")
    else:
        await ask_and_reply(message)

async def ask_and_reply(message: Message):
    global current_model
    await message.answer("🤔 Думаю...")
    
    for i in range(len(MODELS)):
        model_index = (current_model + i) % len(MODELS)
        model = MODELS[model_index]
        result = await ask_openrouter(message.text, model)
        
        if result["success"]:
            current_model = model_index
            await message.answer(result["answer"])
            return
        elif result["error"] == "limit":
            continue
    
    await message.answer("Все модели недоступны")

async def ask_openrouter(prompt, model):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 500}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return {"success": True, "answer": result["choices"][0]["message"]["content"]}
                elif resp.status == 429:
                    return {"success": False, "error": "limit"}
                else:
                    return {"success": False, "error": f"http_{resp.status}"}
        except:
            return {"success": False, "error": "timeout"}

# --- Запуск через Webhook (а не polling) ---
async def on_startup():
    await bot.delete_webhook()  # Принудительно чистим старые хуки
    await bot.set_webhook(WEBHOOK_URL)  # Устанавливаем новый

async def main():
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
    await site.start()
    
    print(f"Webhook set to {WEBHOOK_URL}")
    await asyncio.Event().wait()  # Бесконечное ожидание

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
