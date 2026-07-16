import logging
import json
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
        
        # Получаем DOM узел
        dom_result = await self.client.send_command("DOM.getNodeForLocation", {
            "x": 0,  # Будем искать по координатам
            "y": 0,
            "includeUserAgentShadowDOM": True
        })
        
        # Используем человеческий клик
        await self.client.human_click(f'[data-node-id="{self.backend_node_id}"]')
        logger.info(f"🖱️ Клик по {self.role}: {self.name}")
    
    async def type(self, text: str):
        """Ввод текста в поле"""
        if self.role not in ["textbox", "searchbox", "text", "textarea"]:
            raise Exception(f"Элемент {self.role} не поддерживает ввод текста")
        
        # Кликаем для фокуса
        await self.click()
        
        # Вводим текст
        await self.client.human_type(f'[data-node-id="{self.backend_node_id}"]', text)
        logger.info(f"⌨️ Ввод в {self.role}: {text}")
    
    async def get_text(self) -> str:
        """Получить текст элемента"""
        if not self.backend_node_id:
            return self.name
        
        # Пробуем получить текст через DOM
        try:
            result = await self.client.send_command("DOM.getOuterHTML", {
                "nodeId": self.backend_node_id
            })
            return result.get("outerHTML", self.name)
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
        
    async def enable(self):
        """Включить Accessibility"""
        await self.client.send_command("Accessibility.enable")
        logger.info("♿ Accessibility включен")
    
    async def disable(self):
        """Выключить Accessibility"""
        await self.client.send_command("Accessibility.disable")
        logger.info("♿ Accessibility выключен")
    
    async def get_root_node(self) -> Optional[AccessibilityNode]:
        """Получить корневой узел Accessibility Tree"""
        result = await self.client.send_command("Accessibility.getRootAXNode")
        if result and "node" in result:
            self.root_node = AccessibilityNode(result["node"], self.client)
            return self.root_node
        return None
    
    async def get_children(self, node_id: Optional[str] = None) -> List[AccessibilityNode]:
        """Получить дочерние узлы"""
        params = {}
        if node_id:
            params["nodeId"] = node_id
        
        result = await self.client.send_command("Accessibility.getChildAXNodes", params)
        nodes = result.get("nodes", [])
        return [AccessibilityNode(node, self.client) for node in nodes]
    
    async def find_by_role(self, role: str, node_id: Optional[str] = None) -> List[AccessibilityNode]:
        """Найти все элементы по роли (button, textbox, link и т.д.)"""
        result = []
        
        if not node_id:
            root = await self.get_root_node()
            if not root:
                return []
            node_id = root.node_id
        
        # Рекурсивно ищем
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
    
    async def find_button(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти кнопку (по имени)"""
        if name:
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
            inputs = await self.find_by_role(role)
            if name:
                for inp in inputs:
                    if name.lower() in inp.name.lower():
                        return inp
            else:
                if inputs:
                    return inputs[0]
        
        return None
    
    async def find_link(self, name: Optional[str] = None) -> Optional[AccessibilityNode]:
        """Найти ссылку (по имени)"""
        if name:
            links = await self.find_by_role("link")
            for link in links:
                if name.lower() in link.name.lower():
                    return link
            return None
        
        links = await self.find_by_role("link")
        return links[0] if links else None
    
    async def get_all_buttons(self) -> List[AccessibilityNode]:
        """Получить все кнопки"""
        return await self.find_by_role("button")
    
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