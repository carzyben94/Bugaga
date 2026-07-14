import os
import time
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import TELEGRAM_TOKEN, MAX_HISTORY
from browser import Browser, file_logger
from ai import ask_ai_for_command, ask_ai_for_answer

# ==================== ПАМЯТЬ ====================
class Memory:
    def __init__(self, max_items=MAX_HISTORY):
        self.max_items = max_items
        self.history = []
        self.current_snapshot = None
        self.current_url = None
        self.current_title = None
        self.browser = None
    
    def add_action(self, action_type, data=None):
        entry = {"timestamp": datetime.now().isoformat(), "type": action_type, "data": data}
        self.history.append(entry)
        if len(self.history) > self.max_items:
            self.history = self.history[-self.max_items:]
        file_logger.log(f"📝 Добавлено в память: {action_type}", "DEBUG")
    
    def set_snapshot(self, snapshot, url, title, browser=None):
        self.current_snapshot = snapshot
        self.current_url = url
        self.current_title = title
        if browser:
            self.browser = browser
        self.add_action("snapshot", {"url": url, "title": title, "elements": len(snapshot.get('elements', []))})
    
    def get_last_url(self, index=0):
        snapshots = [a for a in self.history if a['type'] == 'snapshot']
        if snapshots and len(snapshots) > index:
            return snapshots[-(index + 1)].get('data', {}).get('url')
        return None
    
    def find_element_by_text(self, text):
        if not self.current_snapshot:
            return None
        interactive = self.current_snapshot.get('interactive', [])
        text_lower = text.lower().strip()
        for el in interactive:
            el_text = el.get('text', '').lower().strip()
            if el_text == text_lower or text_lower in el_text or el_text in text_lower:
                return {'selector': el.get('selector'), 'text': el.get('text'), 'type': el.get('type'), 'visible': el.get('visible', True)}
        return None
    
    def get_element_names(self):
        if not self.current_snapshot:
            return []
        return [el.get('text', '').strip() for el in self.current_snapshot.get('interactive', [])[:50] if el.get('text', '').strip()]
    
    def get_context_for_ai(self):
        context = []
        if self.current_title:
            context.append(f"Current page: {self.current_title} ({self.current_url})")
        element_names = self.get_element_names()
        if element_names:
            context.append("\nAvailable interactive elements:")
            context.extend([f"• {name}" for name in element_names[:30]])
        if self.history:
            context.append("\nRecent actions:")
            for action in self.history[-5:]:
                action_type = action.get('type', 'unknown')
                timestamp = action.get('timestamp', '')[:16]
                if action_type == 'snapshot':
                    url = action.get('data', {}).get('url', '')
                    context.append(f"- {timestamp}: Navigated to {url[:50]}")
                elif action_type == 'question':
                    question = action.get('data', {}).get('question', '')
                    context.append(f"- {timestamp}: Question: {question[:50]}")
                elif action_type == 'click':
                    target = action.get('data', {}).get('target', '')
                    context.append(f"- {timestamp}: Clicked {target}")
                elif action_type == 'type':
                    text = action.get('data', {}).get('text', '')
                    context.append(f"- {timestamp}: Typed '{text}'")
        return "\n".join(context)
    
    def get_history_text(self):
        if not self.history:
            return "📭 История пуста"
        lines = []
        for i, action in enumerate(self.history, 1):
            timestamp = action.get('timestamp', '')[:16]
            action_type = action.get('type', 'unknown')
            data = action.get('data', {})
            if action_type == 'snapshot':
                lines.append(f"{i}. 🔗 [{timestamp}] {data.get('title', '')} ({data.get('url', '')})")
            elif action_type == 'question':
                lines.append(f"{i}. ❓ [{timestamp}] {data.get('question', '')}")
            elif action_type == 'screenshot':
                lines.append(f"{i}. 📸 [{timestamp}] Screenshot")
            elif action_type == 'click':
                lines.append(f"{i}. 🔘 [{timestamp}] Clicked {data.get('target', '')}")
            elif action_type == 'type':
                lines.append(f"{i}. ✏️ [{timestamp}] Typed '{data.get('text', '')}'")
        return "\n".join(lines)

