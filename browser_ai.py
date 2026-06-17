# browser_ai.py
import requests
import threading
from bs4 import BeautifulSoup
import trafilatura

def register_browser_ai(bot, agnes_api_key):
    """Регистрирует обработчик команды /browser_ai - ИИ с доступом в интернет"""

    @bot.message_handler(commands=['browser_ai'])
    def browser_ai_command(message):
        args = message.text.replace('/browser_ai', '').strip()
        if not args:
            bot.reply_to(message, "🌐 Использование: /browser_ai [URL] [вопрос]\n\n"
                                 "Пример:\n"
                                 "/browser_ai https://github.com Что это за сайт?\n"
                                 "/browser_ai https://news.ycombinator.com Главные новости?")
            return

        parts = args.split(' ', 1)
        if len(parts) < 2:
            bot.reply_to(message, "❌ Укажите URL и вопрос\n"
                                 "Пример: /browser_ai https://example.com О чём этот сайт?")
            return

        url = parts[0]
        question = parts[1]

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        status_msg = bot.reply_to(message, f"🌐 Открываю {url} и анализирую...")

        if not agnes_api_key:
            bot.edit_message_text(
                "❌ Agnes API ключ не настроен",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
            return

        def do_browser_ai():
            try:
                # 1. Получаем содержимое сайта через trafilatura
                text = None
                try:
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        text = trafilatura.extract(
                            downloaded,
                            include_comments=False,
                            include_tables=True,
                            include_links=False,
                            include_formatting=False
                        )
                except Exception as e:
                    print(f"trafilatura error: {e}")

                # 2. Если trafilatura не сработал — используем BeautifulSoup
                if not text or len(text) < 100:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    response = requests.get(url, headers=headers, timeout=15)

                    if response.status_code != 200:
                        bot.edit_message_text(
                            f"❌ Ошибка загрузки сайта: HTTP {response.status_code}",
                            chat_id=message.chat.id,
                            message_id=status_msg.message_id
                        )
                        return

                    soup = BeautifulSoup(response.text, 'html.parser')

                    for script in soup(["script", "style"]):
                        script.decompose()

                    text = soup.get_text(separator='\n', strip=True)
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    text = '\n'.join(lines)

                if not text or len(text) < 100:
                    bot.edit_message_text(
                        "❌ Не удалось извлечь содержимое сайта. Возможно, сайт требует JavaScript.",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )
                    return

                # 3. Ограничиваем текст
                if len(text) > 8000:
                    text = text[:8000] + "\n...(текст обрезан)"

                # 4. Отправляем в ИИ
                bot.edit_message_text(
                    f"📖 Прочитал {len(text)} символов. Анализирую...",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )

                # ✅ ИСПРАВЛЕНО: правильное закрытие f-строки
                prompt = (
                    "Ты — ИИ-ассистент с доступом в интернет. "
                    "Проанализируй содержимое сайта и ответь на вопрос пользователя.\n\n"
                    f"Вот содержимое сайта {url}:\n\n"
                    f"```\n{text}\n```\n\n"
                    f"Вопрос пользователя: {question}\n\n"
                    "Ответь на вопрос, основываясь только на содержимом сайта. "
                    "Если в содержимом нет ответа на вопрос, скажи об этом честно.\n\n"
                    "Ответ должен быть:\n"
                    "1. Кратким и по делу (максимум 2-3 абзаца)\n"
                    "2. Только на основе содержимого сайта\n"
                    "3. На русском языке"
                )

                # 5. Запрос к Agnes AI
                headers_ai = {
                    "Authorization": f"Bearer {agnes_api_key}",
                    "Content-Type": "application/json",
                }

                payload = {
                    "model": "agnes-2.0-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.3
                }

                r = requests.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers_ai,
                    json=payload,
                    timeout=60
                )

                if r.status_code == 200:
                    answer = r.json()["choices"][0]["message"]["content"]
                    bot.edit_message_text(
                        f"🌐 *Результат анализа:*\n\n{answer}\n\n🔗 {url}",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    bot.edit_message_text(
                        f"❌ Ошибка ИИ: {r.status_code}\n{str(r.text)[:200]}",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )

            except requests.exceptions.Timeout:
                bot.edit_message_text(
                    "⏰ Таймаут загрузки сайта. Попробуйте позже.",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )
            except Exception as e:
                bot.edit_message_text(
                    f"❌ Ошибка: {str(e)[:200]}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )

        threading.Thread(target=do_browser_ai, daemon=True).start()