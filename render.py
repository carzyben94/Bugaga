# render.py — модуль управления Render через API
import os
import requests
import telebot

RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
RENDER_API_URL = "https://api.render.com/v1"


def render_headers():
    return {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }


def api_call(method, endpoint, payload=None):
    """Универсальный вызов Render API"""
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
        bot.reply_to(
            message,
            "📋 Логи доступны только в Render Dashboard:\n"
            "https://dashboard.render.com"
        )

    @bot.message_handler(commands=["render_suspend", "render_resume"])
    def render_not_available_command(message):
        bot.reply_to(
            message,
            "⏸️ Suspend/Resume доступны только через Render Dashboard "
            "на платных планах.\nИспользуй /render_restart для перезапуска."
        )
