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

        # Разделяем URL и вопрос
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
                # 1. Получаем содержимое сайта через trafilatura (лучший парсер)
                downloaded = trafilatura.fetch_url(url)
                text = None
                
                if downloaded:
                    text = trafilatura.extract(
                        downloaded,
                        include_comments=False,
                        include_tables=True,
                        include_links=False,
                        include_formatting=False
                    )
                
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
                    
                    # Удаляем скрипты и стили
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    # Извлекаем основной текст
                    text = soup.get_text(separator='\n', strip=True)
                    
                    # Очищаем от лишних пробелов и пустых строк
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    text = '\n'.join(lines)

                if not text or len(text) < 100:
                    bot.edit_message_text(
                        "❌ Не удалось извлечь содержимое сайта. Возможно, сайт требует JavaScript.",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )
                    return

                # 3. Ограничиваем текст (первые 8000 символов)
                if len(text) > 8000:
                    text = text[:8000] + "\n...(текст обрезан)"

                # 4. Отправляем в ИИ
                bot.edit_message_text(
                    f"📖 Прочитал {len(text)} символов. Анализирую...",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )

                # Формируем промпт
                prompt = f"""Ты — ИИ-ассистент с доступом в интернет. Проанализируй содержимое сайта и ответь на вопрос пользователя.

Вот содержимое сайта {url}:
