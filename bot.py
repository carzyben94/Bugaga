import asyncio
import logging
import os
import base64
import requests
import json
import re
import psutil
import platform
import time
import random
from datetime import datetime
from asyncio import TimeoutError
from PIL import Image
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import Key

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    logger.warning("⚠️ AGNES_API_KEY не установлен!")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_PATH = "agent_memory.json"

CHROME_PATH = "/usr/bin/google-chrome"
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
AGNES_IMAGE_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_VISION_URL = "https://apihub.agnes-ai.com/v1/vision/analyze"

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
browser_instance = None
tab_instance = None
current_url = None
page_title = None
page_content = None
start_time = datetime.now()
is_processing = False

# --- ФУНКЦИИ БАЗЫ ДАННЫХ (GitHub) ---
def load_all_memory():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {}
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            content = response.json()['content']
            decoded = base64.b64decode(content).decode('utf-8')
            return json.loads(decoded)
        return {}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return {}

def save_all_memory(data):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        response = requests.get(url, headers=headers)
        sha = response.json().get('sha') if response.status_code == 200 else None
        content = json.dumps(data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {"message": f"Update memory {datetime.now().strftime('%Y-%m-%d %H:%M')}", "content": encoded, "sha": sha}
        response = requests.put(url, json=payload, headers=headers)
        return response.status_code in [200, 201]
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")
        return False

def load_user_memory(user_id):
    all_data = load_all_memory()
    user_key = str(user_id)
    if user_key not in all_data:
        return {"commands": [], "experiments": [], "learned": 0, "created_at": datetime.now().isoformat()}
    return all_data[user_key]

def save_user_memory(user_id, data):
    all_data = load_all_memory()
    all_data[str(user_id)] = data
    return save_all_memory(all_data)

def save_learning(user_id, command, action, context, success):
    data = load_user_memory(user_id)
    data['commands'].append({
        'command': command,
        'action': action,
        'context': context,
        'success': success,
        'created_at': datetime.now().isoformat()
    })
    data['learned'] = len([c for c in data['commands'] if c['success']])
    if len(data['commands']) > 100:
        data['commands'] = data['commands'][-100:]
    return save_user_memory(user_id, data)

def get_learned_actions(user_id, command):
    data = load_user_memory(user_id)
    results = []
    for item in data.get('commands', []):
        if command.lower() in item['command'].lower() and item['success']:
            results.append((item['action'], item['context']))
    return results[:5]

# --- ФУНКЦИИ БРАУЗЕРА ---
def get_browser_options():
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.start_timeout = 30
    return options

async def open_browser():
    global browser_instance, tab_instance
    try:
        if browser_instance is None:
            options = get_browser_options()
            browser_instance = Chrome(options=options)
            await browser_instance.start()
            tab_instance = await browser_instance.start()
            logger.info("✅ Браузер открыт")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def close_browser():
    global browser_instance, tab_instance
    try:
        if browser_instance is not None:
            await browser_instance.stop()
            browser_instance = None
            tab_instance = None
            logger.info("✅ Браузер закрыт")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def safe_go_to_url(url: str, timeout: int = 35):
    """Безопасный переход с таймаутом"""
    global tab_instance, current_url, page_title, page_content
    try:
        if tab_instance is None:
            return False, "Браузер не открыт"
        
        result = await asyncio.wait_for(
            tab_instance.go_to(url),
            timeout=timeout
        )
        current_url = url
        page_title = await tab_instance.title
        try:
            page_content = await tab_instance.get_page_text()
        except:
            page_content = "Текст страницы не доступен"
        return True, f"Перешел на {url}"
    except TimeoutError:
        return False, f"⏰ Страница не загрузилась за {timeout} сек"
    except Exception as e:
        return False, f"❌ {str(e)}"

async def safe_take_screenshot(timeout: int = 20):
    """Безопасный скриншот с таймаутом"""
    global tab_instance
    try:
        if tab_instance is None:
            return None, "Браузер не открыт"
        result = await asyncio.wait_for(
            tab_instance.take_screenshot(beyond_viewport=True, as_base64=True),
            timeout=timeout
        )
        return result, None
    except TimeoutError:
        return None, f"⏰ Скриншот не создался за {timeout} сек"
    except Exception as e:
        return None, f"❌ {str(e)}"

async def get_page_info():
    global current_url, page_title, page_content
    return {
        'url': current_url,
        'title': page_title,
        'content': page_content[:1000] if page_content else None
    }

# --- ФУНКЦИИ MACHINE VISION ---
def analyze_image_with_vision(image_data, prompt: str = "Что на картинке?"):
    if not AGNES_API_KEY:
        return "❌ Agnes Vision не настроен"
    try:
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{img_b64}"
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "agnes-vision-2.0-flash",
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_uri}}]}],
            "max_tokens": 1000
        }
        response = requests.post(AGNES_VISION_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"❌ Vision: {e}")
        return f"❌ Ошибка: {str(e)}"

