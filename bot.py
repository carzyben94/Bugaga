import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.exceptions import ElementNotFound, WaitElementTimeout
import openai  # или ваш клиент для AGNES AI

# ============= НАСТРОЙКИ =============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    raise ValueError("AGNES_API_KEY не установлен!")

# Настройка клиента AGNES (OpenAI-совместимый)
agnes_client = openai.OpenAI(
    api_key=AGNES_API_KEY,
    base_url="https://apihub.agnes-ai.com/v1"  # URL для AGNES API
)

# ============= SYSTEM PROMPT ДЛЯ AGNES =============
AGNES_SYSTEM_PROMPT = """
Ты - AGNES, AI-агент для управления браузером через библиотеку Pydoll.

Твоя задача - преобразовывать команды пользователя в JSON-массив действий, 
которые можно выполнить через API Pydoll.

ДОСТУПНЫЕ МЕТОДЫ PYDOLL (из документации):
1. go_to(url: str) - переход по URL
2. find(selector: str) - поиск элемента по CSS-селектору
3. click(humanize: bool = False) - клик по элементу
4. type_text(text: str, humanize: bool = False) - ввод текста в элемент
5. text() - получить текст элемента
6. take_screenshot(as_base64: bool = False) - скриншот страницы
7. execute_script(script: str) - выполнить JavaScript
8. scroll_to_bottom() - прокрутить вниз
9. scroll_to_top() - прокрутить вверх
10. go_back() - назад
11. go_forward() - вперед
12. reload() - перезагрузить страницу
13. title - получить заголовок страницы
14. url - получить текущий URL
15. wait_for(selector: str, timeout: int = 10) - ожидать элемент
16. get_html() - получить HTML код страницы
17. get_cookies() - получить cookies

Формат ответа (ТОЛЬКО JSON, без лишнего текста):
{"actions": [
    {"method": "go_to", "args": {"url": "https://..."}},
    {"method": "find", "args": {"selector": "#id"}},
    {"method": "click", "args": {"humanize": true}},
    {"method": "type_text", "args": {"text": "текст", "humanize": true}}
]}

Примеры:
Пользователь: "Открой Google и найди кнопку Войти"
Ответ: {"actions": [
    {"method": "go_to", "args": {"url": "https://www.google.com"}},
    {"method": "find", "args": {"selector": "a[href*='accounts']"}},
    {"method": "click", "args": {"humanize": true}}
]}

Пользователь: "Сделай скриншот страницы"
Ответ: {"actions": [
    {"method": "take_screenshot", "args": {"as_base64": true}}
]}

Пользователь: "Найди заголовок и текст кнопки"
Ответ: {"actions": [
    {"method": "find", "args": {"selector": "h1"}},
    {"method": "text", "args": {}},
    {"method": "find", "args": {"selector": "button"}},
    {"method": "text", "args": {}}
]}

Пользователь: "Прокрути вниз"
Ответ: {"actions": [
    {"method": "scroll_to_bottom", "args": {}}
]}

Пользователь: "Вернись назад"
Ответ: {"actions": [
    {"method": "go_back", "args": {}}
]}

Пользователь: "Обнови страницу"
Ответ: {"actions": [
    {"method": "reload", "args": {}}
]}

Пользователь: "Дождись появления кнопки с id submit"
Ответ: {"actions": [
    {"method": "wait_for", "args": {"selector": "#submit", "timeout": 10}}
]}

Отвечай ТОЛЬКО JSON без лишнего текста!
"""

