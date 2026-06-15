import os
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

# 1. Токены
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# 2. Модели
MODELS = [
    "openrouter/free",
    "openai/gpt-oss-120b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a9b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

# 3. Кнопки меню
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🤖 Спросить ИИ")],
        [KeyboardButton(text="📋 О боте"), KeyboardButton(text="🔄 Сменить модель")]
    ],
    resize_keyboard=True
)

# 4. Создание бота
bot = Bot(token=TOKEN)
dp = Dispatcher()
current_model = 0

# 5. Команда /start
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"Привет! Я бот с ИИ.\nТекущая модель: {MODELS[current_model]}",
        reply_markup=menu_keyboard
    )

# 6. Обработка кнопок меню
@dp.message()
async def handle_menu(message: Message):
    global current_model
    
    text = message.text
    
    if text == "🤖 Спросить ИИ":
        await message.answer("Напиши свой вопрос, я передам его ИИ")
    
    elif text == "📋 О боте":
        await message.answer(
            f"Бот использует OpenRouter\n"
            f"Модель: {MODELS[current_model]}\n"
            f"Доступно моделей: {len(MODELS)}\n"
            f"При лимите переключается автоматически"
        )
    
    elif text == "🔄 Сменить модель":
        current_model = (current_model + 1) % len(MODELS)
        await message.answer(f"Модель изменена на: {MODELS[current_model]}")
    
    else:
        # Обычный вопрос к ИИ
        await ask_and_reply(message)

# 7. Функция запроса к ИИ
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
            print(f"Лимит: {model}")
            continue
    
    await message.answer("Все модели временно недоступны. Попробуйте позже.")

# 8. Запрос к OpenRouter
async def ask_openrouter(prompt, model):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500
    }
    
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

# 9. Запуск
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
