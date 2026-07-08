import os
import logging
import asyncio
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from twscrape import API
from twscrape.logger import set_log_level

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

set_log_level("ERROR")
logging.basicConfig(level=logging.INFO)

# ==================== КУКИ ====================
COOKIES = (
    "auth_token=c9d83e923e1ad6cf67d19a0bc4f9877a49087936; "
    "ct0=39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb; "
    "guest_id=v1%3A178267838599411411; "
    "guest_id_marketing=v1%3A178267838599411411; "
    "guest_id_ads=v1%3A178267838599411411; "
    "lang=ru; "
    "dnt=1; "
    "__cuid=55d2d7c5-4888-430a-b024-dd785da46ef4; "
    "personalization_id=\"v1_DKrxLZAC902dMFdd1QrVYg==\"; "
    "twid=u%3D2067347503503052800; "
    "__cf_bm=kXHc9bKDnh3VBAj2Zf3fCc6UUjO5VmliR2SUQvCQ96U-1783519754.100902-1.0.1.1-B1vTWfu988KtDzfqK8x1LwZlZKPRJwVYH385IpVxdY3Gv8hcH4vShkh1WEMenfjcOJ7LagGdDQOtQkIXx1E.BVU7TQ3.u5YpaKD7fdsNsS3FU54NN9E5TMJ1cYSnnoEb"
)

# ==================== API ====================
api = None

async def init_api():
    global api
    try:
        api = API()
        await api.pool.add_account_cookies("temp", COOKIES)
        logging.info("✅ Аккаунт добавлен с куками")
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        return False

# ==================== ФОРМАТИРОВАНИЕ ====================

def format_number(num):
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)

def clean_text(text):
    """Удаляет ссылки из текста"""
    text = re.sub(r'https?://\S+|www\.\S+|t\.co/\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def format_tweet(tweet, index=None):
    text = tweet.rawContent[:150] + "..." if len(tweet.rawContent) > 150 else tweet.rawContent
    text = clean_text(text)
    
    result = ""
    if index:
        result += f"{index}. "
    result += f"{text}\n"
    result += f"   ❤️ {format_number(tweet.likeCount)}"
    result += "\n"
    return result

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие со списком команд"""
    await update.message.reply_text(
        "/tweet <запрос> - поиск твитов\n"
        "/tweets <username> - твиты пользователя\n"
        "/polymarket - твиты @polymarket\n"
        "/ateobreaking - твиты @ateobreaking\n"
        "/cookies - статус кук"
    )

async def search_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /tweet <запрос>\nПример: /tweet python")
        return
    
    query = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        tweets = []
        async for tweet in api.search(query, limit=5):
            tweets.append(tweet)
        
        if not tweets:
            await msg.edit_text("😕 Ничего не найдено")
            return
        
        result = f"📊 Результаты: {query}\n\n"
        for i, tweet in enumerate(tweets[:5], 1):
            result += format_tweet(tweet, i) + "\n"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:150]}")

async def user_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /tweets <username>\nПример: /tweets elonmusk")
        return
    
    username = context.args[0].replace("@", "")
    msg = await update.message.reply_text(f"📝 Твиты @{username}...")
    
    try:
        user = await api.user_by_login(username)
        tweets = []
        async for tweet in api.user_tweets(user.id, limit=5):
            tweets.append(tweet)
        
        if not tweets:
            await msg.edit_text(f"😕 У @{username} нет твитов")
            return
        
        result = f"📝 Твиты @{username}:\n\n"
        for i, tweet in enumerate(tweets[:5], 1):
            result += format_tweet(tweet, i) + "\n"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:150]}")

async def polymarket_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Твиты @polymarket"""
    msg = await update.message.reply_text("📝 Твиты @polymarket...")
    
    try:
        user = await api.user_by_login("polymarket")
        tweets = []
        async for tweet in api.user_tweets(user.id, limit=5):
            tweets.append(tweet)
        
        if not tweets:
            await msg.edit_text("😕 У @polymarket нет твитов")
            return
        
        result = f"📝 Твиты @polymarket:\n\n"
        for i, tweet in enumerate(tweets[:5], 1):
            result += format_tweet(tweet, i) + "\n"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:150]}")

async def ateobreaking_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Твиты @ateobreaking"""
    msg = await update.message.reply_text("📝 Твиты @ateobreaking...")
    
    try:
        user = await api.user_by_login("ateobreaking")
        tweets = []
        async for tweet in api.user_tweets(user.id, limit=5):
            tweets.append(tweet)
        
        if not tweets:
            await msg.edit_text("😕 У @ateobreaking нет твитов")
            return
        
        result = f"📝 Твиты @ateobreaking:\n\n"
        for i, tweet in enumerate(tweets[:5], 1):
            result += format_tweet(tweet, i) + "\n"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:150]}")

async def cookies_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = await api.user_by_login("twitter")
        await update.message.reply_text(f"✅ Куки работают! Аккаунт: @{user.username}")
    except Exception as e:
        await update.message.reply_text(f"❌ Куки не работают: {str(e)[:100]}")

# ==================== ЗАПУСК ====================

async def main():
    await init_api()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tweet", search_tweet))
    app.add_handler(CommandHandler("tweets", user_tweets))
    app.add_handler(CommandHandler("polymarket", polymarket_tweets))
    app.add_handler(CommandHandler("ateobreaking", ateobreaking_tweets))
    app.add_handler(CommandHandler("cookies", cookies_status))
    
    logging.info("🚀 Бот запущен")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logging.info("⏹️ Остановка...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())