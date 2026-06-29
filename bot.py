# bot.py - Бот с агентом-исследователем (без ошибок)
import os
import sys
import subprocess
import json
import logging
import traceback
import asyncio
import random
import time
from datetime import datetime
from typing import Dict, List, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ========== НАСТРОЙКА ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

# ========== КУКИ ==========
COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
browser_data = None
browser_lock = False

# ========== УПРАВЛЕНИЕ БРАУЗЕРОМ ==========
async def get_browser():
    global browser_data, browser_lock
    
    if browser_data:
        try:
            await browser_data['page'].evaluate('1')
            return browser_data
        except:
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
    
    while browser_lock:
        await asyncio.sleep(0.5)
    
    browser_lock = True
    
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        await stealth_async(page)
        
        browser_data = {
            'playwright': p,
            'browser': browser,
            'context': context,
            'page': page
        }
        
        return browser_data
    finally:
        browser_lock = False

async def close_browser():
    global browser_data
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None

# ========== АГЕНТ-ИССЛЕДОВАТЕЛЬ ==========
class Researcher:
    def __init__(self, page, chat_id, bot):
        self.page = page
        self.chat_id = chat_id
        self.bot = bot
        self.results = {
            'pages': [],
            'elements': [],
            'buttons': [],
            'links': [],
            'screenshots': []
        }
        self.visited = set()
        self.step = 0
        self.total = 20
        
    async def send_progress(self, text):
        self.step += 1
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"🔍 [{self.step}/{self.total}] {text}"
            )
        except:
            pass
    
    async def explore(self):
        await self.send_progress("Начинаю исследование...")
        
        # 1. Собираем элементы
        await self.send_progress("Собираю все элементы на странице...")
        elements = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('*').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        result.push({
                            tag: el.tagName.toLowerCase(),
                            text: el.textContent?.trim()?.slice(0, 100) || '',
                            testid: el.getAttribute('data-testid') || '',
                            id: el.id || '',
                            class: el.className || '',
                            x: Math.round(rect.x + rect.width / 2),
                            y: Math.round(rect.y + rect.height / 2)
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['elements'] = elements
        await self.send_progress(f"Найдено элементов: {len(elements)}")
        
        # 2. Ищем кнопки
        await self.send_progress("Ищу кнопки...")
        buttons = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('button, [role="button"], [data-testid*="button"]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        result.push({
                            text: el.textContent?.trim()?.slice(0, 50) || '',
                            testid: el.getAttribute('data-testid') || '',
                            x: Math.round(rect.x + rect.width / 2),
                            y: Math.round(rect.y + rect.height / 2)
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['buttons'] = buttons
        await self.send_progress(f"Найдено кнопок: {len(buttons)}")
        
        # 3. Ищем ссылки
        await self.send_progress("Ищу ссылки...")
        links = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('a[href]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        result.push({
                            text: el.textContent?.trim()?.slice(0, 50) || '',
                            href: el.getAttribute('href') || '',
                            x: Math.round(rect.x + rect.width / 2),
                            y: Math.round(rect.y + rect.height / 2)
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['links'] = links
        await self.send_progress(f"Найдено ссылок: {len(links)}")
        
        # 4. Скриншот
        await self.send_progress("Делаю скриншот...")
        try:
            screenshot = await self.page.screenshot(type='jpeg', quality=80)
            await self.bot.send_photo(
                chat_id=self.chat_id,
                photo=screenshot,
                caption="📸 Скриншот страницы"
            )
        except:
            pass
        
        # 5. Сохраняем результат
        filename = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
        
        await self.send_progress(f"✅ Исследование завершено! Файл: {filename}")
        
        return filename

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот-исследователь X.com\n\n"
        "Команды:\n"
        "/xlogin - войти в X.com\n"
        "/explore - запустить исследование 🚀\n"
        "/tweets - показать посты\n"
        "/tweet N - показать пост N\n"
        "/last - последний пост\n"
        "/screen - скриншот\n"
        "/status - статус браузера\n"
        "/close - закрыть браузер"
    )

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Вход в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('about:blank')
        await page.wait_for_timeout(500)
        
        await browser['context'].clear_cookies()
        for cookie in COOKIES:
            try:
                await browser['context'].add_cookies([cookie])
            except:
                pass
        
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=15000)
        await page.wait_for_timeout(2000)
        
        await msg.edit_text("✅ Вход выполнен!")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:150]}")

