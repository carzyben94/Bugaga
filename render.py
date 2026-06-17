# render.py — модуль управления Render через API
import os
import re
import requests
import telebot

RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
RENDER_API_URL = "https://api.render.com/v1"

# Для парсинга логов через GraphQL (Dashboard API)
RENDER_DASHBOARD_URL = "https://dashboard.render.com"
RENDER_GRAPHQL_URL = "https://api.render.com/graphql"


def render_headers():
    return {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }


def api_call(method, endpoint, payload=None):
    """Универсальный вызов Render API v1"""
    url = f"{RENDER_API_URL}{endpoint}"
    headers = render_headers()

    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=15)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
        else:
            return None, f"Unsupported method: {method}"

        print(f"[Render API] {method} {url} → {resp.status_code}")

        if resp.status_code == 401:
            return None, "401 — неверный API ключ"
        if resp.status_code == 403:
            return None, "403 — нет прав (нужен owner/admin)"
        if resp.status_code == 404:
            return None, "404 — сервис не найден, проверь RENDER_SERVICE_ID через /render_list"

        content_type = resp.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return None, f"HTTP {resp.status_code} (не JSON): {resp.text[:200]}"

        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code}: {resp.text[:300]}"

        return resp.json(), None

    except Exception as e:
        return None, f"Ошибка запроса: {e}"


def graphql_call(query, variables=None):
    """Вызов Render GraphQL API (используется Dashboard)"""
    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    payload = {
        "query": query,
        "variables": variables or {}
    }
    
    try:
        resp = requests.post(
            RENDER_GRAPHQL_URL,
            headers=headers,
            json=payload,
            timeout=15
        )
        
        if resp.status_code != 200:
            return None, f"GraphQL HTTP {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        if "errors" in data:
            return None, f"GraphQL error: {data['errors']}"
        
        return data.get("data"), None
        
    except Exception as e:
        return None, f"GraphQL error: {e}"


def get_logs_via_graphql(service_id, limit=50):
    """Получить логи через Render GraphQL API"""
    query = """
    query GetLogs($serviceId: String!, $start: String, $end: String, $limit: Int) {
        service(id: $serviceId) {
            logs(start: $start, end: $end, limit: $limit) {
                timestamp
                message
                level
                source
            }
        }
    }
    """
    
    variables = {
        "serviceId": service_id,
        "limit": limit
    }
    
    data, error = graphql_call(query, variables)
    if error:
        return None, error
    
    logs = data.get("service", {}).get("logs", []) if data else []
    return logs, None


def get_logs_via_deploys(service_id, limit=20):
    """Альтернативный способ: получить логи через последние deploys"""
    data, error = api_call("GET", f"/services/{service_id}/deploys?limit=5")
    if error:
        return None, error
    
    deploys = data if isinstance(data, list) else data.get("deploys", [])
    if not deploys:
        return None, "Нет deploys для получения логов"
    
    # Берём последний deploy
    last_deploy = deploys[0].get("deploy", deploys[0]) if isinstance(deploys[0], dict) else deploys[0]
    deploy_id = last_deploy.get("id") if isinstance(last_deploy, dict) else None
    
    if not deploy_id:
        return None, "Не удалось получить ID deploy"
    
    # Пробуем получить логи deploy
    data, error = api_call("GET", f"/services/{service_id}/deploys/{deploy_id}/logs?limit={limit}")
    if error:
        return None, error
    
    logs = data if isinstance(data, list) else data.get("logs", [])
    return logs, None


def format_logs(logs, max_lines=20):
    """Форматировать логи для Telegram"""
    if not logs:
        return "📭 Логи пусты"
    
    lines = ["📋 <b>Последние логи:</b>\n"]
    
    for log in logs[:max_lines]:
        if isinstance(log, dict):
            timestamp = log.get("timestamp", "")[:19]  # Обрезаем миллисекунды
            level = log.get("level", "INFO")
            msg = log.get("message", str(log))
            source = log.get("source", "")
            
            # Эмодзи по уровню
            emoji = "🔴" if level in ("ERROR", "FATAL") else "🟡" if level == "WARN" else "🟢"
            
            # Обрезаем длинные сообщения
            msg_short = msg[:200] + "..." if len(msg) > 200 else msg
            
            lines.append(f"{emoji} <code>[{timestamp}]</code>\n{msg_short}\n")
        else:
            lines.append(f"📝 <code>{str(log)[:200]}</code>\n")
    
    return "\n".join(lines)


