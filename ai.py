# ai.py
import requests
import threading
import random

# Актуальные бесплатные модели OpenRouter на июнь 2026 года
FREE_MODELS = [
    "openrouter/free",
    "openrouter/owl-alpha",              # Агентная модель, 1M контекст
    "nvidia/nemotron-3-ultra",           # 55B MoE, 1M контекст
    "nvidia/nemotron-3-super",           # 120B MoE, 1M контекст
    "nvidia/nemotron-3-nano-30b-a3b",    # MoE, 256K контекст
    "nvidia/nemotron-nano-9b-v2",        # Унифицированная модель
    "poolside/laguna-m1",                # Флагманская кодинг-модель
    "openai/gpt-oss-120b",               # 117B MoE
    "openai/gpt-oss-20b",                # 21B, Apache 2.0
    "nex-agi/nex-n2-pro",                # 397B MoE
    "google/gemma-4-31b-it",             # 31B, 256K контекст
    "google/gemma-4-26b-a4b-it",         # MoE версия
    "riverflow/riverflow-v2.5-pro",      # Новая бесплатная модель
    "stepfun/step-3.7-flash",            # MoE, 256K контекст
]

def register_ai(bot, openrouter_api_key):
    """Регистрирует обработчик команды /ai с автоматическим fallback между моделями"""

    def get_models_for_fallback():
        """Возвращает массив моделей для fallback-роутинга"""
        # Берем 3 случайные модели (максимум для fallbacks)
        selected = random.sample(FREE_MODELS, min(3, len(FREE_MODELS)))
        # Всегда добавляем openrouter/free как резерв
        if "openrouter/free" not in selected:
            selected[0] = "openrouter/free"
        return selected

    @bot.message_handler(commands=['ai'])
    def ai_command(message):
        user_text = message.text.replace('/ai', '').strip()
        if not user_text:
            bot.reply_to(message, "🤖 Введите вопрос после /ai\nПример: /ai что такое нейросеть")
            return

        status_msg = bot.reply_to(message, "🤔 Думаю...")

        if not openrouter_api_key:
            bot.edit_message_text("❌ OpenRouter API ключ не настроен",
                                  chat_id=message.chat.id,
                                  message_id=status_msg.message_id)
            return

        def do_ai():
            try:
                models = get_models_for_fallback()

                headers = {
                    "Authorization": f"Bearer {openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/bugaga_bot",
                    "X-Title": "Bugaga AI Bot"
                }

                payload = {
                    "models": models,  # Массив моделей для автоматического fallback
                    "messages": [{"role": "user", "content": user_text}],
                    "max_tokens": 500
                }

                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                if r.status_code == 200:
                    answer = r.json()["choices"][0]["message"]["content"]
                    used_model = r.json().get("model", "openrouter/free")
                    bot.edit_message_text(
                        f"{answer}\n\n🤖 *Модель:* `{used_model}`",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='Markdown'
                    )
                elif r.status_code == 429:
                    bot.edit_message_text(
                        "⚠️ *Превышен лимит запросов*\n"
                        "OpenRouter Free: 20 запросов/мин, 50/день\n"
                        "Попробуйте позже или добавьте $10 для увеличения до 1000/день",
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