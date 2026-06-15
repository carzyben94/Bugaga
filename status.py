import time
import os
import subprocess
import json
import requests
from collections import Counter

def register_status_full(bot):
    @bot.message_handler(commands=['status_full'])
    def status_full_command(message):
        status_msg = bot.reply_to(message, "📊 Собираю статистику...")
        
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
            
            # Отчёт
            report = f"""📊 СТАТУС БОТА

⏱️ ВРЕМЯ РАБОТЫ
• {days}д {hours}ч {minutes}м {seconds}с

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
• Доступно: {len(FREE_MODELS)}"""

            bot.edit_message_text(report, chat_id=message.chat.id, message_id=status_msg.message_id)
            
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка: {e}", 
                                  chat_id=message.chat.id, message_id=status_msg.message_id)