# ============= КЛАСС AGNES BROWSER AGENT =============
class AgnesBrowserAgent:
    """AI-агент для управления браузером через Pydoll"""
    
    def __init__(self):
        self.browser: Optional[Chrome] = None
        self.tab = None
        self._last_element = None
        self.memory: List[Dict] = []
    
    async def init_browser(self):
        """Инициализация браузера с настройками для Docker/Railway"""
        options = ChromiumOptions()
        options.binary_location = "/usr/bin/google-chrome"
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.start_timeout = 30
        
        self.browser = Chrome(options=options)
        self.tab = await self.browser.start()
        logger.info("✅ Браузер успешно запущен")
        return self.tab
    
    async def parse_command(self, user_input: str) -> Dict:
        """Отправляет команду в AGNES для парсинга"""
        try:
            response = agnes_client.chat.completions.create(
                model="agnes-2.0-flash",
                messages=[
                    {"role": "system", "content": AGNES_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            logger.info(f"AGNES ответила: {content}")
            
            # Парсим JSON
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от AGNES: {e}")
            # Если AGNES выдала не JSON, пробуем извлечь JSON из текста
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError("AGNES вернула некорректный JSON")
    
    async def execute_actions(self, actions_data: Dict) -> List[str]:
        """Выполняет список действий от AGNES"""
        actions = actions_data.get("actions", [])
        results = []
        
        for action in actions:
            method = action.get("method")
            args = action.get("args", {})
            
            result = await self._call_pydoll_method(method, args)
            results.append(result)
            
            # Сохраняем в память
            self.memory.append({
                "method": method,
                "args": args,
                "result": result[:100]  # Обрезаем для памяти
            })
        
        return results
    
    async def _call_pydoll_method(self, method: str, args: Dict[str, Any]) -> str:
        """Вызывает метод Pydoll по имени с аргументами"""
        try:
            if method == "go_to":
                url = args.get("url")
                if not url:
                    return "❌ Не указан URL"
                await self.tab.go_to(url, timeout=30)
                return f"✅ Перешёл на {url}"
            
            elif method == "find":
                selector = args.get("selector")
                if not selector:
                    return "❌ Не указан селектор"
                self._last_element = await self.tab.find(selector)
                return f"✅ Нашёл элемент: {selector}"
            
            elif method == "click":
                element = args.get("element") or self._last_element
                if not element:
                    return "❌ Нет элемента для клика"
                await element.click(humanize=args.get("humanize", True))
                return "✅ Кликнул по элементу"
            
            elif method == "type_text":
                element = args.get("element") or self._last_element
                if not element:
                    return "❌ Нет элемента для ввода"
                text = args.get("text", "")
                if not text:
                    return "❌ Нет текста для ввода"
                await element.type_text(text, humanize=args.get("humanize", True))
                return f"✅ Ввёл текст: {text}"
            
            elif method == "text":
                element = args.get("element") or self._last_element
                if not element:
                    return "❌ Нет элемента для получения текста"
                text = await element.text()
                return f"📝 Текст: {text[:200]}..."
            
            elif method == "take_screenshot":
                screenshot = await self.tab.take_screenshot(
                    as_base64=args.get("as_base64", True)
                )
                # Здесь можно сохранить или вернуть
                return "📸 Скриншот сделан"
            
            elif method == "execute_script":
                script = args.get("script")
                if not script:
                    return "❌ Не указан скрипт"
                result = await self.tab.execute_script(script)
                return f"✅ JS выполнен: {result}"
            
            elif method == "scroll_to_bottom":
                await self.tab.scroll_to_bottom()
                return "⬇️ Прокрутил вниз"
            
            elif method == "scroll_to_top":
                await self.tab.scroll_to_top()
                return "⬆️ Прокрутил вверх"
            
            elif method == "go_back":
                await self.tab.go_back()
                return "⬅️ Назад"
            
            elif method == "go_forward":
                await self.tab.go_forward()
                return "➡️ Вперед"
            
            elif method == "reload":
                await self.tab.reload()
                return "🔄 Обновил страницу"
            
            elif method == "title":
                title = await self.tab.title
                return f"📌 Заголовок: {title}"
            
            elif method == "url":
                url = await self.tab.url
                return f"🔗 URL: {url}"
            
            elif method == "wait_for":
                selector = args.get("selector")
                timeout = args.get("timeout", 10)
                if not selector:
                    return "❌ Не указан селектор"
                await self.tab.wait_for(selector, timeout=timeout)
                return f"⏳ Дождался элемента: {selector}"
            
            elif method == "get_html":
                html = await self.tab.get_html()
                return f"📄 HTML получен ({len(html)} символов)"
            
            elif method == "get_cookies":
                cookies = await self.tab.get_cookies()
                return f"🍪 Cookies: {cookies}"
            
            else:
                return f"❌ Неизвестный метод: {method}"
                
        except ElementNotFound as e:
            return f"❌ Элемент не найден: {str(e)}"
        except WaitElementTimeout as e:
            return f"❌ Таймаут ожидания элемента: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка в методе {method}: {e}")
            return f"❌ Ошибка: {str(e)}"
    
    async def close(self):
        """Закрывает браузер"""
        if self.browser:
            await self.browser.close()
            logger.info("Браузер закрыт")

# ============= КЛАСС ДЛЯ КОНТЕКСТА TELEGRAM =============
class ContextData:
    def __init__(self):
        self.agent: Optional[AgnesBrowserAgent] = None

# ============= ОБРАБОТЧИКИ TELEGRAM =============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    # Создаём агента и сохраняем в контекст
    if not hasattr(context.chat_data, 'agent'):
        context.chat_data['agent'] = AgnesBrowserAgent()
    
    await update.message.reply_text(
        "🧠 **AGNES AI Browser Agent** активирована!\n\n"
        "Я управляю браузером через Pydoll.\n"
        "Просто напиши, что нужно сделать:\n\n"
        "📌 _Примеры:_\n"
        "• Открой Google\n"
        "• Найди кнопку 'Войти' и нажми\n"
        "• Сделай скриншот страницы\n"
        "• Прокрути вниз\n"
        "• Найди заголовок страницы",
        parse_mode='Markdown'
    )
    
    # Инициализируем браузер
    agent = context.chat_data['agent']
    await agent.init_browser()
    await update.message.reply_text("✅ Браузер готов к работе!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_input = update.message.text
    logger.info(f"Получена команда: {user_input}")
    
    # Проверяем наличие агента
    if 'agent' not in context.chat_data:
        await update.message.reply_text(
            "⚠️ Сначала запусти бота командой /start"
        )
        return
    
    await update.message.reply_text("⏳ AGNES анализирует команду...")
    
    agent = context.chat_data['agent']
    
    try:
        # 1. AGNES парсит команду
        actions_data = await agent.parse_command(user_input)
        
        # 2. Выполняем действия
        results = await agent.execute_actions(actions_data)
        
        # 3. Отправляем результаты
        for result in results:
            await update.message.reply_text(result)
        
        # 4. Если был скриншот, отправляем его
        # (здесь нужно обработать скриншот отдельно)
        
    except json.JSONDecodeError as e:
        await update.message.reply_text(
            f"❌ Ошибка парсинга команды AGNES: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Ошибка выполнения команды: {e}")
        await update.message.reply_text(
            f"❌ Произошла ошибка: {str(e)}"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
🤖 **Доступные команды:**

/start - Запустить агента и браузер
/help - Показать эту справку
/status - Статус агента и браузера
/clear - Очистить память агента
/stop - Остановить браузер

💬 **Примеры команд на естественном языке:**
- "Открой Google"
- "Найди кнопку Войти и нажми"
- "Сделай скриншот"
- "Найди заголовок страницы"
- "Прокрути вниз"
- "Вернись назад"
- "Обнови страницу"
- "Найди текст в элементе #content"

🧠 **AGNES AI** преобразует твою команду в действия браузера!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус агента"""
    if 'agent' not in context.chat_data:
        await update.message.reply_text("❌ Агент не инициализирован. Используй /start")
        return
    
    agent = context.chat_data['agent']
    status = f"""
📊 **Статус AGNES Browser Agent**

Браузер: {'✅ Активен' if agent.browser else '❌ Не активен'}
Вкладка: {'✅ Открыта' if agent.tab else '❌ Закрыта'}
Память: {len(agent.memory)} действий
Последнее действие: {agent.memory[-1]['result'] if agent.memory else 'Нет'}
"""
    await update.message.reply_text(status, parse_mode='Markdown')

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает память агента"""
    if 'agent' in context.chat_data:
        context.chat_data['agent'].memory = []
        await update.message.reply_text("🧹 Память агента очищена!")
    else:
        await update.message.reply_text("❌ Агент не инициализирован")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Останавливает браузер"""
    if 'agent' in context.chat_data:
        await context.chat_data['agent'].close()
        del context.chat_data['agent']
        await update.message.reply_text("🛑 Браузер остановлен. Агент отключен.")
    else:
        await update.message.reply_text("❌ Агент не инициализирован")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ Произошла внутренняя ошибка. Попробуйте позже."
        )

# ============= ЗАПУСК БОТА =============
def main():
    """Главная функция запуска бота"""
    try:
        # Создаём приложение
        application = Application.builder().token(TOKEN).build()
        
        # Регистрируем команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("clear", clear_command))
        application.add_handler(CommandHandler("stop", stop_command))
        
        # Регистрируем обработчик сообщений
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            handle_message
        ))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)
        
        logger.info("🚀 Бот AGNES Browser Agent запущен!")
        logger.info("ℹ️ Ожидаю команды...")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()