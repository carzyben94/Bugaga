import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class SiteMap:
    """
    Хранилище карт сайтов для AI агента.
    Сохраняет структуру страниц в JSON файл.
    """
    
    def __init__(self, storage_file: str = "site_map.json"):
        self.storage_file = storage_file
        self.data = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Загрузить данные из файла"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки site_map: {e}")
                return {}
        return {}
    
    def _save(self):
        """Сохранить данные в файл"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Карта сайта сохранена в {self.storage_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения site_map: {e}")
    
    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """Получить карту сайта по URL"""
        url = self._normalize_url(url)
        return self.data.get(url)
    
    def save_map(self, url: str, structure: Dict[str, Any]):
        """Сохранить или обновить карту сайта"""
        url = self._normalize_url(url)
        
        if url not in self.data:
            self.data[url] = {}
        
        self.data[url].update({
            "last_updated": datetime.now().isoformat(),
            "structure": structure.get("structure", {}),
            "statistics": structure.get("statistics", {}),
            "selectors": structure.get("selectors", {}),
            "title": structure.get("title", ""),
            "url": url,
            "zones_count": structure.get("zones_count", 0),
            "total_elements": structure.get("total_elements", 0)
        })
        
        self._save()
        logger.info(f"🗺️ Карта сайта обновлена: {url}")
    
    def update_selectors(self, url: str, selectors: Dict[str, str]):
        """Обновить селекторы для сайта"""
        url = self._normalize_url(url)
        if url in self.data:
            self.data[url]["selectors"] = selectors
            self._save()
    
    def get_selectors(self, url: str) -> Dict[str, str]:
        """Получить селекторы для сайта"""
        url = self._normalize_url(url)
        if url in self.data:
            return self.data[url].get("selectors", {})
        return {}
    
    def get_statistics(self, url: str) -> Dict[str, Any]:
        """Получить статистику сайта"""
        url = self._normalize_url(url)
        if url in self.data:
            return self.data[url].get("statistics", {})
        return {}
    
    def get_structure(self, url: str) -> Dict[str, Any]:
        """Получить структуру сайта"""
        url = self._normalize_url(url)
        if url in self.data:
            return self.data[url].get("structure", {})
        return {}
    
    def get_title(self, url: str) -> str:
        """Получить заголовок сайта"""
        url = self._normalize_url(url)
        if url in self.data:
            return self.data[url].get("title", "")
        return ""
    
    def get_last_updated(self, url: str) -> str:
        """Получить время последнего обновления"""
        url = self._normalize_url(url)
        if url in self.data:
            return self.data[url].get("last_updated", "")
        return ""
    
    def find_element(self, url: str, text: str) -> Optional[Dict[str, Any]]:
        """Найти элемент по тексту на странице"""
        url = self._normalize_url(url)
        if url not in self.data:
            return None
        
        structure = self.data[url].get("structure", {})
        for zone, elements in structure.items():
            for el in elements:
                if el.get("text", "").lower() == text.lower():
                    return {"zone": zone, "element": el}
                if text.lower() in el.get("text", "").lower():
                    return {"zone": zone, "element": el}
        return None
    
    def find_by_testid(self, url: str, testid: str) -> Optional[Dict[str, Any]]:
        """Найти элемент по testid"""
        url = self._normalize_url(url)
        if url not in self.data:
            return None
        
        structure = self.data[url].get("structure", {})
        for zone, elements in structure.items():
            for el in elements:
                if el.get("testId", "") == testid:
                    return {"zone": zone, "element": el}
        return None
    
    def find_by_selector(self, url: str, selector: str) -> Optional[Dict[str, Any]]:
        """Найти элемент по селектору"""
        url = self._normalize_url(url)
        if url not in self.data:
            return None
        
        selectors = self.data[url].get("selectors", {})
        for name, sel in selectors.items():
            if sel == selector:
                return {"name": name, "selector": sel}
        return None
    
    def get_all_selectors(self, url: str) -> Dict[str, str]:
        """Получить все селекторы для сайта"""
        url = self._normalize_url(url)
        if url in self.data:
            return self.data[url].get("selectors", {})
        return {}
    
    def get_zone_elements(self, url: str, zone: str) -> List[Dict[str, Any]]:
        """Получить элементы конкретной зоны"""
        url = self._normalize_url(url)
        if url in self.data:
            structure = self.data[url].get("structure", {})
            return structure.get(zone, [])
        return []
    
    def get_all_zones(self, url: str) -> List[str]:
        """Получить список всех зон"""
        url = self._normalize_url(url)
        if url in self.data:
            structure = self.data[url].get("structure", {})
            return list(structure.keys())
        return []
    
    def _normalize_url(self, url: str) -> str:
        """Нормализовать URL (убрать / в конце)"""
        if not url:
            return url
        if url.endswith('/'):
            return url[:-1]
        return url
    
    def list_maps(self) -> List[str]:
        """Список всех сохранённых карт"""
        return list(self.data.keys())
    
    def delete_map(self, url: str) -> bool:
        """Удалить карту сайта"""
        url = self._normalize_url(url)
        if url in self.data:
            del self.data[url]
            self._save()
            logger.info(f"🗑️ Карта удалена: {url}")
            return True
        return False
    
    def clear(self):
        """Очистить все карты"""
        self.data = {}
        self._save()
        logger.info("🗑️ Все карты сайтов удалены")
    
    def to_json(self) -> str:
        """Вернуть все данные в формате JSON"""
        return json.dumps(self.data, ensure_ascii=False, indent=2)
    
    def to_markdown(self, url: str) -> str:
        """Вернуть карту сайта в формате Markdown"""
        url = self._normalize_url(url)
        if url not in self.data:
            return "❌ Карта сайта не найдена"
        
        data = self.data[url]
        response = f"# 🗺️ Карта сайта\n\n"
        response += f"**URL:** {url}\n"
        response += f"**Заголовок:** {data.get('title', '')}\n"
        response += f"**Обновлено:** {data.get('last_updated', '')}\n\n"
        
        response += f"## 📊 Статистика\n\n"
        stats = data.get('statistics', {})
        response += f"- 🔘 Кнопок: {stats.get('buttons', 0)}\n"
        response += f"- ✏️ Полей ввода: {stats.get('inputs', 0)}\n"
        response += f"- 🔗 Ссылок: {stats.get('links', 0)}\n"
        response += f"- 📋 Форм: {stats.get('forms', 0)}\n\n"
        
        response += f"## 🏗️ Структура\n\n"
        structure = data.get('structure', {})
        for zone, elements in structure.items():
            response += f"### {zone} ({len(elements)} элементов)\n\n"
            for el in elements[:10]:
                text = el.get('text', '')[:40]
                testid = el.get('testId', '')
                if testid:
                    response += f"- {text} → `[data-testid=\"{testid}\"]`\n"
                else:
                    response += f"- {text}\n"
            if len(elements) > 10:
                response += f"- ... и ещё {len(elements) - 10} элементов\n"
            response += "\n"
        
        response += f"## 🔖 Селекторы\n\n"
        selectors = data.get('selectors', {})
        for name, selector in list(selectors.items())[:20]:
            response += f"- **{name}**: `{selector}`\n"
        if len(selectors) > 20:
            response += f"- ... и ещё {len(selectors) - 20} селекторов\n"
        
        return response
    
    def get_summary(self, url: str) -> Dict[str, Any]:
        """Получить краткую сводку о сайте"""
        url = self._normalize_url(url)
        if url not in self.data:
            return {}
        
        data = self.data[url]
        return {
            "title": data.get('title', ''),
            "url": url,
            "last_updated": data.get('last_updated', ''),
            "total_elements": data.get('total_elements', 0),
            "zones_count": data.get('zones_count', 0),
            "statistics": data.get('statistics', {}),
            "selectors_count": len(data.get('selectors', {}))
        }