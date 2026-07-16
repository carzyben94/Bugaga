import os
import json
import logging
import re
from typing import Dict, List, Optional, Any
import httpx

logger = logging.getLogger(__name__)

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = os.environ.get("AI_MODEL", "agnes-2.0-flash")


class AI:
    def __init__(self, browser, eval_obj, accessibility):
        self.browser = browser
        self.eval = eval_obj
        self.accessibility = accessibility
        self.conversation_history = []
        self.last_snapshot = []  # Последний снэпшот
        self.system_prompt = self._get_system_prompt()

    def _get_system_prompt(self) -> str:
        return """Ты - агент для автоматизации браузера.

ПРАВИЛА:
1. Всегда выводи список интерактивных элементов в формате:
   [E1] Тип "Название" - role: роль

2. В конце всегда добавляй:
   "Чтобы кликнуть, скажите: /ask кликни [E1]"

3. Если пользователь просит кликнуть:
   "✅ Клик по [E1] выполнен"

4. После каждого действия показывай обновленный список элементов

ФОРМАТ ОТВЕТА:
1. Список элементов с рефами
2. Подсказка для клика
"""

    async def get_page_context(self) -> str:
        """Получить контекст страницы + свежий снэпшот"""
        try:
            url = await self.eval.get_url()
            title = await self.eval.get_title()
            
            # Свежий снэпшот
            elements = await self.accessibility.get_elements_with_refs()
            self.last_snapshot = elements  # Сохраняем
            
            context = f"Страница: {title}\nURL: {url}\n\n"
            context += "Интерактивные элементы:\n"
            
            for el in elements:
                name = el['name'] if el['name'] else 'без названия'
                context += f"  {el['ref']}: {el['role']} - {name}\n"
            
            if not elements:
                context += "  (нет интерактивных элементов)\n"
            
            return context
        except Exception as e:
            logger.error(f"Ошибка получения контекста: {e}")
            return "Не удалось получить контекст страницы"

    async def ask(self, user_input: str) -> str:
        """Отправить запрос к LLM"""
        try:
            # Получаем свежий контекст (обновленный снэпшот)
            page_context = await self.get_page_context()
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "system", "content": f"Актуальное состояние страницы:\n{page_context}"}
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

    async def clear_history(self):
        self.conversation_history = []
        return "🗑️ История очищена"