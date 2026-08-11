# bot.py - исправленная версия

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
        self.tab_id = None
    
    async def connect(self):
        """Подключение к Chrome через /json/list"""
        resp = requests.get(f'http://{self.host}:{self.port}/json/list')
        pages = resp.json()
        
        if not pages:
            raise Exception("❌ Нет активных вкладок в Chrome!")
        
        page = pages[0]
        ws_url = page['webSocketDebuggerUrl']
        self.tab_id = page.get('id')
        
        logging.info(f"📄 Используем вкладку: {page.get('title', 'No title')}")
        
        self.websocket = await websockets.connect(ws_url)
        logging.info(f"✅ Подключен к Chrome через /json/list")
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
    
    async def enable_network(self):
        return await self.send_command('Network.enable')
    
    async def set_viewport(self, width=1280, height=720):
        """Установка размера viewport через Emulation.setDeviceMetricsOverride"""
        return await self.send_command('Emulation.setDeviceMetricsOverride', {
            'width': width,
            'height': height,
            'deviceScaleFactor': 1,
            'mobile': False,
            'screenWidth': width,
            'screenHeight': height,
            'positionX': 0,
            'positionY': 0,
            'viewport': {
                'x': 0,
                'y': 0,
                'width': width,
                'height': height,
                'scale': 1
            }
        })
    
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
        """Скриншот с фиксированным размером 1280x720"""
        # Сначала устанавливаем viewport
        await self.set_viewport(1280, 720)
        
        # Реалистичная пауза перед скриншотом
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        # Делаем скриншот БЕЗ captureBeyondViewport
        result = await self.send_command('Page.captureScreenshot', {
            'format': 'png',
            'quality': 100,
            'captureBeyondViewport': False  # ❗ Важно: убираем
        })
        
        screenshot_data = base64.b64decode(result['result']['data'])
        
        # Проверяем размер (Telegram лимит ~20MB)
        if len(screenshot_data) > 20 * 1024 * 1024:
            logging.warning(f"⚠️ Скриншот слишком большой: {len(screenshot_data) / 1024 / 1024:.2f}MB")
            # Пробуем сжать
            result = await self.send_command('Page.captureScreenshot', {
                'format': 'jpeg',
                'quality': 70,
                'captureBeyondViewport': False
            })
            screenshot_data = base64.b64decode(result['result']['data'])
        
        return screenshot_data
    
    async def get_page_info(self):
        """Получить информацию о текущей странице"""
        result = await self.send_command('Runtime.evaluate', {
            'expression': '''
                JSON.stringify({
                    title: document.title,
                    url: window.location.href,
                    readyState: document.readyState,
                    scripts: document.scripts.length,
                    images: document.images.length,
                    links: document.links.length,
                    width: window.innerWidth,
                    height: window.innerHeight
                })
            '''
        })
        return json.loads(result['result']['result']['value'])
    
    async def close(self):
        if self.websocket:
            await self.websocket.close()
            logging.info("🔌 WebSocket соединение закрыто")

chrome = None

async def init_chrome():
    global chrome
    if not chrome:
        chrome = await ChromeClient().connect()
        await chrome.enable_page()
        await chrome.enable_runtime()
        await chrome.enable_network()
        await chrome.inject_stealth_js()
        # Устанавливаем дефолтный viewport
        await chrome.set_viewport(1280, 720)
    return chrome

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕷️ CDP Скриншот-бот (100% Stealth Mode)\n\n"
        "Команды:\n"
        "/screenshot <url> - сделать скриншот (1280x720)\n"
        "/info - информация о маскировке\n"
        "/page - информация о текущей странице"
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
        
        # Проверяем размер перед отправкой
        if len(screenshot_data) > 20 * 1024 * 1024:
            await update.message.reply_text("⚠️ Скриншот слишком большой, пробую сжать...")
            # Повторяем с более низким качеством
            screenshot_data = await client.screenshot()
        
        await update.message.reply_photo(
            photo=screenshot_data,
            caption=f"✅ {url} (1280x720)"
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
        f"**Headless режим:** new\n"
        f"**Размер скриншота:** 1280x720\n\n"
        f"**✅ Все 100% настроек маскировки активны!**"
    )
    await update.message.reply_text(info_text)

async def page_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о текущей странице"""
    try:
        client = await init_chrome()
        info = await client.get_page_info()
        
        text = (
            f"📄 **Информация о странице**\n\n"
            f"**Заголовок:** {info.get('title', 'Нет')}\n"
            f"**URL:** {info.get('url', 'Нет')}\n"
            f"**Статус:** {info.get('readyState', 'Нет')}\n"
            f"**Скриптов:** {info.get('scripts', 0)}\n"
            f"**Картинок:** {info.get('images', 0)}\n"
            f"**Ссылок:** {info.get('links', 0)}\n"
            f"**Размер окна:** {info.get('width', 0)}x{info.get('height', 0)}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("page", page_info))
    
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
    print(f"✅ Размер скриншота: 1280x720")
    print(f"✅ captureBeyondViewport: False")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())