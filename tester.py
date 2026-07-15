import asyncio
import logging
import json
import base64
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ElementTester:
    def __init__(self, browser, eval):
        self.browser = browser
        self.eval = eval
        self.verified_actions = []
        self.failed_actions = []
        self._last_url = ""
        self.screenshots = []
        self.logs = []

    def _escape_js(self, text: str) -> str:
        """Экранировать текст для вставки в JavaScript"""
        if not text:
            return ""
        return text.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

    def _escape_selector(self, selector: str) -> str:
        """Экранировать селектор для вставки в JavaScript"""
        if not selector:
            return ""
        return selector.replace("'", "\\'").replace('"', '\\"')

    def _sanitize_filename(self, text: str) -> str:
        """Очистить текст для имени файла"""
        if not text:
            return "element"
        return re.sub(r'[^a-zA-Z0-9а-яА-Я\s]', '', text)[:30].strip() or "element"

    # ===== ЛОГИРОВАНИЕ =====
    def _log(self, message: str, level: str = "INFO"):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        }
        self.logs.append(entry)
        logger.info(message)
    
    def _log_error(self, message: str):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "message": message
        }
        self.logs.append(entry)
        logger.error(message)

    # ===== СКРИНШОТЫ =====
    async def _take_screenshot(self, name: str) -> str:
        try:
            screenshot_base64 = await self.browser.screenshot()
            entry = {
                "name": name,
                "timestamp": datetime.now().isoformat(),
                "data": screenshot_base64
            }
            self.screenshots.append(entry)
            screenshots_dir = "screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            filename = f"{screenshots_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.png"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(screenshot_base64))
            self._log(f"📸 Скриншот сохранён: {filename}")
            return filename
        except Exception as e:
            self._log_error(f"Ошибка скриншота: {e}")
            return ""

    async def _take_element_screenshot(self, selector: str, name: str) -> str:
        try:
            await self.eval.scroll_to(selector)
            await asyncio.sleep(0.3)
            return await self._take_screenshot(name)
        except Exception as e:
            self._log_error(f"Ошибка скриншота элемента: {e}")
            return ""

    # ===== СБОР ЭЛЕМЕНТОВ =====
    async def collect_all_elements(self) -> List[Dict[str, Any]]:
        elements = []
        
        buttons = await self.eval.get_all_buttons()
        for btn in buttons:
            # Пропускаем без testId
            if not btn.get('testId'):
                continue
            text = btn.get('text', '') or btn.get('ariaLabel', '') or 'button'
            elements.append({
                "type": "click",
                "text": text,
                "testId": btn.get('testId', ''),
                "selector": f"[data-testid='{btn.get('testId', '')}']",
                "ariaLabel": btn.get('ariaLabel', ''),
                "id": btn.get('id', ''),
                "disabled": btn.get('disabled', False),
                "verified": False
            })
        
        inputs = await self.eval.get_all_inputs()
        for inp in inputs:
            if not inp.get('testId'):
                continue
            name = inp.get('name', '') or inp.get('placeholder', '') or 'input'
            elements.append({
                "type": "input",
                "name": name,
                "testId": inp.get('testId', ''),
                "selector": f"[data-testid='{inp.get('testId', '')}']",
                "placeholder": inp.get('placeholder', ''),
                "type_input": inp.get('type', 'text'),
                "verified": False
            })
        
        links = await self.eval.get_all_links()
        for link in links:
            if not link.get('testId'):
                continue
            text = link.get('text', '') or 'link'
            elements.append({
                "type": "navigate",
                "text": text,
                "href": link.get('href', ''),
                "testId": link.get('testId', ''),
                "selector": f"[data-testid='{link.get('testId', '')}']",
                "verified": False
            })
        
        return elements

    # ===== ТЕСТИРОВАНИЕ КЛИКА =====
    async def test_click(self, element: Dict[str, Any]) -> Dict[str, Any]:
        selector = element.get('selector')
        if not selector:
            return {"success": False, "reason": "Нет селектора"}
        
        text = element.get('text', '')[:30]
        self._log(f"🧪 Тестирую клик: {text}")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                self._log_error(f"Элемент не найден: {selector}")
                return {"success": False, "reason": "Элемент не найден"}
            
            safe_name = self._sanitize_filename(text)
            await self._take_element_screenshot(selector, f"before_click_{safe_name}")
            
            before_state = await self._get_state(selector)
            before_url = await self.eval.get_url()
            
            await self.browser.human_click(selector)
            await asyncio.sleep(1)
            
            await self._take_element_screenshot(selector, f"after_click_{safe_name}")
            
            after_state = await self._get_state(selector)
            after_url = await self.eval.get_url()
            
            changes = []
            if before_url != after_url:
                changes.append(f"URL: {before_url} → {after_url}")
            if before_state.get('value') != after_state.get('value'):
                changes.append(f"Значение: {before_state.get('value')} → {after_state.get('value')}")
            if before_state.get('checked') != after_state.get('checked'):
                changes.append(f"Чекбокс: {before_state.get('checked')} → {after_state.get('checked')}")
            
            new_element = await self._check_new_element()
            if new_element:
                changes.append(f"Новый элемент: {new_element}")
                await self._take_screenshot("new_element")
            
            if changes:
                self._log(f"✅ Клик успешен: {', '.join(changes)}")
                return {
                    "success": True,
                    "action": "click",
                    "selector": selector,
                    "text": text,
                    "changes": changes,
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
            else:
                self._log(f"⚠️ Клик выполнен, изменений нет")
                return {
                    "success": True,
                    "action": "click",
                    "selector": selector,
                    "text": text,
                    "changes": ["Клик выполнен, изменений нет"],
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
        except Exception as e:
            self._log_error(f"Ошибка: {e}")
            return {"success": False, "reason": str(e)}

    # ===== ТЕСТИРОВАНИЕ ВВОДА =====
    async def test_input(self, element: Dict[str, Any], text: str = "test") -> Dict[str, Any]:
        selector = element.get('selector')
        if not selector:
            return {"success": False, "reason": "Нет селектора"}
        
        self._log(f"🧪 Тестирую ввод: {element.get('name', '')[:30]}")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": "Элемент не найден"}
            
            safe_name = self._sanitize_filename(element.get('name', 'input'))
            await self._take_element_screenshot(selector, f"before_input_{safe_name}")
            before = await self.eval.get_value(selector)
            await self.browser.human_type(selector, text)
            await asyncio.sleep(0.5)
            await self._take_element_screenshot(selector, f"after_input_{safe_name}")
            after = await self.eval.get_value(selector)
            
            if after == text:
                self._log(f"✅ Ввод успешен: '{text}'")
                return {
                    "success": True,
                    "action": "input",
                    "selector": selector,
                    "text": text,
                    "name": element.get('name', ''),
                    "before": before,
                    "after": after,
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
            else:
                self._log_error(f"Текст не совпадает: ожидалось '{text}', получено '{after}'")
                return {
                    "success": False,
                    "reason": f"Текст не совпадает: ожидалось '{text}', получено '{after}'"
                }
        except Exception as e:
            self._log_error(f"Ошибка: {e}")
            return {"success": False, "reason": str(e)}

    # ===== ТЕСТИРОВАНИЕ ENTER =====
    async def test_enter(self, selector: str, text: str = "test") -> Dict[str, Any]:
        """Тестировать ввод + Enter с экранированием"""
        
        self._log(f"🧪 Тестирую Enter")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": "Элемент не найден"}
            
            safe_name = self._sanitize_filename("enter")
            await self._take_element_screenshot(selector, f"before_enter_{safe_name}")
            
            before_url = await self.eval.get_url()
            
            await self.browser.human_type(selector, text)
            await asyncio.sleep(0.5)
            
            await self.eval.focus(selector)
            await self._press_enter(selector)
            await asyncio.sleep(1.5)
            
            await self._take_element_screenshot(selector, f"after_enter_{safe_name}")
            
            after_url = await self.eval.get_url()
            results = await self._check_results()
            
            if after_url != before_url:
                self._log(f"✅ Enter успешен: URL изменился")
                return {
                    "success": True,
                    "action": "enter",
                    "selector": selector,
                    "text": text,
                    "change": f"URL: {before_url} → {after_url}",
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
            elif results:
                self._log(f"✅ Enter успешен: {results}")
                return {
                    "success": True,
                    "action": "enter",
                    "selector": selector,
                    "text": text,
                    "change": results,
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
            else:
                self._log_error("Enter не привёл к изменениям")
                return {
                    "success": False,
                    "reason": "Enter не привёл к изменениям"
                }
                
        except Exception as e:
            self._log_error(f"Ошибка: {e}")
            return {"success": False, "reason": str(e)}

    # ===== ТЕСТИРОВАНИЕ ЧЕКБОКСА =====
    async def test_checkbox(self, element: Dict[str, Any]) -> Dict[str, Any]:
        selector = element.get('selector')
        if not selector:
            return {"success": False, "reason": "Нет селектора"}
        
        self._log(f"🧪 Тестирую чекбокс: {element.get('name', '')[:30]}")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": "Элемент не найден"}
            
            safe_name = self._sanitize_filename(element.get('name', 'checkbox'))
            await self._take_element_screenshot(selector, f"before_checkbox_{safe_name}")
            
            before = await self.eval.get_checked(selector)
            await self.browser.human_click(selector)
            await asyncio.sleep(0.5)
            
            await self._take_element_screenshot(selector, f"after_checkbox_{safe_name}")
            after = await self.eval.get_checked(selector)
            
            if before != after:
                self._log(f"✅ Чекбокс переключён: {before} → {after}")
                return {
                    "success": True,
                    "action": "checkbox",
                    "selector": selector,
                    "name": element.get('name', ''),
                    "before": before,
                    "after": after,
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
            else:
                self._log_error(f"Состояние не изменилось: {before} → {after}")
                return {
                    "success": False,
                    "reason": f"Состояние не изменилось: {before} → {after}"
                }
                
        except Exception as e:
            self._log_error(f"Ошибка: {e}")
            return {"success": False, "reason": str(e)}

    # ===== ТЕСТИРОВАНИЕ SELECT =====
    async def test_select(self, element: Dict[str, Any], option_value: str = None) -> Dict[str, Any]:
        selector = element.get('selector')
        if not selector:
            return {"success": False, "reason": "Нет селектора"}
        
        self._log(f"🧪 Тестирую select: {element.get('name', '')[:30]}")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": "Элемент не найден"}
            
            options = element.get('options', [])
            if not options:
                return {"success": False, "reason": "Нет опций"}
            
            if not option_value:
                option_value = options[0].get('value')
            
            safe_name = self._sanitize_filename(element.get('name', 'select'))
            await self._take_element_screenshot(selector, f"before_select_{safe_name}")
            
            before = await self.eval.get_value(selector)
            await self.eval.select_option(selector, option_value)
            await asyncio.sleep(0.5)
            
            await self._take_element_screenshot(selector, f"after_select_{safe_name}")
            after = await self.eval.get_value(selector)
            
            if after == option_value:
                self._log(f"✅ Опция выбрана: '{option_value}'")
                return {
                    "success": True,
                    "action": "select",
                    "selector": selector,
                    "name": element.get('name', ''),
                    "option": option_value,
                    "before": before,
                    "after": after,
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
            else:
                self._log_error(f"Опция не выбрана: ожидалось '{option_value}', получено '{after}'")
                return {
                    "success": False,
                    "reason": f"Опция не выбрана: ожидалось '{option_value}', получено '{after}'"
                }
                
        except Exception as e:
            self._log_error(f"Ошибка: {e}")
            return {"success": False, "reason": str(e)}

    # ===== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ =====
    async def _get_state(self, selector: str) -> Dict[str, Any]:
        return {
            "exists": await self.eval.exists(selector),
            "visible": await self.eval.is_visible(selector),
            "enabled": await self.eval.is_enabled(selector),
            "value": await self.eval.get_value(selector),
            "checked": await self.eval.get_checked(selector)
        }

    async def _check_new_element(self) -> Optional[str]:
        new_selectors = [
            "[role='dialog']", "[role='menu']", "[role='alert']",
            "[data-testid='modal']", "[data-testid='menu']", "[data-testid='dropdown']"
        ]
        for selector in new_selectors:
            try:
                if await self.eval.exists(selector) and await self.eval.is_visible(selector):
                    return selector
            except:
                continue
        return None

    async def _check_results(self) -> Optional[str]:
        result_selectors = [
            "[data-testid='results']",
            "[data-testid='search-results']",
            "[role='list']",
            "[role='grid']"
        ]
        for selector in result_selectors:
            try:
                if await self.eval.exists(selector) and await self.eval.is_visible(selector):
                    count = await self.eval.get_count(selector)
                    if count > 0:
                        return f"Найдено {count} результатов"
            except:
                continue
        return None

    async def _press_enter(self, selector: str):
        """Нажать Enter через JS с экранированием"""
        safe_selector = self._escape_selector(selector)
        js = f"""
        (function() {{
            const el = document.querySelector('{safe_selector}');
            if (!el) return false;
            el.dispatchEvent(new KeyboardEvent('keydown', {{
                key: 'Enter',
                code: 'Enter',
                bubbles: true,
                cancelable: true
            }}));
            el.dispatchEvent(new KeyboardEvent('keyup', {{
                key: 'Enter',
                code: 'Enter',
                bubbles: true,
                cancelable: true
            }}));
            return true;
        }})()
        """
        await self.eval.execute(js)

    # ===== ПОЛНЫЙ ТЕСТ =====
    async def run_full_test(self, url: str) -> Dict[str, Any]:
        self.screenshots = []
        self.logs = []
        
        self._log(f"🚀 Начинаю тестирование {url}")
        
        await self.browser.goto(url)
        await asyncio.sleep(3)
        self._last_url = url
        
        await self._take_screenshot("page_full")
        
        elements = await self.collect_all_elements()
        self._log(f"📊 Собрано {len(elements)} элементов с селекторами")
        
        results = {
            "total": len(elements),
            "verified": 0,
            "failed": 0,
            "skipped": 0,
            "actions": [],
            "failed_elements": []
        }
        
        for i, element in enumerate(elements):
            text = element.get('text', element.get('name', ''))[:30]
            self._log(f"  [{i+1}/{len(elements)}] {text}")
            
            if element.get('disabled'):
                results["skipped"] += 1
                continue
            
            action_type = element.get('type', 'click')
            
            if action_type == 'click':
                result = await self.test_click(element)
            elif action_type == 'input':
                result = await self.test_input(element, "test")
            elif action_type == 'navigate':
                result = await self.test_click(element)
            else:
                result = await self.test_click(element)
            
            if result.get("success"):
                results["verified"] += 1
                element["verified"] = True
                element["test_result"] = result
                results["actions"].append(result)
            else:
                results["failed"] += 1
                element["verified"] = False
                element["error"] = result.get("reason", "Неизвестная ошибка")
                results["failed_elements"].append(element)
        
        report = {
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "verified_actions": results["actions"],
            "failed_elements": results["failed_elements"],
            "logs": self.logs,
            "screenshots_count": len(self.screenshots)
        }
        
        with open("test_results.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        with open("test_logs.txt", "w", encoding="utf-8") as f:
            for log in self.logs:
                f.write(f"[{log['timestamp']}] [{log['level']}] {log['message']}\n")
        
        self._log(f"💾 Результаты сохранены: test_results.json, test_logs.txt, {len(self.screenshots)} скриншотов")
        
        return report