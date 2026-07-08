import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from twscrape import API
from twscrape.logger import set_log_level

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

set_log_level("ERROR")
logging.basicConfig(level=logging.INFO)

# ==================== КУКИ ПРЯМО В КОДЕ ====================
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

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
api = API()

async def init_api():
    """Инициализация с куками из кода"""
    try:
        await api.pool.add_account(
            username="temp",
            password="temp",
            email="temp@temp.com",
            cookies=COOKIES
        )
        await api.pool.login_all()
        logging.info("✅ Twscrape инициализирован с куками из кода")
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации: {e}")
        return False

# ==================== КОМАНДЫ БОТА ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для Twitter.\n\n"
        "Доступные команды:\n"
        "/tweet <запрос> - поиск твитов (до 5 шт.)\n"
        "/user <username> - информация о пользователе\n"
        "/cookies - статус авторизации\n"
        "/reload - перезагрузить куки (только админ)\n\n"
        "📌 Бот работает через неофициальное API (twscrape)"
    )

async def search_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи запрос: /tweet запрос")
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу: *{query}*...", parse_mode='Markdown')
    
    try:
        tweets = []
        async for tweet in api.search(query, limit=5):
            tweets.append(tweet)
        
        if not tweets:
            await update.message.reply_text("😕 Ничего не найдено")
            return
        
        result = f"📊 *Результаты по запросу:* {query}\n\n"
        for i, tweet in enumerate(tweets[:5], 1):
            text = tweet.rawContent[:150] + "..." if len(tweet.rawContent) > 150 else tweet.rawContent
            result += f"{i}. {text}\n"
            result += f"   ❤️ {tweet.likeCount} | 🔄 {tweet.retweetCount}"
            if hasattr(tweet, 'created_at'):
                result += f" | 🕐 {str(tweet.created_at)[:10]}"
            result += "\n\n"
        
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = str(e)[:200]
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")
        logging.error(f"Ошибка search_tweet: {e}")

async def get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: /user username")
        return
    
    username = context.args[0].replace("@", "")
    await update.message.reply_text(f"👤 Ищу пользователя @{username}...")
    
    try:
        user = await api.user(username)
        
        result = (
            f"👤 *{user.displayname}* (@{user.username})\n"
            f"📝 {user.description[:200] if user.description else 'Нет описания'}\n\n"
            f"📊 Подписчики: {user.followersCount:,}\n"
            f"📊 Подписки: {user.friendsCount:,}\n"
            f"📊 Твитов: {user.statusesCount:,}\n"
            f"📅 Регистрация: {str(user.created)[:10] if user.created else 'Н/Д'}"
        )
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = str(e)[:200]
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")
        logging.error(f"Ошибка get_user: {e}")

async def cookies_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса кук"""
    try:
        test = await api.user("twitter")
        if test:
            await update.message.reply_text(
                f"✅ Куки работают!\n"
                f"📦 Текущий аккаунт: @{test.username}\n"
                f"🔑 Авторизация: успешна"
            )
        else:
            await update.message.reply_text("⚠️ Куки не работают, нужно обновить")
    except Exception as e:
        await update.message.reply_text(f"❌ Куки не работают: {str(e)[:100]}")

async def reload_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезагрузить куки (только админ)"""
    if ADMIN_ID and str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⛔ Только для администратора")
        return
    
    global api
    api = API()
    
    if await init_api():
        await update.message.reply_text("✅ Куки перезагружены успешно")
    else:
        await update.message.reply_text("❌ Ошибка перезагрузки кук")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logging.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Произошла ошибка. Попробуйте позже или используйте /reload"
        )

# ==================== ЗАПУСК ====================

async def main():
    # Инициализация
    await init_api()
    
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tweet", search_tweet))
    app.add_handler(CommandHandler("user", get_user))
    app.add_handler(CommandHandler("cookies", cookies_status))
    app.add_handler(CommandHandler("reload", reload_cookies))
    
    # Регистрируем обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Запускаем
    logging.info("🚀 Бот запущен")
    
    # Правильный способ запуска в python-telegram-bot >= 21.0
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Держим бота запущенным
    try:
        # Бесконечный цикл, пока бот работает
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logging.info("⏹️ Остановка бота...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⏹️ Программа завершена")