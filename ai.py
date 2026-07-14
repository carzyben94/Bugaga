import os
import requests
import json
import re
import asyncio
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
2. ask — ответить на вопрос
3. none — ответить без действий

⚠️ ВАЖНО: Если пользователь пишет "открой", "перейди", "зайди" + URL/сайт → ИСПОЛЬЗУЙ action: open

Примеры:
- "открой google.com" → {{"action": "open", "url": "https://google.com", "message": "🌐 Открываю Google"}}
- "привет" → {{"action": "none", "message": "Привет! Я бот для управления браузером. Напиши что хочешь открыть."}}
- "кто ты?" → {{"action": "ask", "question": "кто ты?", "message": "Я бот для управления браузером"}}

ОТВЕТЬ В ФОРМАТЕ JSON:
{{"action": "open | ask | none", "url": "URL для открытия", "message": "ответ пользователю"}}
"""

    @staticmethod
    def get_full_page_prompt(
        command: str,
        title: str,
        url: str,
        interactive_str: str
    ) -> str:
        """Промт для загруженной страницы"""
        return f"""
Ты — AI-ассистент для анализа веб-страниц и выполнения команд.

📄 ТЕКУЩАЯ СТРАНИЦА:
Заголовок: {title}
URL: {url}

🖱 ДОСТУПНЫЕ ЭЛЕМЕНТЫ:
{interactive_str}

🔥 ПРАВИЛА СОРТИРОВКИ (ОТ ВАЖНОГО К МЕНЕЕ ВАЖНОМУ):
1. ВИДИМЫЕ интерактивные элементы (кнопки, ссылки, поля) — САМЫЕ ВАЖНЫЕ
2. ВИДИМЫЕ структурные элементы (заголовки, текст, таблицы)
3. СКРЫТЫЕ интерактивные элементы
4. СКРЫТЫЕ структурные элементы

🔥 ВАЖНО: Различай ВОПРОСЫ и КОМАНДЫ!

ВОПРОСЫ (ask) — пользователь СПРАШИВАЕТ о странице:
• "какие кнопки?" → {{"action": "ask", "question": "какие кнопки?"}}
• "есть ли поле?" → {{"action": "ask", "question": "есть ли поле?"}}
• "что видишь?" → {{"action": "ask", "question": "что видишь?"}}
• "ты можешь ввести текст?" → {{"action": "ask", "question": "ты можешь ввести текст?"}}

КОМАНДЫ (type, click, submit) — пользователь ПРОСИТ СДЕЛАТЬ:
• "введи привет в поиск" → {{"action": "type", "text": "привет", "selector": "селектор поля"}}
• "нажми на Войти" → {{"action": "click", "selector": "селектор кнопки"}}
• "отправь форму" → {{"action": "submit"}}

ПРАВИЛО:
- Если пользователь СПРАШИВАЕТ — используй "ask"
- Если пользователь ПРОСИТ СДЕЛАТЬ — используй действие (type, click, submit)

ПРИМЕРЫ:
Пользователь: "ты можешь ввести текст?" → {{"action": "ask", "question": "ты можешь ввести текст?"}}
Пользователь: "введи привет в поиск" → {{"action": "type", "text": "привет", "selector": "[data-testid='SearchBox_Search_Input']"}}
Пользователь: "нажми на Войти" → {{"action": "click", "selector": "#login-btn"}}
Пользователь: "какие кнопки?" → {{"action": "ask", "question": "какие кнопки?"}}
Пользователь: "напиши туда текст" → {{"action": "type", "text": "текст", "selector": "селектор поля"}}

🔥 Твои ВОЗМОЖНЫЕ ДЕЙСТВИЯ:
1. click — кликнуть по элементу (нужен selector)
2. type — ввести текст (нужны selector + text) — ПОСЛЕ ВВОДА АВТОМАТИЧЕСКИ ENTER
3. open — открыть URL
4. ask — ответить на вопрос о странице
5. wait — ожидать элемент
6. screenshot — сделать скриншот
7. analyze — проанализировать страницу
8. none — просто ответить

⚠️ ВАЖНО: Для click/type ВСЕГДА указывай selector из доступных элементов!
Если есть data-testid — используй его (он самый надёжный).

