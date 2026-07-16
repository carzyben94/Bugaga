import logging
import json
import asyncio
from typing import Optional, List, Dict, Any, Union
from browser import cdp_client

logger = logging.getLogger(__name__)

class AccessibilityNode:
    """Узел Accessibility Tree с методами для взаимодействия"""
    
    def __init__(self, node_data: Dict[str, Any], client):
        self.node_data = node_data
        self.client = client
        self.node_id = node_data.get("nodeId")
        self.backend_node_id = node_data.get("backendDOMNodeId")
        self.role = node_data.get("role", {}).get("value", "")
        self.name = node_data.get("name", {}).get("value", "")
        self.ignored = node_data.get("ignored", False)
        self.child_ids = node_data.get("childIds", [])
        self.description = node_data.get("description", {}).get("value", "")
        self.value = node_data.get("value", {}).get("value", "")
        
    async def click(self):
        """Клик по элементу"""
        try:
            js_code = f"""
            (function() {{
                const elements = document.querySelectorAll('*');
                for (let el of elements) {{
                    if (el.textContent && el.textContent.trim() === '{self.name}') {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }})()
            """
            result = await self.client.execute_script(js_code)
            if result:
                logger.info(f"🖱️ Клик по {self.role}: {self.name}")
                return
        except:
            pass
        
        try:
            js_code = f"""
            (function() {{
                const elements = document.querySelectorAll('[role="{self.role}"]');
                for (let el of elements) {{
                    if (el.textContent && el.textContent.includes('{self.name}')) {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }})()
            """
            await self.client.execute_script(js_code)
            logger.info(f"🖱️ Клик по {self.role}: {self.name}")
        except Exception as e:
            logger.error(f"❌ Ошибка клика: {e}")
            raise
    
    async def type(self, text: str):
        """Ввод текста в поле"""
        if self.role not in ["textbox", "searchbox", "text", "textarea", "input"]:
            raise Exception(f"Элемент {self.role} не поддерживает ввод текста")
        
        await self.click()
        await asyncio.sleep(0.2)
        
        try:
            js_code = f"""
            (function() {{
                const elements = document.querySelectorAll('input, textarea, [role="textbox"], [role="searchbox"]');
                for (let el of elements) {{
                    if (el.textContent && el.textContent.includes('{self.name}')) {{
                        el.focus();
                        el.value = '{text}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
            }})()
            """
            await self.client.execute_script(js_code)
            logger.info(f"⌨️ Ввод в {self.role}: {text}")
        except Exception as e:
            logger.error(f"❌ Ошибка ввода: {e}")
            raise
    
    async def get_text(self) -> str:
        """Получить текст элемента"""
        try:
            js_code = f"""
            (function() {{
                const elements = document.querySelectorAll('*');
                for (let el of elements) {{
                    if (el.textContent && el.textContent.trim() === '{self.name}') {{
                        return el.textContent.trim();
                    }}
                }}
                return '{self.name}';
            }})()
            """
            result = await self.client.execute_script(js_code)
            return result if result else self.name
        except:
            return self.name
    
    async def is_enabled(self) -> bool:
        """Проверить, активен ли элемент"""
        state = self.node_data.get("state", {})
        return not state.get("disabled", {}).get("value", False)
    
    async def is_visible(self) -> bool:
        """Проверить, видим ли элемент"""
        state = self.node_data.get("state", {})
        return not state.get("hidden", {}).get("value", False)
    
    def __repr__(self):
        return f"<AccessibilityNode role='{self.role}' name='{self.name}'>"


