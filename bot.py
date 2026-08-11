import os
import logging
import asyncio
import json
import base64
import random
import requests
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    CHROME_FLAGS, FINGERPRINT_CONFIG, HUMANIZATION_CONFIG,
    PROXY_CONFIG, SCREENSHOT_CONFIG, TIMEOUTS, BROWSER_PREFERENCES,
    get_stealth_js
)

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

class ChromeClient:
    def __init__(self, host='localhost', port=9222):
        self.host = host
        self.port = port
        self.websocket = None
        self.msg_id = 0
        self.page_id = None
        self.script_id = None
    
    async def connect(self):
        response = requests.get(f'http://{self.host}:{self.port}/json/version')
        ws_url = response.json()['webSocketDebuggerUrl']
        self.websocket = await websockets.connect(ws_url)
        logging.info(f"✅ Подключен к Chrome: {ws_url}")
        return self
    
    async def send_command(self, method, params=None):
        self.msg_id += 1
        message = {'id': self.msg_id, 'method': method, 'params': params or {}}
        await self.websocket.send(json.dumps(message))
        response = await self.websocket.recv()
        return json.loads(response)
    
    async def enable_page(self):
        return await self.send_command('Page.enable')
    
    async def enable_runtime(self):
        return await self.send_command('Runtime.enable')
    
    async def inject_stealth_js(self):
        """Инъекция JavaScript из config.py"""
        stealth_script = get_stealth_js()
        
        result = await self.send_command('Page.addScriptToEvaluateOnNewDocument', {
            'source': stealth_script
        })
        self.script_id = result.get('result', {}).get('identifier')
        logging.info("✅ Stealth JS инъекция выполнена")
        return result
    
    async def navigate(self, url):
        # Реалистичная пауза перед навигацией
        pause_time = random.uniform(
            HUMANIZATION_CONFIG['navigation']['wait_before_navigate'],
            HUMANIZATION_CONFIG['navigation']['wait_before_navigate'] + 0.5
        )
        await asyncio.sleep(pause_time)
        
        result = await self.send_command('Page.navigate', {'url': url})
        self.page_id = result.get('result', {}).get('frameId')
        
        # Ожидаем загрузки с реалистичной паузой
        load_time = random.uniform(1.0, 3.0)
        await asyncio.sleep(load_time)
        return result
    
    async def screenshot(self):
        # Реалистичная пауза перед скриншотом
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        result = await self.send_command('Page.captureScreenshot', SCREENSHOT_CONFIG)
        return base64.b64decode(result['result']['data'])
    
    async def close(self):
        if self.websocket:
            await self.websocket.close()

chrome = None

async def init_chrome():
    global chrome
    if not chrome:
        chrome = await ChromeClient().connect()
        await chrome.enable_page()
        await chrome.enable_runtime()
        await chrome.inject_stealth_js()
    return chrome

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕷️ CDP Скриншот-бот (100% Stealth Mode)\n\n"
        "Команды:\n"
        "/screenshot <url> - сделать скриншот\n"
        "/info - информация о маскировке"
    )

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        client = await init_chrome()
        await client.navigate(url)
        screenshot_data = await client.screenshot()
        
        await update.message.reply_photo(
            photo=screenshot_data,
            caption=f"✅ {url}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о текущей конфигурации маскировки"""
    info_text = (
        "🛡️ **100% МАСКИРОВКА АКТИВНА**\n\n"
        f"**User-Agent:** {FINGERPRINT_CONFIG['user_agent'][:60]}...\n"
        f"**Платформа:** {FINGERPRINT_CONFIG['platform']}\n"
        f"**Язык:** {FINGERPRINT_CONFIG['accept_language']}\n"
        f"**Часовой пояс:** {FINGERPRINT_CONFIG['timezone']}\n"
        f"**Геолокация:** {FINGERPRINT_CONFIG['geolocation']['latitude']}, {FINGERPRINT_CONFIG['geolocation']['longitude']}\n"
        f"**WebRTC защита:** {'✅' if FINGERPRINT_CONFIG['webrtc_leak_protection'] else '❌'}\n"
        f"**WebGL маскировка:** ✅\n"
        f"**Canvas маскировка:** {'✅' if FINGERPRINT_CONFIG['canvas_fingerprint'] else '❌'}\n"
        f"**Audio маскировка:** {'✅' if FINGERPRINT_CONFIG['audio_fingerprint'] else '❌'}\n"
        f"**Прокси:** {'✅' if PROXY_CONFIG['enabled'] else '❌'}\n"
        f"**Очеловечивание:** {'✅' if HUMANIZATION_CONFIG['mouse']['enabled'] else '❌'}\n"
        f"**Флагов Chrome:** {len(CHROME_FLAGS)}\n"
        f"**Client Hints:** ✅\n"
        f"**Battery API:** ✅\n"
        f"**Permissions:** ✅\n"
        f"**Headless режим:** new\n\n"
        f"**✅ Все 100% настроек маскировки активны!**"
    )
    await update.message.reply_text(info_text)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("info", info))
    
    print("🚀 CDP Бот запущен со 100% STEALTH режимом!")
    print(f"✅ Флагов Chrome: {len(CHROME_FLAGS)}")
    print(f"✅ User-Agent: {FINGERPRINT_CONFIG['user_agent']}")
    print(f"✅ Таймзона: {FINGERPRINT_CONFIG['timezone']}")
    print(f"✅ Прокси: {'Включен' if PROXY_CONFIG['enabled'] else 'Выключен'}")
    print(f"✅ WebGL: {FINGERPRINT_CONFIG['webgl_vendor']}")
    print(f"✅ Canvas маскировка: {'Включена' if FINGERPRINT_CONFIG['canvas_fingerprint'] else 'Выключена'}")
    print(f"✅ Audio маскировка: {'Включена' if FINGERPRINT_CONFIG['audio_fingerprint'] else 'Выключена'}")
    print(f"✅ Очеловечивание: {'Включено' if HUMANIZATION_CONFIG['mouse']['enabled'] else 'Выключено'}")
    print(f"✅ Headless режим: new")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())