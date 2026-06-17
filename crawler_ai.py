# crawler_ai.py
import requests
import threading
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import trafilatura

def register_crawler_ai(bot, agnes_api_key):
    """Регистрирует обработчик команды /crawler_ai - ИИ собирает заголовки новостей"""

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
                    
                    if urlparse(full_url).netloc == domain:
                        full_url = full_url.split('#')[0]
                        if full_url not in visited and full_url not in to_visit:
                            to_visit.append(full_url)
                            
            except Exception as e:
                print(f"Ошибка при обходе {current_url}: {e}")
                continue
                
        return all_links

    def extract_headers_from_url(url):
        """Извлекает заголовки (h1, h2, h3) с одной страницы"""
        try:
            headers_list = []
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Собираем все заголовки h1, h2, h3
                for tag in soup.find_all(['h1', 'h2', 'h3']):
                    text = tag.get_text(strip=True)
                    if text and len(text) > 10 and len(text) < 200:  # Фильтруем мусор
                        headers_list.append(text)
                
                # Если заголовков нет — пробуем найти title
                if not headers_list:
                    title = soup.find('title')
                    if title:
                        headers_list.append(title.get_text(strip=True))
                        
        except:
            pass
        return headers_list

    @bot.message_handler(commands=['crawler_ai'])
    def crawler_ai_command(message):
        args = message.text.replace('/crawler_ai', '').strip()
        if not args:
            bot.reply_to(message, "🌐 Использование: /crawler_ai [URL]\n\n"
                                 "Пример: /crawler_ai https://lenta.ru\n"
                                 "Бот соберет заголовки новостей")
            return

        url = args

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        status_msg = bot.reply_to(message, f"🕷️ Собираю заголовки с {url}...")

        if not agnes_api_key:
            bot.edit_message_text("❌ Agnes API ключ не настроен", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        def do_crawler_ai():
            try:
                bot.edit_message_text("🔍 Ищу страницы на сайте...", chat_id=message.chat.id, message_id=status_msg.message_id)
                pages = get_all_links(url, max_pages=15)
                
                if not pages:
                    bot.edit_message_text("❌ Не удалось найти страницы на сайте.", chat_id=message.chat.id, message_id=status_msg.message_id)
                    return

                bot.edit_message_text(f"📄 Найдено {len(pages)} страниц. Собираю заголовки...", chat_id=message.chat.id, message_id=status_msg.message_id)

                # Собираем заголовки со всех страниц
                all_headers = []
                for i, page in enumerate(pages[:15]):
                    headers = extract_headers_from_url(page)
                    all_headers.extend(headers)
                    if i % 3 == 0:
                        bot.edit_message_text(f"📖 Обработано {i+1}/{len(pages)} страниц...", chat_id=message.chat.id, message_id=status_msg.message_id)

                # Убираем дубликаты и пустые строки
                unique_headers = []
                seen = set()
                for h in all_headers:
                    h_clean = h.strip()
                    if h_clean and h_clean not in seen and len(h_clean) > 10:
                        seen.add(h_clean)
                        unique_headers.append(h_clean)

                if not unique_headers:
                    bot.edit_message_text("❌ Не удалось найти заголовки на сайте.", chat_id=message.chat.id, message_id=status_msg.message_id)
                    return

                # Ограничиваем до 20 заголовков
                unique_headers = unique_headers[:20]

                # Формируем ответ
                result = f"📰 ЗАГОЛОВКИ НОВОСТЕЙ С {url}\n\n"
                for i, header in enumerate(unique_headers, 1):
                    result += f"{i}. {header}\n"
                result += f"\n📄 Найдено заголовков: {len(unique_headers)}"
                result += f"\n🔗 Источник: {url}"

                bot.edit_message_text(
                    result,
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )

            except Exception as e:
                bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=message.chat.id, message_id=status_msg.message_id)

        threading.Thread(target=do_crawler_ai, daemon=True).start()