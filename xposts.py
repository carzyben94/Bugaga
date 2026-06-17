# xposts.py
import requests
import xml.etree.ElementTree as ET
import threading
from datetime import datetime
import telebot

def register_xposts(bot):
    """Регистрирует обработчик команды /xposts"""
    
    @bot.message_handler(commands=['xposts'])
    def xposts_command(message):
        status_msg = bot.reply_to(message, "🐦 Ищу последние посты из X...")
        
        def do_xposts():
            try:
                accounts = [
                    {"username": "the_lentach", "name": "Лентач"}
                ]
                
                all_posts = []
                
                for account in accounts:
                    try:
                        url = f"https://nitter.net/{account['username']}/rss"
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        response = requests.get(url, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            root = ET.fromstring(response.content)
                            items = root.findall('.//item')
                            
                            for item in items[:3]:
                                title_elem = item.find('title')
                                if title_elem is not None and title_elem.text:
                                    text = title_elem.text.strip()
                                    
                                    pub_date = item.find('pubDate')
                                    date = pub_date.text if pub_date is not None else ""
                                    
                                    link = item.find('link')
                                    post_url = link.text if link is not None else ""
                                    
                                    if len(text) > 500:
                                        text = text[:500] + "..."
                                    
                                    all_posts.append({
                                        'username': account['username'],
                                        'name': account['name'],
                                        'text': text,
                                        'date': date[:16] if date else "",
                                        'url': post_url
                                    })
                                    
                        else:
                            alt_url = f"https://nitter.poast.org/{account['username']}/rss"
                            response = requests.get(alt_url, headers=headers, timeout=10)
                            if response.status_code == 200:
                                root = ET.fromstring(response.content)
                                items = root.findall('.//item')
                                
                                for item in items[:3]:
                                    title_elem = item.find('title')
                                    if title_elem is not None and title_elem.text:
                                        text = title_elem.text.strip()
                                        
                                        pub_date = item.find('pubDate')
                                        date = pub_date.text if pub_date is not None else ""
                                        
                                        link = item.find('link')
                                        post_url = link.text if link is not None else ""
                                        
                                        if len(text) > 500:
                                            text = text[:500] + "..."
                                        
                                        all_posts.append({
                                            'username': account['username'],
                                            'name': account['name'],
                                            'text': text,
                                            'date': date[:16] if date else "",
                                            'url': post_url
                                        })
                        
                    except Exception as e:
                        print(f"xposts_account_error: {account['username']}: {str(e)[:50]}")
                        continue
                
                if not all_posts:
                    bot.edit_message_text(
                        "❌ Не удалось загрузить посты. Попробуйте позже.",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )
                    return
                
                current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
                result = "🐦 *ПОСЛЕДНИЕ ПОСТЫ ИЗ X*\n"
                result += f"📅 {current_time}\n\n"
                
                for i, post in enumerate(all_posts[:3], 1):
                    result += f"📌 *@{post['username']}*\n"
                    result += f"{post['text']}\n"
                    result += f"🕐 {post['date']}\n"
                    if post['url']:
                        result += f"🔗 [Ссылка]({post['url']})\n"
                    
                    if i < len(all_posts[:3]):
                        result += "—" * 30 + "\n\n"
                
                result += "\n💡 /xposts — обновить посты"
                
                bot.edit_message_text(
                    result,
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                
            except Exception as e:
                bot.edit_message_text(
                    f"❌ Ошибка при загрузке постов: {str(e)[:100]}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )
        
        thread = threading.Thread(target=do_xposts, daemon=True)
        thread.start()