import os
import logging
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токены
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")
RAILWAY_TOKEN = os.getenv("RAILWAY_API_TOKEN")
PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID")

if not all([TELEGRAM_TOKEN, RAILWAY_TOKEN, PROJECT_ID]):
    raise ValueError("Не все переменные окружения установлены!")

# GraphQL запросы
GET_DEPLOYMENTS_QUERY = """
query GetDeployments($projectId: String!) {
  project(id: $projectId) {
    deployments(last: 1) {
      nodes {
        id
        status
        createdAt
      }
    }
  }
}
"""

GET_BUILD_LOGS = """
query GetBuildLogs($deploymentId: String!) {
  buildLogs(deploymentId: $deploymentId, limit: 20) {
    timestamp
    message
    severity
    step
  }
}
"""

GET_DEPLOYMENT_LOGS = """
query GetDeploymentLogs($deploymentId: String!) {
  deploymentLogs(deploymentId: $deploymentId, limit: 20) {
    timestamp
    message
    severity
  }
}
"""

GET_HTTP_LOGS = """
query GetHttpLogs($deploymentId: String!) {
  httpLogs(deploymentId: $deploymentId, limit: 10) {
    timestamp
    method
    path
    httpStatus
    totalDuration
  }
}
"""

def get_deployment_id():
    """Получает ID последнего деплоя"""
    response = requests.post(
        "https://backboard.railway.app/graphql/v2",
        json={"query": GET_DEPLOYMENTS_QUERY, "variables": {"projectId": PROJECT_ID}},
        headers={"Authorization": f"Bearer {RAILWAY_TOKEN}"}
    )
    data = response.json()
    deployments = data["data"]["project"]["deployments"]["nodes"]
    return deployments[0]["id"] if deployments else None

def get_logs(deployment_id):
    """Собирает все логи"""
    headers = {"Authorization": f"Bearer {RAILWAY_TOKEN}"}
    
    logs_data = {}
    
    # Build logs
    response = requests.post(
        "https://backboard.railway.app/graphql/v2",
        json={"query": GET_BUILD_LOGS, "variables": {"deploymentId": deployment_id}},
        headers=headers
    )
    logs_data["build"] = response.json().get("data", {}).get("buildLogs", [])
    
    # Runtime logs
    response = requests.post(
        "https://backboard.railway.app/graphql/v2",
        json={"query": GET_DEPLOYMENT_LOGS, "variables": {"deploymentId": deployment_id}},
        headers=headers
    )
    logs_data["runtime"] = response.json().get("data", {}).get("deploymentLogs", [])
    
    # HTTP logs
    response = requests.post(
        "https://backboard.railway.app/graphql/v2",
        json={"query": GET_HTTP_LOGS, "variables": {"deploymentId": deployment_id}},
        headers=headers
    )
    logs_data["http"] = response.json().get("data", {}).get("httpLogs", [])
    
    return logs_data

def format_logs(logs_data):
    """Форматирует логи в чистый текст для копирования"""
    lines = []
    
    lines.append("🚀 LOGS")
    lines.append("=" * 40)
    lines.append("")
    
    # BUILD
    lines.append("🔨 BUILD")
    lines.append("-" * 30)
    build_logs = logs_data.get("build", [])
    if build_logs:
        for log in build_logs[:8]:
            timestamp = log.get("timestamp", "")[11:19]
            step = log.get("step", "")
            msg = log.get("message", "")[:60]
            lines.append(f"  {timestamp} [{step}] {msg}")
    else:
        lines.append("  📭 нет логов")
    lines.append("")
    
    # RUNTIME
    lines.append("🖥️ RUNTIME")
    lines.append("-" * 30)
    runtime_logs = logs_data.get("runtime", [])
    if runtime_logs:
        for log in runtime_logs[:8]:
            timestamp = log.get("timestamp", "")[11:19]
            severity = log.get("severity", "")
            emoji = "✅" if severity != "ERROR" else "❌"
            msg = log.get("message", "")[:60]
            lines.append(f"  {timestamp} {emoji} {msg}")
    else:
        lines.append("  📭 нет логов")
    lines.append("")
    
    # HTTP
    lines.append("🌐 HTTP")
    lines.append("-" * 30)
    http_logs = logs_data.get("http", [])
    if http_logs:
        for log in http_logs[:8]:
            timestamp = log.get("timestamp", "")[11:19]
            method = log.get("method", "")
            path = log.get("path", "")[:25]
            status = log.get("httpStatus", 0)
            emoji = "✅" if status < 400 else "❌"
            lines.append(f"  {timestamp} {emoji} {method} {path} [{status}]")
    else:
        lines.append("  📭 нет логов")
    
    return "\n".join(lines)

