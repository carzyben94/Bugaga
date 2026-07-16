import os
import json
import logging
from typing import Dict, List, Optional, Any

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
        """Системный промпт для агента (как Hermes)"""
        return """Ты - агент для автоматизации браузера. Твоя задача - выполнять действия на странице.

Правила:
1. Для взаимодействия с элементами используй рефы вида [E1], [E2] и т.д.
2. Перед действием всегда проверяй доступность элементов через accessibility.
3. После каждого действия описывай результат.
4. Если страница загрузилась, сообщай об этом.

Доступные действия:
- Клик: [E1]
- Ввод текста: [E1] -> "текст"
- Скролл: scroll_down, scroll_up
- Получение данных: get_text, get_html, get_url

Формат ответа:
1. Описание текущего состояния страницы
2. Действие, которое нужно выполнить
3. Ожидаемый результат

Пример ответа:
"Страница загружена. Вижу кнопку 'Войти' [E1]. Кликаю по [E1] для перехода к форме авторизации."
"""

    async def get_page_context(self) -> str:
        """Получить контекст страницы для LLM"""
        try:
            url = await self.eval.get_url()
            title = await self.eval.get_title()
            
            # Получаем интерактивные элементы с рефами
            elements = await self.accessibility.get_elements_with_refs()
            
            # Формируем контекст
            context = f"Страница: {title}\nURL: {url}\n\n"
            context += "Интерактивные элементы:\n"
            
            for el in elements[:20]:  # Ограничиваем для токенов
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
            # Получаем контекст страницы
            page_context = await self.get_page_context()
            
            # Формируем сообщение
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "system", "content": f"Контекст страницы:\n{page_context}"}
            ]
            
            # Добавляем историю (последние 5 сообщений)
            for msg in self.conversation_history[-5:]:
                messages.append(msg)
            
            # Добавляем текущий запрос
            messages.append({"role": "user", "content": user_input})
            
            # Отправляем запрос к API
            response = await self._call_api(messages)
            
            # Сохраняем в историю
            self.conversation_history.append({"role": "user", "content": user_input})
            self.conversation_history.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка в ask: {e}")
            return f"❌ Ошибка: {e}"

    async def _call_api(self, messages: List[Dict]) -> str:
        """Вызов Agnes API"""
        import aiohttp
        
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
        
        async with aiohttp.ClientSession() as session:
            async with session.post(AGNES_API_URL, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"API ошибка {resp.status}: {error_text}")
                
                data = await resp.json()
                return data['choices'][0]['message']['content']

    async def execute_action(self, action: str) -> str:
        """Выполнить действие, описанное LLM"""
        # Парсим действие из ответа LLM
        # Например: [E1] -> клик
        # [E1] -> "текст" -> ввод текста
        # scroll_down -> скролл
        
        import re
        
        # Проверяем клик
        click_match = re.search(r'\[([Ee]\d+)\]', action)
        if click_match:
            ref = click_match.group(1)
            result = await self.accessibility.click_by_ref(ref)
            if result:
                return f"✅ Клик по [{ref}] выполнен"
            return f"❌ Элемент [{ref}] не найден"
        
        # Проверяем ввод текста
        input_match = re.search(r'\[([Ee]\d+)\]\s*->\s*"([^"]+)"', action)
        if input_match:
            ref = input_match.group(1)
            text = input_match.group(2)
            # TODO: реализовать ввод текста
            return f"✅ Текст '{text}' введен в [{ref}]"
        
        # Скролл
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