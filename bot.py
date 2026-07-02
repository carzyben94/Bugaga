# test_bot.py - cdp-use с /login и /browse
import os
import sys
import subprocess
import logging
import asyncio
import tempfile
import base64
import time
import socket
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== НАСТРОЙКА ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
cdp_client = None
cdp_session_id = None
chrome_process = None
is_connected = False

# ========== УСТАНОВКА CDP-USE ==========

def install_cdp_use():
    try:
        print("⏳ Устанавливаю cdp-use...")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'cdp-use', '--no-cache-dir'
        ], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ cdp-use установлен")
            return True
        else:
            print(f"❌ Ошибка: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

try:
    from cdp_use.client import CDPClient
    print("✅ cdp-use уже установлен")
    CDP_AVAILABLE = True
except ImportError:
    print("⚠️ cdp-use не найден, устанавливаю...")
    if install_cdp_use():
        try:
            from cdp_use.client import CDPClient
            CDP_AVAILABLE = True
            print("✅ cdp-use импортирован после установки")
        except ImportError:
            CDP_AVAILABLE = False
            print("❌ Не удалось импортировать cdp-use")
    else:
        CDP_AVAILABLE = False

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

# ========== ЗАПУСК БРАУЗЕРА ==========

def launch_chrome_with_cdp():
    """Запускает Chrome с CDP и возвращает URL для подключения"""
    global chrome_process
    
    # Ищем свободный порт
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    
    # Запускаем Chrome с CDP
    chrome_cmd = [
        'google-chrome', '--headless=new',
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
    for _ in range(10):
        time.sleep(0.5)
        try:
            import requests
            resp = requests.get(f'http://localhost:{port}/json/version', timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                ws_url = data.get('webSocketDebuggerUrl')
                if ws_url:
                    return ws_url
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
        f"Браузер: {'✅' if is_connected else '❌'}\n\n"
        f"/login — подключиться к браузеру\n"
        f"/browse <задача> — выполнить в браузере\n"
        f"/agnes — статус Agnes\n"
        f"/install — установить cdp-use\n"
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

async def install(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Устанавливаю cdp-use...")
    try:
        if install_cdp_use():
            await msg.edit_text("✅ cdp-use установлен! Перезапусти бота.")
        else:
            await msg.edit_text("❌ Ошибка установки. Попробуй вручную: pip install cdp-use")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подключение к браузеру через CDP"""
    global cdp_client, cdp_session_id, is_connected, chrome_process
    
    msg = await update.message.reply_text("🔄 Запускаю браузер и подключаюсь...")
    
    if not CDP_AVAILABLE:
        await msg.edit_text("❌ cdp-use не установлен. Используй /install")
        return
    
    try:
        from cdp_use.client import CDPClient
        
        # Запускаем браузер
        await msg.edit_text("🔄 Запускаю Chrome...")
        ws_url = launch_chrome_with_cdp()
        
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
        
        is_connected = True
        
        await msg.edit_text(
            f"✅ **Подключено к браузеру!**\n\n"
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
        
        Определи, что нужно сделать:
        1. Если это переход на сайт — верни только URL
        2. Если это поиск — верни: search: запрос
        3. Если это скриншот — верни: screenshot: URL
        
        Ответь кратко, только действие.
        """
        
        response = agnes_llm.invoke(prompt)
        action = response.content.strip().lower()
        
        await msg.edit_text(f"🧠 Agnes: {action[:100]}...")
        
        # Выполняем действие
        if action.startswith('http'):
            # Переход по URL
            await cdp_client.send.Page.navigate({
                'url': action
            }, session_id=cdp_session_id)
            await asyncio.sleep(2)
            
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
                    caption=f"📸 {action}"
                )
                os.unlink(screenshot_path)
            
            await msg.edit_text(f"✅ **Перешел на: {action}**")
            
        elif action.startswith('search:'):
            # Поиск
            query = action.replace('search:', '').strip()
            search_url = f"https://google.com/search?q={query.replace(' ', '+')}"
            
            await cdp_client.send.Page.navigate({
                'url': search_url
            }, session_id=cdp_session_id)
            await asyncio.sleep(2)
            
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
                    caption=f"🔍 Поиск: {query}"
                )
                os.unlink(screenshot_path)
            
            await msg.edit_text(f"✅ **Выполнил поиск: {query}**")
            
        elif action.startswith('screenshot:'):
            # Скриншот
            url = action.replace('screenshot:', '').strip()
            if not url.startswith('http'):
                url = f"https://{url}"
            
            await cdp_client.send.Page.navigate({
                'url': url
            }, session_id=cdp_session_id)
            await asyncio.sleep(2)
            
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
            
            await msg.edit_text(f"✅ **Скриншот сделан: {url}**")
            
        else:
            # Если Agnes не поняла задачу — пробуем перейти по ссылке
            if 'google' in task.lower() or 'x.com' in task.lower():
                url = task.split()[0] if task.split() else 'https://google.com'
                if not url.startswith('http'):
                    url = f"https://{url}"
                
                await cdp_client.send.Page.navigate({
                    'url': url
                }, session_id=cdp_session_id)
                await asyncio.sleep(2)
                
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
            else:
                await msg.edit_text(f"⚠️ Agnes не поняла задачу.\nОтвет: {action}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Browse error: {e}", exc_info=True)

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть браузер"""
    global cdp_client, cdp_session_id, is_connected, chrome_process
    
    if not is_connected:
        await update.message.reply_text("❌ Браузер уже закрыт или не был подключен")
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
    app.add_handler(CommandHandler("install", install))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("close", close))
    
    print("✅ Бот запущен!")
    print(f"🤖 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}")
    print(f"🧠 cdp-use: {'✅' if CDP_AVAILABLE else '❌'}")
    print("Команды:")
    print("  /start, /agnes, /install, /login, /browse, /close")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()