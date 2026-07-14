import os
import requests
import json
import re
from typing import Dict, Any, List

class AgnesAI:
    """Базовый класс для работы с Agnes AI API"""
    
    def __init__(self):
        self.api_key = os.getenv("AGNES_API_KEY")
        self.api_url = os.getenv("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
        self.model = os.getenv("AI_MODEL", "agnes-2.0-flash")
    
    def ask(self, question: str, context_text: str = ""):
        if not self.api_key:
            return "❌ AGNES_API_KEY не настроен"
        
        if not context_text or context_text.strip() == "":
            context_text = "Страница не загружена или не содержит текста"
        
        system_prompt = """Ты помощник для анализа веб-страниц.
Отвечай на вопросы пользователя на основе содержимого страницы.
Если информации нет - честно скажи об этом.
Будь точным, полезным и лаконичным.
Используй русский язык для ответов."""

        user_content = f"Содержимое страницы:\n{context_text}\n\nВопрос пользователя: {question}"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                return f"❌ Ошибка API ({response.status_code}): {response.text[:200]}"
                
        except requests.exceptions.Timeout:
            return "❌ Таймаут запроса к AI (60 секунд)"
        except requests.exceptions.ConnectionError:
            return "❌ Ошибка подключения к AI"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"


class AgentPrompts:
    """Все промты для ИИ-агента"""
    
    @staticmethod
    def get_empty_page_prompt(command: str) -> str:
        """Промт для пустой страницы"""
        return f"""
Ты ИИ-агент, управляешь браузером. СТРАНИЦА ПУСТАЯ (about:blank).

Пользователь хочет: {command}

Твои ВОЗМОЖНЫЕ ДЕЙСТВИЯ:
1. open — открыть URL
2. analyze — просто ответить
3. none — ответить без действий

⚠️ ВАЖНО: Если пользователь пишет "открой", "перейди", "зайди" + URL/сайт → ИСПОЛЬЗУЙ action: open

Примеры:
- "открой google.com" → {{"action": "open", "url": "https://google.com", "message": "🌐 Открываю Google"}}
- "привет" → {{"action": "none", "message": "Привет! Я бот для управления браузером. Напиши что хочешь открыть."}}
- "что ты умеешь?" → {{"action": "analyze", "message": "Я умею открывать страницы, делать скриншоты, кликать по кнопкам, искать элементы, вводить текст. Просто скажи что сделать!"}}

ОТВЕТЬ В ФОРМАТЕ JSON:
{{"action": "open | analyze | none", "url": "URL для открытия", "message": "ответ пользователю"}}
"""

    @staticmethod
    def get_full_page_prompt(
        command: str,
        title: str,
        url: str,
        total_elements: int,
        forms: int,
        links: int,
        interactive_str: str,
        dom_preview: str
    ) -> str:
        """Промт для загруженной страницы"""
        return f"""
Ты ИИ-агент, управляешь браузером.

📄 ТЕКУЩАЯ СТРАНИЦА:
Заголовок: {title}
URL: {url}
Всего элементов: {total_elements}
Форм: {forms}
Ссылок: {links}

🖱 ДОСТУПНЫЕ ЭЛЕМЕНТЫ:
{interactive_str}

📄 ФРАГМЕНТ DOM:
{dom_preview}

КОМАНДА ПОЛЬЗОВАТЕЛЯ: {command}

Твои ВОЗМОЖНЫЕ ДЕЙСТВИЯ:
1. click — кликнуть по элементу (нужен selector)
2. type — ввести текст (нужны selector + text)
3. open — открыть URL
4. find — найти элементы по тексту
5. wait — ожидать элемент
6. screenshot — сделать скриншот
7. analyze — проанализировать страницу
8. none — просто ответить

⚠️ ПРАВИЛА:
- Для click/type ВСЕГДА указывай selector из доступных элементов
- Если пользователь просит "нажми", "кликни" → используй action: click
- Если пользователь просит "введи", "напиши" → используй action: type
- Если пользователь спрашивает "что видишь", "какие кнопки" → используй action: analyze
- Если пользователь просит "открой" → используй action: open

ОТВЕТЬ В ФОРМАТЕ JSON:
{{
    "action": "click | type | open | find | wait | screenshot | analyze | none",
    "selector": "CSS селектор (для click/type/wait/find)",
    "text": "текст для ввода (для type)",
    "url": "URL (для open)",
    "message": "понятный ответ пользователю"
}}

ПРИМЕРЫ:
1. "нажми на кнопку войти" → {{"action": "click", "selector": "#login-btn", "message": "✅ Кликнул по кнопке 'Войти'"}}
2. "введи test@gmail.com" → {{"action": "type", "selector": "input[type='email']", "text": "test@gmail.com", "message": "✅ Ввёл email"}}
3. "какие кнопки есть?" → {{"action": "analyze", "message": "На странице есть кнопки: 'Войти', 'Зарегистрироваться'"}}
4. "открой youtube.com" → {{"action": "open", "url": "https://youtube.com", "message": "🌐 Открываю YouTube"}}
5. "сделай скриншот" → {{"action": "screenshot", "message": "📸 Скриншот готов"}}
"""


class AgentHandler:
    """Обработчик команд ИИ-агента"""
    
    def __init__(self, browser):
        self.browser = browser
        self.ai = AgnesAI()
    
    async def execute(self, command: str) -> str:
        """
        Выполнить команду через ИИ-агент
        Возвращает результат выполнения
        """
        # Проверяем страницу
        page_empty = await self.browser.is_page_empty()
        
        # Собираем данные о странице
        dom_data = {}
        dom_preview = ""
        interactive_str = "Нет данных"
        
        if not page_empty:
            dom_data = await self.browser.get_dom_with_metadata()
            full_dom = await self.browser.get_full_dom()
            dom_preview = full_dom[:3000] + "..." if len(full_dom) > 3000 else full_dom
            interactive_str = self._format_interactive(dom_data.get('interactive', []))
        
        # Формируем промт
        if page_empty:
            prompt = AgentPrompts.get_empty_page_prompt(command)
        else:
            prompt = AgentPrompts.get_full_page_prompt(
                command=command,
                title=dom_data.get('title', 'Нет'),
                url=dom_data.get('url', 'Нет'),
                total_elements=dom_data.get('total_elements', 0),
                forms=dom_data.get('forms', 0),
                links=dom_data.get('links', 0),
                interactive_str=interactive_str,
                dom_preview=dom_preview
            )
        
        # Получаем ответ от ИИ
        response = self.ai.ask(prompt, "")
        
        # Парсим JSON
        try:
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                return f"❌ ИИ не смог распарсить команду: {response[:200]}"
        except Exception as e:
            return f"❌ Ошибка парсинга JSON: {e}\nОтвет ИИ: {response[:200]}"
        
        # Выполняем действие
        return await self._execute_action(data)
    
    async def _execute_action(self, data: Dict[str, Any]) -> str:
        """Выполнить действие из JSON"""
        action = data.get('action', 'none')
        selector = data.get('selector', '')
        text = data.get('text', '')
        url = data.get('url', '')
        message = data.get('message', '')
        
        try:
            if action == 'open':
                if not url:
                    return "❌ Не указан URL для открытия"
                await self.browser.open_page(url)
                title = await self.browser.get_page_title()
                return f"{message}\n✅ Открыто: {title}"
            
            elif action == 'screenshot':
                screenshot_base64 = await self.browser.screenshot()
                return f"{message}\n📸 screenshot_data:{screenshot_base64}"
            
            elif action == 'click':
                if not selector:
                    return "❌ Не найден селектор для клика"
                result = await self.browser.click_element(selector)
                return f"{message}\n{result}"
            
            elif action == 'type':
                if not selector:
                    return "❌ Не найден селектор для ввода"
                js = f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.value = '{text}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})()
                """
                result = await self.browser.execute_script(js)
                if result:
                    return f"{message}\n✅ Текст введён в поле: {selector}"
                else:
                    return f"❌ Не удалось ввести текст в поле: {selector}"
            
            elif action == 'find':
                results = await self.browser.find_elements_by_text(text or selector)
                if results:
                    return f"{message}\n🔍 Найдено {len(results)} элементов"
                else:
                    return f"❌ Элементы не найдены: {message}"
            
            elif action == 'wait':
                if not selector:
                    return "❌ Не указан селектор для ожидания"
                result = await self.browser.wait_for_selector(selector)
                return f"{message}\n{result}"
            
            elif action == 'analyze':
                return message
            
            else:
                return message
        
        except Exception as e:
            return f"❌ Ошибка выполнения команды: {str(e)}"
    
    def _format_interactive(self, elements: List[Dict]) -> str:
        """Форматирует интерактивные элементы для ИИ"""
        if not elements:
            return "Нет интерактивных элементов"
        
        result = ""
        for i, el in enumerate(elements[:30]):
            text = el.get('text', '') or el.get('placeholder', '') or el.get('value', '') or ''
            if text:
                result += f"  {i+1}. <{el.get('tag', '')}> '{text[:40]}'"
            else:
                result += f"  {i+1}. <{el.get('tag', '')}>"
            
            if el.get('type'):
                result += f" type={el.get('type')}"
            
            result += f" → {el.get('selector', '')}"
            
            if not el.get('visible', False):
                result += " ⛔"
            result += "\n"
        
        if len(elements) > 30:
            result += f"  ... и ещё {len(elements) - 30} элементов\n"
        
        return result