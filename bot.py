import os
import logging
import asyncio
import base64
import json
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

CHROME_PATH = '/usr/bin/chromium'

X_COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": "0lyNYlKnbjXejqIk_blw2x20TfMRtW3SWJ_jmpay.t4-1783123617.0158947-1.0.1.1-1rnugK6C5Aw5r.126FQ3rJYZTCG2WhtPATFYO5Ip0QukW40cCR0qDNfacg6VRv3vRh3w.4Un_NQ6hOnxQfvhm68Grg1hZiLbF6HAyxvxzmS06Q8AzQkKu_i248B5sxj7", "domain": ".x.com", "path": "/"}
]

user_browsers = {}

# ==================== МЕНЮ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "🤖 *Бот для X.com*\n\n"
        "🔐 *Авторизация*\n"
        "/login — Войти в X.com\n"
        "/screen — Скриншот текущей страницы\n\n"
        "🤖 *Умный агент*\n"
        "/agent <команда> — ИИ-агент для X.com\n"
        "  /agent что тут есть — анализ страницы\n"
        "  /agent профиль @username — переход в профиль\n"
        "  /agent фото — найти все фото\n"
        "  /agent лайк — лайкнуть твит\n"
        "  /agent подписчики — число подписчиков\n"
        "  /agent поиск текст — поиск\n\n"
        "⚡ *JavaScript*\n"
        "/eval <js> — Выполнить JavaScript"
    )
    await update.message.reply_text(menu, parse_mode='Markdown')

# ==================== АВТОРИЗАЦИЯ ====================

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        browser = Chrome(options=options)
        tab = await browser.start()
        
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        await tab.set_cookies(X_COOKIES)
        await asyncio.sleep(1)
        
        await tab.refresh()
        await asyncio.sleep(5)
        
        user_browsers[user_id] = (browser, tab)
        
        await update.message.reply_text("✅ Вход выполнен успешно!")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

# ==================== СКРИНШОТ ====================

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот текущей страницы"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        _, tab = user_browsers[user_id]
        
        # Даём странице немного подгрузиться
        await asyncio.sleep(1)
        
        # Делаем скриншот
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        
        # Получаем URL для подписи
        url = await tab.current_url
        
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"🖼️ Скриншот страницы\n📍 {url}"
        )
        
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Скриншот занимает слишком много времени. Попробуй ещё раз.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== УМНЫЙ АГЕНТ ====================

class XAgent:
    """Агент для автоматизации X.com"""
    
    def __init__(self, tab):
        self.tab = tab
        
    async def analyze_page(self):
        """Анализирует страницу и собирает информацию"""
        info = {
            'url': await self.tab.current_url,
            'title': await self.tab.title,
            'elements': {}
        }
        
        testids = await self.tab.execute_script("""
            (function() {
                const ids = {};
                document.querySelectorAll('[data-testid]').forEach(el => {
                    const id = el.dataset.testid;
                    if (!ids[id]) ids[id] = 0;
                    ids[id]++;
                });
                return ids;
            })()
        """)
        
        info['elements'] = testids
        return info
    
    async def find_action(self, command):
        """Находит действие по команде"""
        cmd = command.lower()
        
        # Навигация
        if any(w in cmd for w in ['главная', 'home', 'лента']):
            return {'code': "window.location.href = 'https://x.com/home'", 'desc': 'Переход на главную'}
        
        if any(w in cmd for w in ['explore', 'тренды']):
            return {'code': "window.location.href = 'https://x.com/explore'", 'desc': 'Переход на Explore'}
        
        if any(w in cmd for w in ['уведомления', 'notifications']):
            return {'code': "window.location.href = 'https://x.com/notifications'", 'desc': 'Переход в уведомления'}
        
        if any(w in cmd for w in ['сообщения', 'messages']):
            return {'code': "window.location.href = 'https://x.com/messages'", 'desc': 'Переход в сообщения'}
        
        # Профиль
        if 'профиль' in cmd or 'profile' in cmd:
            username = re.search(r'@?(\w+)', command)
            if username:
                user = username.group(1)
                if user not in ['профиль', 'profile']:
                    return {'code': f"window.location.href = 'https://x.com/{user}'", 'desc': f'Переход в профиль @{user}'}
        
        # Действия
        if 'лайк' in cmd:
            if 'все' in cmd:
                return {'code': "document.querySelectorAll('button[data-testid=\"like\"]').forEach(btn => btn.click())", 'desc': 'Лайкнуть все твиты'}
            return {'code': "document.querySelector('button[data-testid=\"like\"]')?.click()", 'desc': 'Лайкнуть первый твит'}
        
        if 'ретвит' in cmd or 'репост' in cmd:
            return {'code': "document.querySelector('button[data-testid=\"retweet\"]')?.click()", 'desc': 'Ретвитнуть первый твит'}
        
        if 'подпишись' in cmd or 'follow' in cmd:
            username = re.search(r'@?(\w+)', command)
            if username:
                user = username.group(1)
                if user not in ['подпишись', 'follow']:
                    return {'code': f"document.querySelector('div[data-testid=\"follow\"]')?.click()", 'desc': f'Подписаться на @{user}'}
            return {'code': "document.querySelector('div[data-testid=\"follow\"]')?.click()", 'desc': 'Подписаться'}
        
        if 'отпишись' in cmd or 'unfollow' in cmd:
            return {'code': "document.querySelector('div[data-testid=\"unfollow\"]')?.click()", 'desc': 'Отписаться'}
        
        # Поиск
        if any(w in cmd for w in ['найти', 'search', 'поиск']):
            query = re.sub(r'(найти|search|поиск)', '', cmd).strip()
            if query:
                return {'code': f"window.location.href = 'https://x.com/search?q={query}&src=typed_query'", 'desc': f'Поиск: {query}'}
        
        # Информация
        if any(w in cmd for w in ['подписчики', 'followers']):
            return {'code': "document.querySelector('a[href*=\"/followers\"] span')?.innerText || '0'", 'desc': 'Количество подписчиков'}
        
        if any(w in cmd for w in ['твиты', 'tweets']):
            return {'code': "document.querySelectorAll('article[data-testid=\"tweet\"]').length", 'desc': 'Количество твитов'}
        
        if any(w in cmd for w in ['заголовок', 'title']):
            return {'code': "document.title", 'desc': 'Заголовок страницы'}
        
        if 'url' in cmd:
            return {'code': "window.location.href", 'desc': 'Текущий URL'}
        
        # Фото
        if any(w in cmd for w in ['фото', 'photo', 'картинки']):
            return {'code': "document.querySelectorAll('img[src*=\"media\"]').forEach(img => console.log(img.src))", 'desc': 'Найти все фото'}
        
        # Прокрутка
        if 'вниз' in cmd:
            if 'много' in cmd or 'все' in cmd:
                return {'code': "window.scrollTo(0, document.body.scrollHeight)", 'desc': 'Прокрутить в самый низ'}
            return {'code': "window.scrollBy(0, 500)", 'desc': 'Прокрутить вниз на 500px'}
        
        if 'вверх' in cmd:
            if 'много' in cmd or 'все' in cmd:
                return {'code': "window.scrollTo(0, 0)", 'desc': 'Прокрутить в самый верх'}
            return {'code': "window.scrollBy(0, -500)", 'desc': 'Прокрутить вверх на 500px'}
        
        return None
    
    async def execute(self, command):
        """Выполняет команду"""
        action = await self.find_action(command)
        
        if not action:
            return {'success': False, 'message': 'Не понял команду'}
        
        try:
            result = await self.tab.execute_script(action['code'])
            return {
                'success': True,
                'description': action['desc'],
                'code': action['code'],
                'result': result
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Ошибка выполнения: {str(e)}',
                'code': action['code']
            }

