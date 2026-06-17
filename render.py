# render.py — модуль управления Render через API (только публичный REST API)
import os
import json
import requests
import telebot

RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
RENDER_SERVICE_NAME = os.environ.get("RENDER_SERVICE_NAME", "Bugaga")
RENDER_API_URL = "https://api.render.com/v1"

# Кэш для service ID
_CACHED_SERVICE_ID = None


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
            return None, "404 — сервис не найден"

        content_type = resp.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return None, f"HTTP {resp.status_code} (не JSON): {resp.text[:200]}"

        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code}: {resp.text[:300]}"

        return resp.json(), None

    except Exception as e:
        return None, f"Ошибка запроса: {e}"


def find_service_id():
    """Найти ID сервиса по имени или вернуть первый web_service"""
    global _CACHED_SERVICE_ID
    
    if _CACHED_SERVICE_ID:
        return _CACHED_SERVICE_ID, None
    
    if not RENDER_API_KEY:
        return None, "RENDER_API_KEY не настроен"
    
    data, error = api_call("GET", "/services?limit=50")
    if error:
        return None, error
    
    services = data if isinstance(data, list) else data.get("services", [])
    if not services:
        return None, "Сервисы не найдены"
    
    # Ищем по точному имени
    for svc in services:
        s = svc.get("service", svc)
        if s.get("name", "").lower() == RENDER_SERVICE_NAME.lower():
            _CACHED_SERVICE_ID = s.get("id")
            print(f"[Render] Found by exact name: {_CACHED_SERVICE_ID}")
            return _CACHED_SERVICE_ID, None
    
    # Ищем по частичному совпадению
    for svc in services:
        s = svc.get("service", svc)
        if RENDER_SERVICE_NAME.lower() in s.get("name", "").lower():
            _CACHED_SERVICE_ID = s.get("id")
            print(f"[Render] Found by partial name: {_CACHED_SERVICE_ID}")
            return _CACHED_SERVICE_ID, None
    
    # Берём первый web_service
    for svc in services:
        s = svc.get("service", svc)
        if s.get("type") == "web_service":
            _CACHED_SERVICE_ID = s.get("id")
            print(f"[Render] Found first web_service: {_CACHED_SERVICE_ID}")
            return _CACHED_SERVICE_ID, None
    
    # Последний fallback — первый любой сервис
    s = services[0].get("service", services[0])
    _CACHED_SERVICE_ID = s.get("id")
    print(f"[Render] Found first service: {_CACHED_SERVICE_ID}")
    return _CACHED_SERVICE_ID, None


def get_service_id():
    """Получить актуальный service ID"""
    global RENDER_SERVICE_ID, _CACHED_SERVICE_ID
    
    # Приоритет 1: Кэш
    if _CACHED_SERVICE_ID:
        return _CACHED_SERVICE_ID, None
    
    # Приоритет 2: Проверяем заданный ID
    if RENDER_SERVICE_ID:
        data, error = api_call("GET", f"/services/{RENDER_SERVICE_ID}")
        if not error:
            print(f"[Render] Using configured ID: {RENDER_SERVICE_ID}")
            _CACHED_SERVICE_ID = RENDER_SERVICE_ID
            return RENDER_SERVICE_ID, None
        print(f"[Render] Configured ID invalid: {error}")
    
    # Приоритет 3: Ищем автоматически
    sid, error = find_service_id()
    if sid:
        RENDER_SERVICE_ID = sid
        _CACHED_SERVICE_ID = sid
        return sid, None
    
    return None, f"Не удалось найти сервис: {error}"


def get_logs_via_events(service_id, limit=50):
    """Получить события/логи через events API (если доступен)"""
    data, error = api_call("GET", f"/services/{service_id}/events?limit={limit}")
    if error:
        return None, error
    
    events = data if isinstance(data, list) else data.get("events", [])
    # Конвертируем events в формат логов
    logs = []
    for ev in events:
        e = ev.get("event", ev) if isinstance(ev, dict) else ev
        if isinstance(e, dict):
            logs.append({
                "timestamp": e.get("createdAt", e.get("timestamp", "")),
                "message": e.get("message", e.get("details", str(e))),
                "level": "INFO"
            })
    
    return logs, None


def get_logs_via_deploys(service_id, limit=20):
    """Получить логи через последний deploy"""
    # Получаем список deploys
    data, error = api_call("GET", f"/services/{service_id}/deploys?limit=5")
    if error:
        return None, error
    
    deploys = data if isinstance(data, list) else data.get("deploys", [])
    if not deploys:
        return None, "Нет deploys"
    
    # Берём последний deploy
    last_deploy = deploys[0].get("deploy", deploys[0]) if isinstance(deploys[0], dict) else deploys[0]
    deploy_id = last_deploy.get("id") if isinstance(last_deploy, dict) else None
    
    if not deploy_id:
        return None, "Не удалось получить ID deploy"
    
    # Пробуем получить логи deploy
    data, error = api_call("GET", f"/services/{service_id}/deploys/{deploy_id}/logs?limit={limit}")
    if error:
        # Пробуем без /logs — иногда логи внутри deploy объекта
        data, error = api_call("GET", f"/services/{service_id}/deploys/{deploy_id}")
        if error:
            return None, error
        
        d = data.get("deploy", data)
        # Проверяем, есть ли логи внутри
        if isinstance(d, dict) and "logs" in d:
            return d["logs"], None
        return None, "Логи deploy недоступны через API"
    
    logs = data if isinstance(data, list) else data.get("logs", [])
    return logs, None


def format_logs(logs, max_lines=20):
    """Форматировать логи для Telegram"""
    if not logs:
        return "📭 Логи пусты"
    
    lines = ["📋 <b>Последние логи:</b>\n"]
    
    for log in logs[:max_lines]:
        if isinstance(log, dict):
            timestamp = log.get("timestamp", log.get("createdAt", ""))[:19]
            level = log.get("level", "INFO")
            msg = log.get("message", log.get("details", str(log)))
            
            emoji = "🔴" if level in ("ERROR", "FATAL") else "🟡" if level == "WARN" else "🟢"
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

        data, error = api_call("GET", "/services?limit=50")
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        services = data if isinstance(data, list) else data.get("services", [])
        if not services:
            bot.reply_to(message, "📭 Сервисы не найдены")
            return

        # Получаем текущий активный ID
        active_id, _ = get_service_id()

        lines = ["📋 <b>Ваши сервисы:</b>\n"]
        for svc in services:
            s = svc.get("service", svc)
            sid = s.get("id", "—")
            name = s.get("name", "—")
            stype = s.get("type", "—")
            status = s.get("status", "—")
            active = " ✅" if sid == active_id else ""
            lines.append(f"\n<code>{sid}</code>{active}\n  📛 {name} | {stype} | {status}")

        lines.append(f"\n\n<i>✅ — активный сервис (используется ботом)</i>")
        if not active_id:
            lines.append(f"\n<i>⚠️ Активный сервис не определён!</i>")
        
        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["render_status"])
    def render_status_command(message):
        if not RENDER_API_KEY:
            bot.reply_to(message, "❌ RENDER_API_KEY не настроен")
            return

        sid, error = get_service_id()
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        data, error = api_call("GET", f"/services/{sid}")
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
        if not RENDER_API_KEY:
            bot.reply_to(message, "❌ RENDER_API_KEY не настроен")
            return

        sid, error = get_service_id()
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        data, error = api_call(
            "POST",
            f"/services/{sid}/deploys",
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
        if not RENDER_API_KEY:
            bot.reply_to(message, "❌ RENDER_API_KEY не настроен")
            return

        sid, error = get_service_id()
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        data, error = api_call("GET", f"/services/{sid}/env-vars")
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
        if not RENDER_API_KEY:
            bot.reply_to(message, "❌ RENDER_API_KEY не настроен")
            return

        sid, error = get_service_id()
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        # Пробуем events API
        logs, error = get_logs_via_events(sid, limit=20)
        
        # Если events не работают — пробуем deploys
        if error or not logs:
            print(f"[Render Logs] Events failed: {error}, trying deploys...")
            logs, error = get_logs_via_deploys(sid, limit=20)
        
        # Если ничего не работает — ссылка на Dashboard
        if error or not logs:
            bot.reply_to(
                message,
                f"⚠️ Логи через API недоступны.\n"
                f"Причина: <code>{error or 'логи пусты'}</code>\n\n"
                f"📋 <a href='https://dashboard.render.com/web/{sid}/logs'>Открыть логи в Dashboard</a>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        
        # Форматируем и отправляем
        formatted = format_logs(logs, max_lines=15)
        
        if len(formatted) > 4000:
            formatted = formatted[:4000] + "\n\n<i>...логи обрезаны</i>"
        
        bot.reply_to(message, formatted, parse_mode="HTML")

    @bot.message_handler(commands=["render_logs_raw"])
    def render_logs_raw_command(message):
        """Показать сырой ответ от API (для отладки)"""
        if not RENDER_API_KEY:
            bot.reply_to(message, "❌ RENDER_API_KEY не настроен")
            return
        
        sid, error = get_service_id()
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        # Проверяем events API
        events_data, events_error = api_call("GET", f"/services/{sid}/events?limit=5")
        
        # Проверяем deploys API
        deploys_data, deploys_error = api_call("GET", f"/services/{sid}/deploys?limit=3")
        
        msg = (
            f"<b>Отладка Render API</b>\n\n"
            f"Service ID: <code>{sid}</code>\n\n"
            f"<b>Events API:</b>\n"
            f"Error: <code>{events_error or 'None'}</code>\n"
            f"Data: <pre>{json.dumps(events_data, indent=2, ensure_ascii=False)[:1000] if events_data else 'No data'}</pre>\n\n"
            f"<b>Deploys API:</b>\n"
            f"Error: <code>{deploys_error or 'None'}</code>\n"
            f"Data: <pre>{json.dumps(deploys_data, indent=2, ensure_ascii=False)[:1000] if deploys_data else 'No data'}</pre>"
        )
        
        bot.reply_to(message, msg, parse_mode="HTML")

    @bot.message_handler(commands=["render_suspend", "render_resume"])
    def render_not_available_command(message):
        bot.reply_to(
            message,
            "⏸️ Suspend/Resume доступны только через Render Dashboard "
            "на платных планах.\nИспользуй /render_restart для перезапуска."
        )
