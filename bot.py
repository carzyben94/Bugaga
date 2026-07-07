import os
import logging
import aiohttp
from typing import List, Dict
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ==================== НАСТРОЙКИ ====================
logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# ==================== API X.COM ====================

class XComAPI:
    def __init__(self):
        self.guest_token = None
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        await self._get_guest_token()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _get_guest_token(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Content-Type': 'application/json',
            }
            async with self.session.post('https://x.com/i/api/1.1/guest/activate.json', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.guest_token = data.get('guest_token')
        except:
            pass
    
    def _headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
            'x-guest-token': self.guest_token or '',
            'Accept': 'application/json',
        }
    
    async def get_tweets(self, username: str, count: int = 10) -> List[Dict]:
        try:
            url = f'https://x.com/i/api/1.1/statuses/user_timeline.json?screen_name={username}&count={count}&tweet_mode=extended'
            async with self.session.get(url, headers=self._headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse(data)
                return []
        except:
            return []
    
    def _parse(self, tweets: List[Dict]) -> List[Dict]:
        result = []
        for t in tweets:
            user = t.get('user', {})
            created = t.get('created_at', '')
            try:
                dt = datetime.strptime(created, '%a %b %d %H:%M:%S +0000 %Y')
                created = dt.strftime('%d %B %Y, %H:%M')
            except:
                pass
            
            result.append({
                'id': t.get('id_str', ''),
                'text': t.get('full_text', t.get('text', '')),
                'author': user.get('name', 'Неизвестно'),
                'username': user.get('screen_name', ''),
                'likes': t.get('favorite_count', 0),
                'retweets': t.get('retweet_count', 0),
                'replies': t.get('reply_count', 0),
                'created_at': created,
            })
        return result
    
    async def search_tweets(self, query: str, count: int = 10) -> List[Dict]:
        try:
            url = f'https://x.com/i/api/1.1/search/tweets.json?q={query}&count={count}&tweet_mode=extended'
            async with self.session.get(url, headers=self._headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse(data.get('statuses', []))
                return []
        except:
            return []

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def escape(text):
    if not text:
        return text
    for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, f'\\{ch}')
    return text

def format_tweet(t: Dict, i: int) -> str:
    text = f"**{i}.** {escape(t['author'])} (@{escape(t['username'])})\n"
    txt = escape(t['text'])
    txt = txt[:200] + '...' if len(txt) > 200 else txt
    text += f"📝 {txt}\n"
    if t.get('created_at'):
        text += f"📅 {t['created_at']}\n"
    text += f"❤️ {t['likes']:,} | 🔁 {t['retweets']:,} | 💬 {t['replies']:,}\n"
    if t.get('id'):
        text += f"🔗 https://x.com/{t['username']}/status/{t['id']}\n"
    text += "\n"
    return text

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Твиты", callback_data="tweets")],
        [InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
    ])
    await update.message.reply_text(
        "🤖 **Twitter Parser**\nВыбери действие:",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

async def tweets_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: `/tweets elonmusk`", parse_mode='Markdown')
        return
    username = context.args[0].replace('@', '')
    await update.message.reply_text(f"⏳ Парсю @{username}...")
    try:
        async with XComAPI() as api:
            tweets = await api.get_tweets(username, 10)
        if not tweets:
            await update.message.reply_text("😕 Твиты не найдены")
            return
        reply = f"📊 **{len(tweets)} твитов от @{username}:**\n\n"
        for i, t in enumerate(tweets, 1):
            reply += format_tweet(t, i)
            if len(reply) > 4000:
                await update.message.reply_text(reply, parse_mode='Markdown')
                reply = ""
        if reply:
            await update.message.reply_text(reply, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи запрос: `/search #python`", parse_mode='Markdown')
        return
    query = ' '.join(context.args)
    await update.message.reply_text(f"⏳ Ищу '{query}'...")
    try:
        async with XComAPI() as api:
            tweets = await api.search_tweets(query, 10)
        if not tweets:
            await update.message.reply_text("😕 Ничего не найдено")
            return
        reply = f"🔍 **Результаты '{query}':**\n\n"
        for i, t in enumerate(tweets, 1):
            reply += format_tweet(t, i)
            if len(reply) > 4000:
                await update.message.reply_text(reply, parse_mode='Markdown')
                reply = ""
        if reply:
            await update.message.reply_text(reply, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи username: `/profile elonmusk`", parse_mode='Markdown')
        return
    username = context.args[0].replace('@', '')
    await update.message.reply_text(f"⏳ Профиль @{username}...")
    try:
        async with XComAPI() as api:
            tweets = await api.get_tweets(username, 5)
        if not tweets:
            await update.message.reply_text("😕 Профиль не найден")
            return
        reply = f"👤 **Профиль @{username}**\n\n📝 {tweets[0]['author']}\n🐦 {len(tweets)} твитов\n\n"
        for i, t in enumerate(tweets[:5], 1):
            txt = t['text'][:100] + '...' if len(t['text']) > 100 else t['text']
            reply += f"**{i}.** {escape(txt)}\n❤️ {t['likes']:,} | 🔁 {t['retweets']:,}\n\n"
        await update.message.reply_text(reply, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if action == "tweets":
        context.user_data['waiting'] = 'tweets'
        await query.message.reply_text("👤 Введи username (например: elonmusk)")
    elif action == "search":
        context.user_data['waiting'] = 'search'
        await query.message.reply_text("🔍 Введи запрос (например: #python)")
    elif action == "profile":
        context.user_data['waiting'] = 'profile'
        await query.message.reply_text("👤 Введи username")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    action = context.user_data.get('waiting')
    
    if action == 'tweets':
        context.user_data['waiting'] = None
        await tweets_cmd(update, context.with_args([text]))
    elif action == 'search':
        context.user_data['waiting'] = None
        await search_cmd(update, context.with_args(text.split()))
    elif action == 'profile':
        context.user_data['waiting'] = None
        await profile_cmd(update, context.with_args([text]))

# ==================== ЗАПУСК ====================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tweets", tweets_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()

if __name__ == "__main__":
    main()