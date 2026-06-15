import os
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

# 1. Токены
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# 2. Создаем бота
bot = Bot(token=TOKEN)
dp = Dispatcher()

# 3. Команда /start
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Бот работает. Задай любой вопрос!")

# 4. На любое сообщение отвечает через OpenRouter
@dp.message()
async def ask_agent(message: Message):
    user_text = message.text
    
    # Запрос к OpenRouter
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [{"role": "user", "content": user_text}]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            result = await resp.json()
            answer = result["choices"][0]["message"]["content"]
            await message.answer(answer)

# 5. Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
