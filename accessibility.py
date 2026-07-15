import logging
logger = logging.getLogger(__name__)

class Accessibility:
    def __init__(self, browser):
        self.browser = browser
        self._enabled = False

    async def enable(self):
        if not self._enabled:
            await self.browser.send("Accessibility.enable")
            self._enabled = True

    async def get_full_tree(self, depth=-1):
        await self.enable()
        result = await self.browser.send("Accessibility.getFullAXTree", {"depth": depth})
        return result.get("nodes", [])

    async def get_summary(self):
        await self.enable()
        nodes = await self.get_full_tree()

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
            if not role or role not in USEFUL_ROLES:
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

    async def get_all_buttons(self):
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role == "button":
                result.append({
                    "name": node.get("name", {}).get("value", ""),
                    "role": role
                })
        return result

    async def get_all_inputs(self):
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role in ["textbox", "searchbox", "combobox"]:
                result.append({
                    "name": node.get("name", {}).get("value", ""),
                    "role": role
                })
        return result

    async def get_all_links(self):
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role == "link":
                result.append({
                    "name": node.get("name", {}).get("value", ""),
                    "role": role
                })
        return result

    async def get_all_headings(self):
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role.startswith("heading"):
                result.append({
                    "name": node.get("name", {}).get("value", ""),
                    "role": role
                })
        return result

    async def get_all_landmarks(self):
        await self.enable()
        nodes = await self.get_full_tree()
        result = []
        for node in nodes:
            if node.get("ignored"):
                continue
            role_obj = node.get("role")
            role = role_obj.get("value", "") if isinstance(role_obj, dict) else ""
            if role in ["banner", "main", "contentinfo", "navigation", "complementary", "search"]:
                result.append({
                    "name": node.get("name", {}).get("value", ""),
                    "role": role
                })
        return result