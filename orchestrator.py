import logging
import asyncio
import json
import re
import base64
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Оркестратор — главный агент Луи.
    Умеет: память, планирование, кэширование, адаптивность.
    """
    
    def __init__(self, browser, eval, accessibility, ai_agent, hermes_agent):
        self.browser = browser
        self.eval = eval
        self.accessibility = accessibility
        self.ai = ai_agent
        self.hermes = hermes_agent
        
        # ===== ПАМЯТЬ =====
        self.memory = {
            "last_url": None,
            "last_snapshot": None,
            "last_action": None,
            "last_result": None,
            "conversation": [],
            "current_step": 0
        }
        
        # ===== КЭШ ПОВЕДЕНИЯ =====
        self.behavior_cache = {}
        
        # ===== СОСТОЯНИЕ =====
        self.current_url = None
        self.is_planning = False
        self.current_plan = []
        self.plan_step = 0
    
    # ===== ПАМЯТЬ =====
    def remember(self, key: str, value: Any):
        """Запомнить что-то"""
        self.memory[key] = value
        self.memory["conversation"].append({
            "timestamp": datetime.now().isoformat(),
            "key": key,
            "value": str(value)[:100]
        })
        logger.debug(f"🧠 Запомнил: {key} = {str(value)[:50]}")
    
    def recall(self, key: str) -> Any:
        """Вспомнить что-то"""
        return self.memory.get(key)
    
    # ===== КЭШ =====
    def cache_behavior(self, site: str, action: str, steps: List[str]):
        """Сохранить успешную цепочку действий"""
        if site not in self.behavior_cache:
            self.behavior_cache[site] = {}
        self.behavior_cache[site][action] = steps
        logger.info(f"💾 Закэшировал поведение для {site} -> {action}")
    
    def get_cached_behavior(self, site: str, action: str) -> Optional[List[str]]:
        """Получить закэшированную цепочку"""
        return self.behavior_cache.get(site, {}).get(action)
    
    # ===== СНАПШОТ С КЭШИРОВАНИЕМ =====
    async def snapshot(self, url: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """Сделать снапшот с кэшированием"""
        if url:
            await self.browser.goto(url)
            self.current_url = url
        
        if self.hermes.snapshot and not force:
            logger.info("📸 Использую кэшированный снапшот")
            return {
                "success": True,
                "cached": True,
                "total_elements": len(self.hermes.snapshot),
                "elements": self.hermes.snapshot[:20]
            }
        
        result = await self.hermes.get_snapshot(self.current_url or "https://x.com")
        self.remember("last_snapshot", result)
        self.remember("last_url", self.current_url)
        
        return {
            "success": True,
            "cached": False,
            "total_elements": result["total_interactive"],
            "elements": result["elements"][:20]
        }
    
    # ===== ПЛАНИРОВАНИЕ =====
    async def plan(self, goal: str) -> List[Dict[str, Any]]:
        """Создать план действий для достижения цели"""
        
        site = "x.com" if self.current_url and "x.com" in self.current_url else "unknown"
        cached = self.get_cached_behavior(site, goal[:30])
        if cached:
            logger.info(f"📋 Использую кэшированный план для {goal[:30]}")
            return [{"action": "click", "ref": ref} for ref in cached]
        
        snapshot_text = "\n".join([
            f"{el['ref']}: {el['role']} — {el['name']}"
            for el in self.hermes.snapshot[:30]
        ])
        
        prompt = f"""
Ты — Луи, AI-помощник для X.com.

**Текущая страница:** {self.current_url}

**Доступные элементы:**
{snapshot_text}

**Цель:** {goal}

**Задача:**
Составь пошаговый план действий для достижения цели.
Используй только ref-ссылки (@e1, @e2, ...) из списка выше.

