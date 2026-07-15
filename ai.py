import os
import json
import logging
import asyncio
import httpx
from site_map import SiteMap  # ← ИМПОРТ

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
        self.site_map = SiteMap()  # ← ХРАНИЛИЩЕ

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

    # ===== ПОСТРОЕНИЕ КАРТЫ САЙТА =====
    async def build_site_map(self, url: str) -> str:
        """Построить карту сайта и сохранить в хранилище"""
        
        await self.browser.goto(url)
        await asyncio.sleep(3)
        
        # 1. Собираем данные
        title = await self.eval.get_title()
        zones = await self.eval.get_elements_with_context(scroll=True)
        buttons = await self.eval.get_all_buttons()
        inputs = await self.eval.get_all_inputs()
        links = await self.eval.get_all_links()
        forms = await self.eval.get_all_forms()
        checkboxes = await self.eval.get_all_checkboxes()
        selects = await self.eval.get_all_selects()
        
        await self.accessibility.enable()
        await asyncio.sleep(2)
        summary = await self.accessibility.get_summary()
        
        # 2. Строим структуру
        structure = {}
        selectors = {}
        total_elements = 0
        
        zone_names = {
            'navigation': 'Навигация',
            'header': 'Шапка',
            'main': 'Основной контент',
            'articles': 'Карточки',
            'complementary': 'Боковая панель',
            'footer': 'Футер',
            'other': 'Остальное'
        }
        
        zone_icons = {
            'navigation': '🏠',
            'header': '🔍',
            'main': '📄',
            'articles': '🐦',
            'complementary': '📋',
            'footer': '📌',
            'other': '📎'
        }
        
        for zone, items in zones.items():
            zone_name = zone_names.get(zone, zone)
            structure[zone_name] = []
            for item in items[:20]:
                el_info = {
                    "text": item.get('text', '')[:50],
                    "testId": item.get('testId', ''),
                    "ariaLabel": item.get('ariaLabel', ''),
                    "type": item.get('tag', '').lower(),
                    "id": item.get('id', ''),
                    "class": item.get('class', '')[:50]
                }
                structure[zone_name].append(el_info)
                total_elements += 1
                
                if item.get('testId'):
                    key = item.get('text', '')[:30] or item.get('testId')
                    selectors[key] = f"[data-testid='{item.get('testId')}']"
        
        # 3. Статистика
        statistics = {
            "buttons": len(buttons),
            "inputs": len(inputs),
            "links": len(links),
            "forms": len(forms),
            "checkboxes": len(checkboxes),
            "selects": len(selects),
            "accessibility": summary
        }
        
        # 4. Сохраняем карту
        self.site_map.save_map(url, {
            "title": title,
            "structure": structure,
            "statistics": statistics,
            "selectors": selectors,
            "zones_count": len(structure),
            "total_elements": total_elements
        })
        
        # 5. Формируем ответ
        response = f"🗺️ **Карта сайта построена и сохранена!**\n\n"
        response += f"📄 **{title}**\n"
        response += f"🔗 {url}\n\n"
        response += f"📊 **Статистика:**\n"
        response += f"  🔘 Кнопок: {len(buttons)}\n"
        response += f"  ✏️ Полей ввода: {len(inputs)}\n"
        response += f"  🔗 Ссылок: {len(links)}\n"
        response += f"  📋 Форм: {len(forms)}\n"
        if checkboxes:
            response += f"  ☑️ Checkbox/Radio: {len(checkboxes)}\n"
        if selects:
            response += f"  📋 Select: {len(selects)}\n\n"
        
        response += f"🏗️ **Структура ({len(structure)} зон, {total_elements} элементов):**\n"
        for zone, items in structure.items():
            if items:
                icon = zone_icons.get(zone, '📎')
                response += f"  {icon} {zone}: {len(items)} элементов\n"
        
        response += f"\n🔖 **Сохранённые селекторы:** {len(selectors)}\n"
        response += f"💾 **Файл:** site_map.json\n\n"
        response += f"💡 Теперь ты можешь спрашивать:\n"
        response += f"  - /ai где находится кнопка 'Опубликовать' на {url}\n"
        response += f"  - /ai покажи структуру {url}\n"
        response += f"  - /ai какие есть селекторы для {url}"
        
        return response

    # ===== АНАЛИЗ СТРУКТУРЫ =====
    async def analyze_structure(self, url: str) -> str:
        """Комбинированный структурный анализ (Accessibility + DOM)"""
        
        await self.browser.goto(url)
        await asyncio.sleep(3)
        
        zones = await self.eval.get_elements_with_context(scroll=True)
        
        await self.accessibility.enable()
        await asyncio.sleep(2)
        summary = await self.accessibility.get_summary()
        
        buttons = await self.eval.get_all_buttons()
        inputs = await self.eval.get_all_inputs()
        links = await self.eval.get_all_links()
        forms = await self.eval.get_all_forms()
        checkboxes = await self.eval.get_all_checkboxes()
        selects = await self.eval.get_all_selects()
        
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
        
        response += f"📊 **Статистика:**\n"
        response += f"  🔘 Кнопок: {len(buttons)}\n"
        response += f"  ✏️ Полей ввода: {len(inputs)}\n"
        response += f"  🔗 Ссылок: {len(links)}\n"
        response += f"  📋 Форм: {len(forms)}\n"
        if checkboxes:
            response += f"  ☑️ Checkbox/Radio: {len(checkboxes)}\n"
        if selects:
            response += f"  📋 Select: {len(selects)}\n"
        
        response += f"\n♿ **Доступность:**\n"
        response += f"  🔘 Кнопок (role=button): {summary['buttons']}\n"
        response += f"  ✏️ Полей (role=textbox): {summary['inputs']}\n"
        response += f"  🔗 Ссылок (role=link): {summary['links']}\n"
        response += f"  📌 Заголовков: {summary['headings']}\n"
        response += f"  🏛️ Landmarks: {summary['landmarks']}\n"
        
        return response

    # ===== ОБЫЧНЫЙ ЧАТ =====
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