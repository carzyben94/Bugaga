import time
import os
import re
import subprocess
import json
import requests
from datetime import datetime
from collections import Counter

def register_status_full(bot):
    @bot.message_handler(commands=['status_full'])
    def status_full_command(message):
        status_msg = bot.reply_to(message, "📊 Собираю полную статистику...")
        
        try:
            # Время работы
            try:
                with open("start_time.txt", "r") as f:
                    start_time = float(f.read())
            except:
                start_time = time.time()
            
            uptime = int(time.time() - start_time)
            days = uptime // 86400
            hours = (uptime % 86400) // 3600
            minutes = (uptime % 3600) // 60
            seconds = uptime % 60
            
            # Статистика команд
            logs = get_agent_logs(5000)
            command_stats = Counter()
            for log in logs:
                if log.get("action", "").startswith("command_"):
                    cmd = log["action"].replace("command_", "")
                    command_stats[cmd] += 1
            
            total_commands = sum(command_stats.values())
            top_commands = command_stats.most_common(5)
            
            # Ошибки
            errors = [log for log in logs if log.get("status") == "error"]
            error_types = Counter()
            for err in errors[-200:]:
                etype = err.get("action", "unknown")
                error_types[etype] += 1
            
            # API ключи
            github_token = bool(os.environ.get("GITHUB_TOKEN"))
            render_key = bool(os.environ.get("RENDER_API_KEY"))
            openrouter_key = bool(os.environ.get("OPENROUTER_API_KEY"))
            github_repo = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
            
            # GitHub
            last_commit = "N/A"
            try:
                result = subprocess.run(["git", "log", "-1", "--pretty=%h - %s"], 
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    last_commit = result.stdout.strip()
            except:
                pass
            
            # Бэкапы
            BACKUP_DIR = "backups"
            backups = 0
            backup_size_kb = 0
            if os.path.exists(BACKUP_DIR):
                files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')]
                backups = len(files)
                backup_size = sum(os.path.getsize(os.path.join(BACKUP_DIR, f)) for f in files)
                backup_size_kb = backup_size / 1024
            
            # Пользователи
            user_ids = set()
            for log in logs:
                details = log.get("details", "")
                if "user_id" in str(details):
                    ids = re.findall(r'user_id[=:]\s*(\d+)', str(details))
                    user_ids.update(ids)
            
            # Модели
            FREE_MODELS = [
                "openrouter/free", "nvidia/nemotron-3-super-120b-a12b:free",
                "nvidia/nemotron-3-ultra:free", "openai/gpt-oss-120b:free",
                "openai/gpt-oss-20b:free", "google/gemma-4-31b-it:free",
                "google/gemma-4-26b-a4b-it:free", "poolside/laguna-m1:free",
                "poolside/laguna-xs2:free", "z-ai/glm-4.5-air:free",
                "moonshotai/kimi-k2.6:free", "nvidia/nemotron-3-nano-30b-a3b:free",
                "nvidia/nemotron-3-nano-omni:free", "deepseek/deepseek-r1:free",
                "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-coder:free",
            ]
            
            # Автономия
            auto_fixes = sum(1 for log in logs if log.get("action") == "auto_fix")
            rollbacks = sum(1 for log in logs if log.get("action") == "rollback")
            
            # Формируем отчёт (без спецсимволов, портящих Markdown)
            top_cmds = ", ".join([f"/{c}" for c, _ in top_commands]) if top_commands else "нет"
            error_types_str = ", ".join([f"{k}({v})" for k, v in error_types.most_common(3)]) if error_types else "нет"
            
            report = f"""📊 ПОЛНЫЙ СТАТУС БОТА

⏱️ ВРЕМЯ РАБОТЫ
• {days}д {hours}ч {minutes}м {seconds}с

📊 СТАТИСТИКА КОМАНД
• Всего команд: {total_commands}
• Топ-5: {top_cmds}

❌ ОШИБКИ
• Всего: {len(errors)}
• Типы: {error_types_str}

🔑 API КЛЮЧИ
• OpenRouter: {'✅' if openrouter_key else '❌'}
• GitHub: {'✅' if github_token else '❌'}
• Render: {'✅' if render_key else '❌'}

📁 GITHUB
• Репо: {github_repo}
• Последний коммит: {last_commit}

💾 БЭКАПЫ
• Количество: {backups}
• Размер: {backup_size_kb:.1f} KB

🤖 ИИ МОДЕЛИ
• Доступно: {len(FREE_MODELS)}

👥 ПОЛЬЗОВАТЕЛИ
• Уникальных: {len(user_ids)}

🔄 АВТОНОМИЯ
• Автоисправлений: {auto_fixes}
• Откатов: {rollbacks}"""

            bot.edit_message_text(report, chat_id=message.chat.id, message_id=status_msg.message_id)
            
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка: {e}", 
                                  chat_id=message.chat.id, message_id=status_msg.message_id)

def get_agent_logs(limit=5000):
    try:
        if not os.path.exists("agent_actions.log"):
            return []
        with open("agent_actions.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
        logs = []
        for line in lines[-limit:]:
            try:
                logs.append(json.loads(line))
            except:
                logs.append({"raw": line.strip()})
        return logs
    except:
        return []
