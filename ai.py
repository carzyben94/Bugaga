# ai.py
import requests
import threading
import random

# AGNES AI - БЕСПЛАТНЫЕ МОДЕЛИ
AGNES_MODELS = [
    "agnes-2.0-flash",           # Текст, 1M контекст
    "agnes-image-2.0-flash",     # Генерация изображений 4K
    "agnes-video-2.0",           # Генерация видео со звуком
]

def register_ai(bot, agnes_api_key):
    """Регистрирует обработчик команды /ai через Agnes AI API"""

    def get_model():
        """Возвращает случайную модель для запроса"""
        return random.choice(AGNES_MODELS)

    @bot.message_handler(commands=['ai'])
    def ai_command(message):
        user_text = message.text.replace('/ai', '').strip()
        if not user_text:
            bot.reply_to(message, "🤖 Введите вопрос после /ai\nПример: /ai что такое нейросеть")
            return

        status_msg = bot.reply_to(message, "🤔 Думаю через Agnes AI...")

        if not agnes_api_key:
            bot.edit_message_text(
                "❌ Agnes API ключ не настроен",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
            return

        def do_ai():
            try:
                model = get_model()

                headers = {
                    "Authorization": f"Bearer {agnes_api_key}",
                    "Content-Type": "application/json",
                }

                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": user_text}],
                    "max_tokens": 500,
                    "temperature": 0.7
                }

                r = requests.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                if r.status_code == 200:
                    answer = r.json()["choices"][0]["message"]["content"]
                    used_model = r.json().get("model", model)
                    bot.edit_message_text(
                        f"{answer}\n\n🤖 *Модель:* `{used_model}`",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='Markdown'
                    )

                elif r.status_code == 429:
                    bot.edit_message_text(
                        "⚠️ *Превышен лимит запросов*\n"
                        "Agnes AI Free: 20 запросов/мин.\n"
                        "Попробуйте через минуту.",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='Markdown'
                    )

                else:
                    bot.edit_message_text(
                        f"❌ Ошибка API: {r.status_code}\n{str(r.text)[:200]}",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )

            except requests.exceptions.Timeout:
                bot.edit_message_text(
                    "⏰ Таймаут запроса. Попробуйте позже.",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )

            except Exception as e:
                bot.edit_message_text(
                    f"❌ Ошибка: {str(e)[:200]}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )

        threading.Thread(target=do_ai, daemon=True).start()