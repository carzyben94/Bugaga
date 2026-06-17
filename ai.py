# ai.py
import requests
import threading
import random

# АКТУАЛЬНЫЙ СПИСОК БЕСПЛАТНЫХ МОДЕЛЕЙ (ИЮНЬ 2026)
FREE_MODELS = [
    "openrouter/free",                                      # Автоматический роутер
    "openrouter/owl-alpha",                                 # Агентная, 1.05M контекст
    "nvidia/nemotron-3-ultra",                              # 55B MoE, 1M контекст
    "nvidia/nemotron-3-super-120b-a12b:free",               # 120B MoE, 1M контекст
    "nvidia/nemotron-3-nano-30b-a3b",                       # MoE, 256K контекст
    "nvidia/nemotron-nano-9b-v2",                           # Унифицированная модель
    "poolside/laguna-m1",                                   # Кодинг-агент, 128K
    "poolside/laguna-xs.2",                                 # Компактная кодинг
    "openai/gpt-oss-120b",                                  # 117B MoE
    "openai/gpt-oss-20b",                                   # 21B, Apache 2.0
    "nex-agi/nex-n2-pro",                                   # 397B MoE
    "google/gemma-4-31b-it",                                # 31B, 256K контекст
    "google/gemma-4-26b-a4b-it",                            # MoE, Apache 2.0
    "riverflow/riverflow-v2.5-pro",                         # Новая бесплатная
    "stepfun/step-3.7-flash",                               # MoE, 256K контекст
    "allenai/molmo-2-8b:free",                              # Vision-Language
    "meta-llama/llama-4-maverick-17b-128e-instruct:free",   # Llama 4 Maverick
    "meta-llama/llama-4-scout-17b-16e-instruct:free",       # Llama 4 Scout
]

def register_ai(bot, openrouter_api_key):
    """Регистрирует обработчик команды /ai с автоматическим fallback"""

    def get_models():
        """Возвращает 3 случайные модели для fallback (максимум 3)"""
        return random.sample(FREE_MODELS, min(3, len(FREE_MODELS)))

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
                        "• Groq — console.groq.com\n"
                        "• Google AI Studio — aistudio.google.com",
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