ОТВЕТЬ В ФОРМАТЕ JSON:
{{
    "action": "click | type | open | ask | wait | screenshot | analyze | none",
    "selector": "CSS селектор (для click/type/wait)",
    "text": "текст для ввода (для type)",
    "url": "URL (для open)",
    "question": "вопрос пользователя (для ask)",
    "message": "понятный ответ пользователю"
}}

КОМАНДА ПОЛЬЗОВАТЕЛЯ: {command}
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
        interactive_str = "Нет данных"
        
        if not page_empty:
            dom_data = await self.browser.get_dom_with_metadata()
            interactive_str = self._format_interactive(dom_data.get('interactive', []))
        
        # Формируем промт
        if page_empty:
            prompt = AgentPrompts.get_empty_page_prompt(command)
        else:
            prompt = AgentPrompts.get_full_page_prompt(
                command=command,
                title=dom_data.get('title', 'Нет'),
                url=dom_data.get('url', 'Нет'),
                interactive_str=interactive_str
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
        question = data.get('question', '')
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
                result = await self.browser.type_text_cdp(selector, text)
                return f"{message}\n{result}"
            
            elif action == 'ask':
                if not question:
                    question = message or "Что на странице?"
                return await self.browser.ai_analyze_page(question)
            
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
                return message or response
        
        except Exception as e:
            return f"❌ Ошибка выполнения команды: {str(e)}"
    
    def _format_interactive(self, elements: List[Dict]) -> str:
        """Форматирует интерактивные элементы для ИИ (с сортировкой по важности)"""
        if not elements:
            return "Нет интерактивных элементов"
        
        result = ""
        
        # Сортируем: сначала видимые, потом интерактивные
        buttons = [el for el in elements if el.get('type') == 'button' and el.get('visible', False)]
        buttons_hidden = [el for el in elements if el.get('type') == 'button' and not el.get('visible', False)]
        links = [el for el in elements if el.get('type') == 'link' and el.get('visible', False)]
        links_hidden = [el for el in elements if el.get('type') == 'link' and not el.get('visible', False)]
        inputs = [el for el in elements if el.get('type') == 'input' and el.get('visible', False)]
        inputs_hidden = [el for el in elements if el.get('type') == 'input' and not el.get('visible', False)]
        
        # 🔘 КНОПКИ
        if buttons:
            result += "\n🔘 **Видимые кнопки (можно кликнуть):**\n"
            for i, el in enumerate(buttons[:30]):
                text = el.get('text', '') or el.get('aria_label', '') or 'без текста'
                selector = el.get('selector', '')
                result += f"  {i+1}. '{text}' → {selector}\n"
            if len(buttons) > 30:
                result += f"  ... и ещё {len(buttons) - 30} видимых кнопок\n"
        
        if buttons_hidden:
            result += "\n👻 **Скрытые кнопки:**\n"
            for i, el in enumerate(buttons_hidden[:10]):
                text = el.get('text', '') or el.get('aria_label', '') or 'без текста'
                selector = el.get('selector', '')
                result += f"  {i+1}. '{text}' → {selector}\n"
            if len(buttons_hidden) > 10:
                result += f"  ... и ещё {len(buttons_hidden) - 10} скрытых кнопок\n"
        
        # 🔗 ССЫЛКИ
        if links:
            result += "\n🔗 **Видимые ссылки:**\n"
            for i, el in enumerate(links[:15]):
                text = el.get('text', '') or 'без текста'
                selector = el.get('selector', '')
                result += f"  {i+1}. '{text}' → {selector}\n"
            if len(links) > 15:
                result += f"  ... и ещё {len(links) - 15} видимых ссылок\n"
        
        # ⌨️ ПОЛЯ ВВОДА
        if inputs:
            result += "\n⌨️ **Видимые поля ввода:**\n"
            for i, el in enumerate(inputs[:10]):
                label = el.get('label', '') or el.get('placeholder', '') or el.get('name', '') or 'поле'
                selector = el.get('selector', '')
                input_type = el.get('input_type', '')
                type_info = f" (type={input_type})" if input_type else ""
                result += f"  {i+1}. '{label}'{type_info} → {selector}\n"
            if len(inputs) > 10:
                result += f"  ... и ещё {len(inputs) - 10} полей\n"
        
        return result