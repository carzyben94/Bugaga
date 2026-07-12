import asyncio
import json
import logging
import os
import time
import re
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
from pydoll import Page, Browser
from pydoll.types import BrowserOptions
import requests

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")

# ---------- КУКИ ДЛЯ X.COM ----------
X_COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com"},
    {"name": "lang", "value": "ru", "domain": ".x.com"},
    {"name": "dnt", "value": "1", "domain": ".x.com"},
    {"name": "__cf_bm", "value": "Eb4nVvazwJ5mDp0c.6Ye5ub0rukgdQkcFzPf8.wdbIQ-1783798267.7075489-1.0.1.1-59IptPdWY9w0zyKvebR59I.8iB4M1DWfNNZQW0.c.E4lDCU3wTfEcds69RVBkOeQ9LUDZNLGRv6z8InGbCsH1RaTCKaqehL94yq0FgvU7QB9cbE8BO4.2Y8BMRnN_Nks", "domain": ".x.com"}
]

# ---------- ЛОГИРОВАНИЕ ----------
LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

file_logger = FileLogger()

# ---------- БРАУЗЕР (Accessibility Tree + Pydoll) ----------
class BrowserAgent:
    def __init__(self):
        self.browser = None
        self.page = None
        self.snapshot = None
        self.masked = False
        self.last_url = ""
    
    async def start(self):
        """Запуск браузера с маскировкой от Pydoll"""
        try:
            file_logger.log("🚀 Запуск браузера с маскировкой Pydoll...")
            
            options = BrowserOptions(
                headless=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                disable_blink_features=["AutomationControlled"],
                disable_features=["IsolateOrigins", "site-per-process"],
                disable_web_security=True,
                disable_default_apps=True,
                disable_sync=True,
                disable_notifications=True,
                window_size=(1920, 1080)
            )
            
            self.browser = await Browser.launch(options)
            self.page = await self.browser.new_page()
            
            # ПРИМЕНЯЕМ ВСТРОЕННУЮ МАСКИРОВКУ Pydoll
            await self.page.apply_mask()
            self.masked = True
            file_logger.log("✅ Маскировка Pydoll применена")
            
            # Устанавливаем куки
            for cookie in X_COOKIES:
                await self.page.add_cookie(cookie)
            file_logger.log(f"🍪 Установлено {len(X_COOKIES)} кук")
            
            # Открываем Google
            await self.navigate("https://google.com")
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка запуска: {e}", "ERROR")
            return False
    
    async def navigate(self, url):
        """Перейти на сайт"""
        file_logger.log(f"🌐 Навигация на {url}")
        self.last_url = url
        await self.page.goto(url)
        await asyncio.sleep(2)
        
        # Обновляем слепок
        await self.get_accessibility_tree()
        return {"success": True}
    
    async def get_accessibility_tree(self):
        """Получить дерево доступности (Accessibility Tree)"""
        try:
            file_logger.log("📸 Делаю Accessibility Tree...")
            
            # Встроенный метод Pydoll
            snapshot = await self.page.accessibility_snapshot()
            
            # Форматируем для AI
            tree = self._flatten_tree(snapshot)
            
            # Добавляем ID для каждого элемента
            for i, el in enumerate(tree):
                el["id"] = f"@e{i+1}"
            
            # Сохраняем
            self.snapshot = {
                "title": await self.page.title(),
                "url": await self.page.current_url(),
                "total": len(tree),
                "elements": tree
            }
            
            file_logger.log(f"✅ Accessibility Tree: {len(tree)} элементов")
            return self.snapshot
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка: {e}", "ERROR")
            return None
    
    def _flatten_tree(self, node, level=0, result=None):
        """Разворачивает дерево доступности в плоский список"""
        if result is None:
            result = []
        
        if node:
            item = {
                "role": node.get("role", "unknown"),
                "name": node.get("name", ""),
                "value": node.get("value", ""),
                "description": node.get("description", ""),
                "level": level
            }
            result.append(item)
        
        # Рекурсивно обрабатываем детей
        for child in node.get("children", []):
            self._flatten_tree(child, level + 1, result)
        
        return result
    
    async def get_page_description(self):
        """Получить описание страницы для AI"""
        if not self.snapshot:
            await self.get_accessibility_tree()
        
        if not self.snapshot:
            return "❌ Не удалось получить дерево доступности"
        
        desc = f"""
📄 СТРАНИЦА: {self.snapshot.get('title', 'Нет заголовка')}
🔗 URL: {self.snapshot.get('url', 'Нет URL')}
📊 ЭЛЕМЕНТОВ: {self.snapshot.get('total', 0)}
🕵️ МАСКИРОВКА: {'✅ Активна' if self.masked else '❌ Нет'}

🔍 ЭЛЕМЕНТЫ:
"""
        
        for el in self.snapshot.get('elements', [])[:30]:  # Ограничиваем для AI
            ident = el.get('id', '')
            role = el.get('role', '')
            name = el.get('name', '')[:30]
            value = el.get('value', '')
            
            desc += f"  {ident}: {role}"
            if name:
                desc += f" \"{name}\""
            if value:
                desc += f" = {value}"
            desc += "\n"
        
        return desc
    
    async def find_element_by_id(self, element_id):
        """Найти элемент по ID из Accessibility Tree"""
        if not self.snapshot:
            return None
        
        for el in self.snapshot.get('elements', []):
            if el.get('id') == element_id:
                return el
        return None
    
    async def click_by_id(self, element_id):
        """Клик по элементу по ID из Accessibility Tree"""
        el = await self.find_element_by_id(element_id)
        if not el:
            return {"success": False, "error": f"Элемент {element_id} не найден"}
        
        # Ищем по роли и имени
        selector = f"[aria-label='{el.get('name')}']" if el.get('name') else None
        
        if selector:
            file_logger.log(f"🖱️ Клик: {element_id} -> {selector}")
            await self.page.click(selector)
            return {"success": True}
        
        return {"success": False, "error": "Не удалось найти селектор"}
    
    async def fill_by_id(self, element_id, text):
        """Заполнить поле по ID"""
        el = await self.find_element_by_id(element_id)
        if not el:
            return {"success": False, "error": f"Элемент {element_id} не найден"}
        
        selector = f"[aria-label='{el.get('name')}']" if el.get('name') else None
        
        if selector:
            file_logger.log(f"📝 Заполняю: {element_id} -> {text}")
            await self.page.fill(selector, text)
            return {"success": True}
        
        return {"success": False, "error": "Не удалось найти селектор"}
    
    async def search(self, text):
        """Умный поиск — клик в поле → ввод → клик по кнопке"""
        file_logger.log(f"🔍 Поиск: {text}")
        
        if not self.snapshot:
            await self.get_accessibility_tree()
        
        # 1. Находим поле поиска
        field = None
        for el in self.snapshot.get('elements', []):
            role = el.get('role', '').lower()
            name = el.get('name', '').lower()
            if role == 'textbox' and ('поиск' in name or 'search' in name):
                field = el
                break
        
        if not field:
            return {"success": False, "error": "Поле поиска не найдено"}
        
        # 2. Кликаем в поле
        await self.click_by_id(field['id'])
        await asyncio.sleep(0.5)
        
        # 3. Вводим текст
        await self.fill_by_id(field['id'], text)
        await asyncio.sleep(0.5)
        
        # 4. Находим кнопку поиска
        btn = None
        for el in self.snapshot.get('elements', []):
            role = el.get('role', '').lower()
            name = el.get('name', '').lower()
            if role == 'button' and ('поиск' in name or 'search' in name):
                btn = el
                break
        
        if btn:
            await self.click_by_id(btn['id'])
            return {"success": True, "method": "click_button"}
        
        return {"success": False, "error": "Кнопка поиска не найдена"}
    
    async def screenshot(self):
        """Сделать скриншот"""
        try:
            file_logger.log("📸 Делаю скриншот...")
            
            # Встроенный метод Pydoll
            screenshot_data = await self.page.screenshot()
            
            file_logger.log(f"✅ Скриншот сделан ({len(screenshot_data)} байт)")
            return screenshot_data
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка скриншота: {e}", "ERROR")
            return None
    
    async def click(self, selector):
        """Клик по селектору"""
        try:
            await self.page.click(selector)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def fill(self, selector, text):
        """Заполнить поле"""
        try:
            await self.page.fill(selector, text)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

