import logging
import json
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class Accessibility:
    def __init__(self, browser, eval_obj):
        self.browser = browser
        self.eval = eval_obj
        self._ref_cache = []  # Кеш рефов для быстрого поиска

    async def get_accessibility_tree(self, compact: bool = True) -> Dict:
        """Получить дерево доступности страницы через CDP"""
        try:
            result = await self.browser.send("Accessibility.getFullAXTree")
            if compact:
                result = self._compact_tree(result)
            return result
        except Exception as e:
            logger.error(f"Ошибка получения дерева доступности: {e}")
            return {"nodes": []}
    
    def _compact_tree(self, tree: Dict) -> Dict:
        """Компактизация дерева доступности"""
        if not tree or 'nodes' not in tree:
            return tree
        
        compact_nodes = []
        for node in tree.get('nodes', []):
            if self._is_interactive(node):
                compact_nodes.append(node)
        
        return {"nodes": compact_nodes}
    
    def _is_interactive(self, node: Dict) -> bool:
        """Проверяет, является ли узел интерактивным"""
        roles = node.get('role', {}).get('value', '').lower()
        interactive_roles = ['button', 'link', 'textbox', 'checkbox', 'radio', 
                           'menuitem', 'tab', 'combobox', 'searchbox', 'spinbutton',
                           'slider', 'switch', 'listbox', 'treeitem', 'option']
        return any(role in roles for role in interactive_roles)

    async def get_elements_with_refs(self) -> List[Dict]:
        """Получить интерактивные элементы с рефами [E1], [E2]..."""
        result = await self.browser.send("Accessibility.getFullAXTree")
        elements = []
        ref_counter = 1
        self._ref_cache = []  # Очищаем кеш
        
        for node in result.get('nodes', []):
            role = node.get('role', {}).get('value', 'unknown').lower()
            name = node.get('name', {}).get('value', '')
            
            interactive_roles = ['button', 'link', 'textbox', 'checkbox', 'radio', 
                               'menuitem', 'tab', 'combobox', 'searchbox', 'spinbutton',
                               'slider', 'switch', 'listbox', 'treeitem', 'option']
            
            if any(role in r for r in interactive_roles):
                ref = f"[E{ref_counter}]"
                element = {
                    'ref': ref,
                    'role': role,
                    'name': name[:100] if name else '',
                    'description': node.get('description', {}).get('value', ''),
                    'nodeId': node.get('nodeId')  # Сохраняем nodeId для клика
                }
                elements.append(element)
                self._ref_cache.append({
                    'ref': ref,
                    'nodeId': node.get('nodeId')
                })
                ref_counter += 1
        
        return elements

    async def click_by_ref(self, ref: str) -> bool:
        """Клик по элементу через CDP (как в Hermes)"""
        try:
            # Ищем nodeId по рефу
            target = next((item for item in self._ref_cache if item['ref'] == ref), None)
            
            # Если нет в кеше, перезапрашиваем элементы
            if not target:
                await self.get_elements_with_refs()
                target = next((item for item in self._ref_cache if item['ref'] == ref), None)
            
            if not target:
                logger.warning(f"Элемент {ref} не найден в Accessibility Tree")
                return False
            
            node_id = target.get('nodeId')
            if not node_id:
                logger.warning(f"Нет nodeId для {ref}")
                return False
            
            # 1. Получаем объект по nodeId
            obj_result = await self.browser.send("DOM.resolveNode", {
                "nodeId": node_id
            })
            
            object_id = obj_result.get('object', {}).get('objectId')
            if not object_id:
                logger.warning(f"Нет objectId для nodeId {node_id}")
                return False
            
            # 2. Кликаем через Runtime.callFunctionOn
            await self.browser.send("Runtime.callFunctionOn", {
                "functionDeclaration": "function() { this.click(); this.style.border = '3px solid red'; }",
                "objectId": object_id
            })
            
            logger.info(f"✅ Клик по {ref} выполнен через CDP")
            return True
            
        except Exception as e:
            logger.error(f"CDP клик ошибка для {ref}: {e}")
            return False

    async def check_heading_hierarchy(self) -> Dict:
        """Проверить иерархию заголовков"""
        return await self.eval.execute("""
            (function() {
                const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
                const result = {
                    total: headings.length,
                    hierarchy: [],
                    issues: []
                };
                
                headings.forEach((h, index) => {
                    const level = parseInt(h.tagName[1]);
                    result.hierarchy.push({
                        level: level,
                        text: h.innerText.trim().substring(0, 50)
                    });
                    
                    if (index > 0) {
                        const prev_level = parseInt(headings[index-1].tagName[1]);
                        if (level - prev_level > 1) {
                            result.issues.push({
                                type: 'missing_level',
                                message: `Пропущен h${prev_level+1} → h${level}`
                            });
                        }
                    }
                });
                
                return result;
            })()
        """)

    async def check_images_alt(self) -> Dict:
        """Проверить наличие alt у изображений"""
        return await self.eval.execute("""
            (function() {
                const images = document.querySelectorAll('img');
                const issues = [];
                let passed = 0, failed = 0;
                
                images.forEach(img => {
                    const alt = img.getAttribute('alt');
                    const src = img.getAttribute('src') || 'без src';
                    
                    if (!alt || alt.trim() === '') {
                        failed++;
                        issues.push({ type: 'missing_alt', src: src });
                    } else if (alt.length > 100) {
                        failed++;
                        issues.push({ type: 'long_alt', src: src, alt: alt });
                    } else {
                        passed++;
                    }
                });
                
                return { total: images.length, passed, failed, issues };
            })()
        """)

    async def check_aria_labels(self) -> Dict:
        """Проверить наличие aria-label у интерактивных элементов"""
        return await self.eval.execute("""
            (function() {
                const elements = document.querySelectorAll('[role], button, a, input, textarea, select');
                const issues = [];
                let total = 0, has_aria = 0;
                
                elements.forEach(el => {
                    total++;
                    const aria = el.getAttribute('aria-label');
                    const label = el.getAttribute('aria-labelledby');
                    if (aria || label) {
                        has_aria++;
                    } else {
                        const text = el.innerText || el.value || '';
                        if (!text.trim() && !el.getAttribute('aria-hidden')) {
                            issues.push({
                                tag: el.tagName,
                                type: 'missing_aria_label'
                            });
                        }
                    }
                });
                
                return { total, has_aria, issues };
            })()
        """)

    async def check_color_contrast(self) -> Dict:
        """Проверить контрастность текста"""
        return await self.eval.execute("""
            (function() {
                const elements = document.querySelectorAll('*');
                const issues = [];
                
                elements.forEach(el => {
                    const style = getComputedStyle(el);
                    const color = style.color;
                    const bg = style.backgroundColor;
                    
                    if (color && bg && color !== 'rgba(0, 0, 0, 0)') {
                        const colorMatch = color === bg;
                        if (colorMatch) {
                            issues.push({
                                element: el.tagName,
                                text: el.innerText?.substring(0, 20),
                                color: color,
                                bg: bg
                            });
                        }
                    }
                });
                
                return { total: elements.length, issues: issues.slice(0, 20) };
            })()
        """)