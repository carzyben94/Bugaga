# browser_tools.py
import subprocess
import json
from typing import List, Dict

class WebSurfer:
    """Позволяет ИИ-агенту исследовать веб-страницы"""
    
    @staticmethod
    def discover_page(url: str) -> Dict:
        """Открывает страницу и возвращает ее структуру (accessibility tree)"""
        cmd = ["python", "-m", "ai_dev_browser.tools.page_goto", "--url", url]
        subprocess.run(cmd, capture_output=True)
        
        cmd = ["python", "-m", "ai_dev_browser.tools.page_discover", "--format", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(result.stdout)
    
    @staticmethod
    def click_on_element(ref: str) -> bool:
        """Кликает по элементу на странице по его ref"""
        cmd = ["python", "-m", "ai_dev_browser.tools.click_by_ref", "--ref", ref]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0
    
    @staticmethod
    def search_web(query: str, num_results: int = 3) -> List[str]:
        """Ищет в интернете и возвращает тексты первых результатов"""
        # Используем DuckDuckGo для простоты, или подключим API поиска
        search_url = f"https://lite.duckduckgo.com/lite/?q={query.replace(' ', '+')}"
        # Здесь будет логика парсинга выдачи через ai-dev-browser
        # Упрощенный пример:
        print(f"Агент ищет в интернете: {query}")
        return [f"Результат поиска для '{query}' (ссылка на найденную документацию)"]
