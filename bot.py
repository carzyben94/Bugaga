import asyncio
import json
import logging
import os
import base64
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Tuple
from pathlib import Path

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)

# ========== ЧИТАЕМ ТОКЕНЫ ИЗ ОКРУЖЕНИЯ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")  # ID сервиса на Render

# Проверка
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")

# Бесплатные модели OpenRouter
FREE_MODELS = [
    "mistralai/mistral-7b-instruct:free",
    "meta-llama/llama-3-8b:free",
    "meta-llama/llama-3-70b:free",
    "google/gemma-2-9b:free",
    "microsoft/phi-2:free",
    "google/gemini-flash-1.5:free",
    "qwen/qwen-2.5-7b:free",
    "nousresearch/hermes-3-llama-3.1-8b:free",
    "cohere/command-r-08-2024:free",
    "liquid/lfm-40b:free"
]

# Глобальные состояния
user_memory: Dict[int, List[dict]] = {}
model_failures: Dict[str, int] = {}
admin_ids = [int(os.environ.get("ADMIN_ID", "0"))]  # Ваш Telegram ID

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== GITHUB API (полный доступ) ==========
def github_api(method: str, endpoint: str, data: dict = None) -> dict:
    """Прямой вызов GitHub API"""
    if not GITHUB_TOKEN:
        return {}
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        
        return response.json() if response.status_code in [200, 201] else {}
    except Exception as e:
        logger.error(f"GitHub API error: {e}")
        return {}

def github_save_file(path: str, content: str, message: str = "Update") -> bool:
    """Сохранить файл в GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    
    # Получаем текущий SHA
    existing = github_api("GET", f"contents/{path}")
    sha = existing.get("sha") if existing else None
    
    # Подготавливаем данные
    data = {
        "message": message,
        "content": base64.b64encode(content.encode('utf-8')).decode('utf-8'),
        "branch": GITHUB_BRANCH
    }
    if sha:
        data["sha"] = sha
    
    result = github_api("PUT", f"contents/{path}", data)
    return bool(result.get("content"))

def github_load_file(path: str) -> str:
    """Загрузить файл из GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return ""
    
    data = github_api("GET", f"contents/{path}")
    if data and "content" in data:
        return base64.b64decode(data["content"]).decode('utf-8')
    return ""

def github_create_issue(title: str, body: str) -> dict:
    """Создать Issue в репозитории"""
    return github_api("POST", "issues", {
        "title": title,
        "body": body,
        "labels": ["bot-report"]
    })

# ========== RENDER API (полный доступ) ==========
def render_api(method: str, endpoint: str, data: dict = None) -> dict:
    """Вызов Render API для управления сервисом"""
    render_api_key = os.environ.get("RENDER_API_KEY")
    if not render_api_key or not RENDER_SERVICE_ID:
        return {}
    
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {render_api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        
        return response.json() if response.status_code in [200, 201, 204] else {}
    except Exception as e:
        logger.error(f"Render API error: {e}")
        return {}

async def restart_render_service():
    """Перезапустить сервис на Render"""
    if RENDER_SERVICE_ID:
        result = render_api("POST", "deploys", {"clearCache": "do_not_clear"})
        return bool(result)
    return False

def get_render_logs(limit: int = 50) -> str:
    """Получить последние логи с Render (через API)"""
    # Render не имеет прямого API для логов, но можно через webhook
    return "Логи доступны в панели Render"

# ========== САМООБНОВЛЕНИЕ ИЗ GITHUB ==========
async def self_update():
    """Обновить код из GitHub и перезапуститься"""
    try:
        # Скачиваем последнюю версию из GitHub
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/bot.py"
        response = requests.get(raw_url)
        
        if response.status_code == 200:
            new_code = response.text
            
            # Сохраняем текущую версию как бэкап
            with open("bot.py.bak", "w") as f:
                f.write(open("bot.py").read())
            
            # Записываем новый код
            with open("bot.py", "w") as f:
                f.write(new_code)
            
            # Перезапускаемся
            logger.info("Обновление успешно, перезапуск...")
            os.execl(sys.executable, sys.executable, *sys.argv)
            return True
    except Exception as e:
        logger.error(f"Self-update error: {e}")
        return False

# ========== OPENROUTER С АВТОПЕРЕКЛЮЧЕНИЕМ ==========
def call_openrouter(model: str, messages: List[dict]) -> Tuple[str, bool]:
    """Вызов модели через OpenRouter"""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            model_failures[model] = 0
            return data["choices"][0]["message"]["content"], True
        elif response.status_code in [429, 402]:
            model_failures[model] = model_failures.get(model, 0) + 1
            return "", False
        else:
            return "", False
    except:
        return "", False

async def get_ai_response(user_id: int, user_message: str) -> str:
    """Автоматическое переключение между моделями"""
    if user_id not in user_memory:
        user_memory[user_id] = []
    
    user_memory[user_id].append({"role": "user", "content": user_message})
    
    if len(user_memory[user_id]) > 15:
        user_memory[user_id] = user_memory[user_id][-15:]
    
    # Пробуем модели по очереди
    for model in FREE_MODELS:
        if model_failures.get(model, 0) >= 5:
            continue
            
        response, success = call_openrouter(model, user_memory[user_id])
        
        if success:
            user_memory[user_id].append({"role": "assistant", "content": response})
            
            # Логируем в GitHub
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "model": model,
                "message_len": len(user_message)
            }
            logs = json.loads(github_load_file("logs/usage.json") or "{}")
            day = datetime.now().strftime("%Y-%m-%d")
            logs.setdefault(day, []).append(log_entry)
            github_save_file("logs/usage.json", json.dumps(logs, indent=2))
            
            return response
    
    return "❌ Все модели временно недоступны. Используйте /status для информации."