class Accessibility:
    """Работа с Accessibility Tree"""
    
    def __init__(self, client):
        self.client = client
        self.root_node = None
        self._enabled = False
        self._nodes_by_id = {}  # {node_id: AccessibilityNode}
        
    async def enable(self):
        """Включить Accessibility"""
        try:
            await self.client.send_command("Accessibility.enable")
            self._enabled = True
            logger.info("♿ Accessibility включен")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка включения Accessibility: {e}")
            return False
    
    async def disable(self):
        """Выключить Accessibility"""
        try:
            await self.client.send_command("Accessibility.disable")
            self._enabled = False
            logger.info("♿ Accessibility выключен")
        except Exception as e:
            logger.error(f"❌ Ошибка выключения Accessibility: {e}")
    
    async def ensure_enabled(self):
        """Убедиться, что Accessibility включен"""
        if not self._enabled:
            return await self.enable()
        return True
    
    async def get_full_tree(self) -> List[Dict]:
        """
        Получить полное дерево Accessibility
        CDP: Accessibility.getFullAXTree
        """
        try:
            if not await self.ensure_enabled():
                return []
            
            result = await self.client.send_command("Accessibility.getFullAXTree")
            nodes = result.get("nodes", [])
            
            if not nodes:
                logger.warning("⚠️ getFullAXTree вернул пустой результат")
                return []
            
            # Строим словарь для быстрого доступа
            self._nodes_by_id = {}
            for node_data in nodes:
                node_id = node_data.get("nodeId")
                if node_id:
                    self._nodes_by_id[node_id] = AccessibilityNode(node_data, self.client)
            
            logger.info(f"🌳 Получено {len(nodes)} узлов через getFullAXTree")
            return nodes
            
        except Exception as e:
            logger.error(f"❌ Ошибка getFullAXTree: {e}")
            return []
    
    async def get_all_nodes(self) -> List[AccessibilityNode]:
        """
        Получить все узлы с обработкой ignored nodes
        """
        try:
            raw_nodes = await self.get_full_tree()
            if not raw_nodes:
                return await self._get_all_nodes_js()
            
            # Собираем все узлы, пропуская ignored
            # Используем словарь для быстрого доступа
            result = []
            for node_data in raw_nodes:
                node = AccessibilityNode(node_data, self.client)
                if not node.ignored:
                    result.append(node)
            
            logger.info(f"🌳 После фильтрации ignored: {len(result)} узлов")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения узлов: {e}")
            return await self._get_all_nodes_js()
    
    async def _get_all_nodes_js(self) -> List[AccessibilityNode]:
        """Получить все элементы через JavaScript (fallback)"""
        try:
            js_code = """
            (function() {
                const elements = [];
                const all = document.querySelectorAll('*');
                for (let el of all) {
                    const text = el.textContent ? el.textContent.trim().substring(0, 100) : '';
                    const role = el.getAttribute('role') || el.tagName;
                    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                    const hidden = el.hidden || el.getAttribute('aria-hidden') === 'true';
                    
                    if (!text && !el.tagName.match(/^(INPUT|TEXTAREA|BUTTON|A)$/)) continue;
                    
                    elements.push({
                        role: role,
                        name: text,
                        disabled: disabled,
                        hidden: hidden
                    });
                }
                return elements.slice(0, 100);
            })()
            """
            result = await self.client.execute_script(js_code)
            
            nodes = []
            for item in result:
                node = AccessibilityNode({
                    "nodeId": f"js_{len(nodes)}",
                    "role": {"value": item.get("role", "unknown")},
                    "name": {"value": item.get("name", "")},
                    "backendDOMNodeId": None,
                    "state": {
                        "disabled": {"value": item.get("disabled", False)},
                        "hidden": {"value": item.get("hidden", False)}
                    },
                    "ignored": False,
                    "childIds": []
                }, self.client)
                nodes.append(node)
            
            logger.info(f"🌳 Получено {len(nodes)} узлов через JS fallback")
            return nodes
        except Exception as e:
            logger.error(f"❌ Ошибка JS fallback: {e}")
            return []
    
    async def find_by_role(self, role: str) -> List[AccessibilityNode]:
        """Найти все элементы по роли"""
        nodes = await self.get_all_nodes()
        result = []
        for node in nodes:
            if node.role.lower() == role.lower():
                result.append(node)
        return result
    
    async def find_by_name(self, name: str) -> List[AccessibilityNode]:
        """Найти элементы по имени"""
        nodes = await self.get_all_nodes()
        result = []
        for node in nodes:
            if name.lower() in node.name.lower():
                result.append(node)
        return result
    
    async def find_button(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти кнопку"""
        buttons = await self.find_by_role("button")
        if name:
            for btn in buttons:
                if name.lower() in btn.name.lower():
                    return btn
            return None
        return buttons[0] if buttons else None
    
    async def find_input(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти поле ввода"""
        roles = ["textbox", "searchbox", "input"]
        inputs = []
        for role in roles:
            inputs.extend(await self.find_by_role(role))
        
        if name:
            for inp in inputs:
                if name.lower() in inp.name.lower():
                    return inp
            return None
        return inputs[0] if inputs else None
    
    async def find_link(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти ссылку"""
        links = await self.find_by_role("link")
        if name:
            for link in links:
                if name.lower() in link.name.lower():
                    return link
            return None
        return links[0] if links else None
    
    async def get_all_buttons(self) -> List[AccessibilityNode]:
        """Получить все кнопки"""
        return await self.find_by_role("button")
    
    async def get_all_inputs(self) -> List[AccessibilityNode]:
        """Получить все поля ввода"""
        result = []
        roles = ["textbox", "searchbox", "input"]
        for role in roles:
            result.extend(await self.find_by_role(role))
        return result
    
    async def get_all_links(self) -> List[AccessibilityNode]:
        """Получить все ссылки"""
        return await self.find_by_role("link")
    
    async def get_all_headings(self) -> List[AccessibilityNode]:
        """Получить все заголовки"""
        return await self.find_by_role("heading")
    
    async def get_root_node(self) -> Optional[AccessibilityNode]:
        """Получить корневой узел (для совместимости)"""
        nodes = await self.get_all_nodes()
        if nodes:
            for node in nodes:
                if node.role in ["RootWebArea", "WebArea", "document"]:
                    return node
            return nodes[0]
        return None


# Глобальный экземпляр
accessibility = Accessibility(cdp_client)