# ---------- AI ----------
AGENT_CODE = """
🤖 ТЫ — АГЕНТ ДЛЯ УПРАВЛЕНИЯ БРАУЗЕРОМ

📌 ДОСТУПНЫЕ ДЕЙСТВИЯ:
1. navigate(url) - открыть сайт
2. click(selector) - кликнуть по селектору
3. fill(selector, value) - заполнить поле
4. search(text) - ПОИСК (самый надежный!)
5. screenshot() - скриншот
6. answer(text) - ответить

📝 СТРАНИЦА ПРЕДСТАВЛЕНА В ВИДЕ ACCESSIBILITY TREE:
- Каждый элемент имеет ID: @e1, @e2, @e3...
- Используй эти ID для кликов и заполнения
- Пример: {"action": "click", "params": {"selector": "@e7"}}

⚠️ ДЛЯ ПОИСКА ВСЕГДА ИСПОЛЬЗУЙ search:
{"action": "search", "params": {"text": "вова"}}

⚠️ ФОРМАТ ОТВЕТА:
- Одно действие: {"action": "...", "params": {...}}
- Несколько действий: [{"action": "...", "params": {...}}, ...]
"""

async def ask_agnes(prompt: str, agent: BrowserAgent) -> dict:
    """Запрос к AI"""
    if not AGNES_API_KEY:
        return {"action": "answer", "params": {"text": "AGNES_API_KEY не установлен"}}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    page_desc = await agent.get_page_description()
    
    system_prompt = f"""
{AGENT_CODE}

📄 СТРАНИЦА:
{page_desc}

📝 ОТВЕЧАЙ ТОЛЬКО JSON!

⚠️ ВАЖНО:
- Для поиска используй search
- Для кликов используй ID из Accessibility Tree (@e1, @e2...)
- Пользователь: {prompt}
"""

    data = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1500
    }
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        
        file_logger.log(f"Agnes ответ: {content[:200]}...")
        
        json_match = re.search(r'\[.*\]|\{.*\}', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            return parsed
        
        return {"action": "answer", "params": {"text": content}}
        
    except Exception as e:
        file_logger.log(f"Agnes error: {e}", "ERROR")
        return {"action": "answer", "params": {"text": f"❌ Ошибка: {str(e)}"}}

# ---------- ВЫПОЛНЕНИЕ ----------
async def execute_action(agent: BrowserAgent, action) -> str:
    if isinstance(action, list):
        results = []
        for a in action:
            result = await execute_single_action(agent, a)
            results.append(result)
        return "\n".join(results)
    return await execute_single_action(agent, action)

async def execute_single_action(agent: BrowserAgent, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение: {action_type}")
    
    try:
        if action_type == "navigate":
            url = params.get("url", "https://google.com")
            await agent.navigate(url)
            title = await agent.page.title()
            return f"✅ Открыл: {url}\n📄 {title}"
        
        elif action_type == "screenshot":
            img_data = await agent.screenshot()
            if img_data:
                with open("screenshot.png", "wb") as f:
                    f.write(img_data)
                return "screenshot"
            return "❌ Не удалось сделать скриншот"
        
        elif action_type == "click":
            selector = params.get("selector")
            if not selector:
                return "❌ Нет селектора"
            
            # Если selector начинается с @ — это ID из Accessibility Tree
            if selector.startswith("@"):
                result = await agent.click_by_id(selector)
                if result.get("success"):
                    return f"✅ Кликнул: {selector}"
                return f"❌ Элемент не найден: {selector}"
            else:
                result = await agent.click(selector)
                if result.get("success"):
                    return f"✅ Кликнул: {selector}"
                return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            
            if selector.startswith("@"):
                result = await agent.fill_by_id(selector, value)
                if result.get("success"):
                    return f"✅ Заполнил: {selector} = {value}"
                return f"❌ Элемент не найден: {selector}"
            else:
                result = await agent.fill(selector, value)
                if result.get("success"):
                    return f"✅ Заполнил: {selector} = {value}"
                return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "search":
            text = params.get("text", "")
            result = await agent.search(text)
            if result.get("success"):
                method = result.get("method", "")
                return f"✅ Поиск выполнен ({method}): {text}"
            return f"❌ Не удалось выполнить поиск: {result.get('error', '')}"
        
        elif action_type == "answer":
            text = params.get('text', 'Нет ответа')
            return f"📝 {text}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        file_logger.log(f"Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ---------- TELEGRAM ----------
clients = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    file_logger.log(f"Сообщение от {user_id}: {prompt[:100]}...")
    
    try:
        if user_id not in clients:
            agent = BrowserAgent()
            await agent.start()
            clients[user_id] = agent
        
        agent = clients[user_id]
        
        response = await ask_agnes(prompt, agent)
        result = await execute_action(agent, response)
        
        if result == "screenshot":
            if os.path.exists("screenshot.png") and os.path.getsize("screenshot.png") > 0:
                with open("screenshot.png", "rb") as photo:
                    await update.message.reply_photo(photo=photo)
            else:
                await update.message.reply_text("❌ Не удалось отправить скриншот")
        else:
            await update.message.reply_text(result)
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Бот с Accessibility Tree + Pydoll**\n\n"
        "🕵️ **Маскировка Pydoll активна!**\n"
        "📊 **Accessibility Tree вместо DOM**\n\n"
        "💡 **Примеры команд:**\n"
        "• Зайди на x.com\n"
        "• Найди вова\n"
        "• Сделай скриншот\n"
        "• Что видишь?"
    )

def main():
    print("🚀 Запуск бота с Accessibility Tree + Pydoll...")
    file_logger.log("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    file_logger.log("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()