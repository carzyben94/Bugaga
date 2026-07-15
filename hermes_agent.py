import asyncio
import logging
import json
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
        self.element_map = {}  # ref → selector
        self.snapshot = []
        self._last_url = ""
    
    # ===== СБОР СНАПШОТА =====
    async def get_snapshot(self, url: str) -> Dict[str, Any]:
        """
        Получить снапшот страницы через Accessibility Tree.
        Возвращает только интерактивные элементы с ref-ссылками.
        """
        await self.browser.goto(url)
        await asyncio.sleep(3)
        self._last_url = url
        
        await self.accessibility.enable()
        await asyncio.sleep(1)
        
        # Получаем полное дерево
        nodes = await self.accessibility.get_full_tree()
        
        # Собираем интерактивные элементы
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
            
            # Получаем имя элемента
            name_obj = node.get("name")
            name = name_obj.get("value", "") if isinstance(name_obj, dict) else ""
            
            # Получаем свойства
            properties = node.get("properties", [])
            is_disabled = False
            is_checked = False
            for prop in properties:
                if prop.get("name") == "disabled" and prop.get("value", {}).get("value"):
                    is_disabled = True
                if prop.get("name") == "checked" and prop.get("value", {}).get("value"):
                    is_checked = True
            
            # Пропускаем disabled элементы
            if is_disabled:
                continue
            
            # Создаём ref
            ref = f"@e{ref_counter}"
            ref_counter += 1
            
            # Пытаемся найти selector (testId или aria-label)
            selector = None
            test_id = await self._find_test_id(node)
            if test_id:
                selector = f"[data-testid='{test_id}']"
            else:
                aria_label = await self._find_aria_label(node)
                if aria_label:
                    selector = f"[aria-label='{aria_label}']"
            
            # Сохраняем
            element_info = {
                "ref": ref,
                "role": role,
                "name": name[:50] if name else "",
                "selector": selector,
                "nodeId": node.get("nodeId"),
                "disabled": is_disabled,
                "checked": is_checked
            }
            snapshot.append(element_info)
            if selector:
                self.element_map[ref] = selector
        
        self.snapshot = snapshot
        return {
            "url": url,
            "total_interactive": len(snapshot),
            "elements": snapshot,
            "element_map": self.element_map
        }
    
    async def _find_test_id(self, node: dict) -> Optional[str]:
        """Найти data-testid в дереве (через DOM)"""
        node_id = node.get("nodeId")
        if not node_id:
            return None
        
        try:
            # Пытаемся получить DOM узел
            dom_result = await self.browser.send("DOM.describeNode", {"nodeId": node_id})
            dom_node = dom_result.get("node", {})
            attributes = dom_node.get("attributes", [])
            
            # Ищем data-testid в атрибутах
            for i in range(0, len(attributes), 2):
                if attributes[i] == "data-testid":
                    return attributes[i + 1]
        except:
            pass
        
        return None
    
    async def _find_aria_label(self, node: dict) -> Optional[str]:
        """Найти aria-label в свойствах узла"""
        properties = node.get("properties", [])
        for prop in properties:
            if prop.get("name") == "ariaLabel":
                return prop.get("value", {}).get("value")
        return None
    
    # ===== ДЕЙСТВИЯ =====
    async def click(self, ref: str) -> Dict[str, Any]:
        """Кликнуть по элементу по ref"""
        selector = self.element_map.get(ref)
        if not selector:
            return {"success": False, "reason": f"Элемент {ref} не найден в карте"}
        
        try:
            # Проверяем, что элемент существует
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": f"Элемент {ref} не найден на странице"}
            
            # Кликаем
            await self.browser.human_click(selector)
            await asyncio.sleep(1)
            
            return {
                "success": True,
                "action": "click",
                "ref": ref,
                "selector": selector
            }
        except Exception as e:
            return {"success": False, "reason": str(e)}
    
    async def type_text(self, ref: str, text: str) -> Dict[str, Any]:
        """Ввести текст в поле по ref"""
        selector = self.element_map.get(ref)
        if not selector:
            return {"success": False, "reason": f"Элемент {ref} не найден в карте"}
        
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
    
    async def press_enter(self, ref: str) -> Dict[str, Any]:
        """Нажать Enter в поле по ref"""
        selector = self.element_map.get(ref)
        if not selector:
            return {"success": False, "reason": f"Элемент {ref} не найден в карте"}
        
        try:
            await self.eval.focus(selector)
            await self._press_enter(selector)
            await asyncio.sleep(1)
            
            return {
                "success": True,
                "action": "enter",
                "ref": ref,
                "selector": selector
            }
        except Exception as e:
            return {"success": False, "reason": str(e)}
    
    async def _press_enter(self, selector: str):
        """Нажать Enter через JS"""
        import json
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
    
    # ===== AI АНАЛИЗ =====
    async def ask_ai(self, question: str) -> str:
        """Задать вопрос AI о странице"""
        if not self.snapshot:
            return "Сначала получите снапшот страницы"
        
        prompt = f"""
Ты — AI агент для автоматизации X.com.

**Страница:** {self._last_url}

**Доступные элементы (Accessibility Tree):**
{json.dumps(self.snapshot, indent=2, ensure_ascii=False)}

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