async def agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Умный агент для X.com"""
    if not context.args:
        await update.message.reply_text(
            "🤖 *Агент X.com*\n\n"
            "Я понимаю команды на русском и английском:\n\n"
            "🌐 *Навигация*\n"
            "  главная, explore, тренды, уведомления, сообщения\n"
            "  профиль @username\n\n"
            "❤️ *Действия*\n"
            "  лайк, все лайки, ретвит, подписаться, отписаться\n\n"
            "📜 *Прокрутка*\n"
            "  вниз, вверх, вниз много, вверх много\n\n"
            "📊 *Информация*\n"
            "  подписчики, твиты, заголовок, url\n\n"
            "📸 *Фото*\n"
            "  фото, картинки\n\n"
            "🔍 *Поиск*\n"
            "  найти текст\n\n"
            "📝 *Примеры:*\n"
            "  /agent профиль elonmusk\n"
            "  /agent все лайки\n"
            "  /agent сколько подписчиков\n"
            "  /agent найти python\n"
            "  /agent фото",
            parse_mode='Markdown'
        )
        return
    
    command = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        
        agent = XAgent(tab)
        
        await update.message.reply_text("🤔 Анализирую команду...")
        
        result = await agent.execute(command)
        
        if result['success']:
            reply = f"🤖 *{result['description']}*\n\n"
            reply += f"```javascript\n{result['code']}\n```\n"
            
            if result['result'] is not None:
                if isinstance(result['result'], (list, dict)):
                    result_str = json.dumps(result['result'], ensure_ascii=False, indent=2)
                else:
                    result_str = str(result['result'])
                if len(result_str) > 300:
                    result_str = result_str[:300] + '...'
                reply += f"\n📊 *Результат:*\n{result_str}"
            
            await update.message.reply_text(reply, parse_mode='Markdown')
        else:
            reply = f"❌ *Ошибка*\n\n{result.get('message', 'Неизвестная ошибка')}"
            if 'code' in result:
                reply += f"\n\n```javascript\n{result['code']}\n```"
            await update.message.reply_text(reply, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== EVAL ====================

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи JS код\n"
            "Пример: /eval document.title"
        )
        return
    
    js_code = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        result = await tab.execute_script(js_code)
        
        if isinstance(result, dict):
            if 'result' in result and isinstance(result['result'], dict):
                if 'value' in result['result']:
                    result = result['result']['value']
            elif 'value' in result:
                result = result['value']
        
        if isinstance(result, (list, dict)):
            result = json.dumps(result, ensure_ascii=False, indent=2)
        
        await update.message.reply_text(f"✅ Результат:\n\n{str(result)[:500]}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ОБРАБОТЧИК ОШИБОК ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# ==================== MAIN ====================

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("agent", agent))
    application.add_handler(CommandHandler("eval", evaluate_js))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()