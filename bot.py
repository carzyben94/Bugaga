#!/usr/bin/env python3
"""
Telegram-бот для управления CloakBrowser + Playwright + Xvfb
С интеграцией Railway API для сбора логов
Автоматически устанавливает все зависимости при первом запуске
"""


import os
import sys
import subprocess
import asyncio
import logging
import tempfile
import shutil
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# ===== АВТОУСТАНОВЩИК =====

def install_dependencies():
    """Автоматическая установка всех зависимостей"""
    
    print("🔧 Проверка и установка зависимостей...")
    
    # 1. Проверяем Python версию
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        sys.exit(1)
    
    # 2. Устанавливаем pip пакеты
    packages = [
        "python-telegram-bot>=21.5",
        "playwright>=1.56.0",
        "cloakbrowser>=0.1.0",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",  # <--- ДОБАВЛЯЕМ requests
    ]
    
    for pkg in packages:
        print(f"📦 Устанавливаю {pkg}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pkg],
            check=False,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"⚠️ Ошибка установки {pkg}: {result.stderr[:200]}")
    
    # 3. Устанавливаем Playwright браузеры
    print("🌐 Устанавливаю Playwright Chromium...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
        capture_output=True
    )
    
    # 4. Проверяем Xvfb (только на Linux)
    if sys.platform == "linux":
        if not shutil.which("Xvfb"):
            print("⚠️ Xvfb не найден. Установите вручную: sudo apt-get install xvfb")
            print("⚠️ Или используйте headless=True")
        else:
            print("✅ Xvfb найден")
    
    print("✅ Все зависимости установлены!")
    print("=" * 50)

# Запускаем установку при первом импорте
if os.environ.get("SKIP_INSTALL") != "true":
    install_dependencies()

# ===== ИМПОРТЫ ПОСЛЕ УСТАНОВКИ =====

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    from playwright.async_api import async_playwright
    from cloakbrowser import launch
    import requests  # <--- ИМПОРТИРУЕМ requests
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("🔄 Перезапустите скрипт для повторной установки")
    sys.exit(1)

# ===== НАСТРОЙКИ =====

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не найден!")
    print("📝 Установите переменную окружения:")
    print("   export TELEGRAM_BOT_TOKEN='ваш_токен'")
    sys.exit(1)

PROXY_URL = os.environ.get('PROXY_URL', '')
HEADLESS = os.environ.get('HEADLESS', 'false').lower() == 'true'
DISPLAY = os.environ.get('DISPLAY', ':99')

# Настройки Railway API
RAILWAY_API_KEY = os.environ.get('RAILWAY_API_KEY', '')
RAILWAY_PROJECT_ID = os.environ.get('RAILWAY_PROJECT_ID', '')
RAILWAY_SERVICE_ID = os.environ.get('RAILWAY_SERVICE_ID', '')
RAILWAY_ENVIRONMENT_ID = os.environ.get('RAILWAY_ENVIRONMENT_ID', '')

# Настройки логирования
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_FILE = os.environ.get('LOG_FILE', 'bot.log')

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)

# ===== RAILWAY API КЛИЕНТ =====

