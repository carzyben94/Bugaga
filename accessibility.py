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
        self._enabled = False
    
    async def enable(self):
        """Включить Accessibility домен"""
        if not self._enabled:
            await self.browser.send("Accessibility.enable")
            self._enabled = True
            logger.info("♿ Accessibility включён")
    
    async def get_full_tree(self, depth: int = -1) -> dict:
        """Получить полное accessibility дерево страницы"""
        await self.enable()
        result = await self.browser.send("Accessibility.getFullAXTree", {
            "depth": depth
        })
        return result.get("nodes", [])
    
    async def get_root(self) -> dict:
        """Получить корневой узел"""
        await self.enable()
        nodes = await self.get_full_tree(depth=0)
        return nodes[0] if nodes else {}
    
    async def get_node_by_id(self, node_id: str) -> dict:
        """Получить узел по ID"""
        await self.enable()
        nodes = await self.get_full_tree()
        for node in nodes:
            if node.get("nodeId") == node_id:
                return node
        return {}
    
    async def get_node_by_selector(self, selector: str) -> dict:
        """Найти accessibility узел по CSS селектору"""
        await self.enable()
        dom_result = await self.browser.send("DOM.querySelector", {
            "selector": selector
        })
        node_id = dom_result.get("nodeId")
        if not node_id:
            return {}
        ax_result = await self.browser.send("Accessibility.getPartialAXTree", {
            "nodeId": node_id
        })
        nodes = ax_result.get("nodes", [])
        return nodes[0] if nodes else {}
    
    def _parse_node(self, node: dict) -> dict:
        """Преобразовать узел в удобный формат"""
        result = {
            "nodeId": node.get("nodeId"),
            "name": node.get("name", {}).get("value", "") if node.get("name") else "",
            "role": "",
            "ariaLabel": "",
            "description": "",
            "disabled": False,
            "children": []
        }
        
        role_obj = node.get("role")
        if role_obj and isinstance(role_obj, dict):
            result["role"] = role_obj.get("value", "")
        
        properties = node.get("properties", [])
        for prop in properties:
            prop_name = prop.get("name")
            prop_value_obj = prop.get("value", {})
            prop_value = prop_value_obj.get("value", "") if isinstance(prop_value_obj, dict) else ""
            
            if prop_name == "ariaLabel":
                result["ariaLabel"] = prop_value
            elif prop_name == "description":
                result["description"] = prop_value
            elif prop_name == "disabled":
                result["disabled"] = bool(prop_value)
        
        return result
    
    async def get_all_buttons(self) -> list:
        """Получить все кнопки"""
        await self.enable()
        nodes = await self.get_full_tree()
        buttons = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role == "button":
                buttons.append(self._parse_node(node))
        return buttons
    
    async def get_all_inputs(self) -> list:
        """Получить все поля ввода"""
        await self.enable()
        nodes = await self.get_full_tree()
        inputs = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role in ["textbox", "searchbox", "combobox"]:
                inputs.append(self._parse_node(node))
        return inputs
    
    async def get_all_links(self) -> list:
        """Получить все ссылки"""
        await self.enable()
        nodes = await self.get_full_tree()
        links = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role == "link":
                links.append(self._parse_node(node))
        return links
    
    async def get_all_headings(self) -> list:
        """Получить все заголовки"""
        await self.enable()
        nodes = await self.get_full_tree()
        headings = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role.startswith("heading"):
                headings.append(self._parse_node(node))
        return headings
    
    async def get_all_landmarks(self) -> list:
        """Получить все landmark элементы"""
        await self.enable()
        nodes = await self.get_full_tree()
        landmarks = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role in ["banner", "main", "contentinfo", "navigation", "complementary", "search"]:
                landmarks.append(self._parse_node(node))
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
        role_obj = node.get("role")
        return role_obj.get("value", "") if isinstance(role_obj, dict) else ""
    
    async def get_name(self, selector: str) -> str:
        """Получить доступное имя элемента"""
        node = await self.get_node_by_selector(selector)
        if not node:
            return ""
        return node.get("name", {}).get("value", "") if node.get("name") else ""
    
    async def get_description(self, selector: str) -> str:
        """Получить описание элемента"""
        node = await self.get_node_by_selector(selector)
        if not node:
            return ""
        properties = node.get("properties", [])
        for prop in properties:
            if prop.get("name") == "description":
                return prop.get("value", {}).get("value", "")
        return ""
    
    async def get_summary(self) -> dict:
        """Получить краткую сводку по accessibility tree (только полезные роли)"""
        await self.enable()
        nodes = await self.get_full_tree()
        
        # ===== ТОЛЬКО ПОЛЕЗНЫЕ РОЛИ =====
        USEFUL_ROLES = {
            "button", "link", "heading", "textbox", "searchbox", "combobox",
            "checkbox", "radio", "select", "listbox", "menuitem", "tab",
            "navigation", "main", "complementary", "contentinfo", "banner",
            "article", "section", "list", "listitem", "img", "image",
            "form", "search", "dialog", "alert", "status", "progressbar"
        }
        
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
            if node.get("ignored"):
                continue
                
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            
            if not role:
                continue
            
            # ===== ПРОПУСКАЕМ МУСОРНЫЕ РОЛИ =====
            if role not in USEFUL_ROLES:
                continue
            
            summary["roles"][role] = summary["roles"].get(role, 0) + 1
            
            if role == "button":
                summary["buttons"] += 1
            elif role in ["textbox", "searchbox", "combobox"]:
                summary["inputs"] += 1
            elif role.startswith("heading"):
                summary["headings"] += 1
            elif role == "link":
                summary["links"] += 1
            elif role in ["banner", "main", "contentinfo", "navigation", "complementary", "search"]:
                summary["landmarks"] += 1
            elif role in ["img", "image"]:
                summary["images"] += 1
            elif role == "list":
                summary["lists"] += 1
            elif role == "table":
                summary["tables"] += 1
        
        return summary
    
    async def find_by_role(self, role: str) -> list:
        """Найти все элементы с указанной ролью"""
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            node_role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if node_role == role:
                result.append(self._parse_node(node))
        return result
    
    async def find_by_name(self, name: str) -> list:
        """Найти элементы по имени (точное совпадение)"""
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            node_name = node.get("name", {}).get("value", "") if node.get("name") else ""
            if node_name == name:
                result.append(self._parse_node(node))
        return result
    
    async def find_by_name_contains(self, text: str) -> list:
        """Найти элементы по имени (частичное совпадение)"""
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            node_name = node.get("name", {}).get("value", "") if node.get("name") else ""
            if text.lower() in node_name.lower():
                result.append(self._parse_node(node))
        return result