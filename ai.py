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
        interactive_str: str
    ) -> str:
        """Промт для загруженной страницы (с приоритетом data-testid)"""
        return f"""
Ты ИИ-агент, управляешь браузером.

📄 ТЕКУЩАЯ СТРАНИЦА:
Заголовок: {title}
URL: {url}

🖱 ДОСТУПНЫЕ ЭЛЕМЕНТЫ (ТОЛЬКО ТЕ, С КОТОРЫМИ МОЖНО ВЗАИМОДЕЙСТВОВАТЬ):
{interactive_str}

⚠️ ВАЖНЫЕ ПРАВИЛА ВЫБОРА СЕЛЕКТОРА:
1. Если у элемента есть data-testid — ИСПОЛЬЗУЙ ЕГО! Это самый надёжный селектор.
   Пример: [data-testid='AppTabBar_Home_Link']

2. Если есть aria-label — используй его.
   Пример: [aria-label='Перейти к ленте']

3. Если есть id — используй #id.

4. CSS-классы (.css-..., .r-...) — ИСПОЛЬЗУЙ ТОЛЬКО В КРАЙНЕМ СЛУЧАЕ, они могут меняться.

5. Для полей ввода используй атрибуты: name, placeholder, type.
   Пример: input[name='email'], input[type='search'], [placeholder='Поиск']

6. Для кнопок без текста используй aria-label или data-testid.

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
- Если есть data-testid — используй его (он самый надёжный)
- НЕ ВЫДУМЫВАЙ элементы, которых нет в списке
- Для ввода текста используй action: type и укажи selector + text

ОТВЕТЬ В ФОРМАТЕ JSON:
{{
    "action": "click | type | open | find | wait | screenshot | analyze | none",
    "selector": "CSS селектор (для click/type/wait/find)",
    "text": "текст для ввода (для type)",
    "url": "URL (для open)",
    "message": "понятный ответ пользователю"
}}

ПРИМЕРЫ:
1. "нажми на главную" → {{"action": "click", "selector": "[data-testid='AppTabBar_Home_Link']", "message": "✅ Перешёл на главную"}}
2. "открой чат" → {{"action": "click", "selector": "[data-testid='AppTabBar_DirectMessage_Link']", "message": "✅ Открыл чат"}}
3. "введи Python в поиск" → {{"action": "type", "selector": "[data-testid='SearchBox_Search_Input']", "text": "Python", "message": "✅ Ввёл Python в поиск"}}
4. "напиши Привет в поле поста" → {{"action": "type", "selector": "[data-testid='tweetTextarea_0']", "text": "Привет", "message": "✅ Написал пост"}}
5. "какие кнопки есть?" → {{"action": "analyze", "message": "На странице есть кнопки: 'Главная', 'Обзор', 'Уведомления', 'Чат', 'Профиль'"}}
6. "найди поле для email" → {{"action": "find", "selector": "input[type='email']", "message": "🔍 Найдено поле для email"}}
7. "введи test@gmail.com в поле email" → {{"action": "type", "selector": "input[name='email']", "text": "test@gmail.com", "message": "✅ Ввёл email"}}
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
        """Форматирует интерактивные элементы для ИИ (с data-testid)"""
        if not elements:
            return "Нет интерактивных элементов"
        
        result = ""
        
        # Группируем по типу
        buttons = [el for el in elements if el.get('type') == 'button']
        links = [el for el in elements if el.get('type') == 'link']
        inputs = [el for el in elements if el.get('type') == 'input']
        
        if buttons:
            result += "\n🔘 КНОПКИ:\n"
            for i, el in enumerate(buttons[:20]):
                text = el.get('text', '') or el.get('aria_label', '') or 'без текста'
                selector = el.get('selector', '')
                # Если есть data-testid — показываем его
                if 'data-testid' in selector:
                    result += f"  {i+1}. '{text}' → {selector}\n"
                else:
                    result += f"  {i+1}. '{text}' → {selector}\n"
            if len(buttons) > 20:
                result += f"  ... и ещё {len(buttons) - 20} кнопок\n"
        
        if links:
            result += "\n🔗 ССЫЛКИ:\n"
            for i, el in enumerate(links[:10]):
                text = el.get('text', '') or 'без текста'
                selector = el.get('selector', '')
                result += f"  {i+1}. '{text}' → {selector}\n"
            if len(links) > 10:
                result += f"  ... и ещё {len(links) - 10} ссылок\n"
        
        if inputs:
            result += "\n⌨️ ПОЛЯ ВВОДА:\n"
            for i, el in enumerate(inputs[:10]):
                label = el.get('label', '') or el.get('placeholder', '') or el.get('name', '') or 'поле'
                selector = el.get('selector', '')
                input_type = el.get('input_type', '')
                type_info = f" (type={input_type})" if input_type else ""
                result += f"  {i+1}. '{label}'{type_info} → {selector}\n"
            if len(inputs) > 10:
                result += f"  ... и ещё {len(inputs) - 10} полей\n"
        
        return result