class RailwayAPIClient:
    """Клиент для работы с Railway API"""
    
    BASE_URL = "https://railway.app/api/v2"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_project_logs(self, project_id: str, service_id: str = None, 
                         environment_id: str = None, limit: int = 100) -> Optional[List[Dict]]:
        """
        Получить логи проекта из Railway
        
        Args:
            project_id: ID проекта
            service_id: ID сервиса (опционально)
            environment_id: ID окружения (опционально)
            limit: Количество последних записей
            
        Returns:
            Список логов или None при ошибке
        """
        try:
            # Используем REST API для получения логов
            url = f"{self.BASE_URL}/projects/{project_id}/deployments"
            
            # Получаем список деплоев
            response = self.session.get(url)
            
            if response.status_code != 200:
                logger.error(f"Ошибка получения деплоев: {response.status_code}")
                return None
            
            deployments = response.json()
            
            if not deployments:
                return []
            
            # Берем последний успешный деплой
            latest_deployment = None
            for deploy in deployments:
                if deploy.get('status') == 'SUCCESS':
                    latest_deployment = deploy
                    break
            
            if not latest_deployment:
                # Если нет успешных, берем последний
                latest_deployment = deployments[0] if deployments else None
            
            if not latest_deployment:
                return []
            
            # Получаем логи деплоя
            deployment_id = latest_deployment.get('id')
            logs_url = f"{self.BASE_URL}/deployments/{deployment_id}/logs"
            
            response = self.session.get(logs_url, params={"limit": limit})
            
            if response.status_code != 200:
                logger.error(f"Ошибка получения логов: {response.status_code}")
                # Пробуем альтернативный метод через GraphQL
                return self._get_logs_graphql(project_id, limit)
            
            logs_data = response.json()
            
            # Форматируем логи
            logs = []
            for log in logs_data.get('logs', []):
                logs.append({
                    "message": log.get('message', ''),
                    "timestamp": log.get('timestamp', ''),
                    "level": log.get('level', 'INFO'),
                    "deployment_id": deployment_id,
                    "deployment_status": latest_deployment.get('status', '')
                })
            
            return logs[-limit:] if logs else []
            
        except Exception as e:
            logger.error(f"Исключение при получении логов: {e}")
            # Пробуем GraphQL как fallback
            try:
                return self._get_logs_graphql(project_id, limit)
            except:
                return None
    
    def _get_logs_graphql(self, project_id: str, limit: int = 100) -> Optional[List[Dict]]:
        """Получение логов через GraphQL API (fallback)"""
        try:
            query = """
            query GetDeployments($projectId: String!, $limit: Int!) {
                deployments(projectId: $projectId, first: $limit) {
                    edges {
                        node {
                            id
                            status
                            createdAt
                            logs {
                                edges {
                                    node {
                                        message
                                        timestamp
                                        level
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """
            
            variables = {
                "projectId": project_id,
                "limit": limit
            }
            
            response = self.session.post(
                f"{self.BASE_URL}/graphql",
                json={"query": query, "variables": variables}
            )
            
            if response.status_code == 200:
                data = response.json()
                logs = []
                
                for deployment in data.get("data", {}).get("deployments", {}).get("edges", []):
                    deployment_node = deployment.get("node", {})
                    logs_data = deployment_node.get("logs", {}).get("edges", [])
                    
                    for log_edge in logs_data:
                        log_node = log_edge.get("node", {})
                        logs.append({
                            "message": log_node.get("message", ""),
                            "timestamp": log_node.get("timestamp", ""),
                            "level": log_node.get("level", "INFO"),
                            "deployment_id": deployment_node.get("id", ""),
                            "deployment_status": deployment_node.get("status", "")
                        })
                
                return logs[-limit:] if logs else []
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка GraphQL запроса: {e}")
            return None
    
    def get_recent_logs(self, limit: int = 50) -> Optional[List[Dict]]:
        """
        Получить последние логи для текущего сервиса
        
        Args:
            limit: Количество записей
            
        Returns:
            Список логов
        """
        return self.get_project_logs(RAILWAY_PROJECT_ID, limit=limit)
    
    def get_service_status(self) -> Optional[Dict]:
        """Получить статус сервиса"""
        try:
            url = f"{self.BASE_URL}/projects/{RAILWAY_PROJECT_ID}/services/{RAILWAY_SERVICE_ID}"
            response = self.session.get(url)
            
            if response.status_code == 200:
                return response.json()
            
            return None
        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}")
            return None
    
    def restart_service(self) -> bool:
        """Перезапустить сервис на Railway"""
        if not RAILWAY_SERVICE_ID:
            return False
        
        try:
            url = f"{self.BASE_URL}/projects/{RAILWAY_PROJECT_ID}/services/{RAILWAY_SERVICE_ID}/restart"
            response = self.session.post(url)
            
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ошибка перезапуска сервиса: {e}")
            return False
    
    def get_deployment_status(self) -> Optional[Dict]:
        """Получить статус последнего деплоя"""
        try:
            url = f"{self.BASE_URL}/projects/{RAILWAY_PROJECT_ID}/deployments"
            response = self.session.get(url, params={"limit": 1})
            
            if response.status_code == 200:
                deployments = response.json()
                if deployments:
                    return deployments[0]
            
            return None
        except Exception as e:
            logger.error(f"Ошибка получения статуса деплоя: {e}")
            return None

# ===== БРАУЗЕРНАЯ ЛОГИКА =====