Верни JSON:
[
    {{"action": "click", "ref": "@e1"}},
    {{"action": "type", "ref": "@e2", "text": "..."}},
    {{"action": "enter", "ref": "@e2"}}
]
"""

        response = await self.ai.ask(prompt)
        
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end != -1:
                plan = json.loads(response[start:end])
                if len(plan) > 1:
                    self.cache_behavior(site, goal[:30], [step.get("ref") for step in plan if step.get("ref")])
                return plan
        except:
            pass
        
        return [{"action": "unknown", "reason": "Не удалось создать план"}]
    
    # ===== ВЫПОЛНЕНИЕ =====
    async def execute(self, text: str) -> Dict[str, Any]:
        """Выполнить команду с умом"""
        
        if not self.hermes.snapshot and "открой" not in text.lower():
            await self.browser.goto("https://x.com")
            self.current_url = "https://x.com"
            await self.snapshot()
            return {
                "success": True,
                "message": "🌐 Я открыл X.com и готов помогать!\n\n" +
                           await self._continue_execution(text)
            }
        
        result = await self._continue_execution(text)
        
        if isinstance(result, str):
            return {"success": True, "message": result}
        if isinstance(result, dict):
            return result
        return {"success": True, "message": str(result)}
    
    async def _continue_execution(self, text: str) -> str:
        """Продолжить выполнение после инициализации"""
        
        parsed = await self._parse_natural_language(text)
        action = parsed.get("action")
        
        # ===== СКРИНШОТ =====
        if action == "screenshot":
            screenshot_base64 = await self.browser.screenshot()
            screenshots_dir = "screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            filename = f"{screenshots_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_screen.png"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(screenshot_base64))
            return {
                "success": True,
                "message": f"📸 Скриншот сохранён: {filename}",
                "screenshot": screenshot_base64,
                "filename": filename
            }
        
        # ===== НАВИГАЦИЯ =====
        if action == "navigate":
            url = parsed.get("url")
            await self.browser.goto(url)
            self.current_url = url
            await self.snapshot(force=True)
            return f"✅ Перешёл на {url}\n📸 Обновил снапшот"
        
        # ===== СНАПШОТ =====
        if action == "snapshot":
            result = await self.snapshot(force=True)
            response = f"📸 **Снапшот страницы**\n\n"
            response += f"📊 Элементов: {result['total_elements']}\n\n"
            for el in result['elements'][:15]:
                response += f"  {el['ref']}: {el['role']} — {el['name'][:40]}\n"
            if result['total_elements'] > 15:
                response += f"\n... и ещё {result['total_elements'] - 15} элементов"
            return response
        
        # ===== КЛИК =====
        if action == "click_by_name":
            name = parsed.get("name")
            for ref, info in self.hermes.element_map.items():
                if name.lower() in info.get("name", "").lower():
                    result = await self.hermes.click(ref)
                    if result.get("success"):
                        await self.snapshot(force=True)
                        return f"✅ Клик по '{name}' выполнен"
            return f"❌ Не нашёл '{name}'"
        
        # ===== ЦЕПОЧКА =====
        if action == "chain" or action == "publish":
            plan = await self.plan(text)
            if not plan:
                return "❌ Не могу построить план"
            
            results = []
            for step in plan:
                action_type = step.get("action")
                ref = step.get("ref")
                
                if action_type == "click":
                    result = await self.hermes.click(ref)
                elif action_type == "type":
                    result = await self.hermes.type_text(ref, step.get("text", ""))
                elif action_type == "enter":
                    result = await self.hermes.press_enter(ref)
                else:
                    result = {"success": False, "reason": f"Неизвестное действие: {action_type}"}
                
                results.append(result)
                await asyncio.sleep(0.5)
            
            await self.snapshot(force=True)
            
            response = "✅ **Цепочка выполнена!**\n\n"
            for i, r in enumerate(results):
                status = "✅" if r.get("success") else "❌"
                response += f"{status} Шаг {i+1}: {r.get('message', r.get('reason', 'Выполнен'))}\n"
            
            return response
        
        # ===== ПОМОЩЬ =====
        if action == "help":
            return """
🤖 **Я Луи!**

Я умею:
  📸 делать скриншоты
  🔍 показывать что есть на странице
  🖱️ кликать по кнопкам и ссылкам
  ✏️ вводить текст
  🧠 выполнять цепочки действий

**Просто скажи что нужно:**
  "открой x.com"
  "перейди в обзор"  
  "опубликуй пост 'Привет мир!'"
  "покажи что есть на странице"
  "сделай скрин"
  "введи в поиск 'AI' и нажми Enter"

🔥 Я сам пойму, что ты хочешь!
"""
        
        return "❌ Не понял. Попробуй переформулировать."
    
    # ===== ПАРСЕР =====
    async def _parse_natural_language(self, text: str) -> Dict[str, Any]:
        """Распарсить команду на естественном языке"""
        text_lower = text.lower()
        
        if "скрин" in text_lower or "screenshot" in text_lower:
            return {"action": "screenshot"}
        
        if "покажи" in text_lower or "что есть" in text_lower:
            return {"action": "snapshot"}
        
        if "помощь" in text_lower or "help" in text_lower:
            return {"action": "help"}
        
        if "открой" in text_lower or "перейди" in text_lower or "зайди" in text_lower:
            url_match = re.search(r'https?://[^\s]+', text)
            if url_match:
                return {"action": "navigate", "url": url_match.group(0)}
            if "x.com" in text_lower:
                return {"action": "navigate", "url": "https://x.com"}
        
        if "опубликуй" in text_lower or "запости" in text_lower or "твит" in text_lower:
            quote_match = re.search(r'["\']([^"\']*)["\']', text)
            if quote_match:
                return {"action": "publish", "text": quote_match.group(1)}
            return {"action": "publish"}
        
        if "клик" in text_lower or "нажми" in text_lower:
            words = text.split()
            for i, word in enumerate(words):
                if word in ["на", "по", "кнопку", "ссылку"] and i + 1 < len(words):
                    name = ' '.join(words[i+1:])
                    if len(name) > 2:
                        return {"action": "click_by_name", "name": name}
        
        if "введи" in text_lower or "напиши" in text_lower:
            quote_match = re.search(r'["\']([^"\']*)["\']', text)
            if quote_match:
                return {"action": "chain", "description": f"введи '{quote_match.group(1)}' и нажми Enter"}
        
        return {"action": "unknown"}