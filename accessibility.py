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
        self.description = node_data.get("description", {}).get("value", "")
        self.value = node_data.get("value", {}).get("value", "")
        
    async def click(self):
        """Клик по элементу"""
        try:
            # Пробуем найти элемент через JS по имени
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
        
        # Если не нашли, пробуем через роль
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
        
        # Кликаем для фокуса
        await self.click()
        await asyncio.sleep(0.2)
        
        # Вводим текст через JS
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
        self._all_nodes_cache = []
        
    async def enable(self):
        """Включить Accessibility (CDP: Accessibility.enable)"""
        try:
            await self.client.send_command("Accessibility.enable")
            self._enabled = True
            logger.info("♿ Accessibility включен")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка включения Accessibility: {e}")
            return False
    
    async def disable(self):
        """Выключить Accessibility (CDP: Accessibility.disable)"""
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
    
    async def get_full_tree(self) -> List[AccessibilityNode]:
        """
        Получить всё дерево Accessibility через getFullAXTree
        CDP: Accessibility.getFullAXTree
        """
        try:
            if not await self.ensure_enabled():
                return []
            
            result = await self.client.send_command("Accessibility.getFullAXTree")
            nodes = result.get("nodes", [])
            
            # Кешируем
            self._all_nodes_cache = [AccessibilityNode(node, self.client) for node in nodes]
            logger.info(f"🌳 Получено {len(self._all_nodes_cache)} узлов Accessibility")
            return self._all_nodes_cache
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения полного дерева: {e}")
            return []
    
    async def get_root_node(self) -> Optional[AccessibilityNode]:
        """
        Получить корневой узел Accessibility Tree
        Использует getFullAXTree для надежности
        """
        try:
            if not await self.ensure_enabled():
                return None
            
            # Пробуем через getFullAXTree (более надежно)
            nodes = await self.get_full_tree()
            if nodes:
                # Ищем корневой узел (обычно RootWebArea)
                for node in nodes:
                    if node.role in ["RootWebArea", "WebArea", "document"]:
                        self.root_node = node
                        return node
                # Если не нашли, берем первый
                self.root_node = nodes[0]
                return nodes[0]
            
            # Fallback на getRootAXNode
            try:
                result = await self.client.send_command("Accessibility.getRootAXNode")
                if result and "node" in result:
                    self.root_node = AccessibilityNode(result["node"], self.client)
                    return self.root_node
            except:
                pass
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения корневого узла: {e}")
            return None
    
    async def get_all_nodes(self) -> List[AccessibilityNode]:
        """
        Получить все узлы дерева
        """
        if self._all_nodes_cache:
            return self._all_nodes_cache
        
        return await self.get_full_tree()
    
    async def find_by_role(self, role: str) -> List[AccessibilityNode]:
        """
        Найти все элементы по роли через getFullAXTree
        """
        result = []
        nodes = await self.get_all_nodes()
        for node in nodes:
            if node.role.lower() == role.lower():
                result.append(node)
        return result
    
    async def find_by_name(self, name: str) -> List[AccessibilityNode]:
        """
        Найти элементы по имени
        """
        result = []
        nodes = await self.get_all_nodes()
        for node in nodes:
            if name.lower() in node.name.lower():
                result.append(node)
        return result
    
    async def find_by_text(self, text: str) -> List[AccessibilityNode]:
        """
        Найти элементы по тексту (через JS fallback)
        """
        try:
            js_code = f"""
            (function() {{
                const elements = [];
                const all = document.querySelectorAll('*');
                for (let el of all) {{
                    if (el.textContent && el.textContent.includes('{text}')) {{
                        elements.push({{
                            tag: el.tagName,
                            text: el.textContent.trim().substring(0, 100),
                            role: el.getAttribute('role') || el.tagName,
                            disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
                            hidden: el.hidden || el.getAttribute('aria-hidden') === 'true'
                        }});
                    }}
                }}
                return elements.slice(0, 50);
            }})()
            """
            result = await self.client.execute_script(js_code)
            
            nodes = []
            for item in result:
                node = AccessibilityNode({
                    "nodeId": f"js_{len(nodes)}",
                    "role": {"value": item.get("role", "unknown")},
                    "name": {"value": item.get("text", "")},
                    "backendDOMNodeId": None,
                    "state": {
                        "disabled": {"value": item.get("disabled", False)},
                        "hidden": {"value": item.get("hidden", False)}
                    }
                }, self.client)
                nodes.append(node)
            
            return nodes
        except Exception as e:
            logger.error(f"❌ Ошибка поиска по тексту: {e}")
            return []
    
    async def find_button(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти кнопку (по имени)"""
        buttons = await self.find_by_role("button")
        if name:
            for btn in buttons:
                if name.lower() in btn.name.lower():
                    return btn
            return None
        return buttons[0] if buttons else None
    
    async def find_input(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти поле ввода (по имени)"""
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
        """Найти ссылку (по имени)"""
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
    
    async def click_by_role(self, role: str, name: Optional[str] = None):
        """Кликнуть по элементу с ролью (и именем)"""
        nodes = await self.find_by_role(role)
        if name:
            for node in nodes:
                if name.lower() in node.name.lower():
                    await node.click()
                    return True
            raise Exception(f"Элемент {role} с именем '{name}' не найден")
        else:
            if nodes:
                await nodes[0].click()
                return True
            raise Exception(f"Элемент {role} не найден")
    
    async def type_by_name(self, name: str, text: str):
        """Ввести текст в поле по имени"""
        inputs = await self.find_by_name(name)
        for inp in inputs:
            if inp.role in ["textbox", "searchbox", "text", "textarea", "input"]:
                await inp.type(text)
                return True
        raise Exception(f"Поле ввода с именем '{name}' не найдено")
    
    async def print_tree(self, node_id: Optional[str] = None, level: int = 0):
        """Вывести Accessibility Tree в консоль (для отладки)"""
        if not node_id:
            root = await self.get_root_node()
            if not root:
                print("🌳 Accessibility Tree пуст")
                return
            node_id = root.node_id
        
        # Получаем все узлы и строим дерево
        nodes = await self.get_all_nodes()
        
        # Группируем по parent_id
        children_map = {}
        for node in nodes:
            parent_id = node.node_data.get("parentId")
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(node)
        
        # Рекурсивно выводим
        async def print_node(node, level):
            indent = "  " * level
            state = ""
            if not await node.is_enabled():
                state += " [disabled]"
            if not await node.is_visible():
                state += " [hidden]"
            print(f"{indent}📌 {node.role}: '{node.name}'{state}")
            
            for child in children_map.get(node.node_id, []):
                await print_node(child, level + 1)
        
        # Находим корень
        root = None
        for node in nodes:
            if node.role in ["RootWebArea", "WebArea", "document"]:
                root = node
                break
        
        if root:
            await print_node(root, level)
        else:
            print("🌳 Корневой узел не найден")


# Глобальный экземпляр
accessibility = Accessibility(cdp_client)