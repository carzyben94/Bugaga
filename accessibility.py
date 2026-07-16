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
        if not self.backend_node_id:
            raise Exception("Нет backend DOM node ID")
        
        # Используем человеческий клик через селектор
        try:
            # Пробуем найти элемент через XPath по имени
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
        
        # Если не нашли по тексту, пробуем через Accessibility
        try:
            # Получаем DOM узел по backend node id
            dom_result = await self.client.send_command("DOM.getNodeForLocation", {
                "x": 100,
                "y": 100
            })
            
            # Ищем все элементы и кликаем по первому подходящему
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
        if self.role not in ["textbox", "searchbox", "text", "textarea"]:
            raise Exception(f"Элемент {self.role} не поддерживает ввод текста")
        
        # Кликаем для фокуса
        await self.click()
        
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
        
    async def enable(self):
        """Включить Accessibility (CDP: Accessibility.enable)"""
        try:
            # Включаем Accessibility
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
    
    async def get_root_node(self) -> Optional[AccessibilityNode]:
        """
        Получить корневой узел Accessibility Tree
        CDP: Accessibility.getRootAXNode
        """
        try:
            if not await self.ensure_enabled():
                return None
            
            # Ждем загрузки страницы
            await asyncio.sleep(1)
            
            result = await self.client.send_command("Accessibility.getRootAXNode")
            if result and "node" in result:
                self.root_node = AccessibilityNode(result["node"], self.client)
                return self.root_node
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения корневого узла: {e}")
            return None
    
    async def get_full_tree(self) -> List[AccessibilityNode]:
        """
        Получить всё дерево Accessibility
        CDP: Accessibility.getFullAXTree
        """
        try:
            if not await self.ensure_enabled():
                return []
            
            result = await self.client.send_command("Accessibility.getFullAXTree")
            nodes = result.get("nodes", [])
            return [AccessibilityNode(node, self.client) for node in nodes]
        except Exception as e:
            logger.error(f"❌ Ошибка получения полного дерева: {e}")
            return []
    
    async def query_by_name_role(self, name: str, role: Optional[str] = None) -> List[AccessibilityNode]:
        """
        Быстрый поиск по имени и роли
        CDP: Accessibility.queryAXTree
        """
        try:
            if not await self.ensure_enabled():
                return []
            
            params = {"accessibleName": name}
            if role:
                params["role"] = role
            
            result = await self.client.send_command("Accessibility.queryAXTree", params)
            nodes = result.get("nodes", [])
            return [AccessibilityNode(node, self.client) for node in nodes]
        except Exception as e:
            logger.error(f"❌ Ошибка queryAXTree: {e}")
            return []
    
    async def get_children(self, node_id: Optional[str] = None) -> List[AccessibilityNode]:
        """
        Получить дочерние узлы
        CDP: Accessibility.getChildAXNodes
        """
        try:
            params = {}
            if node_id:
                params["nodeId"] = node_id
            
            result = await self.client.send_command("Accessibility.getChildAXNodes", params)
            nodes = result.get("nodes", [])
            return [AccessibilityNode(node, self.client) for node in nodes]
        except Exception as e:
            logger.error(f"❌ Ошибка получения дочерних узлов: {e}")
            return []
    
    async def find_by_role(self, role: str, node_id: Optional[str] = None) -> List[AccessibilityNode]:
        """Найти все элементы по роли (button, textbox, link и т.д.)"""
        result = []
        
        # Сначала пробуем через queryAXTree
        if not node_id:
            try:
                # queryAXTree не поддерживает поиск только по роли
                # поэтому используем рекурсивный обход
                pass
            except:
                pass
        
        if not node_id:
            root = await self.get_root_node()
            if not root:
                return []
            node_id = root.node_id
        
        await self._find_by_role_recursive(role, node_id, result)
        return result
    
    async def _find_by_role_recursive(self, role: str, node_id: str, result: List[AccessibilityNode]):
        """Рекурсивный поиск по роли"""
        children = await self.get_children(node_id)
        
        for child in children:
            if child.role.lower() == role.lower():
                result.append(child)
            
            # Рекурсивно ищем в дочерних
            await self._find_by_role_recursive(role, child.node_id, result)
    
    async def find_by_name(self, name: str, node_id: Optional[str] = None) -> List[AccessibilityNode]:
        """Найти элементы по имени"""
        result = []
        
        if not node_id:
            root = await self.get_root_node()
            if not root:
                return []
            node_id = root.node_id
        
        await self._find_by_name_recursive(name, node_id, result)
        return result
    
    async def _find_by_name_recursive(self, name: str, node_id: str, result: List[AccessibilityNode]):
        """Рекурсивный поиск по имени"""
        children = await self.get_children(node_id)
        
        for child in children:
            if name.lower() in child.name.lower():
                result.append(child)
            
            await self._find_by_name_recursive(name, child.node_id, result)
    
    async def find_by_text(self, text: str) -> List[AccessibilityNode]:
        """Найти элементы по тексту (через JS)"""
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
                            role: el.getAttribute('role') || el.tagName
                        }});
                    }}
                }}
                return elements.slice(0, 20);
            }})()
            """
            result = await self.client.execute_script(js_code)
            
            # Превращаем в AccessibilityNode
            nodes = []
            for item in result:
                node = AccessibilityNode({
                    "nodeId": f"js_{len(nodes)}",
                    "role": {"value": item.get("role", "unknown")},
                    "name": {"value": item.get("text", "")},
                    "backendDOMNodeId": None
                }, self.client)
                nodes.append(node)
            
            return nodes
        except Exception as e:
            logger.error(f"❌ Ошибка поиска по тексту: {e}")
            return []
    
    async def find_button(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти кнопку (по имени)"""
        if name:
            # Сначала пробуем через queryAXTree (быстро)
            buttons = await self.query_by_name_role(name, "button")
            if buttons:
                return buttons[0]
            
            # Потом через JS
            buttons = await self.find_by_text(name)
            for btn in buttons:
                if "button" in btn.role.lower() or "button" in btn.name.lower():
                    return btn
            
            # Потом через Accessibility
            buttons = await self.find_by_role("button")
            for btn in buttons:
                if name.lower() in btn.name.lower():
                    return btn
            return None
        
        buttons = await self.find_by_role("button")
        return buttons[0] if buttons else None
    
    async def find_input(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти поле ввода (по имени)"""
        roles = ["textbox", "searchbox", "text", "textarea"]
        
        for role in roles:
            if name:
                inputs = await self.query_by_name_role(name, role)
                if inputs:
                    return inputs[0]
            
            inputs = await self.find_by_role(role)
            if name:
                for inp in inputs:
                    if name.lower() in inp.name.lower():
                        return inp
            else:
                if inputs:
                    return inputs[0]
        
        # Если не нашли через Accessibility, ищем через JS
        if name:
            inputs = await self.find_by_text(name)
            for inp in inputs:
                if "input" in inp.role.lower() or "text" in inp.role.lower():
                    return inp
        
        return None
    
    async def find_link(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти ссылку (по имени)"""
        if name:
            links = await self.query_by_name_role(name, "link")
            if links:
                return links[0]
            
            links = await self.find_by_role("link")
            for link in links:
                if name.lower() in link.name.lower():
                    return link
            return None
        
        links = await self.find_by_role("link")
        return links[0] if links else None
    
    async def get_all_buttons(self) -> List[AccessibilityNode]:
        """Получить все кнопки"""
        # Сначала через Accessibility
        buttons = await self.find_by_role("button")
        
        # Если мало, добавляем через JS
        if len(buttons) < 3:
            js_buttons = await self.find_by_text("")
            for btn in js_buttons:
                if "button" in btn.role.lower() and btn not in buttons:
                    buttons.append(btn)
        
        return buttons
    
    async def get_all_inputs(self) -> List[AccessibilityNode]:
        """Получить все поля ввода"""
        roles = ["textbox", "searchbox", "text", "textarea"]
        result = []
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
        if name:
            nodes = await self.query_by_name_role(name, role)
            if nodes:
                await nodes[0].click()
                return True
            
            nodes = await self.find_by_name(name)
            for node in nodes:
                if node.role.lower() == role.lower():
                    await node.click()
                    return True
            raise Exception(f"Элемент {role} с именем '{name}' не найден")
        else:
            nodes = await self.find_by_role(role)
            if nodes:
                await nodes[0].click()
                return True
            raise Exception(f"Элемент {role} не найден")
    
    async def type_by_name(self, name: str, text: str):
        """Ввести текст в поле по имени"""
        inputs = await self.find_by_name(name)
        for inp in inputs:
            if inp.role in ["textbox", "searchbox", "text", "textarea"]:
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
        
        children = await self.get_children(node_id)
        
        for child in children:
            indent = "  " * level
            state = ""
            if not await child.is_enabled():
                state += " [disabled]"
            if not await child.is_visible():
                state += " [hidden]"
            
            print(f"{indent}📌 {child.role}: '{child.name}'{state}")
            await self.print_tree(child.node_id, level + 1)


# Глобальный экземпляр
accessibility = Accessibility(cdp_client)