import os
import json
import logging
import asyncio
import subprocess
import requests
import base64
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

class CDPClient:
    def __init__(self):
        self.ws = None
        self.message_id = 0
        self.chrome_process = None
        self.ws_url = None
        self.is_launching = False
        
    def get_first_tab_ws(self):
        """Получить WebSocket URL первой вкладки"""
        try:
            resp = requests.get("http://localhost:9222/json/list", timeout=2)
            pages = resp.json()
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
            return None
        except:
            return None
    
    async def ensure_chrome(self):
        """Убедиться что Chrome запущен и подключиться"""
        # Проверяем, есть ли подключение
        if self.ws:
            try:
                # Пинг через простую команду
                await self.send_command("Runtime.evaluate", {"expression": "1"})
                return True, "✅ Уже подключен"
            except:
                self.ws = None
        
        # Проверяем, запущен ли Chrome
        ws_url = self.get_first_tab_ws()
        if ws_url:
            success, msg = await self.connect()
            if success:
                return True, "✅ Подключен к существующему Chrome"
        
        # Запускаем Chrome
        success, msg = await self.launch_chrome()
        if success:
            # Подключаемся
            success2, msg2 = await self.connect()
            if success2:
                return True, f"✅ Chrome запущен и подключен"
            return False, msg2
        return False, msg
    
    async def launch_chrome(self):
        """Запустить Chrome"""
        try:
            if self.is_launching:
                return False, "⏳ Уже запускается..."
            
            self.is_launching = True
            
            # Ищем Chrome
            chrome_paths = [
                'google-chrome',
                'google-chrome-stable',
                'chromium-browser',
                'chromium',
                'chrome'
            ]
            
            chrome_cmd = None
            for path in chrome_paths:
                try:
                    result = subprocess.run(['which', path], capture_output=True)
                    if result.returncode == 0:
                        chrome_cmd = path
                        break
                except:
                    continue
            
            if not chrome_cmd:
                # Для Windows
                if os.name == 'nt':
                    chrome_cmd = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
                    if not os.path.exists(chrome_cmd):
                        chrome_cmd = 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'
                
                if not chrome_cmd or not os.path.exists(chrome_cmd):
                    self.is_launching = False
                    return False, "❌ Chrome не найден"
            
            # Запускаем
            cmd = [
                chrome_cmd,
                '--remote-debugging-port=9222',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-gpu',
                '--window-size=1280,720',
                '--new-window', 'about:blank'
            ]
            
            self.chrome_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=os.name == 'nt'
            )
            
            # Ждем запуска
            for i in range(15):
                await asyncio.sleep(1)
                ws_url = self.get_first_tab_ws()
                if ws_url:
                    self.is_launching = False
                    return True, f"✅ Chrome запущен"
            
            self.is_launching = False
            return False, "❌ Не удалось запустить Chrome"
            
        except Exception as e:
            self.is_launching = False
            return False, f"❌ Ошибка: {e}"
    
    async def connect(self):
        """Подключиться к первой вкладке"""
        try:
            ws_url = self.get_first_tab_ws()
            if not ws_url:
                return False, "❌ Нет открытых вкладок"
            
            self.ws = await websockets.connect(ws_url)
            self.ws_url = ws_url
            
            # Включаем домены
            await self.send_command("Page.enable")
            await self.send_command("DOM.enable")
            await self.send_command("Runtime.enable")
            
            # Устанавливаем размер
            await self.send_command("Emulation.setDeviceMetricsOverride", {
                "width": 1280,
                "height": 720,
                "deviceScaleFactor": 1,
                "mobile": False
            })
            
            return True, f"✅ Подключено"
        except Exception as e:
            return False, f"❌ Ошибка: {e}"
    
    async def send_command(self, method, params=None):
        """Отправить CDP команду"""
        self.message_id += 1
        message = {
            "id": self.message_id,
            "method": method,
            "params": params or {}
        }
        await self.ws.send(json.dumps(message))
        response = await self.ws.recv()
        return json.loads(response)
    
    async def take_screenshot(self):
        """Сделать скриншот"""
        await self.send_command("Emulation.setDeviceMetricsOverride", {
            "width": 1280,
            "height": 720,
            "deviceScaleFactor": 1,
            "mobile": False
        })
        
        result = await self.send_command("Page.captureScreenshot", {
            "format": "png",
            "quality": 100,
            "captureBeyondViewport": False,
            "fromSurface": True
        })
        
        img_data = base64.b64decode(result.get('result', {}).get('data', ''))
        return img_data

cdp = CDPClient()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 CDP Client\n\n"
        "Команды:\n"
        "/screenshot - скриншот (автозапуск Chrome)\n"
        "/evaluate <js> - выполнить JS\n"
        "/navigate <url> - перейти\n"
        "/tabs - список вкладок\n"
        "/status - статус подключения"
    )

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🔄 Запускаю Chrome и делаю скриншот...")
        
        # Автоматически запускаем Chrome если нужно
        success, msg = await cdp.ensure_chrome()
        if not success:
            await update.message.reply_text(f"❌ {msg}")
            return
        
        img_data = await cdp.take_screenshot()
        await update.message.reply_photo(
            photo=img_data,
            caption="📸 Скриншот 1280x720"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def evaluate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ /evaluate document.title")
            return
        
        # Автозапуск Chrome
        success, msg = await cdp.ensure_chrome()
        if not success:
            await update.message.reply_text(f"❌ {msg}")
            return
        
        js = ' '.join(context.args)
        result = await cdp.send_command("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        
        value = result.get('result', {}).get('result', {}).get('value', 'undefined')
        await update.message.reply_text(f"✅ {str(value)[:1000]}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ /navigate https://example.com")
            return
        
        # Автозапуск Chrome
        success, msg = await cdp.ensure_chrome()
        if not success:
            await update.message.reply_text(f"❌ {msg}")
            return
        
        url = context.args[0]
        await cdp.send_command("Page.navigate", {"url": url})
        await update.message.reply_text(f"✅ Переход на {url}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def list_tabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Автозапуск Chrome
        success, msg = await cdp.ensure_chrome()
        if not success:
            await update.message.reply_text(f"❌ {msg}")
            return
        
        resp = requests.get("http://localhost:9222/json/list")
        pages = resp.json()
        
        if not pages:
            await update.message.reply_text("📭 Нет вкладок")
            return
        
        msg = "📄 Вкладки:\n\n"
        for i, page in enumerate(pages, 1):
            msg += f"{i}. {page.get('title', 'Без названия')[:30]}\n"
            msg += f"   {page.get('url', '')[:50]}\n\n"
        
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = "📊 Статус:\n"
    status_msg += f"Подключен: {'✅ Да' if cdp.ws else '❌ Нет'}\n"
    
    try:
        ws_url = cdp.get_first_tab_ws()
        status_msg += f"Chrome запущен: {'✅ Да' if ws_url else '❌ Нет'}\n"
        if ws_url:
            resp = requests.get("http://localhost:9222/json/list")
            pages = resp.json()
            status_msg += f"Вкладок: {len(pages)}"
    except:
        status_msg += "Chrome запущен: ❌ Нет"
    
    await update.message.reply_text(status_msg)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("evaluate", evaluate))
    app.add_handler(CommandHandler("navigate", navigate))
    app.add_handler(CommandHandler("tabs", list_tabs))
    app.add_handler(CommandHandler("status", status))
    
    print("🤖 CDP Client Bot запущен")
    print("💡 Chrome запускается автоматически при первом запросе")
    app.run_polling()

if __name__ == "__main__":
    main()