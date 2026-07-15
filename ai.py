import os
import json
import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

class AIAgent:
    def __init__(self, browser, eval, accessibility):
        self.browser = browser
        self.eval = eval
        self.accessibility = accessibility
        self.api_key = os.environ.get("AGNES_API_KEY")
        self.api_url = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
        self.model = "agnes-2.0-flash"
        self.client = None
        self.conversation_history = []

    async def _get_client(self):
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=60.0)
        return self.client

    async def _call_api(self, messages, temperature=0.7):
        if not self.api_key:
            raise ValueError("AGNES_API_KEY not set")
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
        response = await client.post(self.api_url, headers=headers, json=payload)
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code}")
        return response.json()["choices"][0]["message"]["content"]

    async def analyze_structure(self, url: str) -> str:
        await self.browser.goto(url)
        await asyncio.sleep(3)

        await self.accessibility.enable()
        await asyncio.sleep(2)

        nodes = await self.accessibility.get_full_tree()
        summary = await self.accessibility.get_summary()
        buttons = await self.eval.get_all_buttons()
        inputs = await self.eval.get_all_inputs()
        links = await self.eval.get_all_links()
        forms = await self.eval.get_all_forms()
        zones = await self.eval.get_elements_with_context()

        prompt = f"""
Ты — AI агент для структурного анализа веб-страниц.

**Страница:** {url}

**Accessibility Tree (структура):**
{json.dumps(nodes[:30], indent=2, ensure_ascii=False)[:1500]}

**Статистика доступности:**
- Кнопок: {summary['buttons']}
- Полей: {summary['inputs']}
- Ссылок: {summary['links']}
- Заголовков: {summary['headings']}
- Landmarks: {summary['landmarks']}

**DOM элементы:**
- Кнопок: {len(buttons)}
- Полей ввода: {len(inputs)}
- Ссылок: {len(links)}
- Форм: {len(forms)}

**Группировка по зонам (DOM):**
{json.dumps(zones, indent=2, ensure_ascii=False)[:1500]}

**Задача:**
Создай структурированное описание страницы, объединяя:
1. Семантическую структуру из Accessibility Tree (роли, иерархия)
2. Конкретные элементы из DOM (data-testid, тексты)

Формат ответа — строго такой:

🏗️ **Структура страницы:**

  🏠 **Навигация (navigation):**
    🔘 Главная (testid: ...)
    🔘 Обзор (testid: ...)

  🔍 **Поиск (search):**
    ✏️ Поисковый запрос (testid: ...)

  📄 **Основной контент (main):**
    🐦 **Карточка (article):**
      🔘 Лайк (testid: ...)
      🔘 Ретвит (testid: ...)

  📋 **Боковая панель (complementary):**
    📌 Тренды

  📌 **Футер (contentinfo):**
    🔗 Ссылка

📊 **Статистика:**
  Кнопок: ... | Полей: ... | Ссылок: ... | Форм: ...
"""

        messages = [
            {"role": "system", "content": "Ты — эксперт по структуре веб-страниц. Отвечай строго в указанном формате."},
            {"role": "user", "content": prompt}
        ]

        return await self._call_api(messages)

    async def ask(self, question: str) -> str:
        messages = [{"role": "system", "content": "Ты — AI ассистент для веб-автоматизации."}]
        messages.extend(self.conversation_history[-10:])
        messages.append({"role": "user", "content": question})
        response = await self._call_api(messages)
        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": response})
        return response

    async def close(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()