def register_render(bot):
    """Регистрирует все Render-команды в боте"""

    @bot.message_handler(commands=["render_list"])
    def render_list_command(message):
        if not RENDER_API_KEY:
            bot.reply_to(message, "❌ RENDER_API_KEY не настроен")
            return

        data, error = api_call("GET", "/services?limit=20")
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        services = data if isinstance(data, list) else data.get("services", [])
        if not services:
            bot.reply_to(message, "📭 Сервисы не найдены")
            return

        lines = ["📋 <b>Ваши сервисы:</b>\n"]
        for svc in services:
            s = svc.get("service", svc)
            sid = s.get("id", "—")
            name = s.get("name", "—")
            stype = s.get("type", "—")
            status = s.get("status", "—")
            lines.append(f"\n<code>{sid}</code>\n  📛 {name} | {stype} | {status}")

        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["render_status"])
    def render_status_command(message):
        if not RENDER_API_KEY or not RENDER_SERVICE_ID:
            bot.reply_to(message, "❌ Настрой RENDER_API_KEY и RENDER_SERVICE_ID\nПолучи ID через /render_list")
            return

        data, error = api_call("GET", f"/services/{RENDER_SERVICE_ID}")
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        s = data.get("service", data)

        msg = (
            f"📊 <b>Render Status</b>\n\n"
            f"ID: <code>{s.get('id', '—')}</code>\n"
            f"Имя: <code>{s.get('name', '—')}</code>\n"
            f"Тип: <code>{s.get('type', '—')}</code>\n"
            f"Статус: <code>{s.get('status', '—')}</code>\n"
            f"Приостановлен: <code>{s.get('suspended', '—')}</code>\n"
            f"Регион: <code>{s.get('region', '—')}</code>"
        )
        bot.reply_to(message, msg, parse_mode="HTML")

    @bot.message_handler(commands=["render_restart"])
    def render_restart_command(message):
        if not RENDER_API_KEY or not RENDER_SERVICE_ID:
            bot.reply_to(message, "❌ Настрой RENDER_API_KEY и RENDER_SERVICE_ID")
            return

        data, error = api_call(
            "POST",
            f"/services/{RENDER_SERVICE_ID}/deploys",
            {"clearCache": "do_not_clear"}
        )
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        d = data.get("deploy", data)
        deploy_id = d.get("id", "unknown") if isinstance(d, dict) else "unknown"
        status = d.get("status", "unknown") if isinstance(d, dict) else "unknown"

        bot.reply_to(
            message,
            f"🔄 <b>Deploy создан</b>\nID: <code>{deploy_id}</code>\nСтатус: <code>{status}</code>",
            parse_mode="HTML"
        )

    @bot.message_handler(commands=["render_env"])
    def render_env_command(message):
        if not RENDER_API_KEY or not RENDER_SERVICE_ID:
            bot.reply_to(message, "❌ Настрой RENDER_API_KEY и RENDER_SERVICE_ID")
            return

        data, error = api_call("GET", f"/services/{RENDER_SERVICE_ID}/env-vars")
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        env_vars = data if isinstance(data, list) else data.get("envVars", [])
        if not env_vars:
            bot.reply_to(message, "📭 Переменные не найдены")
            return

        lines = ["🔧 <b>Env Vars:</b>"]
        for item in env_vars:
            ev = item.get("envVar", item) if isinstance(item, dict) else {}
            name = ev.get("key", "?") if isinstance(ev, dict) else "?"
            val = ev.get("value", "") if isinstance(ev, dict) else ""
            masked = val[:2] + "***" if len(val) > 3 else "***"
            lines.append(f"  <code>{name}</code> = {masked}")

        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["render_logs"])
    def render_logs_command(message):
        if not RENDER_API_KEY or not RENDER_SERVICE_ID:
            bot.reply_to(message, "❌ Настрой RENDER_API_KEY и RENDER_SERVICE_ID")
            return

        # Пробуем GraphQL API (Dashboard)
        logs, error = get_logs_via_graphql(RENDER_SERVICE_ID, limit=20)
        
        # Если GraphQL не работает — пробуем через deploys
        if error or not logs:
            print(f"[Render Logs] GraphQL failed: {error}, trying deploys API...")
            logs, error = get_logs_via_deploys(RENDER_SERVICE_ID, limit=20)
        
        # Если и deploys не работают — ссылка на Dashboard
        if error or not logs:
            bot.reply_to(
                message,
                f"⚠️ Не удалось получить логи через API.\n"
                f"Причина: <code>{error or 'логи пусты'}</code>\n\n"
                f"📋 <a href='https://dashboard.render.com/web/{RENDER_SERVICE_ID}/logs'>Открыть логи в Dashboard</a>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        
        # Форматируем и отправляем
        formatted = format_logs(logs, max_lines=15)
        
        # Telegram ограничение ~4096 символов
        if len(formatted) > 4000:
            formatted = formatted[:4000] + "\n\n<i>...логи обрезаны</i>"
        
        bot.reply_to(message, formatted, parse_mode="HTML")

    @bot.message_handler(commands=["render_logs_raw"])
    def render_logs_raw_command(message):
        """Показать сырой ответ от API (для отладки)"""
        if not RENDER_API_KEY or not RENDER_SERVICE_ID:
            bot.reply_to(message, "❌ Настрой RENDER_API_KEY и RENDER_SERVICE_ID")
            return
        
        # Пробуем GraphQL
        query = """
        query {
            service(id: "%s") {
                id
                name
                logs(limit: 5) {
                    timestamp
                    message
                    level
                }
            }
        }
        """ % RENDER_SERVICE_ID
        
        data, error = graphql_call(query)
        if error:
            bot.reply_to(message, f"❌ GraphQL error: {error}")
            return
        
        raw = json.dumps(data, indent=2, ensure_ascii=False)[:3500]
        bot.reply_to(message, f"<pre>{raw}</pre>", parse_mode="HTML")

    @bot.message_handler(commands=["render_suspend", "render_resume"])
    def render_not_available_command(message):
        bot.reply_to(
            message,
            "⏸️ Suspend/Resume доступны только через Render Dashboard "
            "на платных планах.\nИспользуй /render_restart для перезапуска."
        )
