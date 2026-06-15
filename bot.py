import os
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# Бесплатные модели по порядку
MODELS = [
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "google/gemma-2-9b-it:free", 
    "mistralai/mistral-7b-instruct:free",
    "cohere/command-r-plus-08-2024:free",
    "qwen/qwen-2.5-7b-instruct:free"
]

bot = Bot(token=TOKEN)
dp = Dispatcher()

current_model_index = 0

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(f"Бот работает. Модель: {MODELS[current_model_index]}")

@dp.message()
async def ask_agent(message: Message):
    global current_model_index
    
    for i in range(len(MODELS)):
        model_index = (current_model_index + i) % len(MODELS)
        model = MODELS[model_index]
        
        result = await ask_openrouter(message.text, model)
        
        if result["success"]:
            current_model_index = model_index
            await message.answer(result["answer"])
            return
        else:
            # Если модель не работает, пробуем следующую
            continue
    
    await message.answer("Все модели временно недоступны. Попробуйте позже.")

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
                else:
                    return {"success": False, "error": f"Status {resp.status}"}
        except:
            return {"success": False, "error": "Timeout or connection error"}

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
