import os
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from twifork import Client

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

logging.basicConfig(level=logging.INFO)

# ==================== КУКИ ПРЯМО В КОДЕ ====================
COOKIES_DATA = [
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cuid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "lang",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "ru"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "dnt",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "1"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_marketing",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_ads",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "personalization_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\""
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "twid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "u%3D2067347503503052800"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "auth_token",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "ct0",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cf_bm",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "kXHc9bKDnh3VBAj2Zf3fCc6UUjO5VmliR2SUQvCQ96U-1783519754.100902-1.0.1.1-B1vTWfu988KtDzfqK8x1LwZlZKPRJwVYH385IpVxdY3Gv8hcH4vShkh1WEMenfjcOJ7LagGdDQOtQkIXx1E.BVU7TQ3.u5YpaKD7fdsNsS3FU54NN9E5TMJ1cYSnnoEb"
    }
]

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
twitter_client = Client('en-US')
COOKIES_FILE = "cookies.json"

def save_and_load_cookies():
    """Сохраняет куки в файл и загружает их"""
    try:
        # Сохраняем в файл
        with open(COOKIES_FILE, 'w') as f:
            json.dump(COOKIES_DATA, f, indent=2)
        logging.info(f"✅ Куки сохранены в {COOKIES_FILE} ({len(COOKIES_DATA)} шт.)")
        
        # Загружаем в клиент
        twitter_client.load_cookies(COOKIES_FILE)
        logging.info("✅ Куки загружены в клиент")
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка работы с куками: {e}")
        return False

# ==================== КОМАНДЫ БОТА ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для Twitter.\n\n"
        "Доступные команды:\n"
        "/tweet <запрос> - поиск твитов (до 5 шт.)\n"
        "/user <username> - информация о пользователе\n"
        "/cookies - статус авторизации\n\n"
        "📌 Бот работает через неофициальное API"
    )

async def search_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи запрос: /tweet запрос")
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу: *{query}*...", parse_mode='Markdown')
    
    try:
        tweets = await twitter_client.search_tweet(query, limit=5)
        
        if not tweets:
            await update.message.reply_text("😕 Ничего не найдено")
            return
        
        result = f"📊 *Результаты по запросу:* {query}\n\n"
        for i, tweet in enumerate(tweets[:5], 1):
            text = tweet.text[:150] + "..." if len(tweet.text) > 150 else tweet.text
            result += f"{i}. {text}\n"
            result += f"   ❤️ {tweet.favorite_count} | 🔄 {tweet.retweet_count}\n\n"
        
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        logging.error(f"Ошибка search_tweet: {e}")

async def get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: /user username")
        return
    
    username = context.args[0].replace("@", "")
    await update.message.reply_text(f"👤 Ищу пользователя @{username}...")
    
    try:
        user = await twitter_client.get_user_by_screen_name(username)
        
        result = (
            f"👤 *{user.name}* (@{user.screen_name})\n"
            f"📝 {user.description[:200] if user.description else 'Нет описания'}\n\n"
            f"📊 Подписчики: {user.followers_count:,}\n"
            f"📊 Подписки: {user.friends_count:,}\n"
            f"📊 Твитов: {user.statuses_count:,}"
        )
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        logging.error(f"Ошибка get_user: {e}")

async def cookies_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус кук"""
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                data = json.load(f)
                count = len(data)
            # Проверяем наличие важных кук
            has_auth = any(c.get('name') == 'auth_token' for c in data)
            has_ct0 = any(c.get('name') == 'ct0' for c in data)
            
            status = "✅ Куки загружены\n"
            status += f"📦 Всего: {count} шт.\n"
            status += f"🔑 auth_token: {'✅' if has_auth else '❌'}\n"
            status += f"🔑 ct0: {'✅' if has_ct0 else '❌'}"
            
            await update.message.reply_text(status)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Ошибка чтения: {e}")
    else:
        await update.message.reply_text("❌ Файл кук не найден")

async def reload_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезагрузить куки (админ)"""
    if ADMIN_ID and str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⛔ Только для администратора")
        return
    
    if save_and_load_cookies():
        await update.message.reply_text("✅ Куки перезагружены успешно")
    else:
        await update.message.reply_text("❌ Ошибка перезагрузки кук")

# ==================== ЗАПУСК ====================

def main():
    # Сохраняем и загружаем куки
    save_and_load_cookies()
    
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tweet", search_tweet))
    app.add_handler(CommandHandler("user", get_user))
    app.add_handler(CommandHandler("cookies", cookies_status))
    app.add_handler(CommandHandler("reload", reload_cookies))
    
    # Запускаем
    logging.info("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()