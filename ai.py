import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)


class AIAgent:
    """
    ИИ агент для анализа страниц и принятия решений.
    Использует Agnes API.
    """
    
    def __init__(self, browser=None, eval=None, accessibility=None):
        """
        Args:
            browser: экземпляр Browser из browser.py
            eval: экземпляр Eval из eval.py
            accessibility: экземпляр Accessibility из accessibility.py
        """
        self.browser = browser
        self.eval = eval
        self.accessibility = accessibility
        
        self.api_key = os.environ.get("AGNES_API_KEY")
        self.api_url = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
        self.model = "agnes-2.0-flash"
        
        self.client = None
        self.conversation_history = []
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент"""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=60.0)
        return self.client
    
    async def _call_api(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """
        Вызвать Agnes API.
        
        Args:
            messages: список сообщений [{"role": "user", "content": "..."}]
            temperature: температура генерации
        
        Returns:
            ответ от ИИ
        """
        if not self.api_key:
            raise ValueError("AGNES_API_KEY не задан в переменных окружения")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2000
        }
        
        client = await self._get_client()
        
        try:
            response = await client.post(self.api_url, headers=headers, json=payload)
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Agnes API ошибка: {response.status_code} - {error_text}")
                raise Exception(f"Agnes API ошибка: {response.status_code}")
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
                
        except httpx.TimeoutException:
            logger.error("Таймаут подключения к Agnes API")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Ошибка подключения к Agnes API: {e}")
            raise
    
    async def analyze_page(self, url: str) -> str:
        """
        Проанализировать страницу через ИИ.
        
        Args:
            url: URL страницы
        
        Returns:
            Анализ страницы от ИИ
        """
        if not self.browser:
            raise ValueError("Browser не инициализирован")
        
        if not self.eval:
            raise ValueError("Eval не инициализирован")
        
        # Переходим на страницу
        await self.browser.goto(url)
        await asyncio.sleep(2)
        
        # Собираем данные
        title = await self.eval.get_title()
        page_info = await self.eval.get_page_info()
        links = await self.eval.get_all_links()
        buttons = await self.eval.get_all_buttons()
        inputs = await self.eval.get_all_inputs()
        forms = await self.eval.get_all_forms()
        
        # Формируем промпт
        prompt = f"""
Ты — AI агент для анализа веб-страниц.

**Страница:** {url}
**Заголовок:** {title}
**Язык:** {page_info.get('language', 'не определен')}

**Статистика:**
- Ссылок: {len(links)}
- Кнопок: {len(buttons)}
- Полей ввода: {len(inputs)}
- Форм: {len(forms)}

**Первые 10 ссылок:**
{self._format_list(links[:10], ['text', 'href'])}

**Первые 10 кнопок:**
{self._format_list(buttons[:10], ['text', 'type', 'testId'])}

**Первые 10 полей:**
{self._format_list(inputs[:10], ['name', 'type', 'placeholder', 'testId'])}

**Формы:**
{self._format_list(forms[:5], ['method', 'action'])}

**Текст страницы (первые 2000 символов):**
{page_info.get('innerText', '')[:2000]}

**Задача:**
1. Опиши, о чём эта страница
2. Что можно сделать на этой странице (какие действия)
3. Есть ли форма входа/регистрации?
4. Какие основные элементы для автоматизации?
5. Дай краткий вывод
"""

        messages = [
            {"role": "system", "content": "Ты — полезный AI ассистент для веб-автоматизации."},
            {"role": "user", "content": prompt}
        ]
        
        response = await self._call_api(messages)
        
        # Сохраняем историю
        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append({"role": "assistant", "content": response})
        
        return response
    
    async def analyze_accessibility(self, url: str) -> str:
        """
        Проанализировать Accessibility Tree через ИИ.
        
        Args:
            url: URL страницы
        
        Returns:
            Анализ доступности от ИИ
        """
        if not self.browser:
            raise ValueError("Browser не инициализирован")
        
        if not self.accessibility:
            raise ValueError("Accessibility не инициализирован")
        
        await self.browser.goto(url)
        await asyncio.sleep(3)
        
        # Включаем Accessibility
        await self.accessibility.enable()
        await asyncio.sleep(2)
        
        summary = await self.accessibility.get_summary()
        buttons = await self.accessibility.get_all_buttons()
        links = await self.accessibility.get_all_links()
        inputs = await self.accessibility.get_all_inputs()
        headings = await self.accessibility.get_all_headings()
        landmarks = await self.accessibility.get_all_landmarks()
        
        prompt = f"""
Ты — AI агент для анализа доступности (Accessibility) веб-страниц.

**Страница:** {url}

**Accessibility статистика:**
- Всего узлов: {summary['total_nodes']}
- Кнопок: {summary['buttons']}
- Полей ввода: {summary['inputs']}
- Ссылок: {summary['links']}
- Заголовков: {summary['headings']}
- Landmarks: {summary['landmarks']}
- Изображений: {summary['images']}
- Списков: {summary['lists']}
- Таблиц: {summary['tables']}

**Роли (топ 10):**
{self._format_dict(summary.get('roles', {}), 10)}

**Кнопки (первые 10):**
{self._format_list(buttons[:10], ['name', 'role'])}

**Поля ввода (первые 10):**
{self._format_list(inputs[:10], ['name', 'role'])}

**Ссылки (первые 10):**
{self._format_list(links[:10], ['name', 'role'])}

