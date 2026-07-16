import os
import json
import logging
import re
from typing import Dict, List, Optional, Any
import httpx

logger = logging.getLogger(__name__)

# Конфигурация
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = os.environ.get("AI_MODEL", "agnes-2.0-flash")


class AI:
    def __init__(self, browser, eval_obj, accessibility):
        self.browser = browser
        self.eval = eval_obj
        self.accessibility = accessibility
        self.conversation_history = []
        self.system_prompt = self._get_system_prompt()

    def _get_system_prompt(self) -> str:
        """Системный промпт для агента с строгим форматом"""
        return """Ты - агент для автоматизации браузера. Твоя задача - выполнять действия на странице.

ПРАВИЛА ОТВЕТА (СТРОГО):
1. Всегда выводи список интерактивных элементов в формате:
   [E1] Тип "Название" - role: роль
   [E2] Тип "Название" - role: роль

2. В конце всегда добавляй:
   "Чтобы кликнуть, скажите: /ask кликни [E1]"

3. Если пользователь просит кликнуть, используй формат:
   "✅ Клик по [E1] выполнен"

4. Если элемент не найден:
   "❌ Элемент [E1] не найден"

5. Для описания страницы используй краткий формат:
   "Страница: {название}\nURL: {url}\nДоступно элементов: {количество}"

Доступные действия:
- Клик: [E1]
- Ввод текста: [E1] -> "текст"
- Скролл: scroll_down, scroll_up

ФОРМАТ ОТВЕТА ВСЕГДА:
1. Список элементов с рефами
2. Подсказка для клика
"""

    async def get_page_context(self) -> str:
        """Получить контекст страницы для LLM"""
        try:
            url = await self.eval.get_url()
            title = await self.eval.get_title()
            
            elements = await self.accessibility.get_elements_with_refs()
            
            context = f"Страница: {title}\nURL: {url}\n\n"
            context += "Интерактивные элементы:\n"
            
            for el in elements[:20]:
                context += f"  {el['ref']}: {el['role']} - {el['name']}\n"
            
            if len(elements) > 20:
                context += f"  ... и еще {len(elements)-20} элементов\n"
            
            return context
        except Exception as e:
            logger.error(f"Ошибка получения контекста: {e}")
            return "Не удалось получить контекст страницы"

    async def ask(self, user_input: str) -> str:
        """Отправить запрос к LLM"""
        try:
            page_context = await self.get_page_context()
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "system", "content": f"Контекст страницы:\n{page_context}"}
            ]
            
            for msg in self.conversation_history[-5:]:
                messages.append(msg)
            
            messages.append({"role": "user", "content": user_input})
            
            response = await self._call_api(messages)
            
            self.conversation_history.append({"role": "user", "content": user_input})
            self.conversation_history.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка в ask: {e}")
            return f"❌ Ошибка: {e}"

    async def _call_api(self, messages: List[Dict]) -> str:
        """Вызов Agnes API через httpx"""
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(AGNES_API_URL, headers=headers, json=payload)
            
            if response.status_code != 200:
                raise Exception(f"API ошибка {response.status_code}: {response.text}")
            
            data = response.json()
            return data['choices'][0]['message']['content']

    async def execute_action(self, action: str) -> str:
        """Выполнить действие, описанное LLM"""
        click_match = re.search(r'\[([Ee]\d+)\]', action)
        if click_match:
            ref = click_match.group(1)
            result = await self.accessibility.click_by_ref(ref)
            if result:
                return f"✅ Клик по [{ref}] выполнен"
            return f"❌ Элемент [{ref}] не найден"
        
        input_match = re.search(r'\[([Ee]\d+)\]\s*->\s*"([^"]+)"', action)
        if input_match:
            ref = input_match.group(1)
            text = input_match.group(2)
            return f"✅ Текст '{text}' введен в [{ref}]"
        
        if "scroll_down" in action.lower():
            await self.eval.execute("window.scrollBy(0, 500)")
            return "✅ Скролл вниз"
        
        if "scroll_up" in action.lower():
            await self.eval.execute("window.scrollBy(0, -500)")
            return "✅ Скролл вверх"
        
        return "❌ Неизвестное действие"

    async def clear_history(self):
        """Очистить историю диалога"""
        self.conversation_history = []
        return "🗑️ История очищена"