async def explore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск исследования"""
    await update.message.reply_text(
        "🚀 **ЗАПУСК ИССЛЕДОВАНИЯ**\n\n"
        "Агент собирает:\n"
        "• Все элементы страницы\n"
        "• Кнопки и ссылки\n"
        "• Делает скриншот\n\n"
        "⏳ Ожидайте..."
    )
    
    try:
        browser = await get_browser()
        if not browser:
            await update.message.reply_text("❌ Браузер не открыт. Сначала /xlogin")
            return
        
        page = browser['page']
        if 'x.com' not in page.url:
            await update.message.reply_text("❌ Сначала зайди на X.com через /xlogin")
            return
        
        # Создаем исследователя
        researcher = Researcher(page, update.effective_chat.id, context.bot)
        
        # Запускаем исследование
        filename = await researcher.explore()
        
        # Отправляем файл
        await update.message.reply_document(
            document=open(filename, 'rb'),
            filename=filename,
            caption="📊 Результаты исследования"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Ищу посты...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        for _ in range(2):
            await page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(0.5)
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    const author = el.querySelector('[data-testid="User-Name"]')?.textContent?.trim() || '';
                    if (text) {
                        result.push({
                            text: text.slice(0, 100),
                            author: author.slice(0, 30)
                        });
                    }
                });
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text("❌ Посты не найдены")
            return
        
        text = f"📋 Найдено {len(posts)} постов:\n\n"
        for i, post in enumerate(posts[:10], 1):
            text += f"{i}. {post['author']}: {post['text'][:60]}...\n"
        
        if len(posts) > 10:
            text += f"\n... и еще {len(posts)-10} постов"
        
        await msg.edit_text(text)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:150]}")

async def tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи номер: /tweet 1")
        return
    
    try:
        num = int(context.args[0]) - 1
    except:
        await update.message.reply_text("❌ Укажи число")
        return
    
    msg = await update.message.reply_text(f"🔍 Ищу пост #{num+1}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    const author = el.querySelector('[data-testid="User-Name"]')?.textContent?.trim() || '';
                    const likes = el.querySelector('[data-testid="like"]')?.textContent?.trim() || '0';
                    const retweets = el.querySelector('[data-testid="retweet"]')?.textContent?.trim() || '0';
                    if (text) {
                        result.push({
                            text: text.slice(0, 200),
                            author: author,
                            likes: likes,
                            retweets: retweets
                        });
                    }
                });
                return result;
            }
        ''')
        
        if num >= len(posts):
            await msg.edit_text(f"❌ Пост #{num+1} не найден. Всего: {len(posts)}")
            return
        
        post = posts[::-1][num]
        
        await msg.edit_text(
            f"📌 #{num+1} @{post['author']}\n\n"
            f"{post['text']}\n\n"
            f"❤️ {post['likes']}  🔁 {post['retweets']}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:150]}")

async def last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ['1']
    await tweet(update, context)

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await msg.delete()
        await update.message.reply_photo(photo=screenshot, caption="📸 Скриншот")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        browser = await get_browser()
        page = browser['page']
        title = await page.title()
        
        await update.message.reply_text(
            f"✅ Браузер работает\n"
            f"📌 {title[:50]}\n"
            f"🔗 {page.url[:60]}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Браузер не открыт: {str(e)[:100]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await update.message.reply_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("explore", explore))
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("tweet", tweet))
    app.add_handler(CommandHandler("last", last))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    print("🤖 Бот запущен!")
    print("Команды: /xlogin, /explore, /tweets, /tweet, /last, /screen, /status, /close")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()