**Задача:**
1. Оцени качество доступности страницы
2. Какие элементы отсутствуют для хорошей доступности?
3. Есть ли проблемы с семантикой?
4. Дай рекомендации по улучшению доступности
"""

        messages = [
            {"role": "system", "content": "Ты — эксперт по веб-доступности (WCAG)."},
            {"role": "user", "content": prompt}
        ]
        
        response = await self._call_api(messages)
        
        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append({"role": "assistant", "content": response})
        
        return response
    
    async def ask(self, question: str) -> str:
        """
        Задать вопрос ИИ с учётом истории.
        
        Args:
            question: вопрос
        
        Returns:
            ответ от ИИ
        """
        messages = [
            {"role": "system", "content": "Ты — полезный AI ассистент для веб-автоматизации."}
        ]
        
        # Добавляем историю
        messages.extend(self.conversation_history[-10:])  # последние 10 сообщений
        
        # Добавляем вопрос
        messages.append({"role": "user", "content": question})
        
        response = await self._call_api(messages)
        
        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": response})
        
        return response
    
    async def decide_action(self, page_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Принять решение о следующем действии на основе данных страницы.
        
        Args:
            page_info: информация о странице
        
        Returns:
            Словарь с решением: {"action": "click", "selector": "...", "reason": "..."}
        """
        prompt = f"""
Ты — AI агент для принятия решений по автоматизации.

**Данные страницы:**
{json.dumps(page_info, indent=2, ensure_ascii=False)[:2000]}

**Доступные действия:**
- click: кликнуть по элементу (нужен selector)
- type: ввести текст (нужен selector и text)
- scroll: прокрутить страницу (нужен distance)
- wait: подождать (нужен seconds)
- navigate: перейти на URL (нужен url)
- extract: извлечь данные (нужен selector)
- finish: завершить автоматизацию

**Задача:**
Определи, какое действие нужно выполнить на основе данных страницы.
Верни JSON с полями:
- action: название действия
- selector: CSS селектор (если нужен)
- text: текст для ввода (если action = type)
- url: URL для перехода (если action = navigate)
- distance: расстояние для скролла (если action = scroll)
- seconds: время ожидания (если action = wait)
- reason: причина выбора этого действия
"""

        messages = [
            {"role": "system", "content": "Ты — AI агент для веб-автоматизации. Отвечай только JSON."},
            {"role": "user", "content": prompt}
        ]
        
        response = await self._call_api(messages, temperature=0.3)
        
        # Парсим JSON из ответа
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                return json.loads(json_str)
            else:
                return {"action": "finish", "reason": "Не удалось распарсить решение"}
        except json.JSONDecodeError:
            return {"action": "finish", "reason": "Ошибка парсинга JSON"}
    
    async def execute_action(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполнить действие на основе решения AI.
        
        Args:
            decision: решение от AI {"action": "click", "selector": "...", "reason": "..."}
        
        Returns:
            Результат выполнения
        """
        action = decision.get("action")
        selector = decision.get("selector")
        text = decision.get("text")
        distance = decision.get("distance")
        url = decision.get("url")
        
        result = {"success": False, "message": "", "data": None}
        
        try:
            if action == "click":
                if not selector:
                    result["message"] = "Не указан selector для клика"
                    return result
                
                await self.browser.human_click(selector)
                result["success"] = True
                result["message"] = f"Кликнут по {selector}"
                
            elif action == "type":
                if not selector or text is None:
                    result["message"] = "Не указан selector или текст"
                    return result
                
                await self.browser.human_type(selector, text)
                result["success"] = True
                result["message"] = f"Введён текст в {selector}"
                
            elif action == "scroll":
                distance = distance or 500
                await self.browser.human_scroll(distance)
                result["success"] = True
                result["message"] = f"Скролл на {distance}px"
                
            elif action == "wait":
                seconds = decision.get("seconds", 2)
                await asyncio.sleep(seconds)
                result["success"] = True
                result["message"] = f"Ожидание {seconds} сек"
                
            elif action == "navigate":
                if not url:
                    result["message"] = "Не указан URL"
                    return result
                await self.browser.goto(url)
                result["success"] = True
                result["message"] = f"Переход на {url}"
                
            elif action == "extract":
                if not selector:
                    result["message"] = "Не указан selector"
                    return result
                data = await self.eval.get_text(selector)
                result["success"] = True
                result["message"] = f"Извлечён текст из {selector}"
                result["data"] = data
                
            elif action == "finish":
                result["success"] = True
                result["message"] = "Автоматизация завершена"
                
            else:
                result["message"] = f"Неизвестное действие: {action}"
                
        except Exception as e:
            result["message"] = f"Ошибка: {str(e)}"
            logger.error(f"Ошибка выполнения действия {action}: {e}")
        
        return result
    
    def _format_list(self, items: List[Dict], keys: List[str]) -> str:
        """Форматировать список словарей для промпта"""
        if not items:
            return "Нет данных"
        
        result = []
        for i, item in enumerate(items[:10], 1):
            parts = []
            for key in keys:
                value = item.get(key, '')
                if value:
                    parts.append(f"{key}={value}")
            result.append(f"  {i}. " + ", ".join(parts))
        
        return "\n".join(result) if result else "Нет данных"
    
    def _format_dict(self, data: Dict, limit: int = 10) -> str:
        """Форматировать словарь для промпта"""
        if not data:
            return "Нет данных"
        
        sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)[:limit]
        return "\n".join([f"  {key}: {value}" for key, value in sorted_items])
    
    async def close(self):
        """Закрыть HTTP клиент"""
        if self.client and not self.client.is_closed:
            await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()