# ai.py
import requests
import threading
import random

# ТОЛЬКО БЕСПЛАТНЫЕ МОДЕЛИ (ПРОВЕРЕНО)
FREE_MODELS = [
    "google/gemma-4-31b-it",                # ✅ Бесплатно
    "google/gemma-4-26b-a4b-it",            # ✅ Бесплатно
    "microsoft/phi-4",                      # ✅ Бесплатно
    "qwen/qwen-2.5-72b-instruct",           # ✅ Бесплатно
    "qwen/qwen-2.5-32b-instruct",           # ✅ Бесплатно
    "meta-llama/llama-4-maverick-17b",      # ✅ Бесплатно
    "meta-llama/llama-4-scout-17b",         # ✅ Бесплатно
    "deepseek/deepseek-r1-distill-qwen-32b", # ✅ Бесплатно
    "mistralai/mistral-small-3.1-24b",      # ✅ Бесплатно
]

def register_ai(bot, openrouter_api_key):
    def get_models():
        """Возвращает 3 модели для fallback"""
        selected = random.sample(FREE_MODELS, min(3, len(FREE_MODELS)))
        return selected

    @bot.message_handler(commands=['ai'])
    def ai_command(message):
        user_text = message.text.replace('/ai', '').strip()
        if not user_text:
            bot.reply_to(message, "🤖 Введите вопрос после /ai\nПример: /ai что такое нейросеть")
            return

        status_msg = bot.reply_to(message, "🤔 Думаю...")

        if not openrouter_api_key:
            bot.edit_message_text(
                "❌ OpenRouter API ключ не настроен",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
            return

        def do_ai():
            try:
                models = get_models()

                headers = {
                    "Authorization": f"Bearer {openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/bugaga_bot",
                    "X-Title": "Bugaga AI Bot"
                }

                payload = {
                    "models": models,
                    "messages": [{"role": "user", "content": user_text}],
                    "max_tokens": 500,
                    "temperature": 0.7
                }

                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                if r.status_code == 200:
                    answer = r.json()["choices"][0]["message"]["content"]
                    used_model = r.json().get("model", models[0])
                    bot.edit_message_text(
                        f"{answer}\n\n🤖 *Модель:* `{used_model}`",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='Markdown'
                    )
                elif r.status_code == 402:
                    bot.edit_message_text(
                        "⚠️ *Дневной лимит OpenRouter Free исчерпан*\n"
                        "50 запросов/день. Попробуйте завтра.\n\n"
                        "💡 Альтернативы:\n"
                        "• Groq — console.groq.com (бесплатно)\n"
                        "• Google AI Studio — aistudio.google.com\n"
                        "• Hugging Face — huggingface.co",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='Markdown'
                    )
                elif r.status_code == 429:
                    bot.edit_message_text(
                        "⚠️ *Превышен лимит запросов*\n"
                        "20 запросов/мин. Попробуйте через минуту.",
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
            except Exception as e:
                bot.edit_message_text(
                    f"❌ Ошибка: {str(e)[:200]}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )

        threading.Thread(target=do_ai, daemon=True).start()