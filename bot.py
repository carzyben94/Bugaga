import os
import json
import logging
import asyncio
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
        
    async def connect(self, ws_url):
        """Подключение к Chrome DevTools"""
        self.ws = await websockets.connect(ws_url)
        return self.ws
        
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
    
    async def get_targets(self):
        """Получить список вкладок"""
        # Подключаемся к /json/list
        async with websockets.connect('ws://localhost:9222/json/list') as ws:
            response = await ws.recv()
            return json.loads(response)
    
    async def close(self):
        if self.ws:
            await self.ws.close()

cdp = CDPClient()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 CDP Client\n\n"
        "Команды:\n"
        "/connect <ws_url> - подключиться к Chrome\n"
        "/targets - список вкладок\n"
        "/attach <target_id> - прикрепиться к вкладке\n"
        "/evaluate <js> - выполнить JS\n"
        "/screenshot - скриншот\n"
        "/navigate <url> - перейти по URL\n"
        "/dom - получить DOM"
    )

async def connect_chrome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подключиться к Chrome через WebSocket"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите WebSocket URL\n"
                "Пример: /connect ws://localhost:9222/devtools/browser/xxx"
            )
            return
        
        ws_url = context.args[0]
        await cdp.connect(ws_url)
        await update.message.reply_text(f"✅ Подключено к CDP\n{ws_url}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def list_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех вкладок"""
    try:
        targets = await cdp.get_targets()
        
        if not targets:
            await update.message.reply_text("📭 Нет вкладок")
            return
        
        msg = "📄 Вкладки:\n\n"
        for i, target in enumerate(targets, 1):
            msg += f"{i}. {target.get('title', 'Без названия')[:30]}\n"
            msg += f"   ID: {target.get('id', '')[:16]}...\n"
            msg += f"   URL: {target.get('url', '')[:50]}\n\n"
        
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def attach_to_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Прикрепиться к вкладке"""
    try:
        if not context.args:
            await update.message.reply_text("❌ /attach <target_id>")
            return
        
        target_id = context.args[0]
        ws_url = f"ws://localhost:9222/devtools/page/{target_id}"
        
        await cdp.connect(ws_url)
        
        # Включение нужных доменов
        await cdp.send_command("Page.enable")
        await cdp.send_command("DOM.enable")
        await cdp.send_command("Runtime.enable")
        
        await update.message.reply_text(f"✅ Прикреплен к вкладке {target_id[:16]}...")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить JavaScript через CDP"""
    try:
        if not context.args:
            await update.message.reply_text("❌ /evaluate document.title")
            return
        
        if not cdp.ws:
            await update.message.reply_text("❌ Не подключен. Используйте /connect")
            return
        
        js_code = ' '.join(context.args)
        result = await cdp.send_command("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": True
        })
        
        value = result.get('result', {}).get('result', {}).get('value', 'undefined')
        await update.message.reply_text(f"✅ Результат:\n{str(value)[:1000]}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def take_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сделать скриншот через CDP"""
    try:
        if not cdp.ws:
            await update.message.reply_text("❌ Не подключен")
            return
        
        result = await cdp.send_command("Page.captureScreenshot", {
            "format": "png",
            "quality": 100
        })
        
        import base64
        img_data = base64.b64decode(result.get('result', {}).get('data', ''))
        
        await update.message.reply_photo(photo=img_data)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def navigate_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перейти по URL"""
    try:
        if not context.args:
            await update.message.reply_text("❌ /navigate https://example.com")
            return
        
        if not cdp.ws:
            await update.message.reply_text("❌ Не подключен")
            return
        
        url = context.args[0]
        result = await cdp.send_command("Page.navigate", {"url": url})
        
        frame_id = result.get('result', {}).get('frameId', '')
        await update.message.reply_text(f"✅ Переход на {url}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def get_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить DOM дерево"""
    try:
        if not cdp.ws:
            await update.message.reply_text("❌ Не подключен")
            return
        
        result = await cdp.send_command("DOM.getDocument", {"depth": 2})
        
        import json
        dom = json.dumps(result, indent=2)[:3000]
        await update.message.reply_text(f"📄 DOM:\n{dom}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect_chrome))
    app.add_handler(CommandHandler("targets", list_targets))
    app.add_handler(CommandHandler("attach", attach_to_target))
    app.add_handler(CommandHandler("evaluate", evaluate_js))
    app.add_handler(CommandHandler("screenshot", take_screenshot))
    app.add_handler(CommandHandler("navigate", navigate_to))
    app.add_handler(CommandHandler("dom", get_dom))
    
    print("🤖 CDP Client Bot запущен")
    app.run_polling()

if __name__ == "__main__":
    main()