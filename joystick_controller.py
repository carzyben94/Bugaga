# joystick_controller.py
import asyncio
import math
import random
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass
from playwright.async_api import Page

@dataclass
class JoystickState:
    x: float = 0.0  # -1.0 до 1.0
    y: float = 0.0  # -1.0 до 1.0
    speed: float = 1.0
    smoothness: float = 0.3

class JoystickController:
    """Управление мышью как джойстиком для AI-агентов"""
    
    def __init__(self, page: Page):
        self.page = page
        self.state = JoystickState()
        self.current_pos = (0, 0)
        self.is_moving = False
        self.move_task = None
        self.viewport_width = 1920
        self.viewport_height = 1080
        
    async def init_position(self) -> Tuple[int, int]:
        """Устанавливает курсор в центр экрана"""
        try:
            viewport = await self.page.viewport_size()
            if viewport:
                self.viewport_width = viewport['width']
                self.viewport_height = viewport['height']
                center_x = viewport['width'] // 2
                center_y = viewport['height'] // 2
                await self.page.mouse.move(center_x, center_y)
                self.current_pos = (center_x, center_y)
                return center_x, center_y
        except Exception as e:
            print(f"Init position error: {e}")
        return 0, 0
    
    async def move_joystick(self, 
                           x: float, 
                           y: float, 
                           duration: float = 0.5,
                           speed_mult: float = 1.0) -> Tuple[int, int]:
        """Перемещает курсор как джойстик"""
        max_move = 200 * speed_mult
        dx = x * max_move
        dy = y * max_move
        
        cx, cy = self.current_pos
        target_x = max(0, min(self.viewport_width, cx + dx))
        target_y = max(0, min(self.viewport_height, cy + dy))
        
        steps = max(1, int(duration * 60))
        
        for i in range(steps):
            progress = (i + 1) / steps
            eased = self._ease_in_out(progress)
            
            cur_x = cx + (target_x - cx) * eased
            cur_y = cy + (target_y - cy) * eased
            
            await self.page.mouse.move(cur_x, cur_y)
            self.current_pos = (cur_x, cur_y)
            
            if i < steps - 1:
                await asyncio.sleep(duration / steps)
        
        return self.current_pos
    
    async def move_to_element(self, 
                            selector: str,
                            offset_x: int = 0,
                            offset_y: int = 0,
                            duration: float = 0.5) -> bool:
        """Перемещает курсор к элементу"""
        try:
            element = await self.page.query_selector(selector)
            if not element:
                return False
            
            box = await element.bounding_box()
            if not box:
                return False
            
            target_x = box['x'] + box['width'] // 2 + offset_x
            target_y = box['y'] + box['height'] // 2 + offset_y
            
            cx, cy = self.current_pos
            steps = max(1, int(duration * 60))
            
            for i in range(steps):
                progress = (i + 1) / steps
                eased = self._ease_in_out(progress)
                
                cur_x = cx + (target_x - cx) * eased
                cur_y = cy + (target_y - cy) * eased
                
                await self.page.mouse.move(cur_x, cur_y)
                self.current_pos = (cur_x, cur_y)
                
                if i < steps - 1:
                    await asyncio.sleep(duration / steps)
            
            return True
            
        except Exception as e:
            print(f"Move to element error: {e}")
            return False
    
    async def click(self, 
                   button: str = 'left',
                   double: bool = False,
                   delay: float = 0.1) -> None:
        """Клик в текущей позиции"""
        await asyncio.sleep(delay)
        
        if double:
            await self.page.mouse.dblclick(*self.current_pos)
        else:
            if button == 'left':
                await self.page.mouse.click(*self.current_pos)
            elif button == 'right':
                await self.page.mouse.click(*self.current_pos, button='right')
            elif button == 'middle':
                await self.page.mouse.click(*self.current_pos, button='middle')
    
    async def drag(self, 
                  target_x: float, 
                  target_y: float,
                  duration: float = 0.5) -> None:
        """Перетаскивание"""
        cx, cy = self.current_pos
        
        await self.page.mouse.down()
        
        steps = max(1, int(duration * 60))
        for i in range(steps):
            progress = (i + 1) / steps
            eased = self._ease_in_out(progress)
            
            cur_x = cx + (target_x - cx) * eased
            cur_y = cy + (target_y - cy) * eased
            
            await self.page.mouse.move(cur_x, cur_y)
            self.current_pos = (cur_x, cur_y)
            
            if i < steps - 1:
                await asyncio.sleep(duration / steps)
        
        await self.page.mouse.up()
    
    async def scroll(self, delta_x: int = 0, delta_y: int = 0) -> None:
        """Скролл"""
        await self.page.mouse.wheel(delta_x, delta_y)
    
    async def human_like_move(self, 
                            target_x: int, 
                            target_y: int,
                            speed: float = 1.0) -> None:
        """Движение похожее на человеческое"""
        cx, cy = self.current_pos
        
        distance = math.sqrt((target_x - cx)**2 + (target_y - cy)**2)
        duration = min(2.0, distance / (800 * speed)) + random.uniform(0.1, 0.3)
        
        steps = max(1, int(duration * 60))
        
        for i in range(steps):
            progress = (i + 1) / steps
            
            human_progress = self._human_curve(progress)
            
            noise_x = random.uniform(-5, 5) * (1 - progress)
            noise_y = random.uniform(-5, 5) * (1 - progress)
            
            cur_x = cx + (target_x - cx) * human_progress + noise_x
            cur_y = cy + (target_y - cy) * human_progress + noise_y
            
            cur_x = max(0, min(self.viewport_width, cur_x))
            cur_y = max(0, min(self.viewport_height, cur_y))
            
            await self.page.mouse.move(cur_x, cur_y)
            self.current_pos = (cur_x, cur_y)
            
            if i < steps - 1:
                await asyncio.sleep(duration / steps)
    
    async def explore_screen(self) -> List[Dict[str, Any]]:
        """Находит все интерактивные элементы на странице"""
        try:
            elements = await self.page.evaluate('''
                () => {
                    const result = [];
                    const selectors = [
                        'button', 
                        'a[href]', 
                        'input', 
                        'textarea',
                        'select',
                        '[role="button"]',
                        '[role="link"]',
                        '[role="checkbox"]',
                        '[role="radio"]',
                        '[role="tab"]',
                        '[role="menuitem"]',
                        '[role="option"]',
                        '[contenteditable="true"]',
                        '[data-testid]'
                    ];
                    
                    document.querySelectorAll(selectors.join(',')).forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight) {
                            const text = el.textContent?.trim() || '';
                            const ariaLabel = el.getAttribute('aria-label') || '';
                            const placeholder = el.getAttribute('placeholder') || '';
                            const value = el.value || '';
                            
                            result.push({
                                tag: el.tagName.toLowerCase(),
                                type: el.type || '',
                                text: text.slice(0, 100),
                                ariaLabel: ariaLabel.slice(0, 100),
                                placeholder: placeholder.slice(0, 50),
                                value: value.slice(0, 50),
                                testid: el.getAttribute('data-testid') || '',
                                id: el.id || '',
                                className: el.className || '',
                                x: rect.x + rect.width / 2,
                                y: rect.y + rect.height / 2,
                                width: rect.width,
                                height: rect.height,
                                visible: rect.width > 0 && rect.height > 0,
                                disabled: el.disabled || false,
                                readonly: el.readOnly || false
                            });
                        }
                    });
                    return result;
                }
            ''')
            return elements
        except Exception as e:
            print(f"Explore screen error: {e}")
            return []
    
    async def find_and_click(self, 
                            description: str,
                            ai_agent = None) -> bool:
        """AI-агент ищет элемент по описанию и кликает"""
        elements = await self.explore_screen()
        
        if not elements:
            return False
        
        # Если есть AI агент - используем его
        if ai_agent:
            # Здесь интеграция с твоим AI
            # Например: selected = await ai_agent.find_element(description, elements)
            pass
        
        # Простой поиск по тексту, aria-label, testid
        best_match = None
        best_score = 0
        
        keywords = description.lower().split()
        
        for el in elements:
            score = 0
            text_lower = el['text'].lower()
            aria_lower = el['ariaLabel'].lower()
            testid_lower = el['testid'].lower()
            placeholder_lower = el['placeholder'].lower()
            
            for keyword in keywords:
                if keyword in text_lower:
                    score += 3
                if keyword in aria_lower:
                    score += 2
                if keyword in testid_lower:
                    score += 2
                if keyword in placeholder_lower:
                    score += 1
            
            if score > best_score:
                best_score = score
                best_match = el
        
        if best_match and best_score > 0:
            await self.human_like_move(best_match['x'], best_match['y'])
            await asyncio.sleep(0.2)
            await self.click()
            return True
        
        # Если ничего не нашли, кликаем первый попавшийся элемент
        if elements:
            el = elements[0]
            await self.human_like_move(el['x'], el['y'])
            await asyncio.sleep(0.2)
            await self.click()
            return True
        
        return False
    
    async def continuous_move(self, duration: float = 5.0):
        """Непрерывное движение курсора"""
        self.is_moving = True
        start_time = asyncio.get_event_loop().time()
        
        while self.is_moving and (asyncio.get_event_loop().time() - start_time) < duration:
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(50, 200)
            
            cx, cy = self.current_pos
            target_x = max(0, min(self.viewport_width, cx + math.cos(angle) * distance))
            target_y = max(0, min(self.viewport_height, cy + math.sin(angle) * distance))
            
            await self.human_like_move(target_x, target_y, speed=0.7)
            
            if random.random() < 0.1:
                await self.click()
            
            await asyncio.sleep(random.uniform(0.5, 2.0))
        
        self.is_moving = False
    
    def stop_continuous_move(self):
        """Останавливает непрерывное движение"""
        self.is_moving = False
    
    async def move_with_pattern(self, pattern: str, **kwargs):
        """Движение по паттерну"""
        cx, cy = self.current_pos
        duration = kwargs.get('duration', 3.0)
        size = kwargs.get('size', 100)
        steps = max(1, int(duration * 60))
        
        if pattern == 'circle':
            for i in range(steps):
                angle = (i / steps) * 2 * math.pi
                x = cx + math.cos(angle) * size
                y = cy + math.sin(angle) * size
                x = max(0, min(self.viewport_width, x))
                y = max(0, min(self.viewport_height, y))
                await self.page.mouse.move(x, y)
                self.current_pos = (x, y)
                await asyncio.sleep(duration / steps)
                
        elif pattern == 'square':
            points = [
                (cx - size, cy - size),
                (cx + size, cy - size),
                (cx + size, cy + size),
                (cx - size, cy + size),
                (cx - size, cy - size)
            ]
            per_side = max(1, steps // 4)
            for side in range(4):
                start = points[side]
                end = points[side + 1]
                for i in range(per_side):
                    t = i / per_side
                    x = start[0] + (end[0] - start[0]) * t
                    y = start[1] + (end[1] - start[1]) * t
                    x = max(0, min(self.viewport_width, x))
                    y = max(0, min(self.viewport_height, y))
                    await self.page.mouse.move(x, y)
                    self.current_pos = (x, y)
                    await asyncio.sleep(duration / steps)
                    
        elif pattern == 'spiral':
            for i in range(steps):
                t = i / steps
                angle = t * 4 * math.pi
                r = t * size
                x = cx + math.cos(angle) * r
                y = cy + math.sin(angle) * r
                x = max(0, min(self.viewport_width, x))
                y = max(0, min(self.viewport_height, y))
                await self.page.mouse.move(x, y)
                self.current_pos = (x, y)
                await asyncio.sleep(duration / steps)
                
        elif pattern == 'random':
            for _ in range(min(steps, 20)):
                x = random.randint(0, self.viewport_width)
                y = random.randint(0, self.viewport_height)
                await self.human_like_move(x, y)
                await asyncio.sleep(random.uniform(0.3, 1.0))
    
    @staticmethod
    def _ease_in_out(t: float) -> float:
        return t * t * (3.0 - 2.0 * t)
    
    @staticmethod
    def _human_curve(t: float) -> float:
        return 1 - math.pow(1 - t, 2.5)