import os
import logging
import asyncio
import json
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

def format_tweet(tweet, index=None):
    text = tweet.rawContent[:150] + "..." if len(tweet.rawContent) > 150 else tweet.rawContent
    result = ""
    if index:
        result += f"{index}. "
    result += f"{text}\n"
    result += f"   ❤️ {format_number(tweet.likeCount)} | 🔄 {format_number(tweet.retweetCount)}"
    result += "\n"
    return result

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие со списком команд"""
    await update.message.reply_text(
        "👋 Привет! Я Twitter-бот.\n\n"
        "📋 Команды:\n"
        "/tweet <запрос> - поиск твитов\n"
        "/user <username> - профиль\n"
        "/tweets <username> - твиты пользователя\n"
        "/trends - тренды\n"
        "/test - диагностика всех методов\n"
        "/cookies - статус кук\n"
        "/help - справка"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    await update.message.reply_text(
        "📋 Команды:\n\n"
        "/tweet <запрос> - поиск твитов\n"
        "Пример: /tweet python\n\n"
        "/user <username> - профиль пользователя\n"
        "Пример: /user elonmusk\n\n"
        "/tweets <username> - последние твиты\n"
        "Пример: /tweets elonmusk\n\n"
        "/trends - текущие тренды\n"
        "/test - диагностика всех методов API\n\n"
        "/cookies - проверить статус кук\n"
        "/help - показать это сообщение"
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

async def get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /user <username>\nПример: /user elonmusk")
        return
    
    username = context.args[0].replace("@", "")
    msg = await update.message.reply_text(f"👤 Ищу @{username}...")
    
    try:
        user = await api.user_by_login(username)
        
        result = (
            f"👤 {user.displayname} (@{user.username})\n"
            f"📝 {user.rawDescription[:150] if user.rawDescription else 'Нет описания'}\n\n"
            f"👥 Подписчики: {format_number(user.followersCount)}\n"
            f"📋 Подписки: {format_number(user.friendsCount)}\n"
            f"📝 Твитов: {format_number(user.statusesCount)}"
        )
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

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полная диагностика всех методов API"""
    msg = await update.message.reply_text("🔄 Запускаю полную диагностику...")
    
    result = "🔍 **Полная диагностика API**\n\n"
    
    # 1. Проверка статуса аккаунта
    try:
        user = await api.user_by_login("twitter")
        result += "✅ **Аккаунт:** работает\n"
        result += f"   @{user.username}\n\n"
    except Exception as e:
        result += f"❌ **Аккаунт:** ошибка - {str(e)[:50]}\n\n"
    
    # 2. Проверка всех методов с приставкой "trend"
    trend_methods = [m for m in dir(api) if 'trend' in m.lower() and not m.startswith('_')]
    result += f"📌 **Методы с 'trend':** {len(trend_methods)}\n"
    for method in trend_methods:
        result += f"   • {method}\n"
    result += "\n"
    
    # 3. Тестируем каждый метод отдельно
    result += "🧪 **Тестирование методов:**\n"
    
    # 3.1 trends()
    result += "\n**1. api.trends('trending'):**\n"
    try:
        count = 0
        async for trend in api.trends("trending", limit=5):
            count += 1
        result += f"   ✅ Получено {count} трендов\n"
    except Exception as e:
        result += f"   ❌ Ошибка: {str(e)[:100]}\n"
    
    # 3.2 trends() с другими категориями
    for cat in ["news", "sport", "entertainment"]:
        result += f"\n**api.trends('{cat}'):**\n"
        try:
            count = 0
            async for trend in api.trends(cat, limit=3):
                count += 1
            result += f"   ✅ Получено {count} трендов\n"
        except Exception as e:
            result += f"   ❌ Ошибка: {str(e)[:100]}\n"
    
    # 3.3 trends_raw()
    result += "\n**api.trends_raw('trending'):**\n"
    try:
        count = 0
        async for raw in api.trends_raw("trending", limit=3):
            count += 1
            # Показываем структуру первого элемента
            if count == 1:
                data_str = json.dumps(raw, indent=2, ensure_ascii=False)[:200]
                result += f"   Структура: {data_str}\n"
                break
        result += f"   ✅ Получено {count} элементов\n"
    except Exception as e:
        result += f"   ❌ Ошибка: {str(e)[:100]}\n"
    
    # 3.4 Поиск доступных методов с "available"
    if hasattr(api, 'trends_available'):
        result += "\n**api.trends_available():**\n"
        try:
            available = await api.trends_available()
            result += f"   ✅ Получено {len(available)} локаций\n"
            if available:
                first = available[0]
                result += f"   Первая: {first}\n"
        except Exception as e:
            result += f"   ❌ Ошибка: {str(e)[:100]}\n"
    
    # 3.5 Попытка получить WOEID через другой метод
    if hasattr(api, 'available_trends'):
        result += "\n**api.available_trends():**\n"
        try:
            available = await api.available_trends()
            result += f"   ✅ Получено {len(available)} локаций\n"
        except Exception as e:
            result += f"   ❌ Ошибка: {str(e)[:100]}\n"
    
    # 4. Проверка других методов
    result += "\n📊 **Другие методы:**\n"
    
    # search
    try:
        count = 0
        async for tweet in api.search("twitter", limit=2):
            count += 1
        result += f"   ✅ search(): {count} результатов\n"
    except Exception as e:
        result += f"   ❌ search(): {str(e)[:50]}\n"
    
    # user_by_login
    try:
        user = await api.user_by_login("twitter")
        result += f"   ✅ user_by_login(): @{user.username}\n"
    except Exception as e:
        result += f"   ❌ user_by_login(): {str(e)[:50]}\n"
    
    # Обрезаем если слишком длинно
    if len(result) > 4000:
        result = result[:3900] + "\n\n... обрезано"
    
    await msg.edit_text(result, parse_mode="Markdown")

