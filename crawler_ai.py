# crawler_ai.py
import requests
import threading
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import trafilatura

def register_crawler_ai(bot, agnes_api_key):
    """Регистрирует обработчик команды /crawler_ai - ИИ исследует весь сайт"""

    def get_all_links(url, max_pages=10):
        """Собирает все ссылки с сайта (до max_pages страниц)"""
        visited = set()
        to_visit = [url]
        all_links = []
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        domain = urlparse(url).netloc
        
        while to_visit and len(visited) < max_pages:
            current_url = to_visit.pop(0)
            if current_url in visited:
                continue
                
            try:
                response = requests.get(current_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    continue
                    
                visited.add(current_url)
                all_links.append(current_url)
                
                soup = BeautifulSoup(response.text, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(current_url, href)
                    
                    # Только ссылки на том же домене
                    if urlparse(full_url).netloc == domain:
                        # Убираем якоря и дубликаты
                        full_url = full_url.split('#')[0]
                        if full_url not in visited and full_url not in to_visit:
                            to_visit.append(full_url)
                            
            except Exception as e:
                print(f"Ошибка при обходе {current_url}: {e}")
                continue
                
        return all_links

    def extract_text_from_url(url):
        """Извлекает текст с одной страницы"""
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                if text and len(text) > 100:
                    return text[:3000]
        except:
            pass
            
        # Fallback на BeautifulSoup
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text(separator='\n', strip=True)
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                return '\n'.join(lines)[:3000]
        except:
            pass
        return ""

    @bot.message_handler(commands=['crawler_ai'])
    def crawler_ai_command(message):
        args = message.text.replace('/crawler_ai', '').strip()
        if not args:
            bot.reply_to(message, "🌐 Использование: /crawler_ai [URL] [вопрос]")
            return

        parts = args.split(' ', 1)
        if len(parts) < 2:
            bot.reply_to(message, "❌ Укажите URL и вопрос\nПример: /crawler_ai https://news.ycombinator.com Какие новости?")
            return

        url = parts[0]
        question = parts[1]

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        status_msg = bot.reply_to(message, f"🕷️ Исследую сайт {url}...")

        if not agnes_api_key:
            bot.edit_message_text("❌ Agnes API ключ не настроен", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        def do_crawler_ai():
            try:
                # 1. Собираем все страницы
                bot.edit_message_text("🔍 Собираю все страницы сайта...", chat_id=message.chat.id, message_id=status_msg.message_id)
                pages = get_all_links(url, max_pages=15)
                
                if not pages:
                    bot.edit_message_text("❌ Не удалось найти страницы на сайте.", chat_id=message.chat.id, message_id=status_msg.message_id)
                    return

                bot.edit_message_text(f"📄 Найдено {len(pages)} страниц. Читаю содержимое...", chat_id=message.chat.id, message_id=status_msg.message_id)

                # 2. Собираем текст со всех страниц
                all_text = ""
                for i, page in enumerate(pages[:15]):
                    text = extract_text_from_url(page)
                    if text:
                        all_text += f"\n--- Страница: {page} ---\n{text}\n"
                    if i % 3 == 0:
                        bot.edit_message_text(f"📖 Прочитано {i+1}/{len(pages)} страниц...", chat_id=message.chat.id, message_id=status_msg.message_id)

                if len(all_text) < 200:
                    bot.edit_message_text("❌ Не удалось извлечь содержимое сайта.", chat_id=message.chat.id, message_id=status_msg.message_id)
                    return

                # 3. Ограничиваем текст
                if len(all_text) > 15000:
                    all_text = all_text[:15000] + "\n...(текст обрезан)"

                bot.edit_message_text(f"📖 Всего {len(all_text)} символов. Анализирую...", chat_id=message.chat.id, message_id=status_msg.message_id)

                # 4. Запрос к ИИ
                prompt = (
                    "Ты — ИИ-ассистент. Я дам тебе содержимое нескольких страниц сайта. "
                    "Проанализируй всё и ответь на вопрос пользователя.\n\n"
                    f"Содержимое сайта {url}:\n\n{all_text}\n\n"
                    f"Вопрос: {question}\n\n"
                    "Ответь кратко, только на основе содержимого сайта."
                )

                headers_ai = {
                    "Authorization": f"Bearer {agnes_api_key}",
                    "Content-Type": "application/json",
                }

                payload = {
                    "model": "agnes-2.0-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.3
                }

                r = requests.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers_ai,
                    json=payload,
                    timeout=90
                )

                if r.status_code == 200:
                    answer = r.json()["choices"][0]["message"]["content"]
                    bot.edit_message_text(
                        f"🌐 *Результат исследования:*\n\n{answer}\n\n"
                        f"📄 Изучено страниц: {len(pages)}\n🔗 {url}",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    bot.edit_message_text(f"❌ Ошибка ИИ: {r.status_code}\n{str(r.text)[:200]}", chat_id=message.chat.id, message_id=status_msg.message_id)

            except Exception as e:
                bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=message.chat.id, message_id=status_msg.message_id)

        threading.Thread(target=do_crawler_ai, daemon=True).start()