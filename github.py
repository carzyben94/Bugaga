# github.py — модуль управления GitHub репозиторием
import os
import base64
import json
import requests
from flask import request
import telebot

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
GITHUB_API_URL = "https://api.github.com"


def github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }


def api_call(method, endpoint, payload=None, params=None):
    """Универсальный вызов GitHub API"""
    url = f"{GITHUB_API_URL}{endpoint}"
    headers = github_headers()

    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        elif method == "PUT":
            resp = requests.put(url, headers=headers, json=payload, timeout=15)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, json=payload, timeout=15)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
        else:
            return None, f"Unsupported method: {method}"

        print(f"[GitHub API] {method} {url} → {resp.status_code}")

        if resp.status_code == 401:
            return None, "401 — неверный GitHub токен"
        if resp.status_code == 404:
            return None, "404 — файл или репозиторий не найден"
        if resp.status_code == 403:
            return None, "403 — нет прав (проверь scope токена: repo)"
        if resp.status_code == 422:
            return None, f"422 — неверные данные: {resp.text[:200]}"

        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code}: {resp.text[:300]}"

        # DELETE может вернуть 204 (No Content)
        if resp.status_code == 204:
            return {"deleted": True}, None

        return resp.json(), None

    except Exception as e:
        return None, f"Ошибка запроса: {e}"


def get_file_content(path, branch="main"):
    """Получить содержимое файла"""
    params = {"ref": branch}
    data, error = api_call("GET", f"/repos/{GITHUB_REPO}/contents/{path}", params=params)
    if error:
        return None, None, error
    
    content = data.get("content", "")
    sha = data.get("sha", "")
    
    # GitHub возвращает base64
    try:
        decoded = base64.b64decode(content).decode("utf-8")
    except:
        decoded = content
    
    return decoded, sha, None


def create_or_update_file(path, content, message, sha=None, branch="main"):
    """Создать или обновить файл"""
    # Кодируем в base64
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": message,
        "content": encoded,
        "branch": branch
    }
    
    if sha:
        payload["sha"] = sha  # Для обновления существующего файла
    
    return api_call("PUT", f"/repos/{GITHUB_REPO}/contents/{path}", payload)


def delete_file(path, sha, message, branch="main"):
    """Удалить файл"""
    payload = {
        "message": message,
        "sha": sha,
        "branch": branch
    }
    return api_call("DELETE", f"/repos/{GITHUB_REPO}/contents/{path}", payload)


def get_repo_tree(path="", branch="main"):
    """Получить список файлов в папке"""
    params = {"ref": branch}
    if path:
        data, error = api_call("GET", f"/repos/{GITHUB_REPO}/contents/{path}", params=params)
    else:
        data, error = api_call("GET", f"/repos/{GITHUB_REPO}/contents", params=params)
    
    if error:
        return None, error
    
    # Если один файл — оборачиваем в список
    if isinstance(data, dict):
        data = [data]
    
    return data, None


def get_commits(path=None, branch="main", limit=10):
    """Получить коммиты"""
    params = {"sha": branch, "per_page": limit}
    if path:
        params["path"] = path
    
    return api_call("GET", f"/repos/{GITHUB_REPO}/commits", params=params)


def get_branches():
    """Получить список веток"""
    return api_call("GET", f"/repos/{GITHUB_REPO}/branches")


def register_github(bot):
    """Регистрирует GitHub-команды в боте"""

    @bot.message_handler(commands=["gh_list", "github_list"])
    def gh_list_command(message):
        """Список файлов в корне репозитория"""
        if not GITHUB_TOKEN:
            bot.reply_to(message, "❌ GITHUB_TOKEN не настроен")
            return

        # Парсим аргументы: /gh_list [путь]
        args = message.text.split(maxsplit=1)
        path = args[1] if len(args) > 1 else ""

        files, error = get_repo_tree(path)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        lines = [f"📁 <b>{GITHUB_REPO}</b>"]
        if path:
            lines.append(f"Путь: <code>{path}</code>\n")
        else:
            lines.append("Корневая папка:\n")

        for f in files:
            emoji = "📁" if f.get("type") == "dir" else "📄"
            name = f.get("name", "—")
            size = f.get("size", 0)
            size_str = f" ({size} bytes)" if f.get("type") == "file" else ""
            lines.append(f"{emoji} <code>{name}</code>{size_str}")

        msg = "\n".join(lines[:50])  # Лимит Telegram
        bot.reply_to(message, msg, parse_mode="HTML")

    @bot.message_handler(commands=["gh_read", "github_read"])
    def gh_read_command(message):
        """Прочитать файл: /gh_read [путь]"""
        if not GITHUB_TOKEN:
            bot.reply_to(message, "❌ GITHUB_TOKEN не настроен")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажи путь: <code>/gh_read bot.py</code>", parse_mode="HTML")
            return

        path = args[1].strip()
        content, sha, error = get_file_content(path)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        # Обрезаем длинные файлы
        preview = content[:3500]
        if len(content) > 3500:
            preview += "\n\n<i>...файл обрезан</i>"

        msg = (
            f"📄 <b>{path}</b>\n"
            f"<code>{sha[:7]}</code>\n\n"
            f"<pre>{preview}</pre>"
        )
        bot.reply_to(message, msg, parse_mode="HTML")

    @bot.message_handler(commands=["gh_write", "github_write"])
    def gh_write_command(message):
        """Записать файл: /gh_write [путь] [содержимое]"""
        if not GITHUB_TOKEN:
            bot.reply_to(message, "❌ GITHUB_TOKEN не настроен")
            return

        # Формат: /gh_write path/to/file.py содержимое...
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot.reply_to(message, 
                "❌ Формат: <code>/gh_write path/to/file.py текст или код</code>\n\n"
                "Для многострочного текста отправь reply на сообщение с кодом.", 
                parse_mode="HTML"
            )
            return

        path = args[1].strip()
        content = args[2]

        # Проверяем, существует ли файл (для получения sha)
        _, sha, _ = get_file_content(path)

        commit_msg = f"Update {path} via Telegram bot"
        data, error = create_or_update_file(path, content, commit_msg, sha)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        commit = data.get("commit", {})
        commit_sha = commit.get("sha", "unknown")[:7]
        bot.reply_to(
            message,
            f"✅ <b>Файл обновлён</b>\n"
            f"Путь: <code>{path}</code>\n"
            f"Коммит: <code>{commit_sha}</code>",
            parse_mode="HTML"
        )

    @bot.message_handler(commands=["gh_del", "github_del"])
    def gh_del_command(message):
        """Удалить файл: /gh_del [путь]"""
        if not GITHUB_TOKEN:
            bot.reply_to(message, "❌ GITHUB_TOKEN не настроен")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажи путь: <code>/gh_del old_file.py</code>", parse_mode="HTML")
            return

        path = args[1].strip()

        # Получаем sha для удаления
        _, sha, error = get_file_content(path)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        commit_msg = f"Delete {path} via Telegram bot"
        data, error = delete_file(path, sha, commit_msg)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        bot.reply_to(message, f"🗑️ <b>Файл удалён</b>\n<code>{path}</code>", parse_mode="HTML")

    @bot.message_handler(commands=["gh_commits", "github_commits"])
    def gh_commits_command(message):
        """История коммитов: /gh_commits [limit]"""
        if not GITHUB_TOKEN:
            bot.reply_to(message, "❌ GITHUB_TOKEN не настроен")
            return

        args = message.text.split()
        limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5

        data, error = get_commits(limit=min(limit, 20))
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        lines = [f"📜 <b>Коммиты {GITHUB_REPO}</b>\n"]
        for commit in data:
            c = commit.get("commit", {})
            sha = commit.get("sha", "")[:7]
            msg = c.get("message", "—")[:50]
            author = c.get("author", {}).get("name", "—")
            date = c.get("author", {}).get("date", "")[:10]
            lines.append(f"<code>{sha}</code> <b>{msg}</b>\n  👤 {author} | 📅 {date}\n")

        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["gh_branches", "github_branches"])
    def gh_branches_command(message):
        """Список веток"""
        if not GITHUB_TOKEN:
            bot.reply_to(message, "❌ GITHUB_TOKEN не настроен")
            return

        data, error = get_branches()
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        lines = [f"🌿 <b>Ветки {GITHUB_REPO}</b>\n"]
        for branch in data:
            name = branch.get("name", "—")
            protected = "🔒" if branch.get("protected") else ""
            lines.append(f"  <code>{name}</code> {protected}")

        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["gh_repo", "github_repo"])
    def gh_repo_command(message):
        """Информация о репозитории"""
        if not GITHUB_TOKEN:
            bot.reply_to(message, "❌ GITHUB_TOKEN не настроен")
            return

        data, error = api_call("GET", f"/repos/{GITHUB_REPO}")
        if error:
            bot.reply_to(message, f"❌ {error}")
            return

        msg = (
            f"📦 <b>{data.get('full_name', GITHUB_REPO)}</b>\n\n"
            f"⭐ Stars: <code>{data.get('stargazers_count', 0)}</code>\n"
            f"🍴 Forks: <code>{data.get('forks_count', 0)}</code>\n"
            f"👁️ Watchers: <code>{data.get('watchers_count', 0)}</code>\n"
            f"📝 Open issues: <code>{data.get('open_issues_count', 0)}</code>\n"
            f"🌿 Default branch: <code>{data.get('default_branch', 'main')}</code>\n"
            f"🔒 Private: <code>{data.get('private', False)}</code>\n"
            f"📅 Created: <code>{data.get('created_at', '—')[:10]}</code>\n"
            f"🔄 Updated: <code>{data.get('updated_at', '—')[:10]}</code>\n"
            f"🔗 <a href='{data.get('html_url', '')}'>Открыть на GitHub</a>"
        )
        bot.reply_to(message, msg, parse_mode="HTML", disable_web_page_preview=True)
