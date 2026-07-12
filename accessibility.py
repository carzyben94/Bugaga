import asyncio
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


# ---------- UniversalElement ----------

@dataclass
class UniversalElement:
    """Универсальный элемент из Accessibility Tree"""
    role: str
    name: str
    description: str = ""
    states: Dict = field(default_factory=dict)
    ref: str = ""
    node_id: str = ""
    children: List = field(default_factory=list)
    
    def get_text(self) -> str:
        return self.name or self.description or self.role
    
    def is_interactive(self) -> bool:
        interactive_roles = ['button', 'link', 'textbox', 'combobox', 
                            'checkbox', 'radio', 'menuitem', 'tab', 
                            'searchbox', 'slider', 'spinbutton']
        return self.role in interactive_roles


# ---------- UniversalModel ----------

@dataclass
class UniversalModel:
    """Универсальная модель страницы с точной нумерацией"""
    
    title: str = ""
    url: str = ""
    total_elements: int = 0
    
    all_elements: List[UniversalElement] = field(default_factory=list)
    buttons: List[UniversalElement] = field(default_factory=list)
    links: List[UniversalElement] = field(default_factory=list)
    headings: List[UniversalElement] = field(default_factory=list)
    text_inputs: List[UniversalElement] = field(default_factory=list)
    images: List[UniversalElement] = field(default_factory=list)
    articles: List[UniversalElement] = field(default_factory=list)
    interactive: List[UniversalElement] = field(default_factory=list)
    
    TRANSLATIONS = {
        'обзор': ['explore', 'обзор', 'review'],
        'главная': ['home', 'главная', 'main'],
        'закладки': ['bookmarks', 'закладки'],
        'уведомления': ['notifications', 'уведомления'],
        'сообщения': ['messages', 'сообщения', 'direct'],
        'профиль': ['profile', 'профиль', 'account'],
        'поиск': ['search', 'поиск', 'find'],
        'чат': ['chat', 'чат', 'messages'],
        'лента': ['feed', 'лента', 'timeline'],
        'настройки': ['settings', 'настройки'],
    }
    
    @classmethod
    def from_ax_tree(cls, ax_tree: Dict) -> 'UniversalModel':
        """Создание модели из Accessibility Tree"""
        model = cls()
        
        model.title = ax_tree.get('title', '')
        model.url = ax_tree.get('url', '')
        
        elements = ax_tree.get('all_elements', [])
        model.total_elements = len(elements)
        
        for idx, el in enumerate(elements):
            element = UniversalElement(
                role=el.get('role', 'unknown'),
                name=el.get('name', ''),
                description=el.get('description', ''),
                states=el.get('states', {}),
                ref=f"@e{idx}",
                node_id=el.get('node_id', '')
            )
            
            model.all_elements.append(element)
            
            role = element.role
            if role == 'button':
                model.buttons.append(element)
            elif role == 'link':
                model.links.append(element)
            elif role in ['heading', 'heading1', 'heading2', 'heading3']:
                model.headings.append(element)
            elif role in ['textbox', 'searchbox', 'combobox']:
                model.text_inputs.append(element)
            elif role == 'image':
                model.images.append(element)
            elif role == 'article':
                model.articles.append(element)
            
            if element.is_interactive():
                model.interactive.append(element)
        
        return model
    
    def find_by_text(self, query: str) -> List[UniversalElement]:
        """Поиск по тексту (русский + английский)"""
        query_lower = query.lower()
        results = []
        
        search_terms = [query_lower]
        for ru, en_list in self.TRANSLATIONS.items():
            if query_lower in ru or query_lower in ' '.join(en_list):
                search_terms.extend(en_list)
                search_terms.append(ru)
        
        search_terms = list(set(search_terms))
        
        for el in self.all_elements:
            name_lower = el.name.lower()
            desc_lower = el.description.lower()
            
            for term in search_terms:
                if term in name_lower or term in desc_lower:
                    results.append(el)
                    break
        
        return results
    
    def find_button_by_text(self, query: str) -> Optional[UniversalElement]:
        results = self.find_by_text(query)
        buttons = [el for el in results if el.role == 'button']
        return buttons[0] if buttons else None
    
    def find_posts(self) -> List[UniversalElement]:
        return self.articles
    
    def find_post_by_text(self, query: str) -> List[UniversalElement]:
        query_lower = query.lower()
        return [el for el in self.articles if query_lower in el.name.lower()]
    
    def get_by_number(self, number: int) -> Optional[UniversalElement]:
        if 0 <= number < len(self.all_elements):
            return self.all_elements[number]
        return None
    
    def get_button_by_number(self, number: int) -> Optional[UniversalElement]:
        if 0 <= number < len(self.buttons):
            return self.buttons[number]
        return None
    
    def group_sort(self, elements: List[UniversalElement]) -> Dict[str, List[UniversalElement]]:
        groups = {
            'navigation': [],
            'actions': [],
            'content': [],
            'settings': [],
            'other': []
        }
        
        NAVIGATION = ['home', 'explore', 'notifications', 'messages', 'bookmarks', 
                      'profile', 'grok', 'чат', 'лента', 'обзор', 'главная',
                      'уведомления', 'сообщения', 'закладки', 'профиль']
        
        ACTIONS = ['post', 'reply', 'like', 'retweet', 'share', 'send', 'publish',
                   'опубликовать', 'ответить', 'отправить', 'лайк', 'репост']
        
        SETTINGS = ['settings', 'privacy', 'security', 'help', 'about',
                    'настройки', 'конфиденциальность', 'помощь']
        
        CONTENT = ['article', 'post', 'tweet', 'читат', 'читать', 'новости']
        
        for el in elements:
            name_lower = el.name.lower()
            
            if any(word in name_lower for word in NAVIGATION):
                groups['navigation'].append(el)
            elif any(word in name_lower for word in ACTIONS):
                groups['actions'].append(el)
            elif any(word in name_lower for word in SETTINGS):
                groups['settings'].append(el)
            elif any(word in name_lower for word in CONTENT) or el.role == 'article':
                groups['content'].append(el)
            else:
                groups['other'].append(el)
        
        return groups
    
    def format_with_groups(self, max_items: int = 10) -> str:
        if not self.buttons:
            return "❌ Кнопки не найдены"
        
        groups = self.group_sort(self.buttons)
        
        group_names = {
            'navigation': '🧭 НАВИГАЦИЯ',
            'actions': '⚡ ДЕЙСТВИЯ',
            'content': '📄 КОНТЕНТ',
            'settings': '⚙️ НАСТРОЙКИ',
            'other': '📦 ОСТАЛЬНОЕ'
        }
        
        result = []
        result.append(f"📄 СТРАНИЦА: {self.title}")
        result.append(f"🔗 URL: {self.url}")
        result.append(f"🔘 ВСЕГО КНОПОК: {len(self.buttons)}")
        result.append("")
        
        for group_key, group_name in group_names.items():
            items = groups.get(group_key, [])
            if items:
                result.append(f"{group_name} ({len(items)}):")
                for i, item in enumerate(items[:max_items], 1):
                    state = "✅" if item.states.get('enabled', True) else "🔒"
                    result.append(f"  {i}. {state} [{item.ref}] {item.name}")
                if len(items) > max_items:
                    result.append(f"  ... и ещё {len(items) - max_items}")
                result.append("")
        
        if self.text_inputs:
            result.append(f"📝 ПОЛЯ ВВОДА ({len(self.text_inputs)}):")
            for i, inp in enumerate(self.text_inputs[:5], 1):
                result.append(f"  {i}. [{inp.ref}] {inp.name}")
            if len(self.text_inputs) > 5:
                result.append(f"  ... и ещё {len(self.text_inputs) - 5}")
            result.append("")
        
        if self.articles:
            result.append(f"📰 ПОСТЫ ({len(self.articles)}):")
            for i, article in enumerate(self.articles[:5], 1):
                result.append(f"  {i}. [{article.ref}] {article.name[:80]}...")
            if len(self.articles) > 5:
                result.append(f"  ... и ещё {len(self.articles) - 5}")
        
        return "\n".join(result)
    
    def format_posts(self, posts: List[UniversalElement], limit: int = 5) -> str:
        if not posts:
            return "❌ Посты не найдены"
        
        result = f"📰 Найдено {len(posts)} постов:\n\n"
        
        for i, post in enumerate(posts[:limit], 1):
            text = post.name or post.description or 'Без текста'
            ref = post.ref
            result += f"{i}. {text[:150]}\n"
            result += f"   🔗 [{ref}]\n\n"
        
        if len(posts) > limit:
            result += f"... и ещё {len(posts) - limit} постов"
        
        return result
    
    def to_text(self, max_items: int = 20) -> str:
        result = []
        
        result.append(f"📄 СТРАНИЦА: {self.title}")
        result.append(f"🔗 URL: {self.url}")
        result.append(f"📊 ВСЕГО ЭЛЕМЕНТОВ: {self.total_elements}")
        result.append("")
        
        if self.buttons:
            result.append(f"🔘 КНОПКИ ({len(self.buttons)}):")
            for i, btn in enumerate(self.buttons[:max_items], 1):
                state = "✅" if btn.states.get('enabled', True) else "🔒"
                result.append(f"  {i}. {state} [{btn.ref}] {btn.name}")
            if len(self.buttons) > max_items:
                result.append(f"  ... и ещё {len(self.buttons) - max_items} кнопок")
        result.append("")
        
        if self.text_inputs:
            result.append(f"📝 ПОЛЯ ВВОДА ({len(self.text_inputs)}):")
            for i, inp in enumerate(self.text_inputs[:max_items], 1):
                result.append(f"  {i}. [{inp.ref}] {inp.name}")
            if len(self.text_inputs) > max_items:
                result.append(f"  ... и ещё {len(self.text_inputs) - max_items} полей")
        result.append("")
        
        if self.articles:
            result.append(f"📰 ПОСТЫ ({len(self.articles)}):")
            for i, article in enumerate(self.articles[:max_items], 1):
                result.append(f"  {i}. [{article.ref}] {article.name[:80]}...")
            if len(self.articles) > max_items:
                result.append(f"  ... и ещё {len(self.articles) - max_items} постов")
        
        return "\n".join(result)


