# qwen_bot.py
import os
import json  
import asyncio
import logging
import uuid
import httpx
from datetime import datetime
from typing import Optional, Dict, List, Generator, AsyncGenerator
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ============================================================
# НАСТРОЙКИ
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
QWEN_TOKEN = os.getenv("QWEN_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# ЗАГРУЗКА КУК
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"✅ Загружено {len(COOKIES)} кук из cookies.py")
except ImportError:
    COOKIES = []
    logger.warning("⚠️ cookies.py не найден")

# ============================================================
# QWEN КЛИЕНТ (на httpx)
# ============================================================

class QwenClient:
    """Клиент для работы с Qwen API на httpx"""
    
    def __init__(self, token: Optional[str] = None):
        self.base_url = "https://chat.qwen.ai/api/v2"
        self.client = httpx.Client(timeout=60.0)
        
        # Заголовки из перехваченных запросов
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/150.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Referer": "https://chat.qwen.ai/",
            "source": "web",
            "Version": "0.2.81",
            "bx-v": "2.5.37",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
            "Timezone": datetime.now().strftime("%a %b %d %Y %H:%M:%S GMT+0000")
        }
        
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        
        # Загрузка кук из cookies.py
        if COOKIES:
            for cookie in COOKIES:
                name = cookie.get("name")
                value = cookie.get("value")
                domain = cookie.get("domain", ".qwen.ai")
                path = cookie.get("path", "/")
                
                if name and value:
                    self.client.cookies.set(name, value, domain=domain, path=path)
            
            logger.info(f"✅ Установлено {len(COOKIES)} кук")
        else:
            logger.warning("⚠️ Куки не загружены")
        
        self._load_cookies_file()
    
    def _load_cookies_file(self):
        """Дополнительная загрузка кук из JSON файла"""
        try:
            with open("qwen_cookies.json", "r") as f:
                cookies = json.load(f)
                for name, value in cookies.items():
                    self.client.cookies.set(name, value)
                logger.info(f"✅ Загружено {len(cookies)} кук из qwen_cookies.json")
        except FileNotFoundError:
            pass
    
    def _save_cookies(self):
        """Сохраняем куки в файл"""
        cookies = dict(self.client.cookies)
        with open("qwen_cookies.json", "w") as f:
            json.dump(cookies, f)
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Универсальный метод для запросов"""
        url = f"{self.base_url}{endpoint}"
        self.headers["X-Request-Id"] = str(uuid.uuid4())
        
        try:
            response = self.client.request(
                method, 
                url, 
                headers=self.headers,
                **kwargs
            )
            
            logger.info(f"📤 {method} {endpoint} -> {response.status_code}")
            
            if response.status_code == 429:
                logger.warning("⚠️ Rate limit, ждем 5 секунд...")
                import time
                time.sleep(5)
                return self._request(method, endpoint, **kwargs)
            
            if response.status_code == 403:
                logger.error(f"❌ Ошибка авторизации: {response.text}")
                raise Exception("Требуется авторизация. Проверьте куки или токен.")
            
            if response.status_code == 401:
                logger.error(f"❌ Не авторизован: {response.text}")
                raise Exception("Не авторизован. Обновите куки.")
            
            response.raise_for_status()
            self._save_cookies()
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"❌ Ошибка запроса: {e}")
            raise Exception(f"Ошибка запроса: {e}")
    
    def chat(self, prompt: str, stream: bool = False, **kwargs) -> Dict:
        """Отправка запроса к модели"""
        payload = {
            "model": "qwen-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000)
        }
        return self._request("POST", "/chat/completions", json=payload)
    
    def chat_stream(self, prompt: str, **kwargs) -> Generator:
        """Потоковый чат (синхронный генератор)"""
        payload = {
            "model": "qwen-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000)
        }
        
        url = f"{self.base_url}/chat/completions"
        self.headers["X-Request-Id"] = str(uuid.uuid4())
        
        with self.client.stream("POST", url, headers=self.headers, json=payload) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]
                        if data != '[DONE]':
                            try:
                                chunk = json.loads(data)
                                if 'choices' in chunk and chunk['choices']:
                                    content = chunk['choices'][0].get('delta', {}).get('content', '')
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
    
    def get_chats(self, page: int = 1) -> Dict:
        """Получение истории чатов"""
        params = {"page": page, "exclude_project": "true"}
        return self._request("GET", "/chats/", params=params)
    
    def get_folders(self) -> Dict:
        """Получение папок"""
        params = {"exclude_project": "true"}
        return self._request("GET", "/folders/", params=params)
    
    def get_notifications(self) -> Dict:
        """Получение уведомлений"""
        params = {"type": "memory"}
        return self._request("GET", "/notifications/latest", params=params)
    
    def get_chat_messages(self, chat_id: str) -> Dict:
        """Получение сообщений чата"""
        return self._request("GET", f"/chats/{chat_id}")
    
    def delete_chat(self, chat_id: str) -> Dict:
        """Удаление чата"""
        return self._request("DELETE", f"/chats/{chat_id}")
    
    def close(self):
        """Закрываем клиент"""
        self.client.close()

# ============================================================
# СОСТОЯНИЯ
# ============================================================

user_sessions = {}  # {user_id: {"history": [], "mode": "chat"}}

# ============================================================
# КОМАНДЫ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    keyboard = [
        [InlineKeyboardButton("💬 Чат", callback_data="mode_chat")],
        [InlineKeyboardButton("📚 История", callback_data="history")],
        [InlineKeyboardButton("📁 Папки", callback_data="folders")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data="notifications")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 **Qwen Bot**\n\n"
        "Я бот для работы с Qwen AI от Alibaba.\n\n"
        "**Команды:**\n"
        "/qwen <текст> - задать вопрос\n"
        "/history - показать историю\n"
        "/folders - показать папки\n"
        "/notifications - уведомления\n"
        "/clear - очистить историю\n\n"
        "Или используйте кнопки ниже 👇",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def qwen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /qwen - задать вопрос"""
    if not context.args:
        await update.message.reply_text(
            "❌ Введите запрос\n"
            "Пример: `/qwen Что такое Python?`",
            parse_mode='Markdown'
        )
        return
    
    prompt = " ".join(context.args)
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {"history": [], "mode": "chat"}
    user_sessions[user_id]["history"].append({"role": "user", "content": prompt})
    
    status_msg = await update.message.reply_text("🤔 Думаю...")
    
    client = None
    try:
        client = QwenClient(QWEN_TOKEN)
        response = client.chat(prompt)
        
        if 'choices' in response:
            answer = response['choices'][0]['message']['content']
            user_sessions[user_id]["history"].append({"role": "assistant", "content": answer})
            
            if len(answer) > 3000:
                answer = answer[:3000] + "...\n\n(ответ обрезан)"
            
            await status_msg.edit_text(
                f"💬 **Вопрос:** {prompt}\n\n"
                f"📝 **Ответ:**\n{answer}",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(f"❌ Ошибка: {json.dumps(response, ensure_ascii=False)}")
            
    except Exception as e:
        logger.error(f"Ошибка /qwen: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if client:
            client.close()

async def qwen_stream_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /qwen_stream - потоковый ответ"""
    if not context.args:
        await update.message.reply_text("❌ Введите запрос")
        return
    
    prompt = " ".join(context.args)
    status_msg = await update.message.reply_text("📡 Получаю поток...")
    
    client = None
    try:
        client = QwenClient(QWEN_TOKEN)
        full_response = ""
        
        for chunk in client.chat_stream(prompt):
            full_response += chunk
            if len(full_response) % 100 < 20:
                await status_msg.edit_text(
                    f"📡 **Генерация:**\n{full_response[:500]}...",
                    parse_mode='Markdown'
                )
        
        await status_msg.edit_text(
            f"💬 **Вопрос:** {prompt}\n\n"
            f"📝 **Ответ:**\n{full_response[:3000]}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка /qwen_stream: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if client:
            client.close()

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /history - показать историю"""
    status_msg = await update.message.reply_text("📚 Загружаю историю...")
    
    client = None
    try:
        client = QwenClient(QWEN_TOKEN)
        history = client.get_chats(page=1)
        
        if 'data' in history and history['data']:
            caption = "📚 **Последние чаты:**\n\n"
            for chat in history['data'][:10]:
                title = chat.get('title', 'Без названия')[:50]
                created = chat.get('created_at', '')
                chat_id = chat.get('id', '')
                caption += f"• `{title}`\n  🕐 {created}\n  🆔 `{chat_id}`\n\n"
            
            caption += "\n_Для просмотра сообщений используйте /messages <chat_id>_"
            await status_msg.edit_text(caption, parse_mode='Markdown')
        else:
            await status_msg.edit_text("📭 История пуста")
            
    except Exception as e:
        logger.error(f"Ошибка /history: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if client:
            client.close()

async def messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /messages <chat_id> - показать сообщения чата"""
    if not context.args:
        await update.message.reply_text("❌ Укажите ID чата\nПример: `/messages abc123`", parse_mode='Markdown')
        return
    
    chat_id = context.args[0]
    status_msg = await update.message.reply_text("📨 Загружаю сообщения...")
    
    client = None
    try:
        client = QwenClient(QWEN_TOKEN)
        messages = client.get_chat_messages(chat_id)
        
        if 'data' in messages and messages['data']:
            caption = f"💬 **Сообщения чата** `{chat_id}`\n\n"
            for msg in messages['data'][:20]:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:200]
                if role == 'user':
                    caption += f"👤 **Вы:** {content}\n\n"
                else:
                    caption += f"🤖 **Qwen:** {content}\n\n"
            
            await status_msg.edit_text(caption[:4000], parse_mode='Markdown')
        else:
            await status_msg.edit_text("📭 Сообщений нет")
            
    except Exception as e:
        logger.error(f"Ошибка /messages: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if client:
            client.close()

async def folders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /folders - показать папки"""
    status_msg = await update.message.reply_text("📁 Загружаю папки...")
    
    client = None
    try:
        client = QwenClient(QWEN_TOKEN)
        folders = client.get_folders()
        
        if 'data' in folders and folders['data']:
            caption = "📁 **Папки:**\n\n"
            for folder in folders['data']:
                name = folder.get('name', 'Без названия')
                count = folder.get('chat_count', 0)
                folder_id = folder.get('id', '')
                caption += f"• `{name}` ({count} чатов)\n  🆔 `{folder_id}`\n\n"
            
            await status_msg.edit_text(caption, parse_mode='Markdown')
        else:
            await status_msg.edit_text("📭 Папок нет")
            
    except Exception as e:
        logger.error(f"Ошибка /folders: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if client:
            client.close()

async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /notifications - показать уведомления"""
    status_msg = await update.message.reply_text("🔔 Загружаю уведомления...")
    
    client = None
    try:
        client = QwenClient(QWEN_TOKEN)
        notifications = client.get_notifications()
        
        caption = "🔔 **Уведомления:**\n\n"
        caption += f"```json\n{json.dumps(notifications, indent=2, ensure_ascii=False)[:2000]}\n```"
        await status_msg.edit_text(caption, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Ошибка /notifications: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if client:
            client.close()

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /clear - очистить историю"""
    user_id = update.effective_user.id
    if user_id in user_sessions:
        user_sessions[user_id]["history"] = []
    
    await update.message.reply_text("🧹 История очищена")

async def delete_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /delete <chat_id> - удалить чат"""
    if not context.args:
        await update.message.reply_text("❌ Укажите ID чата\nПример: `/delete abc123`", parse_mode='Markdown')
        return
    
    chat_id = context.args[0]
    status_msg = await update.message.reply_text(f"🗑️ Удаляю чат `{chat_id}`...", parse_mode='Markdown')
    
    client = None
    try:
        client = QwenClient(QWEN_TOKEN)
        result = client.delete_chat(chat_id)
        await status_msg.edit_text(f"✅ Чат `{chat_id}` удален", parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Ошибка /delete: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if client:
            client.close()

# ============================================================
# ОБРАБОТЧИК КНОПОК
# ============================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "mode_chat":
        await query.edit_message_text(
            "💬 **Режим чата**\n\n"
            "Просто отправьте сообщение или используйте команду:\n"
            "`/qwen <текст>`\n\n"
            "Для потокового ответа:\n"
            "`/qwen_stream <текст>`",
            parse_mode='Markdown'
        )
    
    elif data == "history":
        # Создаем фейковое сообщение для history_command
        class FakeUpdate:
            def __init__(self, effective_user, message):
                self.effective_user = effective_user
                self.message = message
        
        fake_msg = await query.message.reply_text("📚 Загружаю историю...")
        fake_update = FakeUpdate(update.effective_user, fake_msg)
        await history_command(fake_update, context)
    
    elif data == "folders":
        fake_msg = await query.message.reply_text("📁 Загружаю папки...")
        fake_update = FakeUpdate(update.effective_user, fake_msg)
        await folders_command(fake_update, context)
    
    elif data == "notifications":
        fake_msg = await query.message.reply_text("🔔 Загружаю уведомления...")
        fake_update = FakeUpdate(update.effective_user, fake_msg)
        await notifications_command(fake_update, context)
    
    elif data == "help":
        await query.edit_message_text(
            "❓ **Помощь**\n\n"
            "**Основные команды:**\n"
            "/qwen <текст> - задать вопрос\n"
            "/qwen_stream <текст> - потоковый ответ\n"
            "/history - история чатов\n"
            "/messages <id> - сообщения чата\n"
            "/folders - список папок\n"
            "/notifications - уведомления\n"
            "/delete <id> - удалить чат\n"
            "/clear - очистить историю\n\n"
            "**Требуется токен Qwen?**\n"
            "Установите переменную QWEN_TOKEN",
            parse_mode='Markdown'
        )

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qwen", qwen_command))
    app.add_handler(CommandHandler("qwen_stream", qwen_stream_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("messages", messages_command))
    app.add_handler(CommandHandler("folders", folders_command))
    app.add_handler(CommandHandler("notifications", notifications_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("delete", delete_chat_command))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🚀 Qwen Bot запущен!")
    logger.info(f"🍪 Загружено кук: {len(COOKIES)}")
    logger.info("📋 Доступные команды:")
    logger.info("  /qwen <текст> - задать вопрос")
    logger.info("  /qwen_stream <текст> - потоковый ответ")
    logger.info("  /history - история чатов")
    logger.info("  /messages <id> - сообщения чата")
    logger.info("  /folders - папки")
    logger.info("  /notifications - уведомления")
    logger.info("  /delete <id> - удалить чат")
    logger.info("  /clear - очистить историю")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()