# bot.py - правильный способ для удалённого браузера
import os
import sys
import asyncio
import logging
import time

# ============================================================
# 1. НАСТРОЙКА
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# 2. BROWSER HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    close_tab,
    page_info,
    capture_screenshot,
    js,
    fill_input,
    click_at_xy,
    scroll,
)

# ВАЖНО: импортируем start_remote_daemon
from browser_harness.admin import start_remote_daemon, stop_remote_daemon

# ============================================================
# 3. ИМПОРТЫ
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"🍪 Загружено {len(COOKIES)} кук")
except ImportError:
    COOKIES = []

from telegram import Update
from telegram.ext import Application, CommandHandler
from telegram.helpers import escape_markdown

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Ваш CDP URL
CDP_URL = "https://9d683906-74b6-44a1-a138-c33b957fb907.cdp.browser-use.com"

# ============================================================
# 4. DSPy (упрощённо)
# ============================================================

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

def init_dspy():
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        return None
    
    class SimpleLM(dspy.LM):
        def __init__(self):
            super().__init__(model="agnes")
            self.api_key = api_key
        
        def forward(self, prompt=None, messages=None, **kwargs):
            import httpx
            try:
                with httpx.Client(timeout=60) as client:
                    resp = client.post(
                        "https://apihub.agnes-ai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": "agnes-2.0-flash",
                            "messages": messages or [{"role": "user", "content": prompt}],
                            "temperature": 0.3,
                            "max_tokens": 2000
                        }
                    )
                    data = resp.json()
                    return [data["choices"][0]["message"]["content"]]
            except Exception as e:
                return [f"Ошибка: {e}"]
    
    lm = SimpleLM()
    settings.configure(lm=lm)
    
    # Инструменты
    def tool_goto(url: str) -> str:
        try:
            goto_url(url)
            wait_for_load()
            return f"✅ Перешел на {url}"
        except Exception as e:
            return f"❌ {e}"
    
    def tool_screenshot(name: str = None) -> str:
        try:
            if not name:
                name = f"screenshot_{int(time.time())}.png"
            path = f"/app/screenshots/{name}"
            capture_screenshot(path=path)
            return f"✅ Скриншот: {name}"
        except Exception as e:
            return f"❌ {e}"
    
    def tool_text() -> str:
        try:
            text = js('document.body.innerText')
            return str(text)[:3000]
        except Exception as e:
            return f"❌ {e}"
    
    def tool_click(selector: str) -> str:
        try:
            result = js(f"""
                (() => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return {{x: r.left + r.width/2, y: r.top + r.height/2}};
                }})()
            """)
            if result:
                click_at_xy(int(result["x"]), int(result["y"]))
                return f"✅ Клик на {selector}"
            return f"❌ Элемент {selector} не найден"
        except Exception as e:
            return f"❌ {e}"
    
    tools = [
        Tool(tool_goto),
        Tool(tool_screenshot),
        Tool(tool_text),
        Tool(tool_click),
    ]
    
    return ReActV2(signature=BrowserTask, tools=tools, max_iters=5)


# ============================================================
# 5. ОСНОВНОЙ КЛАСС
# ============================================================

class HarnessBot:
    def __init__(self):
        self.page = None
        self.agent = None
        self.session_name = "my_browser_session"
    
    async def start(self):
        """Запуск - подключаемся к удалённому браузеру"""
        logger.info("🚀 Подключение к удалённому браузеру...")
        
        # 1. Запускаем удалённый демон с CDP URL
        # start_remote_daemon() принимает CDP URL и имя сессии
        start_remote_daemon(self.session_name, cdp_url=CDP_URL)
        logger.info(f"✅ Подключен к CDP: {CDP_URL}")
        
        # Даём время на подключение
        await asyncio.sleep(2)
        
        # 2. Создаём вкладку
        logger.info("🌐 Создаю вкладку...")
        self.page = new_tab("https://example.com")
        wait_for_load()
        logger.info(f"✅ Вкладка создана: {self.page}")
        
        # 3. Устанавливаем куки
        if COOKIES:
            for cookie in COOKIES:
                try:
                    js(f"document.cookie = '{cookie['name']}={cookie['value']}; domain={cookie.get('domain', '')}; path=/'")
                except:
                    pass
            logger.info(f"🍪 Установлено {len(COOKIES)} кук")
        
        # 4. Инициализируем DSPy
        self.agent = init_dspy()
        if self.agent:
            logger.info("🧠 DSPy готов")
        else:
            logger.warning("⚠️ DSPy не инициализирован")
        
        self.is_ready = True
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def ask(self, question: str) -> str:
        """Задать вопрос агенту"""
        if not self.agent:
            return "❌ DSPy не инициализирован"
        try:
            result = self.agent(question=question)
            return getattr(result, 'answer', str(result))
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def close(self):
        """Закрыть"""
        if self.page:
            try:
                close_tab(self.page)
            except:
                pass
        
        # Останавливаем удалённый демон
        try:
            stop_remote_daemon(self.session_name)
            logger.info("✅ Удалённый демон остановлен")
        except:
            pass
        
        logger.info("✅ Закрыто")


# ============================================================
# 6. TELEGRAM
# ============================================================

bot = None

async def dspy_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Примеры:\n"
            "`/dspy открыть google.com`\n"
            "`/dspy сделать скриншот`\n"
            "`/dspy получить текст страницы`",
            parse_mode='Markdown'
        )
        return
    
    query = " ".join(context.args)
    msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        answer = await bot.ask(query)
        if len(answer) > 4000:
            answer = answer[:4000] + "..."
        await msg.edit_text(
            f"✅ **Результат:**\n\n{escape_markdown(answer, version=2)}",
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


# ============================================================
# 7. ЗАПУСК
# ============================================================

async def main():
    global bot
    
    bot = HarnessBot()
    await bot.start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    logger.info("🚀 Бот запущен! Используй /dspy")
    
    try:
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
    except KeyboardInterrupt:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())