import logging
import json

logger = logging.getLogger(__name__)


class Accessibility:
    """
    Работа с Accessibility Tree через CDP.
    Позволяет получить семантическую структуру страницы.
    """
    
    def __init__(self, browser):
        self.browser = browser
    
    async def get_full_tree(self, depth: int = -1) -> dict:
        """
        Получить полное accessibility дерево страницы.
        
        Args:
            depth: глубина дерева (-1 = всё)
        
        Returns:
            Словарь с accessibility деревом
        """
        result = await self.browser.send("Accessibility.getFullAXTree", {
            "depth": depth
        })
        return result.get("nodes", [])
    
    async def get_root(self) -> dict:
        """Получить корневой узел accessibility дерева"""
        nodes = await self.get_full_tree(depth=0)
        return nodes[0] if nodes else {}
    
    async def get_node_by_id(self, node_id: str) -> dict:
        """Получить узел по ID"""
        nodes = await self.get_full_tree()
        for node in nodes:
            if node.get("nodeId") == node_id:
                return node
        return {}
    
    async def get_node_by_selector(self, selector: str) -> dict:
        """
        Найти accessibility узел по CSS селектору.
        Сначала ищем DOM элемент, потом его accessibility узел.
        """
        # Ищем DOM элемент
        dom_result = await self.browser.send("DOM.querySelector", {
            "selector": selector
        })
        node_id = dom_result.get("nodeId")
        
        if not node_id:
            return {}
        
        # Получаем accessibility узел для DOM элемента
        ax_result = await self.browser.send("Accessibility.getPartialAXTree", {
            "nodeId": node_id
        })
        
        nodes = ax_result.get("nodes", [])
        return nodes[0] if nodes else {}
    
    async def get_all_buttons(self) -> list:
        """Получить все кнопки из accessibility tree"""
        nodes = await self.get_full_tree()
        buttons = []
        
        for node in nodes:
            properties = node.get("properties", [])
            for prop in properties:
                if prop.get("name") == "role" and prop.get("value", {}).get("value") in ["button", "link"]:
                    buttons.append(self._parse_node(node))
                    break
        
        return buttons
    
    async def get_all_inputs(self) -> list:
        """Получить все поля ввода из accessibility tree"""
        nodes = await self.get_full_tree()
        inputs = []
        
        for node in nodes:
            properties = node.get("properties", [])
            for prop in properties:
                if prop.get("name") == "role" and prop.get("value", {}).get("value") in ["textbox", "searchbox", "combobox"]:
                    inputs.append(self._parse_node(node))
                    break
        
        return inputs
    
    async def get_all_headings(self) -> list:
        """Получить все заголовки (h1-h6) из accessibility tree"""
        nodes = await self.get_full_tree()
        headings = []
        
        for node in nodes:
            properties = node.get("properties", [])
            for prop in properties:
                if prop.get("name") == "role" and prop.get("value", {}).get("value", "").startswith("heading"):
                    headings.append(self._parse_node(node))
                    break
        
        return headings
    
    async def get_all_links(self) -> list:
        """Получить все ссылки из accessibility tree"""
        nodes = await self.get_full_tree()
        links = []
        
        for node in nodes:
            properties = node.get("properties", [])
            for prop in properties:
                if prop.get("name") == "role" and prop.get("value", {}).get("value") == "link":
                    links.append(self._parse_node(node))
                    break
        
        return links
    
    async def get_all_landmarks(self) -> list:
        """Получить все landmark элементы (header, main, footer, nav, aside)"""
        nodes = await self.get_full_tree()
        landmarks = []
        
        for node in nodes:
            properties = node.get("properties", [])
            for prop in properties:
                if prop.get("name") == "role" and prop.get("value", {}).get("value") in [
                    "banner", "main", "contentinfo", "navigation", "complementary", "search"
                ]:
                    landmarks.append(self._parse_node(node))
                    break
        
        return landmarks
    
    async def get_aria_label(self, selector: str) -> str:
        """Получить aria-label элемента"""
        node = await self.get_node_by_selector(selector)
        if not node:
            return ""
        
        properties = node.get("properties", [])
        for prop in properties:
            if prop.get("name") == "ariaLabel":
                return prop.get("value", {}).get("value", "")
        
        return ""
    
    async def get_aria_role(self, selector: str) -> str:
        """Получить aria-role элемента"""
        node = await self.get_node_by_selector(selector)
        if not node:
            return ""
        
        properties = node.get("properties", [])
        for prop in properties:
            if prop.get("name") == "role":
                return prop.get("value", {}).get("value", "")
        
        return ""
    
    async def get_name(self, selector: str) -> str:
        """Получить доступное имя элемента (из accessibility tree)"""
        node = await self.get_node_by_selector(selector)
        if not node:
            return ""
        
        return node.get("name", {}).get("value", "")
    
    async def get_description(self, selector: str) -> str:
        """Получить описание элемента из accessibility tree"""
        node = await self.get_node_by_selector(selector)
        if not node:
            return ""
        
        properties = node.get("properties", [])
        for prop in properties:
            if prop.get("name") == "description":
                return prop.get("value", {}).get("value", "")
        
        return ""
    
    def _parse_node(self, node: dict) -> dict:
        """Преобразовать узел accessibility tree в удобный формат"""
        result = {
            "nodeId": node.get("nodeId"),
            "name": node.get("name", {}).get("value", ""),
            "role": "",
            "ariaLabel": "",
            "description": "",
            "children": []
        }
        
        properties = node.get("properties", [])
        for prop in properties:
            prop_name = prop.get("name")
            prop_value = prop.get("value", {}).get("value", "")
            
            if prop_name == "role":
                result["role"] = prop_value
            elif prop_name == "ariaLabel":
                result["ariaLabel"] = prop_value
            elif prop_name == "description":
                result["description"] = prop_value
        
        return result
    
    async def get_summary(self) -> dict:
        """Получить краткую сводку по accessibility tree"""
        nodes = await self.get_full_tree()
        
        summary = {
            "total_nodes": len(nodes),
            "buttons": 0,
            "inputs": 0,
            "links": 0,
            "headings": 0,
            "landmarks": 0,
            "images": 0,
            "lists": 0,
            "tables": 0,
            "roles": {}
        }
        
        for node in nodes:
            properties = node.get("properties", [])
            role = ""
            for prop in properties:
                if prop.get("name") == "role":
                    role = prop.get("value", {}).get("value", "")
                    break
            
            if role:
                summary["roles"][role] = summary["roles"].get(role, 0) + 1
                
                if role in ["button", "link"]:
                    summary["buttons"] += 1
                elif role in ["textbox", "searchbox", "combobox"]:
                    summary["inputs"] += 1
                elif role.startswith("heading"):
                    summary["headings"] += 1
                elif role in ["banner", "main", "contentinfo", "navigation", "complementary"]:
                    summary["landmarks"] += 1
                elif role == "img":
                    summary["images"] += 1
                elif role == "list":
                    summary["lists"] += 1
                elif role == "table":
                    summary["tables"] += 1
        
        return summary
    
    async def find_by_role(self, role: str) -> list:
        """Найти все элементы с указанной ролью"""
        nodes = await self.get_full_tree()
        result = []
        
        for node in nodes:
            properties = node.get("properties", [])
            for prop in properties:
                if prop.get("name") == "role" and prop.get("value", {}).get("value") == role:
                    result.append(self._parse_node(node))
                    break
        
        return result
    
    async def find_by_name(self, name: str) -> list:
        """Найти элементы по имени (точное совпадение)"""
        nodes = await self.get_full_tree()
        result = []
        
        for node in nodes:
            node_name = node.get("name", {}).get("value", "")
            if node_name == name:
                result.append(self._parse_node(node))
        
        return result
    
    async def find_by_name_contains(self, text: str) -> list:
        """Найти элементы по имени (частичное совпадение)"""
        nodes = await self.get_full_tree()
        result = []
        
        for node in nodes:
            node_name = node.get("name", {}).get("value", "")
            if text.lower() in node_name.lower():
                result.append(self._parse_node(node))
        
        return result
    
    async def get_node_children(self, node_id: str) -> list:
        """Получить дочерние узлы"""
        nodes = await self.get_full_tree()
        for node in nodes:
            if node.get("nodeId") == node_id:
                children = []
                for child_id in node.get("childIds", []):
                    for child in nodes:
                        if child.get("nodeId") == child_id:
                            children.append(self._parse_node(child))
                            break
                return children
        return []