# ========== ТЕЛЕГРАМ КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие"""
    keyboard = [
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🗑 Очистить память", callback_data="clear")],
        [InlineKeyboardButton("🔄 Сброс моделей", callback_data="reset")],
        [InlineKeyboardButton("💾 Сохранить в GitHub", callback_data="save")]
    ]
    
    # Админские кнопки
    if update.effective_user.id in admin_ids:
        keyboard.append([InlineKeyboardButton("🔧 Админ-панель", callback_data="admin")])
    
    await update.message.reply_text(
        "🤖 *ИИ-агент с полным доступом*\n\n"
        f"✅ {len(FREE_MODELS)} моделей\n"
        "🔄 Автопереключение при лимитах\n"
        "💾 Автосохранение в GitHub\n"
        "🔄 Самообновление из репозитория\n\n"
        "Просто отправь сообщение!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус"""
    status_text = f"*📊 Статус:*\n\n"
    
    working = 0
    for model in FREE_MODELS:
        short_name = model.split("/")[-1].replace(":free", "")
        failures = model_failures.get(model, 0)
        
        if failures >= 5:
            status_text += f"🔴 `{short_name}` - лимит\n"
        else:
            status_text += f"🟢 `{short_name}` - OK\n"
            working += 1
    
    status_text += f"\n✅ Работает: {working}/{len(FREE_MODELS)}\n"
    status_text += f"👥 Диалогов: {len(user_memory)}\n"
    
    # Статистика из GitHub
    logs = json.loads(github_load_file("logs/usage.json") or "{}")
    today = datetime.now().strftime("%Y-%m-%d")
    today_requests = len(logs.get(today, []))
    status_text += f"📈 Запросов сегодня: {today_requests}"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    keyboard = [
        [InlineKeyboardButton("🔄 Перезапустить Render", callback_data="restart_render")],
        [InlineKeyboardButton("📦 Обновить из GitHub", callback_data="self_update")],
        [InlineKeyboardButton("📊 Логи", callback_data="logs")],
        [InlineKeyboardButton("💾 Бэкап в GitHub", callback_data="backup")],
        [InlineKeyboardButton("🗑 Очистить все диалоги", callback_data="clear_all")]
    ]
    
    await update.message.reply_text(
        "🔧 *Админ-панель*\n\n"
        "Управление ботом и инфраструктурой:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def backup_to_github(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полный бэкап в GitHub"""
    # Сохраняем память пользователей
    memory_data = {str(uid): conv for uid, conv in user_memory.items()}
    github_save_file("backups/memory.json", json.dumps(memory_data, indent=2), 
                    f"Backup {datetime.now().isoformat()}")
    
    # Сохраняем статистику ошибок
    github_save_file("backups/failures.json", json.dumps(model_failures, indent=2))
    
    await update.message.reply_text("✅ Полный бэкап сохранен в GitHub!")

async def clear_all_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить память всех пользователей"""
    if update.effective_user.id not in admin_ids:
        return
    
    user_memory.clear()
    await update.message.reply_text("🧹 Память всех пользователей очищена!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    try:
        response = await get_ai_response(user_id, user_message)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("⚠️ Ошибка, попробуйте позже")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "status":
        await status_command(update, context)
    elif query.data == "clear":
        user_id = update.effective_user.id
        if user_id in user_memory:
            del user_memory[user_id]
        await query.edit_message_text("🧹 Память очищена!")
    elif query.data == "reset":
        model_failures.clear()
        await query.edit_message_text("✅ Все модели разблокированы!")
    elif query.data == "save":
        backup_to_github(update, context)
    elif query.data == "admin":
        await admin_panel(update, context)
    elif query.data == "restart_render":
        if await restart_render_service():
            await query.edit_message_text("🔄 Render перезапускается...")
        else:
            await query.edit_message_text("❌ Ошибка перезапуска")
    elif query.data == "self_update":
        if await self_update():
            await query.edit_message_text("✅ Обновлено, бот перезапускается...")
        else:
            await query.edit_message_text("❌ Ошибка обновления")
    elif query.data == "clear_all":
        await clear_all_memory(update, context)

# ========== MAIN ==========
def main():
    """Запуск"""
    logger.info("🚀 Запуск бота с полным доступом")
    logger.info(f"GitHub: {GITHUB_REPO}")
    logger.info(f"Render: {RENDER_SERVICE_ID}")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("✅ Бот активен!")
    app.run_polling()

if __name__ == "__main__":
    main()