# --- ФУНКЦИИ AGNES ---
def call_agnes_agent(prompt: str, context: dict = None):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен"
    try:
        system_prompt = """
🤖 ТЫ - PYDOLL-АГЕНТ С МАШИННЫМ ЗРЕНИЕМ!

Ты УПРАВЛЯЕШЬ БРАУЗЕРОМ через Pydoll и ВИДИШЬ страницы через Agnes Vision!

✅ ЧТО ТЫ УМЕЕШЬ:
1. Переходить по ссылкам
2. Делать скриншоты
3. Анализировать страницы через Vision
4. Находить элементы по описанию
5. Кликать на элементы
6. Вводить текст в поля
7. Извлекать данные
8. Учиться новым командам

❌ НЕ ИСПОЛЬЗУЙ КОМАНДЫ БОТА!
Ты ВЫПОЛНЯЕШЬ действия напрямую!

🔥 ТВОЯ СУПЕРСИЛА: Ты видишь страницы как человек!
"""
        messages = [{"role": "system", "content": system_prompt}]
        if context and context.get('url'):
            messages.append({"role": "user", "content": f"Страница: {context['url']}"})
        messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "agnes-2.0-flash", "messages": messages, "max_tokens": 1000}
        response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'], None
    except Exception as e:
        return None, str(e)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def extract_url(text: str) -> str:
    url_match = re.search(r'(https?://[^\s]+|google\.com|vk\.com|youtube\.com|yandex\.ru)', text, re.IGNORECASE)
    if url_match:
        url = url_match.group(0)
        if not url.startswith('http'):
            url = 'https://' + url
        return url
    if 'ютуб' in text.lower() or 'youtube' in text.lower():
        return 'https://youtube.com'
    if 'вк' in text.lower() or 'vk' in text.lower():
        return 'https://vk.com'
    return None

def extract_command(text: str) -> str:
    for word in ['ютуб', 'youtube', 'вк', 'vk', 'google']:
        if word in text.lower():
            return word
    return text[:20]

