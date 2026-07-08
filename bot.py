import os
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from twscrape import API
from twscrape.logger import set_log_level

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

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
current_user = None

async def init_api():
    global api, current_user
    try:
        api = API()
        await api.pool.add_account_cookies("temp", COOKIES)
        logging.info("✅ Аккаунт добавлен с куками")
        
        # Получаем текущего пользователя
        current_user = await api.user_by_login("temp")  # или любой существующий
        logging.info(f"✅ Авторизован как: @{current_user.username if current_user else 'unknown'}")
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        return False

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_number(num):
    """Форматирует число (1000 -> 1K, 1000000 -> 1M)"""
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)

def format_tweet(tweet, index=None):
    """Форматирует твит для вывода"""
    text = tweet.rawContent[:200] + "..." if len(tweet.rawContent) > 200 else tweet.rawContent
    result = ""
    if index:
        result += f"{index}. "
    result += f"{text}\n"
    result += f"   ❤️ {format_number(tweet.likeCount)} | 🔄 {format_number(tweet.retweetCount)} | 💬 {format_number(tweet.replyCount)}"
    if hasattr(tweet, 'created_at'):
        result += f" | 🕐 {str(tweet.created_at)[:10]}"
    result += "\n"
    return result

# ==================== КОМАНДЫ БОТА ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск твитов", callback_data="help_search")],
        [InlineKeyboardButton("👤 Инфо о пользователе", callback_data="help_user")],
        [InlineKeyboardButton("📊 Тренды", callback_data="help_trends")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_all")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Привет! Я бот для Twitter.\n\n"
        "📌 *Основные команды:*\n"
        "/tweet <запрос> - поиск твитов\n"
        "/user <username> - инфо о пользователе\n"
        "/tweets <username> - последние твиты пользователя\n"
        "/followers <username> - список подписчиков\n"
        "/following <username> - список подписок\n"
        "/trends - текущие тренды\n"
        "/search_user <запрос> - поиск пользователей\n"
        "/cookies - статус авторизации\n\n"
        "📌 *Дополнительно:*\n"
        "/reload - перезагрузить куки (админ)",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ==================== 1. ПОИСК ТВИТОВ ====================

async def search_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи запрос: /tweet запрос")
        return
    
    query = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: *{query}*...", parse_mode='Markdown')
    
    try:
        tweets = []
        async for tweet in api.search(query, limit=10):
            tweets.append(tweet)
        
        if not tweets:
            await msg.edit_text("😕 Ничего не найдено")
            return
        
        result = f"📊 *Результаты по запросу:* {query}\n\n"
        for i, tweet in enumerate(tweets[:10], 1):
            result += format_tweet(tweet, i) + "\n"
        
        await msg.edit_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== 2. ИНФО О ПОЛЬЗОВАТЕЛЕ ====================

async def get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: /user username")
        return
    
    username = context.args[0].replace("@", "")
    msg = await update.message.reply_text(f"👤 Ищу @{username}...")
    
    try:
        user = await api.user_by_login(username)
        
        # Создаём клавиатуру с действиями
        keyboard = [
            [InlineKeyboardButton("📝 Твиты", callback_data=f"usertweets_{username}")],
            [InlineKeyboardButton("👥 Подписчики", callback_data=f"followers_{username}")],
            [InlineKeyboardButton("📋 Подписки", callback_data=f"following_{username}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        result = (
            f"👤 *{user.displayname}* (@{user.username})\n"
            f"📝 {user.rawDescription[:300] if user.rawDescription else 'Нет описания'}\n\n"
            f"📊 *Статистика:*\n"
            f"   👥 Подписчики: {format_number(user.followersCount)}\n"
            f"   📋 Подписки: {format_number(user.friendsCount)}\n"
            f"   📝 Твитов: {format_number(user.statusesCount)}\n"
            f"   ❤️ Лайков: {format_number(user.favouritesCount)}\n"
            f"   📅 Регистрация: {str(user.created)[:10] if user.created else 'Н/Д'}\n"
            f"   🔒 { 'Приватный' if user.protected else 'Публичный' } аккаунт"
        )
        await msg.edit_text(result, parse_mode='Markdown', reply_markup=reply_markup)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== 3. ТВИТЫ ПОЛЬЗОВАТЕЛЯ ====================

async def user_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: /tweets username")
        return
    
    username = context.args[0].replace("@", "")
    msg = await update.message.reply_text(f"📝 Получаю твиты @{username}...")
    
    try:
        user = await api.user_by_login(username)
        tweets = []
        async for tweet in api.user_tweets(user.id, limit=10):
            tweets.append(tweet)
        
        if not tweets:
            await msg.edit_text(f"😕 У @{username} нет твитов")
            return
        
        result = f"📝 *Последние твиты @{username}:*\n\n"
        for i, tweet in enumerate(tweets[:10], 1):
            result += format_tweet(tweet, i) + "\n"
        
        await msg.edit_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== 4. ПОДПИСЧИКИ ====================

async def get_followers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: /followers username")
        return
    
    username = context.args[0].replace("@", "")
    msg = await update.message.reply_text(f"👥 Получаю подписчиков @{username}...")
    
    try:
        user = await api.user_by_login(username)
        followers = []
        async for follower in api.followers(user.id, limit=10):
            followers.append(follower)
        
        if not followers:
            await msg.edit_text(f"😕 У @{username} нет подписчиков")
            return
        
        result = f"👥 *Подписчики @{username}:*\n\n"
        for i, follower in enumerate(followers[:10], 1):
            result += f"{i}. @{follower.username} - {follower.displayname}\n"
            if follower.rawDescription:
                desc = follower.rawDescription[:50] + "..." if len(follower.rawDescription) > 50 else follower.rawDescription
                result += f"   📝 {desc}\n"
        
        await msg.edit_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== 5. ПОДПИСКИ ====================

async def get_following(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: /following username")
        return
    
    username = context.args[0].replace("@", "")
    msg = await update.message.reply_text(f"📋 Получаю подписки @{username}...")
    
    try:
        user = await api.user_by_login(username)
        following = []
        async for follow in api.following(user.id, limit=10):
            following.append(follow)
        
        if not following:
            await msg.edit_text(f"😕 @{username} ни на кого не подписан")
            return
        
        result = f"📋 *Подписки @{username}:*\n\n"
        for i, follow in enumerate(following[:10], 1):
            result += f"{i}. @{follow.username} - {follow.displayname}\n"
            if follow.rawDescription:
                desc = follow.rawDescription[:50] + "..." if len(follow.rawDescription) > 50 else follow.rawDescription
                result += f"   📝 {desc}\n"
        
        await msg.edit_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== 6. ТРЕНДЫ ====================

async def get_trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📊 Получаю тренды...")
    
    try:
        # Получаем тренды (WOEID = 1 для мировых)
        trends = await api.trends(1)
        
        if not trends:
            await msg.edit_text("😕 Не удалось получить тренды")
            return
        
        result = "📊 *Тренды Twitter:*\n\n"
        for i, trend in enumerate(trends[:10], 1):
            result += f"{i}. {trend.name}\n"
            if hasattr(trend, 'tweet_volume') and trend.tweet_volume:
                result += f"   📊 {format_number(trend.tweet_volume)} твитов\n"
        
        await msg.edit_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== 7. ПОИСК ПОЛЬЗОВАТЕЛЕЙ ====================

async def search_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи запрос: /search_user запрос")
        return
    
    query = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу пользователей: *{query}*...", parse_mode='Markdown')
    
    try:
        users = []
        async for user in api.search_users(query, limit=10):
            users.append(user)
        
        if not users:
            await msg.edit_text("😕 Ничего не найдено")
            return
        
        result = f"👤 *Результаты поиска пользователей:* {query}\n\n"
        for i, user in enumerate(users[:10], 1):
            result += f"{i}. @{user.username} - {user.displayname}\n"
            if user.rawDescription:
                desc = user.rawDescription[:80] + "..." if len(user.rawDescription) > 80 else user.rawDescription
                result += f"   📝 {desc}\n"
            result += f"   👥 {format_number(user.followersCount)} подписчиков\n\n"
        
        await msg.edit_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== 8. СТАТУС КУК ====================

async def cookies_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = await api.user_by_login("twitter")
        await update.message.reply_text(
            f"✅ Куки работают!\n"
            f"📦 Аккаунт: @{user.username}\n"
            f"🔑 Авторизация: успешна"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Куки не работают: {str(e)[:100]}")

# ==================== 9. ПЕРЕЗАГРУЗКА КУК ====================

async def reload_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⛔ Только для администратора")
        return
    
    global api
    api = API()
    if await init_api():
        await update.message.reply_text("✅ Куки перезагружены")
    else:
        await update.message.reply_text("❌ Ошибка перезагрузки")

# ==================== ОБРАБОТЧИК КНОПОК ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    username = data.split('_', 1)[1] if '_' in data else None
    
    if data == "help_search":
        await query.edit_message_text(
            "🔍 *Поиск твитов*\n\n"
            "Используй: `/tweet запрос`\n"
            "Пример: `/tweet python programming`\n\n"
            "Найдёт до 10 последних твитов по вашему запросу.",
            parse_mode='Markdown'
        )
    
    elif data == "help_user":
        await query.edit_message_text(
            "👤 *Информация о пользователе*\n\n"
            "Используй: `/user username`\n"
            "Пример: `/user elonmusk`\n\n"
            "Покажет профиль, статистику и кнопки для быстрого доступа к твитам, подписчикам и подпискам.",
            parse_mode='Markdown'
        )
    
    elif data == "help_trends":
        await query.edit_message_text(
            "📊 *Тренды Twitter*\n\n"
            "Используй: `/trends`\n\n"
            "Покажет 10 самых популярных тем в Twitter на данный момент.",
            parse_mode='Markdown'
        )
    
    elif data == "help_all":
        await query.edit_message_text(
            "📌 *Все команды бота:*\n\n"
            "🔍 `/tweet <запрос>` - поиск твитов\n"
            "👤 `/user <username>` - инфо о пользователе\n"
            "📝 `/tweets <username>` - последние твиты\n"
            "👥 `/followers <username>` - список подписчиков\n"
            "📋 `/following <username>` - список подписок\n"
            "📊 `/trends` - текущие тренды\n"
            "🔍 `/search_user <запрос>` - поиск пользователей\n"
            "🍪 `/cookies` - статус авторизации\n"
            "🔄 `/reload` - перезагрузить куки (админ)",
            parse_mode='Markdown'
        )
    
    elif data.startswith("usertweets_"):
        await query.edit_message_text(f"📝 Получаю твиты @{username}...")
        # Вызываем функцию с контекстом
        context.args = [username]
        await user_tweets(update, context)
    
    elif data.startswith("followers_"):
        await query.edit_message_text(f"👥 Получаю подписчиков @{username}...")
        context.args = [username]
        await get_followers(update, context)
    
    elif data.startswith("following_"):
        await query.edit_message_text(f"📋 Получаю подписки @{username}...")
        context.args = [username]
        await get_following(update, context)

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
    app.add_handler(CommandHandler("tweets", user_tweets))
    app.add_handler(CommandHandler("followers", get_followers))
    app.add_handler(CommandHandler("following", get_following))
    app.add_handler(CommandHandler("trends", get_trends))
    app.add_handler(CommandHandler("search_user", search_users))
    app.add_handler(CommandHandler("cookies", cookies_status))
    app.add_handler(CommandHandler("reload", reload_cookies))
    
    # Регистрируем обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logging.info("🚀 Бот запущен")
    logging.info("📋 Доступные команды:")
    logging.info("  /tweet <запрос> - поиск твитов")
    logging.info("  /user <username> - инфо о пользователе")
    logging.info("  /tweets <username> - последние твиты")
    logging.info("  /followers <username> - подписчики")
    logging.info("  /following <username> - подписки")
    logging.info("  /trends - тренды")
    logging.info("  /search_user <запрос> - поиск пользователей")
    logging.info("  /cookies - статус кук")
    logging.info("  /reload - перезагрузка кук (админ)")
    
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