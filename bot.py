# test_bot.py - cdp-use + автоустановка Chrome + куки
import os
import sys
import subprocess
import logging
import asyncio
import tempfile
import base64
import time
import socket
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== НАСТРОЙКА ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== УСТАНОВКА ЗАВИСИМОСТЕЙ ==========

def install_chrome():
    """Устанавливает Chrome/Chromium через playwright"""
    try:
        print("⏳ Устанавливаю playwright...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'playwright'], check=True, capture_output=True)
        print("⏳ Устанавливаю chromium...")
        subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True, capture_output=True)
        
        # Находим путь к chromium
        import shutil
        chrome_path = shutil.which('chromium') or shutil.which('chrome')
        if chrome_path:
            print(f"✅ Браузер установлен: {chrome_path}")
            return chrome_path
        
        # Ищем в .cache
        home = os.path.expanduser('~')
        cache_paths = [
            f'{home}/.cache/ms-playwright/chromium-*/chrome-linux/chrome',
            f'{home}/.cache/ms-playwright/chromium-*/chrome-linux/chrome',
        ]
        import glob
        for pattern in cache_paths:
            matches = glob.glob(pattern)
            if matches:
                print(f"✅ Браузер найден: {matches[0]}")
                return matches[0]
        
        return None
    except Exception as e:
        print(f"❌ Ошибка установки Chrome: {e}")
        return None

def install_cdp_use():
    """Устанавливает cdp-use"""
    try:
        print("⏳ Устанавливаю cdp-use...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'cdp-use'], check=True, capture_output=True)
        print("✅ cdp-use установлен")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки cdp-use: {e}")
        return False

# ========== ПРОВЕРКА И УСТАНОВКА ==========

CDP_AVAILABLE = False
CHROME_PATH = None

def check_dependencies():
    global CDP_AVAILABLE, CHROME_PATH
    
    # Проверяем cdp-use
    try:
        from cdp_use.client import CDPClient
        CDP_AVAILABLE = True
        print("✅ cdp-use загружен")
    except ImportError:
        print("⚠️ cdp-use не найден, устанавливаю...")
        if install_cdp_use():
            try:
                from cdp_use.client import CDPClient
                CDP_AVAILABLE = True
                print("✅ cdp-use установлен и загружен")
            except ImportError:
                CDP_AVAILABLE = False
                print("❌ Не удалось загрузить cdp-use")
    
    # Проверяем Chrome
    import shutil
    chrome_path = shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chrome')
    
    if not chrome_path:
        print("⚠️ Chrome не найден, устанавливаю через playwright...")
        chrome_path = install_chrome()
    
    if chrome_path:
        CHROME_PATH = chrome_path
        print(f"✅ Chrome найден: {chrome_path}")
    else:
        print("❌ Chrome не найден")

check_dependencies()

# ========== AGNES ==========

AGNES_AVAILABLE = False
agnes_llm = None

def init_agnes():
    global AGNES_AVAILABLE, agnes_llm
    try:
        from langchain_openai import ChatOpenAI
        
        api_key = os.environ.get("AGNES_API_KEY", "")
        if not api_key:
            print("⚠️ AGNES_API_KEY не установлен")
            return False
        
        llm = ChatOpenAI(
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",
            temperature=0.7,
            api_key=api_key,
        )
        
        test_response = llm.invoke("Test")
        if test_response:
            agnes_llm = llm
            AGNES_AVAILABLE = True
            print("✅ Agnes загружена")
            return True
    except Exception as e:
        print(f"⚠️ Ошибка Agnes: {e}")
    return False

init_agnes()

# ========== КУКИ X.COM ==========

X_COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "v1_DKrxLZAC902dMFdd1QrVYg==", "domain": ".x.com", "path": "/"},
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
cdp_client = None
cdp_session_id = None
chrome_process = None
is_connected = False

# ========== ЗАПУСК БРАУЗЕРА С CDP ==========

