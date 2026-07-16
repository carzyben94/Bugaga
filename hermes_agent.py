import asyncio
import logging
import json
import base64
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class HermesAgent:
    """
    AI агент для работы с X.com через Accessibility Tree.
    Использует подход Hermes: доступность → действия.
    """
    
    def __init__(self, browser, accessibility, eval, ai_agent):
        self.browser = browser
        self.accessibility = accessibility
        self.eval = eval
        self.ai = ai_agent
        self.element_map = {}
        self.snapshot = []
        self._last_url = ""

    # ===== СБОР СНАПШОТА =====
    async def get_snapshot(self, url: str) -> Dict[str, Any]:
        """Получить снапшот страницы через Accessibility Tree"""
        await self.browser.goto(url)
        await asyncio.sleep(3)
        self._last_url = url
        
        await self.accessibility.enable()
        await asyncio.sleep(1)
        
        nodes = await self.accessibility.get_full_tree()
        
        interactive_roles = {"button", "link", "textbox", "searchbox", "combobox", "checkbox", "radio", "select"}
        
        snapshot = []
        self.element_map = {}
        
        ref_counter = 1
        for node in nodes:
            if node.get("ignored"):
                continue
            
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            
            if role not in interactive_roles:
                continue
            
            name_obj = node.get("name")
            name = name_obj.get("value", "") if isinstance(name_obj, dict) else ""
            
            properties = node.get("properties", [])
            is_disabled = False
            is_checked = False
            for prop in properties:
                if prop.get("name") == "disabled" and prop.get("value", {}).get("value"):
                    is_disabled = True
                if prop.get("name") == "checked" and prop.get("value", {}).get("value"):
                    is_checked = True
            
            if is_disabled:
                continue
            
            ref = f"@e{ref_counter}"
            ref_counter += 1
            
            # Пытаемся найти селектор
            selector = None
            test_id = await self._find_test_id(node)
            if test_id:
                selector = f"[data-testid='{test_id}']"
            else:
                aria_label = await self._find_aria_label(node)
                if aria_label:
                    selector = f"[aria-label='{aria_label}']"
            
            element_info = {
                "ref": ref,
                "role": role,
                "name": name[:50] if name else "",
                "selector": selector,
                "nodeId": node.get("nodeId"),
                "disabled": is_disabled,
                "checked": is_checked,
                "has_selector": selector is not None
            }
            snapshot.append(element_info)
            self.element_map[ref] = element_info
        
        self.snapshot = snapshot
        
        logger.info(f"📊 Собрано {len(snapshot)} элементов")
        logger.info(f"🔑 Доступные ref: {list(self.element_map.keys())[:20]}")
        
        return {
            "url": url,
            "total_interactive": len(snapshot),
            "elements": snapshot,
            "element_map": self.element_map
        }

    async def _find_test_id(self, node: dict) -> Optional[str]:
        """Найти data-testid в дереве"""
        node_id = node.get("nodeId")
        if not node_id:
            return None
        
        try:
            node_id_int = int(node_id)
        except (ValueError, TypeError):
            return None
        
        try:
            dom_result = await self.browser.send("DOM.describeNode", {"nodeId": node_id_int})
            dom_node = dom_result.get("node", {})
            attributes = dom_node.get("attributes", [])
            for i in range(0, len(attributes), 2):
                if attributes[i] == "data-testid":
                    return attributes[i + 1]
        except Exception as e:
            # Элемент мог быть удалён из DOM — просто пропускаем
            logger.debug(f"Не удалось найти testId для nodeId {node_id}: {e}")
            return None
        
        return None

    async def _find_aria_label(self, node: dict) -> Optional[str]:
        """Найти aria-label в свойствах узла"""
        properties = node.get("properties", [])
        for prop in properties:
            if prop.get("name") == "ariaLabel":
                value_obj = prop.get("value", {})
                return value_obj.get("value", "")
        return None

    # ===== СКРИНШОТЫ =====
    async def _take_screenshot(self, name: str) -> str:
        """Сделать скриншот и сохранить"""
        try:
            screenshot_base64 = await self.browser.screenshot()
            screenshots_dir = "screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            filename = f"{screenshots_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.png"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(screenshot_base64))
            logger.info(f"📸 Скриншот сохранён: {filename}")
            return filename
        except Exception as e:
            logger.error(f"Ошибка скриншота: {e}")
            return ""

    # ===== ДЕЙСТВИЯ =====
    async def click(self, ref: str) -> Dict[str, Any]:
        """Кликнуть по элементу по ref"""
        
        logger.info(f"🔍 Ищу {ref}")
        logger.info(f"📋 В карте {len(self.element_map)} элементов")
        
        element_info = self.element_map.get(ref)
        if not element_info:
            logger.error(f"❌ {ref} НЕ НАЙДЕН в карте!")
            return {"success": False, "reason": f"Элемент {ref} не найден в карте"}
        
        logger.info(f"✅ {ref} найден: role={element_info.get('role')}, name={element_info.get('name')[:30]}")
        
        selector = element_info.get("selector")
        role = element_info.get("role", "")
        name = element_info.get("name", "")
        
        # ===== ЕСЛИ ЕСТЬ СЕЛЕКТОР — ИСПОЛЬЗУЕМ =====
        if selector:
            try:
                exists = await self.eval.exists(selector)
                if not exists:
                    return {"success": False, "reason": f"Элемент {ref} не найден на странице"}
                
                screenshot_before = await self._take_screenshot("before_click")
                await self.browser.human_click(selector)
                await asyncio.sleep(1.5)
                screenshot_after = await self._take_screenshot("after_click")
                
                return {
                    "success": True,
                    "action": "click",
                    "ref": ref,
                    "selector": selector,
                    "role": role,
                    "screenshot_before": screenshot_before,
                    "screenshot_after": screenshot_after
                }
            except Exception as e:
                return {"success": False, "reason": str(e)}
        
        # ===== ЕСЛИ НЕТ СЕЛЕКТОРА — ИЩЕМ ПО ТЕКСТУ (ДЛЯ ССЫЛОК) =====
        if not name:
            return {"success": False, "reason": f"Элемент {ref} не имеет имени"}
        
        try:
            safe_name = json.dumps(name)
            
            # ===== ИЩЕМ ССЫЛКУ ПО ТЕКСТУ =====
            js = f"""
            (function() {{
                const elements = document.querySelectorAll('a, [role="link"], button, [role="button"], div[role="link"], span[role="link"]');
                for (const el of elements) {{
                    const text = el.innerText || el.textContent || '';
                    if (text.includes({safe_name})) {{
                        el.click();
                        return true;
                    }}
                }}
                
                const byAria = document.querySelector('[aria-label*={safe_name}]');
                if (byAria) {{
                    byAria.click();
                    return true;
                }}
                
                return false;
            }})()
            """
            clicked = await self.eval.execute(js)
            if clicked:
                await asyncio.sleep(1.5)
                screenshot_after = await self._take_screenshot("after_click")
                return {
                    "success": True,
                    "action": "click",
                    "ref": ref,
                    "method": "text_search",
                    "screenshot_after": screenshot_after
                }
            
            return {"success": False, "reason": f"Не удалось найти элемент {ref} по тексту '{name}'"}
            
        except Exception as e:
            return {"success": False, "reason": str(e)}

    async def type_text(self, ref: str, text: str) -> Dict[str, Any]:
        """Ввести текст в поле по ref"""
        element_info = self.element_map.get(ref)
        if not element_info:
            return {"success": False, "reason": f"Элемент {ref} не найден в карте"}
        
        selector = element_info.get("selector")
        
        if selector:
            try:
                exists = await self.eval.exists(selector)
                if not exists:
                    return {"success": False, "reason": f"Элемент {ref} не найден на странице"}
                
                await self.browser.human_type(selector, text)
                await asyncio.sleep(0.5)
                
                return {
                    "success": True,
                    "action": "type",
                    "ref": ref,
                    "selector": selector,
                    "text": text
                }
            except Exception as e:
                return {"success": False, "reason": str(e)}
        
        return {"success": False, "reason": f"Элемент {ref} не имеет селектора"}

    async def press_enter(self, ref: str) -> Dict[str, Any]:
        """Нажать Enter в поле по ref"""
        element_info = self.element_map.get(ref)
        if not element_info:
            return {"success": False, "reason": f"Элемент {ref} не найден в карте"}
        
        selector = element_info.get("selector")
        
        if selector:
            try:
                await self.eval.focus(selector)
                
                safe_selector = json.dumps(selector)
                js = f"""
                (function() {{
                    const el = document.querySelector({safe_selector});
                    if (!el) return false;
                    el.dispatchEvent(new KeyboardEvent('keydown', {{
                        key: 'Enter',
                        code: 'Enter',
                        bubbles: true,
                        cancelable: true
                    }}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {{
                        key: 'Enter',
                        code: 'Enter',
                        bubbles: true,
                        cancelable: true
                    }}));
                    return true;
                }})()
                """
                await self.eval.execute(js)
                await asyncio.sleep(1)
                
                return {
                    "success": True,
                    "action": "enter",
                    "ref": ref,
                    "selector": selector
                }
            except Exception as e:
                return {"success": False, "reason": str(e)}
        
        return {"success": False, "reason": f"Элемент {ref} не имеет селектора"}

    # ===== AI АНАЛИЗ =====
    async def ask_ai(self, question: str) -> str:
        """Задать вопрос AI о странице"""
        if not self.snapshot:
            return "Сначала получите снапшот страницы"
        
        elements_text = "\n".join([
            f"  {el['ref']}: {el['role']} — {el['name']}"
            for el in self.snapshot[:30]
        ])
        if len(self.snapshot) > 30:
            elements_text += f"\n  ... и ещё {len(self.snapshot) - 30} элементов"
        
        prompt = f"""
Ты — AI агент для автоматизации X.com.

**Страница:** {self._last_url}

**Доступные элементы (Accessibility Tree):**
{elements_text}

**Вопрос пользователя:** {question}

Ответь на вопрос, используя ref-ссылки (@e1, @e2, ...) для указания элементов.
"""

        return await self.ai.ask(prompt)

    # ===== ВЫПОЛНЕНИЕ ЦЕПОЧКИ =====
    async def execute_chain(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Выполнить цепочку действий"""
        results = []
        for step in steps:
            action = step.get("action")
            ref = step.get("ref")
            
            if action == "click":
                result = await self.click(ref)
            elif action == "type":
                result = await self.type_text(ref, step.get("text", ""))
            elif action == "enter":
                result = await self.press_enter(ref)
            else:
                result = {"success": False, "reason": f"Неизвестное действие: {action}"}
            
            results.append(result)
            await asyncio.sleep(0.5)
        
        return results