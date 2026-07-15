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
        """Комбинированный структурный анализ (Accessibility + DOM)"""
        
        await self.browser.goto(url)
        await asyncio.sleep(3)
        
        # 1. Собираем DOM с прокруткой
        zones = await self.eval.get_elements_with_context(scroll=True)
        
        # 2. Собираем Accessibility
        await self.accessibility.enable()
        await asyncio.sleep(2)
        summary = await self.accessibility.get_summary()
        
        # 3. Собираем все элементы
        buttons = await self.eval.get_all_buttons()
        inputs = await self.eval.get_all_inputs()
        links = await self.eval.get_all_links()
        forms = await self.eval.get_all_forms()
        checkboxes = await self.eval.get_all_checkboxes()
        selects = await self.eval.get_all_selects()
        
        # 4. Формируем ответ
        response = f"🏗️ **Структура страницы:**\n\n"
        
        zone_icons = {
            'navigation': '🏠',
            'header': '🔍',
            'main': '📄',
            'articles': '🐦',
            'complementary': '📋',
            'footer': '📌',
            'other': '📎'
        }
        
        zone_names = {
            'navigation': 'Навигация',
            'header': 'Шапка / Поиск',
            'main': 'Основной контент',
            'articles': 'Карточки',
            'complementary': 'Боковая панель',
            'footer': 'Футер',
            'other': 'Остальное'
        }
        
        for zone, items in zones.items():
            if not items:
                continue
            
            icon = zone_icons.get(zone, '📎')
            name = zone_names.get(zone, zone)
            response += f"  {icon} **{name} ({len(items)}):**\n"
            
            for item in items[:10]:
                text = item.get('text', '')[:35]
                test_id = item.get('testId', '')
                aria_label = item.get('ariaLabel', '')
                
                tag = item.get('tag', '').lower()
                if tag in ['button', 'input[type="submit"]']:
                    prefix = '🔘'
                elif tag in ['input', 'textarea']:
                    prefix = '✏️'
                elif tag == 'a':
                    prefix = '🔗'
                elif tag == 'form':
                    prefix = '📋'
                else:
                    prefix = '•'
                
                if test_id:
                    display = f"{text} (testid: {test_id})"
                elif aria_label:
                    display = f"{aria_label} (aria: {aria_label})"
                elif text:
                    display = text
                else:
                    display = f"[{tag}]"
                
                response += f"    {prefix} {display}\n"
            
            if len(items) > 10:
                response += f"    ... и ещё {len(items) - 10} элементов\n"
            response += "\n"
        
        # Статистика
        response += f"📊 **Статистика:**\n"
        response += f"  🔘 Кнопок: {len(buttons)}\n"
        response += f"  ✏️ Полей ввода: {len(inputs)}\n"
        response += f"  🔗 Ссылок: {len(links)}\n"
        response += f"  📋 Форм: {len(forms)}\n"
        if checkboxes:
            response += f"  ☑️ Checkbox/Radio: {len(checkboxes)}\n"
        if selects:
            response += f"  📋 Select: {len(selects)}\n"
        
        # Дополнительно: Accessibility статистика
        response += f"\n♿ **Доступность:**\n"
        response += f"  🔘 Кнопок (role=button): {summary['buttons']}\n"
        response += f"  ✏️ Полей (role=textbox): {summary['inputs']}\n"
        response += f"  🔗 Ссылок (role=link): {summary['links']}\n"
        response += f"  📌 Заголовков: {summary['headings']}\n"
        response += f"  🏛️ Landmarks: {summary['landmarks']}\n"
        
        return response

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