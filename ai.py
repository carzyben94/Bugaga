import os
import requests
import json

class AgnesAI:
    def __init__(self):
        self.api_key = os.getenv("AGNES_API_KEY")
        self.api_url = os.getenv("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
        self.model = os.getenv("AI_MODEL", "agnes-2.0-flash")
    
    def ask(self, question: str, context_text: str = ""):
        if not self.api_key:
            return "❌ AGNES_API_KEY не настроен"
        
        if not context_text or context_text.strip() == "":
            context_text = "Страница не загружена или не содержит текста"
        
        system_prompt = """Ты помощник для анализа веб-страниц.
Отвечай на вопросы пользователя на основе содержимого страницы.
Если информации нет - честно скажи об этом.
Будь точным, полезным и лаконичным.
Используй русский язык для ответов."""

        user_content = f"Содержимое страницы:\n{context_text}\n\nВопрос пользователя: {question}"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                return f"❌ Ошибка API ({response.status_code}): {response.text[:200]}"
                
        except requests.exceptions.Timeout:
            return "❌ Таймаут запроса к AI"
        except requests.exceptions.ConnectionError:
            return "❌ Ошибка подключения к AI"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"