def launch_chrome_with_cdp():
    """Запускает Chrome с CDP и возвращает URL для подключения"""
    global chrome_process, CHROME_PATH
    
    if not CHROME_PATH:
        raise Exception("Chrome не найден. Попробуй перезапустить бота для установки.")
    
    # Ищем свободный порт
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    
    # Запускаем Chrome с CDP
    chrome_cmd = [
        CHROME_PATH, '--headless=new',
        f'--remote-debugging-port={port}',
        '--no-sandbox', '--disable-gpu',
        '--disable-dev-shm-usage',
        '--window-size=1280,720',
        'about:blank'
    ]
    
    chrome_process = subprocess.Popen(
        chrome_cmd, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL
    )
    
    # Ждем запуска
    for _ in range(15):
        time.sleep(0.5)
        try:
            import requests
            resp = requests.get(f'http://localhost:{port}/json/version', timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                ws_url = data.get('webSocketDebuggerUrl')
                if ws_url:
                    return ws_url, port
        except:
            continue
    
    chrome_process.terminate()
    chrome_process = None
    raise Exception("Не удалось запустить Chrome с CDP")

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Бот запущен\n"
        f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
        f"cdp-use: {'✅' if CDP_AVAILABLE else '❌'}\n"
        f"Chrome: {'✅' if CHROME_PATH else '❌'}\n"
        f"Браузер: {'✅' if is_connected else '❌'}\n"
        f"Куки: {'✅' if X_COOKIES else '❌'}\n\n"
        f"/login — подключиться к браузеру\n"
        f"/browse <задача> — выполнить в браузере\n"
        f"/agnes — статус Agnes\n"
        f"/close — закрыть браузер"
    )

async def agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if AGNES_AVAILABLE:
        await update.message.reply_text("✅ Agnes готова!")
    else:
        await update.message.reply_text(
            "❌ Agnes не доступна\n\n"
            "1. Получи ключ на https://agnes-ai.com/\n"
            "2. Добавь AGNES_API_KEY=твой_ключ\n"
            "3. Перезапусти бота"
        )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подключение к браузеру через CDP"""
    global cdp_client, cdp_session_id, is_connected, chrome_process
    
    msg = await update.message.reply_text("🔄 Запускаю браузер и подключаюсь...")
    
    if not CDP_AVAILABLE:
        await msg.edit_text("❌ cdp-use не установлен. Перезапусти бота.")
        return
    
    if not CHROME_PATH:
        await msg.edit_text("❌ Chrome не найден. Устанавливаю...")
        chrome_path = install_chrome()
        if chrome_path:
            global CHROME_PATH
            CHROME_PATH = chrome_path
            await msg.edit_text("✅ Chrome установлен! Повтори /login")
        else:
            await msg.edit_text("❌ Не удалось установить Chrome")
        return
    
    try:
        from cdp_use.client import CDPClient
        
        # Запускаем браузер
        await msg.edit_text("🔄 Запускаю Chrome...")
        ws_url, port = launch_chrome_with_cdp()
        
        await msg.edit_text("🔄 Подключаюсь к браузеру...")
        
        # Подключаемся
        cdp_client = CDPClient(ws_url)
        await cdp_client.connect()
        
        # Получаем список целей
        targets = await cdp_client.send.Target.getTargets()
        
        # Ищем или создаем страницу
        target_id = None
        for target in targets.get('targetInfos', []):
            if target.get('type') == 'page':
                target_id = target.get('targetId')
                break
        
        if not target_id:
            create_result = await cdp_client.send.Target.createTarget({
                'url': 'about:blank',
                'width': 1280,
                'height': 720,
            })
            target_id = create_result.get('targetId')
        
        # Прикрепляемся к странице
        attach_result = await cdp_client.send.Target.attachToTarget({
            'targetId': target_id,
            'flatten': True,
        })
        cdp_session_id = attach_result.get('sessionId')
        
        # Включаем домены
        await cdp_client.send.Page.enable(session_id=cdp_session_id)
        await cdp_client.send.DOM.enable(session_id=cdp_session_id)
        
        # Добавляем куки если есть
        if X_COOKIES:
            for cookie in X_COOKIES:
                try:
                    await cdp_client.send.Network.setCookie(
                        name=cookie['name'],
                        value=cookie['value'],
                        domain=cookie['domain'],
                        path=cookie['path'],
                        session_id=cdp_session_id
                    )
                except Exception as e:
                    print(f"⚠️ Ошибка добавления куки {cookie['name']}: {e}")
            print(f"✅ Добавлено {len(X_COOKIES)} кук")
        
        is_connected = True
        
        await msg.edit_text(
            f"✅ **Подключено к браузеру!**\n\n"
            f"Куки: {'✅' if X_COOKIES else '❌'}\n"
            f"Теперь можно использовать:\n"
            f"/browse <задача> — выполнить действие\n"
            f"/close — закрыть браузер"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка подключения: {str(e)[:200]}")
        logger.error(f"Login error: {e}", exc_info=True)

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить задачу в браузере"""
    global cdp_client, cdp_session_id, is_connected
    
    if not context.args:
        await update.message.reply_text("ℹ️ /browse <задача>\nПример: /browse открой google.com")
        return
    
    if not AGNES_AVAILABLE:
        await update.message.reply_text("❌ Agnes не доступна")
        return
    
    if not is_connected:
        await update.message.reply_text(
            "❌ Нет подключения к браузеру.\n"
            "Используй /login для подключения"
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🌐 Выполняю: {task[:100]}...")
    
    try:
        # Используем Agnes для понимания задачи
        prompt = f"""
        Ты — AI-агент, который управляет браузером.
        
        Задача пользователя: {task}
        
        Определи, что нужно сделать и верни только URL или действие.
        """
        
        response = agnes_llm.invoke(prompt)
        action = response.content.strip().lower()
        
        await msg.edit_text(f"🧠 Agnes: {action[:100]}...")
        
        # Выполняем действие
        if 'x.com' in action or 'twitter' in action:
            url = 'https://x.com'
        elif action.startswith('http'):
            url = action
        else:
            url = f"https://{action}"
        
        # Переходим по URL
        await cdp_client.send.Page.navigate({
            'url': url
        }, session_id=cdp_session_id)
        await asyncio.sleep(3)
        
        # Делаем скриншот
        screenshot_result = await cdp_client.send.Page.captureScreenshot(
            session_id=cdp_session_id
        )
        
        if screenshot_result.get('data'):
            image_data = base64.b64decode(screenshot_result['data'])
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                f.write(image_data)
                screenshot_path = f.name
            
            await update.message.reply_photo(
                photo=open(screenshot_path, 'rb'),
                caption=f"📸 {url}"
            )
            os.unlink(screenshot_path)
        
        await msg.edit_text(f"✅ **Открыл: {url}**")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Browse error: {e}", exc_info=True)

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть браузер"""
    global cdp_client, cdp_session_id, is_connected, chrome_process
    
    if not is_connected:
        await update.message.reply_text("❌ Браузер уже закрыт")
        return
    
    try:
        if cdp_client:
            await cdp_client.close()
        
        if chrome_process:
            chrome_process.terminate()
            chrome_process = None
        
        cdp_client = None
        cdp_session_id = None
        is_connected = False
        
        await update.message.reply_text("✅ Браузер закрыт!")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Close error: {e}", exc_info=True)


# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("agnes", agnes))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("close", close))
    
    print("✅ Бот запущен!")
    print(f"🤖 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}")
    print(f"🧠 cdp-use: {'✅' if CDP_AVAILABLE else '❌'}")
    print(f"🌐 Chrome: {'✅' if CHROME_PATH else '❌'}")
    print(f"🍪 Куки: {'✅' if X_COOKIES else '❌'}")
    print("Команды: /start, /agnes, /login, /browse, /close")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()