# ==================== ОБРАБОТЧИКИ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    await update.message.reply_text(
        "👋 Привет! Я бот с ИИ-пониманием.\n\n"
        "🗣️ Говори как хочешь:\n"
        "• зайди на x.com\n"
        "• what buttons do you see?\n"
        "• нажми Обзор\n"
        "• введи текст в поиск\n\n"
        "🌐 Понимаю русский и английский!\n"
        "🍪 Авторизация на X.com!\n"
        "🔍 Автоматически открываю поиск на X.com!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    memory = context.user_data['memory']
    
    if text.lower() in ['привет', 'здравствуй', 'hello', 'hi']:
        await update.message.reply_text("👋 Привет! Спрашивай что хочешь.")
        return
    
    if text.lower() in ['помоги', 'что умеешь', 'help']:
        await update.message.reply_text(
            "🤖 Я умею:\n"
            "• зайди на сайт (с куками для X.com)\n"
            "• нажми на элемент (понимаю русский и английский)\n"
            "• показать все кнопки, ссылки, поля\n"
            "• ввести текст (автоматически Enter)\n"
            "• сделать скриншот\n\n"
            "🌐 Понимаю русский и английский!"
        )
        return
    
    thinking_msg = await update.message.reply_text("🤔 Думаю...")
    command = ask_ai_for_command(text, memory)
    action = command.get('action', 'unknown')
    
    # Если AI не понял - пробуем угадать
    if action == 'unknown':
        text_lower = text.lower()
        if any(word in text_lower for word in ['кнопк', 'button', 'buttons', 'кнопки']):
            action, command = 'ask', {'action': 'ask', 'question': text}
        elif any(word in text_lower for word in ['what', 'where', 'how', 'why', 'when', 'что', 'какие', 'какая', 'какой', 'где', 'когда']):
            action, command = 'ask', {'action': 'ask', 'question': text}
        else:
            await thinking_msg.edit_text(
                "❌ I didn't understand the command\n\n"
                "Examples:\n"
                "• go to x.com\n"
                "• what buttons do you see?\n"
                "• click Explore\n"
                "• type hello in search"
            )
            return
    
    # --- NAVIGATE ---
    if action == 'navigate':
        url = command.get('url')
        if not url:
            await thinking_msg.edit_text("❌ Не понял, на какой сайт перейти")
            return
        memory.add_action("url", {"url": url})
        await thinking_msg.edit_text(f"🔄 Загружаю {url}...")
        try:
            browser = Browser()
            screenshot = await browser.navigate_and_screenshot(url)
            await thinking_msg.delete()
            await update.message.reply_photo(screenshot, caption=f"✅ {url}")
            memory.set_snapshot(browser.snapshot, url, browser.snapshot.get('title', 'Без названия'), browser)
            context.user_data['browser'] = browser
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # --- ASK ---
    if action == 'ask':
        question = command.get('question', text)
        if not memory.current_snapshot:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        memory.add_action("question", {"question": question})
        await thinking_msg.edit_text("🤖 Анализирую страницу...")
        try:
            snapshot = memory.current_snapshot
            interactive = snapshot.get('interactive', [])[:50]
            context_text = "Interactive elements:\n" + "\n".join([f"• {el.get('text', '').strip()[:50]}" for el in interactive[:30] if el.get('text', '').strip()])
            answer = ask_ai_for_answer(question, context_text, memory)
            await thinking_msg.edit_text(f"🤖 Answer:\n\n{answer}")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # --- CLICK ---
    if action == 'click':
        target = command.get('target')
        if not target:
            await thinking_msg.edit_text("❌ Не понял, на что кликнуть")
            return
        if not memory.browser:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        await thinking_msg.edit_text(f"🔘 Ищу '{target}'...")
        try:
            result = await memory.browser.click_element(target, memory)
            if result:
                memory.add_action("click", {"target": target})
                await thinking_msg.edit_text(f"✅ Кликнул по '{target}'")
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
                screenshot = await memory.browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(screenshot, caption=f"✅ После клика на '{target}'")
            else:
                await thinking_msg.edit_text(f"❌ Элемент '{target}' не найден")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # --- TYPE ---
    if action == 'type':
        text_input = command.get('text')
        field = command.get('field')
        if not text_input or not field:
            await thinking_msg.edit_text("❌ Не понял, что и куда вводить")
            return
        if not memory.browser:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        await thinking_msg.edit_text(f"✏️ Ищу поле '{field}'...")
        try:
            result = await memory.browser.type_text(text_input, field)
            if result:
                memory.add_action("type", {"text": text_input, "field": field})
                await thinking_msg.edit_text(f"✅ Ввел '{text_input}' + Enter")
                await memory.browser.wait_for_page_load()
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
                screenshot = await memory.browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(screenshot, caption=f"✅ Результаты поиска '{text_input}'")
            else:
                await thinking_msg.edit_text("❌ Не нашел поле ввода")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # --- SCREENSHOT ---
    if action == 'screenshot':
        if not memory.current_url or not memory.browser:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        await thinking_msg.edit_text("📸 Делаю скриншот...")
        try:
            screenshot = await memory.browser.screenshot()
            if screenshot:
                await thinking_msg.delete()
                await update.message.reply_photo(screenshot, caption=f"✅ {memory.current_url}")
                memory.add_action("screenshot", {"url": memory.current_url})
            else:
                await thinking_msg.edit_text("❌ Не удалось сделать скриншот")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # --- BACK ---
    if action == 'back':
        last_url = memory.get_last_url(1)
        if last_url:
            await thinking_msg.edit_text(f"🔄 Возвращаюсь на {last_url}...")
            try:
                browser = Browser()
                screenshot = await browser.navigate_and_screenshot(last_url)
                await thinking_msg.delete()
                await update.message.reply_photo(screenshot, caption=f"✅ {last_url}")
                memory.set_snapshot(browser.snapshot, last_url, browser.snapshot.get('title', 'Без названия'), browser)
                context.user_data['browser'] = browser
            except Exception as e:
                await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        else:
            await thinking_msg.edit_text("📭 Нет предыдущей страницы")
        return
    
    # --- HISTORY ---
    if action == 'history':
        history_text = memory.get_history_text()
        await thinking_msg.delete()
        if len(history_text) > 4000:
            with open('history_temp.txt', 'w', encoding='utf-8') as f:
                f.write(history_text)
            with open('history_temp.txt', 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"history_{datetime.now().strftime('%Y-%m-%d')}.txt",
                    caption="📜 История"
                )
            os.remove('history_temp.txt')
        else:
            await update.message.reply_text(f"📜 **История:**\n\n{history_text}", parse_mode='Markdown')
        return
    
    # --- CLEAR ---
    if action == 'clear':
        context.user_data['memory'] = Memory()
        await thinking_msg.edit_text("🧹 Память очищена!")
        return
    
    if action == 'unknown':
        await thinking_msg.edit_text(
            "❌ Не понял команду\n\n"
            "Примеры:\n"
            "• зайди на x.com\n"
            "• what buttons do you see?\n"
            "• нажми Обзор\n"
            "• введи текст в поиск"
        )
        return
    
    if action == 'error':
        await thinking_msg.edit_text(f"❌ Ошибка: {command.get('message', 'Неизвестная ошибка')}")
        return
    
    await thinking_msg.edit_text("❌ Что-то пошло не так. Попробуй еще раз.")

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not os.path.exists("bot_logs.txt"):
            await update.message.reply_text("📭 Файл логов ещё не создан")
            return
        with open("bot_logs.txt", 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ==================== ЗАПУСК ====================
def main():
    print("="*50)
    print("🚀 ЗАПУСК БОТА (4 МОДУЛЯ)")
    print("="*50)
    print("📁 bot.py    - Telegram бот + память")
    print("📁 browser.py - Chrome + CDP + DOM + маскировка")
    print("📁 ai.py     - AI клиент (Agnes)")
    print("📁 config.py - Конфигурация")
    print("="*50)
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN!")
        return
    
    if not AGNES_API_KEY:
        print("⚠️ AGNES_API_KEY не указан!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот готов!")
    app.run_polling()

if __name__ == "__main__":
    main()