# --- ОСНОВНАЯ ЛОГИКА АГЕНТА ---
async def process_agent_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_request: str):
    """Основная логика с таймаутами"""
    global is_processing
    
    if is_processing:
        await update.message.reply_text("⏳ Агент уже работает. Подождите...")
        return
    
    is_processing = True
    user_id = update.effective_user.id
    
    try:
        # Проверяем выученные команды
        learned = get_learned_actions(user_id, user_request)
        if learned:
            action = learned[0][0]
            await update.message.reply_text(f"🧠 Знаю! Делаю: {action}")
            await execute_action(update, action)
            is_processing = False
            return
        
        # Анализ через Agnes с таймаутом
        page_info = await get_page_info()
        
        try:
            agnes_response, error = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    call_agnes_agent,
                    f"Пользователь: {user_request}\nЧто нужно сделать?",
                    page_info
                ),
                timeout=25
            )
        except TimeoutError:
            await update.message.reply_text("⏰ Agnes AI долго думает. Попробуйте переформулировать.")
            is_processing = False
            return
        
        if error:
            await update.message.reply_text(f"❌ Ошибка: {error}")
            is_processing = False
            return
        
        request_lower = user_request.lower()
        
        # --- ПЕРЕХОД НА САЙТ ---
        if any(word in request_lower for word in ['перейди', 'зайди', 'открой', 'ютуб', 'youtube', 'вк', 'vk', 'google']):
            url = extract_url(user_request)
            if url:
                await update.message.reply_text(f"🌐 Перехожу на {url}...")
                success, msg = await safe_go_to_url(url, timeout=35)
                if success:
                    screenshot_data, _ = await safe_take_screenshot(timeout=15)
                    if screenshot_data:
                        screenshot_bytes = base64.b64decode(screenshot_data)
                        await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
                    await update.message.reply_text(f"✅ {msg}")
                    save_learning(user_id, extract_command(user_request), url, "auto_learn", True)
                else:
                    await update.message.reply_text(f"❌ {msg}")
                is_processing = False
                return
        
        # --- СКРИНШОТ ---
        elif any(word in request_lower for word in ['скрин', 'screenshot']):
            await update.message.reply_text("📸 Делаю скриншот...")
            screenshot_data, error = await safe_take_screenshot(timeout=15)
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
            else:
                await update.message.reply_text(f"❌ {error}")
            is_processing = False
            return
        
        # --- АНАЛИЗ СТРАНИЦЫ (Vision) ---
        elif any(word in request_lower for word in ['что на странице', 'анализ', 'что видишь', 'описание']):
            await update.message.reply_text("👁️ Анализирую страницу...")
            screenshot_data, error = await safe_take_screenshot(timeout=15)
            if not screenshot_data:
                await update.message.reply_text(f"❌ {error}")
                is_processing = False
                return
            
            if isinstance(screenshot_data, str):
                screenshot_bytes = base64.b64decode(screenshot_data)
            else:
                screenshot_bytes = screenshot_data
            
            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        analyze_image_with_vision,
                        screenshot_bytes,
                        "Опиши подробно, что на этой странице"
                    ),
                    timeout=20
                )
                await update.message.reply_photo(screenshot_bytes, caption=f"👁️ **Анализ:**\n{result[:500]}...")
            except TimeoutError:
                await update.message.reply_text("⏰ Vision слишком долго анализирует.")
            is_processing = False
            return
        
        # --- ПОИСК ЭЛЕМЕНТА (Vision) ---
        elif any(word in request_lower for word in ['найди', 'где', 'покажи', 'кнопка', 'поле']):
            await update.message.reply_text("🔍 Ищу элемент...")
            screenshot_data, error = await safe_take_screenshot(timeout=15)
            if not screenshot_data:
                await update.message.reply_text(f"❌ {error}")
                is_processing = False
                return
            
            if isinstance(screenshot_data, str):
                screenshot_bytes = base64.b64decode(screenshot_data)
            else:
                screenshot_bytes = screenshot_data
            
            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        analyze_image_with_vision,
                        screenshot_bytes,
                        f"Найди на этой странице: {user_request}. Опиши расположение, цвет, текст, как найти."
                    ),
                    timeout=20
                )
                await update.message.reply_photo(screenshot_bytes, caption=f"🔍 **Результат:**\n{result[:500]}...")
            except TimeoutError:
                await update.message.reply_text("⏰ Vision слишком долго ищет.")
            is_processing = False
            return
        
        # --- ЗАМЕНА ФОНА ---
        elif any(word in request_lower for word in ['замени фон', 'смени фон']):
            if 'last_image' not in context.user_data:
                await update.message.reply_text("📸 Сначала отправьте фото!")
                is_processing = False
                return
            
            bg_match = re.search(r'фон\s+на\s+(.+)', request_lower)
            if not bg_match:
                await update.message.reply_text("✏️ Укажите фон. Например: 'замени фон на ночь'")
                is_processing = False
                return
            
            bg_prompt = bg_match.group(1)
            await update.message.reply_text(f"🎨 Заменяю фон на: {bg_prompt}...")
            image_data = context.user_data['last_image']
            img_b64 = base64.b64encode(image_data).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{img_b64}"
            headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "agnes-image-2.0-flash",
                "prompt": f"Replace the background with: {bg_prompt}. Keep the main subject unchanged.",
                "size": "1024x1024",
                "extra_body": {"image": [data_uri], "response_format": "url"}
            }
            try:
                response = requests.post(AGNES_IMAGE_URL, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                result_url = response.json()['data'][0]['url']
                img_response = requests.get(result_url, timeout=30)
                if img_response.status_code == 200:
                    await update.message.reply_photo(img_response.content, caption=f"🖼️ Готово! {bg_prompt}")
                else:
                    await update.message.reply_text("❌ Ошибка загрузки")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            is_processing = False
            return
        
        # --- ОБУЧЕНИЕ В ДИАЛОГЕ ---
        elif 'запомни' in request_lower and '->' in request_lower:
            match = re.search(r'запомни\s+"?([^"]+)"?\s*->\s*"?([^"]+)"?', request_lower)
            if match:
                command = match.group(1).strip()
                action = match.group(2).strip()
                if save_learning(user_id, command, action, "dialog_learning", True):
                    await update.message.reply_text(f"✅ Запомнил! 💾\n{command} -> {action}")
            is_processing = False
            return
        
        # --- ЕСЛИ НИЧЕГО НЕ ПОДОШЛО ---
        else:
            await update.message.reply_text(f"🤖 {agnes_response}")
            is_processing = False
            return
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}\n\nПопробуйте /stop или /restart")
        is_processing = False

async def execute_action(update, action):
    """Выполняет действие напрямую"""
    action_lower = action.lower()
    
    if any(word in action_lower for word in ['youtube', 'ютуб']):
        success, msg = await safe_go_to_url("https://youtube.com", timeout=30)
        if success:
            screenshot_data, _ = await safe_take_screenshot(timeout=15)
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
            await update.message.reply_text(f"✅ {msg}")
    elif any(word in action_lower for word in ['vk', 'вк']):
        success, msg = await safe_go_to_url("https://vk.com", timeout=30)
        if success:
            screenshot_data, _ = await safe_take_screenshot(timeout=15)
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
            await update.message.reply_text(f"✅ {msg}")
    elif 'скрин' in action_lower or 'screen' in action_lower:
        screenshot_data, error = await safe_take_screenshot(timeout=15)
        if screenshot_data:
            screenshot_bytes = base64.b64decode(screenshot_data)
            await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
        else:
            await update.message.reply_text(f"❌ {error}")
    else:
        await update.message.reply_text(f"⚠️ Не знаю как выполнить: {action}")

# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Я - твой AI-агент с машинным зрением!**\n\n"
        "Просто напиши что нужно сделать:\n"
        "• перейди на ютуб\n"
        "• сделай скриншот\n"
        "• найди кнопку Войти\n"
        "• что на странице?\n"
        "• замени фон на фото\n"
        "• запомни вк -> vk.com\n\n"
        "Я понимаю естественный язык и вижу страницы!\n\n"
        "📋 **Команды:**\n"
        "/agent - начать работу\n"
        "/status - статус системы\n"
        "/open_bw - открыть браузер\n"
        "/close_bw - закрыть браузер\n"
        "/stop - остановить агента\n"
        "/restart - перезапустить браузер\n"
        "/reset_memory - очистить память"
    )

async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🤖 **Я готов!**\n\n"
            "Просто напиши что нужно сделать.\n"
            "Например:\n"
            "• перейди на ютуб\n"
            "• найди кнопку Войти\n"
            "• что на странице?"
        )
        context.user_data['dialog_active'] = True
        context.user_data['dialog_history'] = []
        return
    
    user_request = ' '.join(context.args)
    context.user_data['dialog_active'] = True
    if 'dialog_history' not in context.user_data:
        context.user_data['dialog_history'] = []
    
    await process_agent_request(update, context, user_request)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = load_user_memory(user_id)
    browser_status = "🟢 Включен" if browser_instance is not None else "🔴 Выключен"
    agnes_status = "✅ Настроен" if AGNES_API_KEY else "❌ Не настроен"
    github_status = "✅ Подключен" if GITHUB_TOKEN and GITHUB_REPO else "❌ Не подключен"
    uptime = str(datetime.now() - start_time).split('.')[0]
    
    await update.message.reply_text(
        f"📊 **Статус:**\n\n"
        f"🖥️ Браузер: {browser_status}\n"
        f"🤖 Agnes AI: {agnes_status}\n"
        f"💾 GitHub: {github_status}\n"
        f"🧠 Выучено команд: {user_data.get('learned', 0)}\n"
        f"⏱️ Работает: {uptime}\n"
        f"🔄 Активна: {'Да' if is_processing else 'Нет'}\n\n"
        f"💡 Просто напиши что нужно сделать!"
    )

async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌐 Открываю браузер...")
    success = await open_browser()
    await update.message.reply_text("✅ Браузер открыт!" if success else "❌ Не удалось открыть браузер")

async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Закрываю браузер...")
    success = await close_browser()
    await update.message.reply_text("✅ Браузер закрыт!" if success else "❌ Не удалось закрыть браузер")

async def stop_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_processing
    is_processing = False
    await update.message.reply_text("🛑 Агент остановлен!")

async def restart_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Перезапускаю браузер...")
    await close_browser()
    await asyncio.sleep(1)
    success = await open_browser()
    await update.message.reply_text("✅ Браузер перезапущен!" if success else "❌ Не удалось перезапустить")

async def reset_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = {"commands": [], "experiments": [], "learned": 0, "created_at": datetime.now().isoformat()}
    if save_user_memory(user_id, data):
        await update.message.reply_text("🧹 Память очищена!")
    else:
        await update.message.reply_text("❌ Ошибка очистки памяти")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    if user_message.startswith('/'):
        return
    
    if not context.user_data.get('dialog_active', False):
        await update.message.reply_text(
            "🤖 Я готов помочь!\n"
            "Просто напиши что нужно сделать, или используй /agent"
        )
        context.user_data['dialog_active'] = True
        context.user_data['dialog_history'] = []
        return
    
    await process_agent_request(update, context, user_message)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        context.user_data['last_image'] = bytes(photo_bytes)
        await update.message.reply_text("📸 Фото сохранено!\nСкажи: 'замени фон на ...'")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ Произошла ошибка.\n"
            "Попробуйте /stop или /restart"
        )

# --- ГЛАВНАЯ ФУНКЦИЯ ---
def main():
    try:
        application = Application.builder().token(TOKEN).build()

        # Основные команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("agent", agent_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("open_bw", open_browser_command))
        application.add_handler(CommandHandler("close_bw", close_browser_command))
        application.add_handler(CommandHandler("stop", stop_agent_command))
        application.add_handler(CommandHandler("restart", restart_browser_command))
        application.add_handler(CommandHandler("reset_memory", reset_memory_command))
        
        # Обработчики сообщений
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        logger.info("🤖 Агент понимает естественный язык и видит страницы!")
        logger.info("📋 Команды: /agent, /status, /open_bw, /close_bw, /stop, /restart")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()