async def trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать текущие тренды"""
    msg = await update.message.reply_text("📊 Загружаю тренды...")
    
    try:
        trends_data = []
        
        # Пробуем через обычный trends
        try:
            async for trend in api.trends("trending", limit=20):
                trends_data.append(trend)
        except Exception as e:
            logging.warning(f"Ошибка trends: {e}")
        
        # Если не получилось, пробуем другие категории
        if not trends_data:
            for cat in ["news", "sport", "entertainment"]:
                try:
                    async for trend in api.trends(cat, limit=10):
                        trends_data.append(trend)
                    if trends_data:
                        break
                except:
                    continue
        
        # Если все еще пусто, пробуем через trends_raw
        if not trends_data:
            try:
                async for raw in api.trends_raw("trending", limit=10):
                    if isinstance(raw, dict) and 'trends' in raw:
                        for t in raw['trends']:
                            if isinstance(t, dict) and 'name' in t:
                                trends_data.append(t)
                    break
            except:
                pass
        
        if not trends_data:
            await msg.edit_text(
                "😕 Не удалось получить тренды\n\n"
                "Возможные причины:\n"
                "• Куки устарели\n"
                "• API Twitter изменился\n"
                "• Аккаунт ограничен\n\n"
                "Используй /test для диагностики"
            )
            return
        
        result = "🔥 **Тренды Twitter**\n\n"
        
        for i, trend in enumerate(trends_data[:20], 1):
            if isinstance(trend, dict):
                name = trend.get('name', str(trend))
                count = trend.get('tweet_count')
            else:
                name = trend.name if hasattr(trend, 'name') else str(trend)
                count = trend.tweet_count if hasattr(trend, 'tweet_count') else None
            
            result += f"{i}. {name}"
            if count:
                result += f" ({format_number(count)} твитов)"
            result += "\n"
        
        if len(result) > 4000:
            result = result[:3900] + "\n\n... и еще много трендов"
        
        await msg.edit_text(result, parse_mode="Markdown")
        
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
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tweet", search_tweet))
    app.add_handler(CommandHandler("user", get_user))
    app.add_handler(CommandHandler("tweets", user_tweets))
    app.add_handler(CommandHandler("trends", trends))
    app.add_handler(CommandHandler("test", test_command))
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