async def launch_browser():
    """Запускает CloakBrowser с правильными настройками"""
    try:
        return await launch(
            headless=HEADLESS,
            proxy=PROXY_URL if PROXY_URL else None,
            geoip=bool(PROXY_URL),
            humanize=True,
            timeout=60000,
            args=['--disable-blink-features=AutomationControlled']
        )
    except Exception as e:
        logger.error(f"Ошибка запуска браузера: {e}")
        return None

async def open_x_com():
    """Открыть X.com и вернуть информацию"""
    browser = await launch_browser()
    if not browser:
        return "❌ Не удалось запустить браузер"
    
    try:
        page = await browser.new_page()
        await page.goto('https://x.com', wait_until='networkidle', timeout=30000)
        title = await page.title()
        url = page.url
        await browser.close()
        return f"✅ X.com загружен\n📄 Заголовок: {title}\n🔗 URL: {url}"
    except Exception as e:
        await browser.close()
        return f"❌ Ошибка: {str(e)[:200]}"

async def take_screenshot():
    """Сделать скриншот и сохранить во временный файл"""
    browser = await launch_browser()
    if not browser:
        return None
    
    try:
        page = await browser.new_page()
        await page.goto('https://x.com', wait_until='networkidle', timeout=30000)
        
        # Сохраняем во временный файл
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        await page.screenshot(path=temp_file.name, full_page=True)
        await browser.close()
        return temp_file.name
    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")
        await browser.close()
        return None

async def check_status():
    """Проверка статуса всех компонентов"""
    status = []
    status.append(f"🤖 Бот: ✅ работает")
    status.append(f"🐍 Python: {sys.version}")
    status.append(f"🖥️ DISPLAY: {DISPLAY}")
    status.append(f"🌐 Headless: {HEADLESS}")
    status.append(f"🔌 Proxy: {'✅ установлен' if PROXY_URL else '❌ не используется'}")
    
    # Проверяем Xvfb
    if sys.platform == "linux" and shutil.which("Xvfb"):
        status.append("🖥️ Xvfb: ✅ установлен")
    else:
        status.append("🖥️ Xvfb: ❌ не найден")
    
    # Проверяем Railway API
    if RAILWAY_API_KEY:
        status.append("🚂 Railway API: ✅ подключен")
        status.append(f"📦 Проект: {RAILWAY_PROJECT_ID or 'не указан'}")
        status.append(f"🔧 Сервис: {RAILWAY_SERVICE_ID or 'не указан'}")
    else:
        status.append("🚂 Railway API: ❌ не настроен")
    
    # Проверяем зависимости
    try:
        import requests
        status.append("📦 Requests: ✅ установлен")
    except:
        status.append("📦 Requests: ❌ не установлен")
    
    return "\n".join(status)

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ЛОГАМИ =====

def format_logs(logs: List[Dict], limit: int = 20) -> str:
    """Форматирует логи для отображения в Telegram"""
    if not logs:
        return "📭 Логи не найдены"
    
    formatted = ["📋 *Последние логи Railway:*\n"]
    formatted.append(f"📊 Всего записей: {len(logs)}\n")
    
    # Берем последние limit записей
    recent_logs = logs[-limit:]
    
    for i, log in enumerate(recent_logs, 1):
        timestamp = log.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.strftime('%H:%M:%S')
            except:
                timestamp = timestamp[:8] if len(timestamp) >= 8 else timestamp
        
        level = log.get('level', 'INFO')
        message = log.get('message', '')
        
        # Эмодзи для уровня лога
        level_emoji = {
            'ERROR': '❌',
            'WARNING': '⚠️',
            'INFO': 'ℹ️',
            'DEBUG': '🔍'
        }.get(level, '📝')
        
        # Обрезаем длинные сообщения
        if len(message) > 100:
            message = message[:97] + '...'
        
        formatted.append(
            f"{i}. {level_emoji} `{timestamp}` {level}: {message}"
        )
    
    # Если слишком много текста, отправляем частями
    return "\n".join(formatted)