def format_logs_html(logs_data):
    """Форматирует логи в HTML для отображения"""
    lines = []
    
    lines.append("<b>🚀 LOGS</b>")
    lines.append("══════════════════════════════════")
    lines.append("")
    
    # BUILD
    lines.append("<b>🔨 BUILD</b>")
    lines.append("─" * 25)
    build_logs = logs_data.get("build", [])
    if build_logs:
        for log in build_logs[:8]:
            timestamp = log.get("timestamp", "")[11:19]
            step = log.get("step", "")
            msg = log.get("message", "")[:60]
            lines.append(f"  <code>{timestamp}</code> [{step}] {msg}")
    else:
        lines.append("  📭 нет логов")
    lines.append("")
    
    # RUNTIME
    lines.append("<b>🖥️ RUNTIME</b>")
    lines.append("─" * 25)
    runtime_logs = logs_data.get("runtime", [])
    if runtime_logs:
        for log in runtime_logs[:8]:
            timestamp = log.get("timestamp", "")[11:19]
            severity = log.get("severity", "")
            emoji = "✅" if severity != "ERROR" else "❌"
            msg = log.get("message", "")[:60]
            lines.append(f"  <code>{timestamp}</code> {emoji} {msg}")
    else:
        lines.append("  📭 нет логов")
    lines.append("")
    
    # HTTP
    lines.append("<b>🌐 HTTP</b>")
    lines.append("─" * 25)
    http_logs = logs_data.get("http", [])
    if http_logs:
        for log in http_logs[:8]:
            timestamp = log.get("timestamp", "")[11:19]
            method = log.get("method", "")
            path = log.get("path", "")[:25]
            status = log.get("httpStatus", 0)
            emoji = "✅" if status < 400 else "❌"
            lines.append(f"  <code>{timestamp}</code> {emoji} {method} {path} [{status}]")
    else:
        lines.append("  📭 нет логов")
    
    return "\n".join(lines)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет логи с кнопкой копирования"""
    status_msg = await update.message.reply_text("📡 <i>Получаю логи...</i>", parse_mode="HTML")
    
    try:
        deployment_id = get_deployment_id()
        if not deployment_id:
            await status_msg.edit_text("❌ Нет активных деплоев")
            return
        
        logs_data = get_logs(deployment_id)
        
        # Текст для отображения (с HTML)
        display_text = format_logs_html(logs_data)
        
        # Текст для копирования (без HTML)
        copy_text = format_logs(logs_data)
        
        # Сохраняем в контекст для callback
        context.user_data['copy_text'] = copy_text
        
        # Заголовок
        header = f"📦 <b>Деплой:</b> <code>{deployment_id[:8]}...</code>\n"
        header += f"🕐 <b>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</b>\n\n"
        
        message = header + display_text
        
        # Кнопка копирования
        keyboard = [[InlineKeyboardButton("📋 Копировать логи", callback_data="copy_logs")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем
        await status_msg.edit_text(
            message,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
            
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Ошибка:</b>\n<code>{str(e)}</code>", parse_mode="HTML")

async def copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки копирования"""
    query = update.callback_query
    await query.answer()  # Закрываем уведомление
    
    copy_text = context.user_data.get('copy_text', '')
    
    if copy_text:
        # Отправляем отдельное сообщение с логами в виде кода
        # Это создаст "окно" с возможностью копирования
        await query.message.reply_text(
            f"📋 <b>Логи (скопируйте текст ниже)</b>\n\n"
            f"<pre>{copy_text}</pre>",
            parse_mode="HTML"
        )
        
        # Показываем уведомление
        await query.answer("✅ Логи отправлены отдельным сообщением!")
    else:
        await query.answer("❌ Логи не найдены", show_alert=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>Railway Log Bot</b>\n\n"
        "📋 <b>/logs</b> - получить логи в отдельном окне\n"
        "📋 Нажмите кнопку <b>Копировать логи</b>\n"
        "📋 Затем скопируйте текст из сообщения",
        parse_mode="HTML"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    
    port = int(os.getenv("PORT", 8080))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"https://{os.getenv('RAILWAY_STATIC_URL')}/webhook"
    )

if __name__ == "__main__":
    main()