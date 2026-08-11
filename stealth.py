# stealth.py - Только маскировка и антидетект
from typing import List, Dict
from dataclasses import dataclass, field

@dataclass
class TimingConfig:
    """Тайминги для человеческого поведения"""
    keystroke_min: float = 0.04
    keystroke_max: float = 0.15
    punctuation_delay: float = 0.08
    thinking_probability: float = 0.03
    thinking_delay_min: float = 0.3
    thinking_delay_max: float = 0.7
    error_probability: float = 0.02
    mouse_speed_min: float = 0.005
    mouse_speed_max: float = 0.015
    click_delay_min: float = 0.05
    click_delay_max: float = 0.15
    scroll_speed: float = 0.05
    pause_on_read_probability: float = 0.05
    pause_on_read_delay_min: float = 0.5
    pause_on_read_delay_max: float = 1.5

@dataclass
class BrowserPreferences:
    """Настройки браузера"""
    default_content_settings: Dict[str, int] = field(default_factory=lambda: {
        'cookies': 1,
        'images': 1,
        'javascript': 1,
        'plugins': 1,
        'popups': 2,
        'geolocation': 1,
        'notifications': 2,
        'auto_select_certificate': 2,
        'fullscreen': 1,
        'mouselock': 1,
        'mixed_script': 1,
        'media_stream': 2,
        'media_stream_mic': 2,
        'media_stream_camera': 2,
        'protocol_handlers': 1,
        'push_messaging': 2,
        'sensors': 1,
        'sound': 1,
        'usb_guard': 2,
        'web_authentication': 2,
        'web_bluetooth': 2,
        'web_usb': 2,
    })
    password_manager_enabled: bool = False
    autofill_enabled: bool = False
    translate_enabled: bool = False
    network_prediction_enabled: bool = True
    safe_browsing_enabled: bool = True
    spellcheck_enabled: bool = True
    hyperlink_auditing_enabled: bool = False

class Stealth:
    """ВСЯ маскировка в одном классе"""
    
    @staticmethod
    def get_chrome_flags(headless: bool = True, user_agent: str = None, 
                         proxy: str = None, webrtc_leak_protection: bool = True) -> List[str]:
        """Все CDP флаги для маскировки"""
        cmd = [
            '/usr/bin/chromium',
            '--remote-debugging-port=9222',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-setuid-sandbox',
            '--no-sandbox',
            '--window-size=1280,720',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process,TranslateUI',
            '--disable-web-security',
            '--allow-running-insecure-content',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-breakpad',
            '--disable-component-extensions-with-background-pages',
            '--disable-default-apps',
            '--disable-domain-reliability',
            '--disable-hang-monitor',
            '--disable-ipc-flooding-protection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-renderer-backgrounding',
            '--disable-sync',
            '--force-color-profile=srgb',
            '--ignore-certificate-errors',
            '--ignore-ssl-errors',
            '--mute-audio',
            '--password-store=basic',
            '--use-fake-device-for-media-stream',
            '--use-fake-ui-for-media-stream',
            '--enable-features=NetworkService,NetworkServiceInProcess'
        ]
        
        if headless:
            cmd.insert(cmd.index('--remote-debugging-port=9222') + 1, '--headless=new')
        
        if user_agent:
            cmd.append(f'--user-agent={user_agent}')
        
        if webrtc_leak_protection:
            cmd.append('--force-webrtc-ip-handling-policy=disable_non_proxied_udp')
            cmd.append('--enable-webrtc-srtp-aes-gcm')
        
        if proxy:
            cmd.append(f'--proxy-server={proxy}')
        
        return cmd
    
    @staticmethod
    def get_stealth_scripts() -> List[str]:
        """Stealth JavaScript для маскировки"""
        return [
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
            "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})",
            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})",
            "window.chrome = { runtime: {} }",
            "window.navigator.permissions.query = (params) => Promise.resolve({state: 'prompt'})",
            """
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            }
            """,
            "Object.defineProperty(screen, 'availWidth', {get: () => 1280})",
            "Object.defineProperty(screen, 'availHeight', {get: () => 720})",
        ]
    
    @staticmethod
    def get_referrer_script() -> str:
        """Маскировка referrer"""
        return """
            Object.defineProperty(document, 'referrer', {
                get: () => 'https://www.google.com/'
            });
        """