async def get_railway_logs(context: ContextTypes.DEFAULT_TYPE, limit: int = 50) -> str:
    """Получить логи из Railway API"""
    if not RAILWAY_API_KEY:
        return "❌ Railway API ключ не настроен. Установите переменную RAILWAY_API_KEY"
    
    if not RAILWAY_PROJECT_ID:
        return "❌ Railway Project ID не настроен. Установите переменную RAILWAY_PROJECT_ID"
    
    try:
        client = RailwayAPIClient(RAILWAY_API_KEY)
        logs = client.get_recent_logs(limit=limit)
        
        if logs is None:
            return "❌ Ошибка получения логов из Railway API\n\nПроверьте:\n• API ключ\n• Project ID\n• Доступ к интернету"
        
        if not logs:
            return "📭 Логи не найдены. Возможно, деплой еще не выполнялся."
        
        return format_logs(logs, limit=min(limit, 20))
        
    except Exception as e:
        logger.error(f"Ошибка получения логов: {e}")
        return f"❌ Ошибка: {str(e)[:200]}"

async def get_service_status_text() -> str:
    """Получить статус сервиса Railway"""
    if not RAILWAY_API_KEY or not RAILWAY_PROJECT_ID:
        return "❌ Railway API не настроен"
    
    try:
        client = RailwayAPIClient(RAILWAY_API_KEY)
        
        # Получаем статус сервиса
        service_status = client.get_service_status()
        deployment_status = client.get_deployment_status()
        
        lines = [
            "🚂 *Статус сервиса Railway*",
            "=" * 30
        ]
        
        if service_status:
            lines.append(f"📊 Статус: {service_status.get('status', 'Неизвестно')}")
            lines.append(f"🔄 Реплики: {service_status.get('replicas', 'N/A')}")
            lines.append(f"📦 Память: {service_status.get('memory', 'N/A')}")
            lines.append(f"💾 CPU: {service_status.get('cpu', 'N/A')}")
        else:
            lines.append("❌ Не удалось получить статус сервиса")
        
        if deployment_status:
            lines.append("")
            lines.append("*Последний деплой:*")
            lines.append(f"📅 Создан: {deployment_status.get('createdAt', 'N/A')[:19]}")
            lines.append(f"📊 Статус: {deployment_status.get('status', 'N/A')}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        return f"❌ Ошибка: {str(e)[:200]}"

async def restart_railway_service() -> str:
    """Перезапустить сервис на Railway"""
    if not RAILWAY_API_KEY:
        return "❌ Railway API ключ не настроен"
    
    if not RAILWAY_SERVICE_ID:
        return "❌ Service ID не указан. Установите RAILWAY_SERVICE_ID"
    
    try:
        client = RailwayAPIClient(RAILWAY_API_KEY)
        success = client.restart_service()
        
        if success:
            return "✅ Сервис успешно перезапущен\n🔄 Ожидайте перезагрузки (1-2 минуты)"
        else:
            return "❌ Не удалось перезапустить сервис\nПроверьте права доступа API ключа"
            
    except Exception as e:
        logger.error(f"Ошибка перезапуска: {e}")
        return f"❌ Ошибка: {str(e)[:200]}"

# ===== КОМАНДЫ ТЕЛЕГРАМ =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и главное меню"""
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть X.com", callback_data='open_x')],
        [InlineKeyboardButton("📸 Сделать скриншот", callback_data='screenshot')],
        [InlineKeyboardButton("📊 Статус системы", callback_data='status')],
        [InlineKeyboardButton("📋 Логи Railway", callback_data='logs')],
        [InlineKeyboardButton("🚂 Статус Railway", callback_data='railway_status')],
        [InlineKeyboardButton("🔄 Перезапустить сервис", callback_data='restart_service')],
        [InlineKeyboardButton("📖 Помощь", callback_data='help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *Бот управления браузером + Railway*\n\n"
        "Стек: Playwright + CloakBrowser + Xvfb\n"
        "Интеграция: Railway API для мониторинга\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'open_x':
        await query.edit_message_text("⏳ Открываю X.com... Это может занять 10-30 секунд")
        result = await open_x_com()
        await query.edit_message_text(result)
    
    elif data == 'screenshot':
        await query.edit_message_text("📸 Делаю скриншот X.com...")
        screenshot_path = await take_screenshot()
        if screenshot_path:
            await query.edit_message_text("✅ Скриншот готов!")
            with open(screenshot_path, 'rb') as photo:
                await query.message.reply_photo(photo=photo)
            os.unlink(screenshot_path)
        else:
            await query.edit_message_text("❌ Не удалось сделать скриншот")
    
    elif data == 'status':
        status_text = await check_status()
        await query.edit_message_text(f"📊 *Статус системы*\n\n{status_text}", parse_mode='Markdown')
    
    elif data == 'logs':
        await query.edit_message_text("⏳ Получаю логи из Railway...")
        logs_text = await get_railway_logs(context, limit=50)
        
        # Если текст слишком длинный, отправляем по частям
        if len(logs_text) > 4000:
            # Отправляем первые строки
            await query.edit_message_text(logs_text[:4000])
            # Отправляем остаток новым сообщением
            await query.message.reply_text(logs_text[4000:8000])
        else:
            await query.edit_message_text(logs_text, parse_mode='Markdown')
    
    elif data == 'railway_status':
        await query.edit_message_text("⏳ Получаю статус...")
        status_text = await get_service_status_text()
        await query.edit_message_text(status_text, parse_mode='Markdown')
    
    elif data == 'restart_service':
        # Подтверждение перезапуска
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, перезапустить", callback_data='confirm_restart'),
                InlineKeyboardButton("❌ Отмена", callback_data='cancel_restart')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚠️ *Подтверждение перезапуска*\n\n"
            "Вы действительно хотите перезапустить сервис на Railway?\n"
            "Это может занять несколько минут.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif data == 'confirm_restart':
        await query.edit_message_text("🔄 Перезапускаю сервис...")
        result = await restart_railway_service()
        await query.edit_message_text(result)
    
    elif data == 'cancel_restart':
        await query.edit_message_text("❌ Перезапуск отменен")
    
    elif data == 'help':
        help_text = """
📖 *Помощь*

*Основные команды:*
/start - Главное меню
/status - Статус системы
/logs - Получить логи из Railway
/railway - Статус сервиса Railway
/restart - Перезапустить сервис

*Кнопки:*
🌐 Открыть X.com - проверяет доступность
📸 Сделать скриншот - фото главной страницы
📋 Логи Railway - последние логи сервиса
🚂 Статус Railway - информация о сервисе
🔄 Перезапустить сервис - перезапуск на Railway

*Настройка Railway:*
• RAILWAY_API_KEY - API ключ
• RAILWAY_PROJECT_ID - ID проекта
• RAILWAY_SERVICE_ID - ID сервиса (опционально)
• RAILWAY_ENVIRONMENT_ID - ID окружения (опционально)

*Настройка бота:*
• TELEGRAM_BOT_TOKEN - токен бота
• PROXY_URL - прокси (опционально)
• HEADLESS - true/false (по умолчанию false)

*Стек:* Playwright + CloakBrowser + Xvfb
"""
        await query.edit_message_text(help_text, parse_mode='Markdown')

# ===== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ =====

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения логов"""
    await update.message.reply_text("⏳ Получаю логи из Railway...")
    logs_text = await get_railway_logs(context, limit=50)
    await update.message.reply_text(logs_text, parse_mode='Markdown')

async def railway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения статуса Railway"""
    await update.message.reply_text("⏳ Получаю статус...")
    status_text = await get_service_status_text()
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для перезапуска сервиса"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, перезапустить", callback_data='confirm_restart'),
            InlineKeyboardButton("❌ Отмена", callback_data='cancel_restart')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚠️ *Подтверждение перезапуска*\n\n"
        "Вы действительно хотите перезапустить сервис на Railway?\n"
        "Это может занять несколько минут.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ===== ОБРАБОТЧИК ОШИБОК =====

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка глобальных ошибок"""
    error_msg = str(context.error)
    logger.error(f"Ошибка: {error_msg}")
    
    # Логируем в файл
    with open(LOG_FILE, 'a') as f:
        f.write(f"{datetime.now()} - ERROR: {error_msg}\n")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            f"❌ Произошла ошибка: {error_msg[:100]}\n\n"
            "Попробуйте снова позже."
        )

# ===== ЗАПУСК =====

def main():
    """Основная функция запуска"""
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("railway", railway_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("status", start))  # Перенаправляем на меню
    
    # Регистрируем обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Регистрируем обработчик ошибок
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🔑 Токен: {TOKEN[:10]}...")
    logger.info(f"🖥️ Headless: {HEADLESS}")
    logger.info(f"🔌 Proxy: {'✅' if PROXY_URL else '❌'}")
    logger.info(f"🚂 Railway API: {'✅' if RAILWAY_API_KEY else '❌'}")
    logger.info(f"📝 Логи пишутся в: {LOG_FILE}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()