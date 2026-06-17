# ai.py
import requests
import threading
import random

def register_ai(bot, agnes_api_key):
    """Регистрирует обработчик команды /ai через Agnes AI API"""

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
                headers = {
                    "Authorization": f"Bearer {agnes_api_key}",
                    "Content-Type": "application/json",
                }

                payload = {
                    "model": "agnes-2.0-flash",  # Пробуем одно название
                    "messages": [{"role": "user", "content": user_text}],
                    "max_tokens": 500,
                    "temperature": 0.7
                }

                # Пробуем разные эндпоинты
                endpoints = [
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    "https://api.agnes-ai.com/v1/chat/completions",
                ]

                response = None
                for endpoint in endpoints:
                    try:
                        r = requests.post(
                            endpoint,
                            headers=headers,
                            json=payload,
                            timeout=60
                        )
                        if r.status_code == 200:
                            response = r
                            break
                        elif r.status_code == 404:
                            continue  # Пробуем следующий эндпоинт
                        else:
                            response = r
                            break
                    except:
                        continue

                if response is None:
                    bot.edit_message_text(
                        "❌ Не удалось подключиться к Agnes AI.\n"
                        "Проверьте API-ключ или попробуйте позже.",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )
                    return

                if response.status_code == 200:
                    answer = response.json()["choices"][0]["message"]["content"]
                    bot.edit_message_text(
                        answer,
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )

                elif response.status_code == 429:
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
                        f"❌ Ошибка API: {response.status_code}\n{str(response.text)[:200]}",
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