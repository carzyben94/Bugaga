import time
import os
import re
import subprocess
import json
import requests
import psutil
from datetime import datetime, timedelta
from collections import Counter

def register_status_full(bot):
    """Регистрирует команду /status_full в боте"""
    
    @bot.message_handler(commands=['status_full'])
    def status_full_command(message):
        status_msg = bot.reply_to(message, "📊 Собираю полную статистику...")
        
        try:
            # ===== 1. ВРЕМЯ РАБОТЫ =====
            start_time = 0
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
            
            last_restart = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
            
            # ===== 2. СИСТЕМНЫЕ РЕСУРСЫ =====
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            ram_used = memory.percent
            ram_used_gb = memory.used / (1024**3)
            ram_total_gb = memory.total / (1024**3)
            disk = psutil.disk_usage('/')
            disk_free_gb = disk.free / (1024**3)
            disk_total_gb = disk.total / (1024**3)
            threads = len(os.listdir('/proc/self/task')) if os.path.exists('/proc/self/task') else "Н/Д"
            
            # ===== 3. СТАТИСТИКА КОМАНД =====
            logs = get_agent_logs(5000)
            command_stats = {}
            command_errors = {}
            for log in logs:
                if log.get("action", "").startswith("command_"):
                    cmd = log["action"].replace("command_", "")
                    command_stats[cmd] = command_stats.get(cmd, 0) + 1
                    if log.get("status") == "error":
                        command_errors[cmd] = command_errors.get(cmd, 0) + 1
            
            total_commands = sum(command_stats.values())
            top_commands = sorted(command_stats.items(), key=lambda x: -x[1])[:10]
            
            # ===== 4. ОШИБКИ =====
            errors = [log for log in logs if log.get("status") == "error"]
            errors_last_hour = 0
            errors_last_day = 0
            
            now = datetime.now()
            for err in errors:
                try:
                    err_time = datetime.strptime(err.get("timestamp", "2000-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S")
                    if now - err_time < timedelta(hours=1):
                        errors_last_hour += 1
                    if now - err_time < timedelta(days=1):
                        errors_last_day += 1
                except:
                    pass
            
            error_types = Counter()
            for err in errors[-200:]:
                etype = err.get("action", "unknown")
                error_types[etype] += 1
            
            last_error = None
            for log in logs[::-1]:
                if log.get("status") == "error":
                    last_error = log.get("details", "Неизвестно")[:200]
                    break
            
            # ===== 5. API КЛЮЧИ =====
            telegram_token = bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
            openrouter_key = bool(os.environ.get("OPENROUTER_API_KEY"))
            github_token = bool(os.environ.get("GITHUB_TOKEN"))
            render_key = bool(os.environ.get("RENDER_API_KEY"))
            github_repo = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
            render_service_id = os.environ.get("RENDER_SERVICE_ID", "не задан")
            
            # Проверка лимитов OpenRouter
            openrouter_limit = "Н/Д"
            if openrouter_key:
                try:
                    headers = {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}"}
                    resp = requests.get("https://openrouter.ai/api/v1/auth/key", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        openrouter_limit = f"{data.get('usage', 0)}/{data.get('limit', 0)}"
                except:
                    pass
            
            # ===== 6. GITHUB =====
            last_commit = "Н/Д"
            last_commit_author = "Н/Д"
            last_commit_date = "Н/Д"
            branch = "main"
            try:
                result = subprocess.run(["git", "log", "-1", "--pretty=%h - %s"], 
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    last_commit = result.stdout.strip()
                result = subprocess.run(["git", "log", "-1", "--pretty=%an"], 
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    last_commit_author = result.stdout.strip()
                result = subprocess.run(["git", "log", "-1", "--pretty=%cr"], 
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    last_commit_date = result.stdout.strip()
                result = subprocess.run(["git", "branch", "--show-current"], 
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    branch = result.stdout.strip()
            except:
                pass
            
            # ===== 7. RENDER =====
            render_status = "Н/Д"
            render_last_deploy = "Н/Д"
            if render_key and render_service_id != "не задан":
                try:
                    headers = {"Authorization": f"Bearer {os.environ.get('RENDER_API_KEY')}"}
                    resp = requests.get(f"https://api.render.com/v1/services/{render_service_id}", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        render_status = data.get("status", "Н/Д")
                    resp = requests.get(f"https://api.render.com/v1/services/{render_service_id}/deploys", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        deploys = resp.json()
                        if deploys:
                            render_last_deploy = deploys[0].get("createdAt", "Н/Д")[:19]
                except:
                    pass
            
            # ===== 8. БЭКАПЫ =====
            BACKUP_DIR = "backups"
            backups = 0
            backup_size_kb = 0
            last_backup = "Нет"
            if os.path.exists(BACKUP_DIR):
                files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')]
                backups = len(files)
                backup_size = sum(os.path.getsize(os.path.join(BACKUP_DIR, f)) for f in files)
                backup_size_kb = backup_size / 1024
                if files:
                    last_backup_time = max(os.path.getmtime(os.path.join(BACKUP_DIR, f)) for f in files)
                    last_backup = datetime.fromtimestamp(last_backup_time).strftime("%Y-%m-%d %H:%M:%S")
            
            # ===== 9. ЛОГИ =====
            log_size_lines = 0
            log_size_kb = 0
            if os.path.exists("agent_actions.log"):
                with open("agent_actions.log", "r") as f:
                    log_size_lines = len(f.readlines())
                log_size_kb = os.path.getsize("agent_actions.log") / 1024
            
            last_actions = []
            for log in logs[-10:]:
                action = log.get("action", "")
                if action:
                    last_actions.append(action[:30])
            
            # ===== 10. ИИ МОДЕЛИ =====
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
            
            model_switches = sum(1 for log in logs if "model" in str(log.get("details", "")) and "переключаем" in str(log.get("details", "")))
            
            # ===== 11. ПОЛЬЗОВАТЕЛИ =====
            user_ids = set()
            active_users_24h = set()
            user_command_counts = {}
            
            now = datetime.now()
            for log in logs:
                details = log.get("details", "")
                if "user_id" in str(details):
                    ids = re.findall(r'user_id[=:]\s*(\d+)', str(details))
                    user_ids.update(ids)
                    
                    try:
                        log_time = datetime.strptime(log.get("timestamp", "2000-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S")
                        if now - log_time < timedelta(hours=24):
                            active_users_24h.update(ids)
                    except:
                        pass
                    
                    if "command" in details:
                        cmd_match = re.search(r'command[=:]\s*(\w+)', str(details))
                        if cmd_match:
                            cmd = cmd_match.group(1)
                            user_command_counts[cmd] = user_command_counts.get(cmd, 0) + 1
            
            # ===== 12. АКТИВНОСТЬ =====
            messages_per_min = round(total_commands / (uptime / 60)) if uptime > 0 else 0
            
            # Пиковые нагрузки по часам
            hour_counts = Counter()
            for log in logs:
                try:
                    log_time = datetime.strptime(log.get("timestamp", "2000-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S")
                    hour_counts[log_time.hour] += 1
                except:
                    pass
            peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else "Н/Д"
            peak_value = hour_counts.most_common(1)[0][1] if hour_counts else 0
            
            # ===== 13. АВТОНОМИЯ =====
            auto_fixes = sum(1 for log in logs if log.get("action") == "auto_fix")
            auto_fix_success = sum(1 for log in logs if log.get("action") == "auto_fix" and log.get("status") == "success")
            rollbacks = sum(1 for log in logs if log.get("action") == "rollback")
            last_auto_fix = "Нет"
            for log in logs[::-1]:
                if log.get("action") == "auto_fix":
                    last_auto_fix = log.get("timestamp", "Неизвестно")
                    break
            
            # ===== 14. СЕТЬ =====
            ping_github = "Н/Д"
            ping_render = "Н/Д"
            ping_openrouter = "Н/Д"
            
            try:
                start = time.time()
                requests.get("https://api.github.com", timeout=5)
                ping_github = round((time.time() - start) * 1000)
            except:
                pass
            
            try:
                start = time.time()
                requests.get("https://api.render.com/v1", timeout=5)
                ping_render = round((time.time() - start) * 1000)
            except:
                pass
            
            try:
                start = time.time()
                requests.get("https://openrouter.ai/api/v1/auth/key", timeout=5)
                ping_openrouter = round((time.time() - start) * 1000)
            except:
                pass
            
            # ===== 15. ЗДОРОВЬЕ =====
            webhook_status = "❌ Не установлен"
            try:
                resp = requests.get(f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/getWebhookInfo", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("result", {}).get("url"):
                        webhook_status = f"✅ {data['result']['url'][:50]}..."
                    else:
                        webhook_status = "❌ Не установлен"
            except:
                pass
            
            # Версия бота
            bot_version = "3.0"
            try:
                with open("version.txt", "r") as f:
                    bot_version = f.read().strip()
            except:
                pass
            
            # ===== ФОРМИРУЕМ ОТЧЁТ =====
            report = f"""📊 **ПОЛНЫЙ СТАТУС БОТА v{bot_version}**

**⏱️ ВРЕМЯ РАБОТЫ**
• {days}д {hours}ч {minutes}м {seconds}с
• Последний перезапуск: {last_restart}

**💻 СИСТЕМНЫЕ РЕСУРСЫ**
• CPU: {cpu}%
• RAM: {ram_used}% ({ram_used_gb:.1f} / {ram_total_gb:.1f} GB)
• Диск: свободно {disk_free_gb:.1f} / {disk_total_gb:.1f} GB
• Потоков: {threads}

**📊 СТАТИСТИКА КОМАНД**
• Всего команд: {total_commands}
• Топ-5: {', '.join([f'/{c}' for c, _ in top_commands[:5]])}

**❌ ОШИБКИ**
• Всего: {len(errors)}
• За час: {errors_last_hour} | За день: {errors_last_day}
• Типы: {', '.join([f'{k}({v})' for k, v in error_types.most_common(3)])}
• Последняя: {last_error[:80] if last_error else 'Нет'}...

**🔑 API КЛЮЧИ**
• Telegram: {'✅' if telegram_token else '❌'}
• OpenRouter: {'✅' if openrouter_key else '❌'} (лимиты: {openrouter_limit})
• GitHub: {'✅' if github_token else '❌'}
• Render: {'✅' if render_key else '❌'}

**📁 GITHUB**
• Репо: {github_repo}
• Ветка: {branch}
• Последний коммит: {last_commit}
• Автор: {last_commit_author} ({last_commit_date})

**🖥️ RENDER**
• Сервис ID: {render_service_id}
• Статус: {render_status}
• Последний деплой: {render_last_deploy}

**💾 БЭКАПЫ**
• Количество: {backups}
• Размер: {backup_size_kb:.1f} KB
• Последний: {last_backup}

**📋 ЛОГИ**
• Строк: {log_size_lines}
• Размер: {log_size_kb:.1f} KB
• Последние действия: {', '.join(last_actions[:3])}...

**🤖 ИИ МОДЕЛИ**
• Доступно: {len(FREE_MODELS)}
• Переключений моделей: {model_switches}

**👥 ПОЛЬЗОВАТЕЛИ**
• Уникальных: {len(user_ids)}
• Активных за 24ч: {len(active_users_24h)}
• Команд создано: {len(user_command_counts)}

**📈 АКТИВНОСТЬ**
• Сообщений в минуту: {messages_per_min}
• Пик активности: {peak_hour}:00 ({peak_value} команд)

**🔄 АВТОНОМИЯ**
• Автоисправлений: {auto_fixes} (успешно: {auto_fix_success})
• Откатов: {rollbacks}
• Последнее автоисправление: {last_auto_fix}

**🌐 СЕТЬ**
• GitHub API: {ping_github} ms
• Render API: {ping_render} ms
• OpenRouter API: {ping_openrouter} ms

**❤️ ЗДОРОВЬЕ**
• Вебхук: {webhook_status}
• Версия: {bot_version}
• Проверка: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

            bot.edit_message_text(report, chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")
            
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка сбора статистики: {e}", 
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