class BezierCurve:
    """Генерация кривых для человеческого движения"""
    
    @staticmethod
    def generate_points(start: tuple, end: tuple, num_points: int = 30, spread: int = 50) -> List[tuple]:
        """Генерирует точки кривой Безье"""
        x1, y1 = start
        x2, y2 = end
        
        cx1 = x1 + (x2 - x1) * 0.3 + random.randint(-spread, spread)
        cy1 = y1 + (y2 - y1) * 0.3 + random.randint(-spread, spread)
        cx2 = x1 + (x2 - x1) * 0.7 + random.randint(-spread, spread)
        cy2 = y1 + (y2 - y1) * 0.7 + random.randint(-spread, spread)
        
        points = []
        for i in range(num_points + 1):
            t = i / num_points
            mt = 1 - t
            x = mt**3 * x1 + 3 * mt**2 * t * cx1 + 3 * mt * t**2 * cx2 + t**3 * x2
            y = mt**3 * y1 + 3 * mt**2 * t * cy1 + 3 * mt * t**2 * cy2 + t**3 * y2
            points.append((x, y))
        
        return points

class HumanBehavior:
    """Эмуляция человеческого поведения"""
    
    @staticmethod
    async def human_click(page, x: float, y: float, button: str = "left",
                          config: TimingConfig = None):
        """Реалистичный клик"""
        if config is None:
            config = TimingConfig()
        
        try:
            result = await page.connection.send_command("Runtime.evaluate", {
                "expression": "window.innerWidth/2, window.innerHeight/2",
                "returnByValue": True
            })
            current_pos = result.get('result', {}).get('value', (200, 200))
            start_x, start_y = current_pos if isinstance(current_pos, tuple) else (200, 200)
        except:
            start_x, start_y = random.randint(100, 500), random.randint(100, 500)
        
        points = BezierCurve.generate_points(
            (start_x, start_y),
            (x, y),
            num_points=random.randint(20, 40),
            spread=30
        )
        
        for px, py in points:
            await page.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": px,
                "y": py
            })
            await asyncio.sleep(random.uniform(config.mouse_speed_min, config.mouse_speed_max))
        
        await asyncio.sleep(random.uniform(config.click_delay_min, config.click_delay_max))
        
        await page.connection.send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })
        await asyncio.sleep(random.uniform(0.05, 0.1))
        await page.connection.send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })
    
    @staticmethod
    async def human_type_global(page, text: str, config: TimingConfig = None):
        """Реалистичный ввод текста"""
        if config is None:
            config = TimingConfig()
        
        for i, char in enumerate(text):
            if char in '.!?;:,' and random.random() < 0.4:
                await asyncio.sleep(random.uniform(0.1, 0.25))
            
            if random.random() < config.error_probability and char.isalpha():
                keyboard_rows = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
                for row in keyboard_rows:
                    if char.lower() in row:
                        idx = row.index(char.lower())
                        if idx > 0 and random.random() < 0.5:
                            wrong_char = row[idx - 1]
                        elif idx < len(row) - 1:
                            wrong_char = row[idx + 1]
                        else:
                            wrong_char = char
                        break
                else:
                    wrong_char = char
                
                await page.connection.send_command("Input.insertText", {"text": wrong_char})
                await asyncio.sleep(random.uniform(config.keystroke_min, config.keystroke_max))
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.connection.send_command("Input.dispatchKeyEvent", {
                    "type": "keyDown",
                    "key": "Backspace",
                    "code": "Backspace"
                })
                await page.connection.send_command("Input.dispatchKeyEvent", {
                    "type": "keyUp",
                    "key": "Backspace",
                    "code": "Backspace"
                })
                await asyncio.sleep(random.uniform(config.keystroke_min, config.keystroke_max))
            
            await page.connection.send_command("Input.insertText", {"text": char})
            await asyncio.sleep(random.uniform(config.keystroke_min, config.keystroke_max))
            
            if random.random() < config.thinking_probability:
                await asyncio.sleep(random.uniform(config.thinking_delay_min, config.thinking_delay_max))