# super_agent.py
import os
import re
import json
import logging
import requests
import base64
import time
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SuperAgent:
    def __init__(self, config):
        """
        Супер-агент с доступом ко всем сервисам
        
        Args:
            config: словарь с токенами и настройками
        """
        self.config = config
        self.github_token = config.get('GITHUB_TOKEN')
        self.render_api_key = config.get('RENDER_API_KEY')
        self.telegram_token = config.get('TELEGRAM_TOKEN')
        self.openrouter_key = config.get('OPENROUTER_API_KEY')
        self.repo = config.get('GITHUB_REPO', 'carzyben94/Bugaga')
        self.service_id = config.get('RENDER_SERVICE_ID')
        
        self.headers_github = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.headers_openrouter = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json"
        }
        self.headers_render = {
            "Authorization": f"Bearer {self.render_api_key}",
            "Content-Type": "application/json"
        }
        
        self.analysis_history = []
    
    # ===== GITHUB =====
    def github_get_file(self, path: str) -> str:
        """Получает файл из GitHub репозитория"""
        try:
            url = f"https://api.github.com/repos/{self.repo}/contents/{path}"
            response = requests.get(url, headers=self.headers_github)
            
            if response.status_code == 200:
                content = response.json()
                return base64.b64decode(content['content']).decode('utf-8')
            else:
                logger.error(f"GitHub ошибка: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"GitHub ошибка: {e}")
            return None
    
    def github_update_file(self, path: str, content: str, message: str = "Auto-update by AI agent") -> bool:
        """Обновляет файл в GitHub"""
        try:
            url = f"https://api.github.com/repos/{self.repo}/contents/{path}"
            get_response = requests.get(url, headers=self.headers_github)
            
            if get_response.status_code != 200:
                sha = None
            else:
                sha = get_response.json()['sha']
            
            data = {
                "message": message,
                "content": base64.b64encode(content.encode('utf-8')).decode('utf-8'),
                "sha": sha
            }
            
            response = requests.put(url, headers=self.headers_github, json=data)
            
            if response.status_code in [200, 201]:
                logger.info(f"Файл {path} обновлён в GitHub")
                return True
            else:
                logger.error(f"Ошибка обновления: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"GitHub ошибка: {e}")
            return False
    
    def github_list_files(self, path: str = "") -> List[str]:
        """Получает список файлов в репозитории"""
        try:
            url = f"https://api.github.com/repos/{self.repo}/contents/{path}"
            response = requests.get(url, headers=self.headers_github)
            
            if response.status_code == 200:
                files = response.json()
                return [f['name'] for f in files if f['type'] == 'file']
            return []
        except Exception as e:
            logger.error(f"GitHub ошибка: {e}")
            return []
    
    # ===== RENDER =====
    def render_restart_service(self) -> bool:
        """Перезапускает сервис на Render"""
        if not self.service_id:
            logger.error("RENDER_SERVICE_ID не настроен")
            return False
        
        try:
            url = f"https://api.render.com/v1/services/{self.service_id}/restart"
            response = requests.post(url, headers=self.headers_render)
            
            if response.status_code in [200, 202]:
                logger.info("Сервис на Render перезапущен")
                return True
            else:
                logger.error(f"Ошибка перезапуска: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Render ошибка: {e}")
            return False
    
    def render_get_service_info(self) -> Dict:
        """Получает информацию о сервисе на Render"""
        if not self.service_id:
            return {"error": "RENDER_SERVICE_ID не настроен"}
        
        try:
            url = f"https://api.render.com/v1/services/{self.service_id}"
            response = requests.get(url, headers=self.headers_render)
            
            if response.status_code == 200:
                return response.json()
            return {"error": f"Ошибка: {response.status_code}"}
            
        except Exception as e:
            return {"error": str(e)}
    
    def render_get_deploy_logs(self, limit: int = 50) -> str:
        """Получает логи деплоя с Render"""
        if not self.service_id:
            return "RENDER_SERVICE_ID не настроен"
        
        try:
            url = f"https://api.render.com/v1/services/{self.service_id}/deploys"
            response = requests.get(url, headers=self.headers_render)
            
            if response.status_code == 200:
                deploys = response.json()
                if not deploys:
                    return "Нет логов деплоя"
                
                logs = f"📋 ПОСЛЕДНИЕ ДЕПЛОИ:\n\n"
                for i, deploy in enumerate(deploys[:limit]):
                    status = deploy.get('status', 'unknown')
                    emoji = "✅" if status == "live" else "🔄" if status == "in_progress" else "❌"
                    logs += f"{emoji} {deploy.get('createdAt', '')} - {status}\n"
                    logs += f"   Commit: {deploy.get('commit', {}).get('message', '')[:50]}\n"
                
                return logs
            return f"Ошибка: {response.status_code}"
            
        except Exception as e:
            return f"Ошибка: {e}"
    
    # ===== OPENROUTER (AI) =====
    def ai_analyze_code(self, code: str) -> Dict:
        """Анализирует код через OpenRouter"""
        prompt = f"""
        Ты — эксперт по Python и Telegram ботам. Проанализируй этот код:
        
        ```python
        {code[:4000]}
        ```
        
        Ответь в формате JSON:
        {{
            "issues": [
                {{"line": номер, "message": "проблема", "severity": "high/medium/low"}}
            ],
            "suggestions": ["рекомендация 1", "рекомендация 2"],
            "improvements": [
                {{"description": "описание улучшения", "code": "исправленный код"}}
            ],
            "summary": "краткий вывод"
        }}
        """
        
        try:
            payload = {
                "model": "openrouter/free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=self.headers_openrouter,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            
            return {"error": "Не удалось получить анализ"}
            
        except Exception as e:
            return {"error": str(e)}
    
    # ===== TELEGRAM =====
    def send_telegram_message(self, chat_id: str, text: str) -> bool:
        """Отправляет сообщение в Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=data)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram ошибка: {e}")
            return False
    
    def get_telegram_updates(self, limit: int = 10) -> List[Dict]:
        """Получает последние сообщения в Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/getUpdates"
            response = requests.get(url, params={"limit": limit})
            
            if response.status_code == 200:
                return response.json().get('result', [])
            return []
        except Exception as e:
            logger.error(f"Telegram ошибка: {e}")
            return []
    
    # ===== ОСНОВНЫЕ ФУНКЦИИ =====
    def analyze_current_bot(self) -> Dict:
        """Анализирует текущий код бота из GitHub"""
        bot_code = self.github_get_file("bot.py")
        if not bot_code:
            return {"error": "Не удалось получить файл bot.py из GitHub"}
        
        issues = self._static_analysis(bot_code)
        metrics = self._code_metrics(bot_code)
        ai_analysis = self.ai_analyze_code(bot_code)
        render_info = self.render_get_service_info()
        
        return {
            "code": bot_code,
            "issues": issues,
            "metrics": metrics,
            "ai_suggestions": ai_analysis.get('suggestions', []),
            "ai_improvements": ai_analysis.get('improvements', []),
            "ai_summary": ai_analysis.get('summary', ''),
            "render_status": render_info.get('status', 'unknown'),
            "timestamp": datetime.now().isoformat()
        }
    
    def _static_analysis(self, code: str) -> List[Dict]:
        """Статический анализ кода"""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            if len(line) > 100:
                issues.append({
                    'line': i,
                    'message': f'Строка слишком длинная ({len(line)} символов)',
                    'severity': 'low'
                })
            
            if 'TODO' in line or 'FIXME' in line:
                issues.append({
                    'line': i,
                    'message': 'Найден TODO/FIXME комментарий',
                    'severity': 'medium'
                })
            
            if 'except:' in line and 'except Exception' not in line:
                issues.append({
                    'line': i,
                    'message': 'Голый except без указания исключения',
                    'severity': 'high'
                })
        
        if 'try:' in code and 'except' not in code:
            issues.append({
                'line': 0,
                'message': 'Есть try без except',
                'severity': 'high'
            })
        
        if 'logger' not in code and 'log_action' not in code:
            issues.append({
                'line': 0,
                'message': 'Нет системы логирования',
                'severity': 'medium'
            })
        
        return issues
    
    def _code_metrics(self, code: str) -> Dict:
        """Метрики кода"""
        lines = code.split('\n')
        
        return {
            'total_lines': len(lines),
            'code_lines': len([l for l in lines if l.strip() and not l.strip().startswith('#')]),
            'comment_lines': len([l for l in lines if l.strip().startswith('#')]),
            'functions': len([l for l in lines if 'def ' in l]),
            'classes': len([l for l in lines if 'class ' in l]),
            'imports': len([l for l in lines if 'import ' in l or 'from ' in l])
        }
    
    def auto_improve_code(self, issue_description: str) -> bool:
        """Автоматически улучшает код на основе описания проблемы"""
        bot_code = self.github_get_file("bot.py")
        if not bot_code:
            return False
        
        prompt = f"""
        Вот код Telegram бота на Python:
        
        ```python
        {bot_code[:3000]}
        ```
        
        Задача: {issue_description}
        
        Покажи только исправленный код, без объяснений.
        """
        
        try:
            payload = {
                "model": "openrouter/free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=self.headers_openrouter,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                improved_code = response.json()["choices"][0]["message"]["content"]
                code_match = re.search(r'```python\n(.*?)\n```', improved_code, re.DOTALL)
                if code_match:
                    improved_code = code_match.group(1)
                
                self.github_update_file(
                    "bot.py",
                    improved_code,
                    f"Auto-improve: {issue_description[:50]}"
                )
                
                time.sleep(2)
                self.render_restart_service()
                
                return True
            
        except Exception as e:
            logger.error(f"Ошибка авто-улучшения: {e}")
        
        return False
    
    def get_full_report(self) -> str:
        """Полный отчёт о состоянии системы"""
        analysis = self.analyze_current_bot()
        
        if "error" in analysis:
            return f"❌ {analysis['error']}"
        
        report = "🧠 *СУПЕР-АГЕНТ: ОТЧЁТ О СОСТОЯНИИ*\n\n"
        
        metrics = analysis.get('metrics', {})
        report += "📊 *Метрики кода:*\n"
        report += f"   • Всего строк: {metrics.get('total_lines', 0)}\n"
        report += f"   • Код строк: {metrics.get('code_lines', 0)}\n"
        report += f"   • Комментариев: {metrics.get('comment_lines', 0)}\n"
        report += f"   • Функций: {metrics.get('functions', 0)}\n"
        report += f"   • Классов: {metrics.get('classes', 0)}\n"
        report += f"   • Импортов: {metrics.get('imports', 0)}\n\n"
        
        issues = analysis.get('issues', [])
        if issues:
            report += "⚠️ *Найденные проблемы:*\n"
            for issue in issues:
                emoji = "🔴" if issue.get('severity') == 'high' else "🟡" if issue.get('severity') == 'medium' else "🟢"
                report += f"   {emoji} {issue['message']} (строка {issue['line']})\n"
            report += "\n"
        
        suggestions = analysis.get('ai_suggestions', [])
        if suggestions:
            report += "💡 *Рекомендации AI:*\n"
            for s in suggestions[:5]:
                report += f"   • {s}\n"
            report += "\n"
        
        if analysis.get('ai_summary'):
            report += f"📌 *Вывод:* {analysis['ai_summary']}\n\n"
        
        status = analysis.get('render_status', 'unknown')
        status_emoji = "✅" if status == "live" else "🔄" if status == "in_progress" else "❌"
        report += f"☁️ *Render:* {status_emoji} {status}\n\n"
        
        report += "🔗 *Доступные сервисы:*\n"
        report += f"   ✅ GitHub: {self.repo}\n"
        report += f"   ✅ Telegram: активен\n"
        report += f"   ✅ OpenRouter: активен\n"
        report += f"   ✅ Render: {'активен' if self.service_id else 'не настроен'}\n\n"
        
        report += f"🕐 Обновлено: {analysis.get('timestamp', '')}"
        
        return report