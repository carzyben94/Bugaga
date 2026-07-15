import asyncio
import logging
import json
import base64
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ElementTester:
    """
    Тестировщик элементов страницы.
    Собирает, проверяет и сохраняет рабочие команды для AI агента.
    """
    
    def __init__(self, browser, eval):
        self.browser = browser
        self.eval = eval
        self.verified_actions = []
        self.failed_actions = []
        self._last_url = ""
        self.screenshots = []
        self.logs = []
    
    # ===== ЛОГИРОВАНИЕ =====
    def _log(self, message: str, level: str = "INFO"):
        """Записать в лог"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        }
        self.logs.append(entry)
        logger.info(message)
    
    def _log_error(self, message: str):
        """Записать ошибку в лог"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "message": message
        }
        self.logs.append(entry)
        logger.error(message)
    
    # ===== СКРИНШОТЫ =====
    async def _take_screenshot(self, name: str) -> str:
        """Сделать скриншот и сохранить"""
        try:
            screenshot_base64 = await self.browser.screenshot()
            
            # Сохраняем в память для отчёта
            entry = {
                "name": name,
                "timestamp": datetime.now().isoformat(),
                "data": screenshot_base64
            }
            self.screenshots.append(entry)
            
            # Сохраняем в файл
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
        """Сделать скриншот конкретного элемента"""
        try:
            # Скроллим к элементу
            await self.eval.scroll_to(selector)
            await asyncio.sleep(0.5)
            
            # Делаем скриншот
            return await self._take_screenshot(name)
            
        except Exception as e:
            self._log_error(f"Ошибка скриншота элемента: {e}")
            return ""
    
    # ===== СБОР ЭЛЕМЕНТОВ =====
    async def collect_all_elements(self) -> List[Dict[str, Any]]:
        """Собрать все интерактивные элементы"""
        
        elements = []
        
        # Кнопки
        buttons = await self.eval.get_all_buttons()
        for btn in buttons:
            elements.append({
                "type": "click",
                "text": btn.get('text', ''),
                "testId": btn.get('testId', ''),
                "selector": f"[data-testid='{btn.get('testId', '')}']" if btn.get('testId') else None,
                "ariaLabel": btn.get('ariaLabel', ''),
                "id": btn.get('id', ''),
                "disabled": btn.get('disabled', False),
                "verified": False
            })
        
        # Поля ввода
        inputs = await self.eval.get_all_inputs()
        for inp in inputs:
            elements.append({
                "type": "input",
                "name": inp.get('name', ''),
                "testId": inp.get('testId', ''),
                "selector": f"[data-testid='{inp.get('testId', '')}']" if inp.get('testId') else None,
                "placeholder": inp.get('placeholder', ''),
                "type_input": inp.get('type', 'text'),
                "verified": False
            })
        
        # Ссылки
        links = await self.eval.get_all_links()
        for link in links:
            elements.append({
                "type": "navigate",
                "text": link.get('text', ''),
                "href": link.get('href', ''),
                "testId": link.get('testId', ''),
                "selector": f"[data-testid='{link.get('testId', '')}']" if link.get('testId') else None,
                "verified": False
            })
        
        # Чекбоксы
        checkboxes = await self.eval.get_all_checkboxes()
        for cb in checkboxes:
            elements.append({
                "type": "checkbox",
                "name": cb.get('name', ''),
                "testId": cb.get('testId', ''),
                "selector": f"[data-testid='{cb.get('testId', '')}']" if cb.get('testId') else None,
                "verified": False
            })
        
        # Select
        selects = await self.eval.get_all_selects()
        for sel in selects:
            elements.append({
                "type": "select",
                "name": sel.get('name', ''),
                "testId": sel.get('testId', ''),
                "selector": f"[data-testid='{sel.get('testId', '')}']" if sel.get('testId') else None,
                "options": sel.get('options', []),
                "verified": False
            })
        
        return elements
    
    # ===== ТЕСТИРОВАНИЕ =====
    async def test_click(self, element: Dict[str, Any]) -> Dict[str, Any]:
        """Тестировать клик с скриншотами"""
        
        selector = element.get('selector')
        if not selector:
            return {"success": False, "reason": "Нет селектора"}
        
        self._log(f"🧪 Тестирую клик: {element.get('text', '')[:30]}")
        
        try:
            # Проверяем элемент
            exists = await self.eval.exists(selector)
            if not exists:
                self._log_error(f"Элемент не найден: {selector}")
                return {"success": False, "reason": "Элемент не найден"}
            
            # Скриншот ДО
            await self._take_element_screenshot(selector, f"before_click_{element.get('text', '')[:20]}")
            
            # Сохраняем состояние ДО
            before_state = await self._get_state(selector)
            before_url = await self.eval.get_url()
            
            # Кликаем
            await self.browser.human_click(selector)
            await asyncio.sleep(1)
            
            # Скриншот ПОСЛЕ
            await self._take_element_screenshot(selector, f"after_click_{element.get('text', '')[:20]}")
            
            # Проверяем состояние ПОСЛЕ
            after_state = await self._get_state(selector)
            after_url = await self.eval.get_url()
            
            # Анализируем изменения
            changes = []
            if before_url != after_url:
                changes.append(f"URL: {before_url} → {after_url}")
            if before_state.get('value') != after_state.get('value'):
                changes.append(f"Значение: {before_state.get('value')} → {after_state.get('value')}")
            if before_state.get('checked') != after_state.get('checked'):
                changes.append(f"Чекбокс: {before_state.get('checked')} → {after_state.get('checked')}")
            
            # Проверяем новые элементы
            new_element = await self._check_new_element()
            if new_element:
                changes.append(f"Новый элемент: {new_element}")
                await self._take_screenshot(f"new_element_{new_element.replace('[', '').replace(']', '')}")
            
            if changes:
                self._log(f"✅ Клик успешен: {', '.join(changes)}")
                return {
                    "success": True,
                    "action": "click",
                    "selector": selector,
                    "text": element.get('text', ''),
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
                    "text": element.get('text', ''),
                    "changes": ["Клик выполнен, изменений нет"],
                    "verified": True,
                    "screenshots": [s.get('name') for s in self.screenshots[-2:]]
                }
                
        except Exception as e:
            self._log_error(f"Ошибка: {e}")
            return {"success": False, "reason": str(e)}
    
    async def test_input(self, element: Dict[str, Any], text: str = "test") -> Dict[str, Any]:
        """Тестировать ввод текста с скриншотами"""
        
        selector = element.get('selector')
        if not selector:
            return {"success": False, "reason": "Нет селектора"}
        
        self._log(f"🧪 Тестирую ввод: {element.get('name', '')[:30]}")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": "Элемент не найден"}
            
            # Скриншот ДО
            await self._take_element_screenshot(selector, "before_input")
            
            # Сохраняем значение ДО
            before = await self.eval.get_value(selector)
            
            # Вводим текст
            await self.browser.human_type(selector, text)
            await asyncio.sleep(0.5)
            
            # Скриншот ПОСЛЕ
            await self._take_element_screenshot(selector, "after_input")
            
            # Проверяем значение
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
    
    async def test_enter(self, selector: str, text: str = "test") -> Dict[str, Any]:
        """Тестировать ввод + Enter с скриншотами"""
        
        self._log(f"🧪 Тестирую Enter")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": "Элемент не найден"}
            
            # Скриншот ДО
            await self._take_element_screenshot(selector, "before_enter")
            
            before_url = await self.eval.get_url()
            
            # Вводим текст
            await self.browser.human_type(selector, text)
            await asyncio.sleep(0.5)
            
            # Нажимаем Enter
            await self.eval.focus(selector)
            await self._press_enter(selector)
            await asyncio.sleep(1.5)
            
            # Скриншот ПОСЛЕ
            await self._take_element_screenshot(selector, "after_enter")
            
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
    
    async def test_checkbox(self, element: Dict[str, Any]) -> Dict[str, Any]:
        """Тестировать чекбокс"""
        
        selector = element.get('selector')
        if not selector:
            return {"success": False, "reason": "Нет селектора"}
        
        self._log(f"🧪 Тестирую чекбокс: {element.get('name', '')[:30]}")
        
        try:
            exists = await self.eval.exists(selector)
            if not exists:
                return {"success": False, "reason": "Элемент не найден"}
            
            # Скриншот ДО
            await self._take_element_screenshot(selector, "before_checkbox")
            
            before = await self.eval.get_checked(selector)
            
            # Кликаем
            await self.browser.human_click(selector)
            await asyncio.sleep(0.5)
            
            # Скриншот ПОСЛЕ
            await self._take_element_screenshot(selector, "after_checkbox")
            
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
    
    async def test_select(self, element: Dict[str, Any], option_value: str = None) -> Dict[str, Any]:
        """Тестировать select"""
        
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
            
            # Скриншот ДО
            await self._take_element_screenshot(selector, "before_select")
            
            before = await self.eval.get_value(selector)
            
            # Выбираем опцию
            await self.eval.select_option(selector, option_value)
            await asyncio.sleep(0.5)
            
            # Скриншот ПОСЛЕ
            await self._take_element_screenshot(selector, "after_select")
            
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
        """Получить состояние элемента"""
        return {
            "exists": await self.eval.exists(selector),
            "visible": await self.eval.is_visible(selector),
            "enabled": await self.eval.is_enabled(selector),
            "value": await self.eval.get_value(selector),
            "checked": await self.eval.get_checked(selector)
        }
    
    async def _check_new_element(self) -> Optional[str]:
        """Проверить появление нового элемента"""
        new_selectors = [
            "[role='dialog']",
            "[role='menu']",
            "[role='alert']",
            "[data-testid='modal']",
            "[data-testid='menu']",
            "[data-testid='dropdown']"
        ]
        
        for selector in new_selectors:
            try:
                exists = await self.eval.exists(selector)
                if exists:
                    visible = await self.eval.is_visible(selector)
                    if visible:
                        return selector
            except:
                continue
        
        return None
    
    async def _check_results(self) -> Optional[str]:
        """Проверить появление результатов"""
        result_selectors = [
            "[data-testid='results']",
            "[data-testid='search-results']",
            "[role='list']",
            "[role='grid']"
        ]
        
        for selector in result_selectors:
            try:
                exists = await self.eval.exists(selector)
                if exists:
                    visible = await self.eval.is_visible(selector)
                    if visible:
                        count = await self.eval.get_count(selector)
                        if count > 0:
                            return f"Найдено {count} результатов"
            except:
                continue
        
        return None
    
    async def _press_enter(self, selector: str):
        """Нажать Enter через JS"""
        js = f"""
        (function() {{
            const el = document.querySelector('{selector}');
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
        """Запустить полное тестирование с логами и скриншотами"""
        
        self.screenshots = []
        self.logs = []
        
        self._log(f"🚀 Начинаю тестирование {url}")
        
        await self.browser.goto(url)
        await asyncio.sleep(3)
        self._last_url = url
        
        # Скриншот всей страницы
        await self._take_screenshot("page_full")
        
        # Собираем элементы
        elements = await self.collect_all_elements()
        self._log(f"📊 Собрано {len(elements)} элементов")
        
        results = {
            "total": len(elements),
            "verified": 0,
            "failed": 0,
            "skipped": 0,
            "actions": [],
            "failed_elements": []
        }
        
        for i, element in enumerate(elements):
            self._log(f"  [{i+1}/{len(elements)}] {element.get('text', element.get('name', ''))[:30]}")
            
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
            elif action_type == 'checkbox':
                result = await self.test_checkbox(element)
            elif action_type == 'select':
                result = await self.test_select(element)
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
        
        # Формируем отчёт
        report = {
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "verified_actions": results["actions"],
            "failed_elements": results["failed_elements"],
            "logs": self.logs,
            "screenshots_count": len(self.screenshots)
        }
        
        # Сохраняем отчёт
        with open("test_results.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # Сохраняем логи
        with open("test_logs.txt", "w", encoding="utf-8") as f:
            for log in self.logs:
                f.write(f"[{log['timestamp']}] [{log['level']}] {log['message']}\n")
        
        self._log(f"💾 Результаты сохранены: test_results.json, test_logs.txt, {len(self.screenshots)} скриншотов")
        
        return report