# ---------- Функции для работы с Accessibility Tree ----------

async def get_accessibility_snapshot(client) -> Dict:
    """Получение Accessibility Tree через CDP"""
    try:
        resp = await client.send_safe("Accessibility.getFullAXTree", {
            "depth": -1
        })
        
        if "error" in resp:
            return {"error": resp.get('error')}
        
        nodes = resp.get("result", {}).get("nodes", [])
        
        if not nodes:
            return {"error": "Пустое дерево доступности"}
        
        elements = []
        buttons = []
        fields = []
        
        for idx, node in enumerate(nodes):
            role_obj = node.get("role", {})
            role = role_obj.get("value", "unknown") if isinstance(role_obj, dict) else "unknown"
            
            name_obj = node.get("name", {})
            name = name_obj.get("value", "") if isinstance(name_obj, dict) else ""
            
            desc_obj = node.get("description", {})
            description = desc_obj.get("value", "") if isinstance(desc_obj, dict) else ""
            
            node_id = node.get("nodeId")
            
            states = {}
            for prop in node.get("properties", []):
                prop_name = prop.get("name", "")
                prop_value_obj = prop.get("value", {})
                prop_value = prop_value_obj.get("value", "") if isinstance(prop_value_obj, dict) else ""
                states[prop_name] = prop_value
            
            interactive_roles = ['button', 'link', 'textbox', 'combobox', 
                                 'checkbox', 'radio', 'menuitem', 'tab', 
                                 'searchbox', 'slider', 'spinbutton']
            
            is_interactive = role in interactive_roles
            is_button = role == 'button' or (role == 'link' and is_interactive)
            
            element = {
                "role": role,
                "name": name,
                "description": description,
                "states": states,
                "node_id": node_id,
                "is_interactive": is_interactive,
                "ref": f"@e{idx}"
            }
            
            elements.append(element)
            
            if is_button:
                buttons.append(element)
            elif role in ['textbox', 'combobox', 'searchbox']:
                fields.append(element)
        
        return {
            "all_elements": elements,
            "buttons": buttons,
            "fields": fields,
            "total": len(elements)
        }
        
    except Exception as e:
        return {"error": str(e)}