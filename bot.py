# bot.py
import os
import sys
import time
import logging
import json
import asyncio
import httpx
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# НАСТРОЙКА
# ============================================================

LOGS_DIR = '/app/logs'
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, js,
    list_tabs, current_tab, close_tab, switch_tab
)
from browser_harness.admin import ensure_daemon

# ============================================================
# НАСТРОЙКИ
# ============================================================

MAX_TABS = 5
_search_enabled = True

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 **Браузер бот**\n\n"
        "/z <запрос> — спросить Z.ai (GLM-4.7/5.2 + поиск)\n"
        "/dom <url> — скачать DOM в JSON\n"
        "/tabs — список вкладок\n"
        "/tab_new — открыть вкладку\n"
        "/tab_close <номер> — закрыть вкладку\n"
        "/tab_switch <номер> — переключить вкладку\n"
        "/log — скачать логи",
        parse_mode='Markdown'
    )

async def log(update, context):
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        with open(log_file, 'rb') as f:
            await update.message.reply_document(document=f, filename='bot.log')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def dom(update, context):
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите URL\n"
                "Пример: /dom https://example.com"
            )
            return

        url = context.args[0].strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        status_msg = await update.message.reply_text(f"🌐 Открываю {url}...")

        try:
            new_tab()
            goto_url(url)
            wait_for_load(timeout=30)
            await status_msg.edit_text(f"✅ Страница загружена, парсинг...")
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return

        js_code = """
        const elements = {
            buttons: [],
            inputs: [],
            links: [],
            forms: [],
            selects: [],
            textareas: [],
            divs: [],
            spans: [],
            lis: [],
            others: []
        };
        
        const allElements = document.querySelectorAll('*');
        
        for (const el of allElements) {
            if (el.offsetParent === null && !el.hasAttribute('data-testid')) continue;
            
            const text = el.textContent?.trim() || '';
            if (!text || text.length < 1) continue;
            
            const tag = el.tagName.toLowerCase();
            
            const info = {
                tag: tag,
                text: text.substring(0, 500),
                className: el.className || '',
                id: el.id || '',
                attributes: {},
                dataAttributes: {}
            };
            
            for (const attr of el.attributes) {
                info.attributes[attr.name] = attr.value;
                if (attr.name.startsWith('data-')) {
                    info.dataAttributes[attr.name] = attr.value;
                }
            }
            
            if (tag === 'button' || el.getAttribute('role') === 'button') {
                elements.buttons.push(info);
            } else if (tag === 'input') {
                elements.inputs.push(info);
            } else if (tag === 'a') {
                elements.links.push(info);
            } else if (tag === 'form') {
                elements.forms.push(info);
            } else if (tag === 'select') {
                elements.selects.push(info);
            } else if (tag === 'textarea') {
                elements.textareas.push(info);
            } else if (tag === 'div') {
                elements.divs.push(info);
            } else if (tag === 'span') {
                elements.spans.push(info);
            } else if (tag === 'li') {
                elements.lis.push(info);
            } else {
                elements.others.push(info);
            }
        }
        
        return JSON.stringify({
            page: {
                url: window.location.href,
                title: document.title,
                timestamp: Date.now()
            },
            elements: elements
        }, null, 2);
        """
        
        result = js(js_code)

        if not result:
            await status_msg.edit_text("❌ Не удалось получить данные DOM")
            return

        try:
            dom_data = json.loads(result)
        except:
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return

        timestamp = int(time.time())
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]
        filename = f"dom_{domain}_{timestamp}.json"
        file_path = os.path.join(LOGS_DIR, filename)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(dom_data, f, ensure_ascii=False, indent=2)

        with open(file_path, 'rb') as f:
            await status_msg.edit_text("📄 Отправляю JSON...")
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📊 DOM страницы\nURL: {dom_data.get('page', {}).get('url', 'unknown')}"
            )

        elements = dom_data.get('elements', {})
        stats = "📊 Статистика DOM:\n\n"
        total = 0
        for key, value in elements.items():
            if value:
                count = len(value)
                total += count
                stats += f"• {key}: {count}\n"
        stats += f"\nВсего: {total}"

        await update.message.reply_text(stats)

        try:
            os.remove(file_path)
        except:
            pass

    except Exception as e:
        logger.error(f"❌ Ошибка в /dom: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def z(update, context):
    """
    Отправляет запрос к Z.ai с GLM-5.2 (если доступна) и включенным поиском
    """
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Напишите запрос\n"
                "Пример: /z кто лидер сша?\n\n"
                "🔍 Поиск всегда включён\n"
                "🤖 Модель: GLM-4.7 / GLM-5.2 (выбирается автоматически)"
            )
            return

        query = " ".join(context.args)
        logger.info(f"📝 /z запрос: {query}")
        logger.info(f"🔍 Поиск: {_search_enabled}")

        status_msg = await update.message.reply_text(f"🤖 Отправляю запрос к Z.ai...")

        try:
            # Закрываем старые вкладки
            tabs = list_tabs()
            for tab in tabs:
                if tab != current_tab():
                    try:
                        close_tab(tab)
                    except:
                        pass

            new_tab()
            goto_url("https://chat.z.ai/")
            wait_for_load(timeout=60)
            
            await status_msg.edit_text("✍️ Ввожу запрос...")
            await asyncio.sleep(2)

            query_escaped = query.replace("'", "\\'").replace('"', '\\"')
            search_enabled = str(_search_enabled).lower()

            js_code = f"""
            (function() {{
                const query = '{query_escaped}';
                const searchEnabled = {search_enabled};
                
                let result = '';
                
                // 1. Выбираем GLM-5.2 (если доступна)
                const modelBtn = document.querySelector('#model-selector-glm-4_7-button');
                if (modelBtn) {{
                    modelBtn.click();
                    result += '🔄 Открываю меню моделей...\\n';
                    
                    // Ждём появления меню и ищем GLM-5.2
                    const checkMenu = () => {{
                        const items = document.querySelectorAll('[role="menuitemradio"]');
                        let found = false;
                        for (const item of items) {{
                            const text = item.textContent?.trim() || '';
                            if (text.includes('GLM-5.2')) {{
                                item.click();
                                result += '✅ Модель: GLM-5.2\\n';
                                found = true;
                                break;
                            }}
                        }}
                        if (!found) {{
                            // Если GLM-5.2 нет, выбираем GLM-4.7
                            for (const item of items) {{
                                const text = item.textContent?.trim() || '';
                                if (text.includes('GLM-4.7')) {{
                                    item.click();
                                    result += '✅ Модель: GLM-4.7\\n';
                                    found = true;
                                    break;
                                }}
                            }}
                            if (!found && items.length > 0) {{
                                const first = items[0];
                                const name = first.textContent?.trim() || 'неизвестная';
                                first.click();
                                result += `✅ Модель: ${{name}}\\n`;
                            }}
                        }}
                    }};
                    setTimeout(checkMenu, 500);
                }} else {{
                    result += '❌ Кнопка модели не найдена\\n';
                }}
                
                // 2. Включаем Deep Think
                const deepThinkBtn = document.querySelector('[data-autothink="true"], [data-autothink="false"]');
                if (deepThinkBtn) {{
                    const isActive = deepThinkBtn.getAttribute('data-autothink') === 'true';
                    if (isActive !== searchEnabled) {{
                        deepThinkBtn.click();
                        result += '🔄 Deep Think: клик\\n';
                    }} else {{
                        result += '✅ Deep Think: уже включён\\n';
                    }}
                }} else {{
                    result += '❌ Deep Think: не найден\\n';
                }}
                
                // 3. Включаем Web Search
                const webSearchBtn = document.querySelector('[data-active="true"], [data-active="false"]');
                if (webSearchBtn) {{
                    const isActive = webSearchBtn.getAttribute('data-active') === 'true';
                    if (isActive !== searchEnabled) {{
                        webSearchBtn.click();
                        result += '🔄 Web Search: клик\\n';
                    }} else {{
                        result += '✅ Web Search: уже включён\\n';
                    }}
                }} else {{
                    result += '❌ Web Search: не найден\\n';
                }}
                
                // 4. Вводим запрос
                const input = document.querySelector('#chat-input, textarea, [contenteditable="true"]');
                if (!input) return result + '❌ Поле ввода не найдено';
                
                input.value = '';
                input.focus();
                
                for (let i = 0; i < query.length; i++) {{
                    input.value += query[i];
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
                
                // 5. Отправляем
                const sendBtn = document.querySelector('#send-message-button, button[type="submit"]');
                if (sendBtn && !sendBtn.disabled) {{
                    sendBtn.click();
                    result += '✅ Запрос отправлен';
                }} else {{
                    input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
                    result += '✅ Запрос отправлен (Enter)';
                }}
                
                return result;
            }})();
            """
            
            result = js(js_code)
            logger.info(f"📊 Результат JS: {result}")
            await status_msg.edit_text(f"✅ {result}")

            # Ждём ответ
            await status_msg.edit_text("⏳ Жду ответ AI (до 30 секунд)...")
            await asyncio.sleep(30)

            # Парсим ответ
            await status_msg.edit_text("📊 Получаю ответ...")
            
            js_response = """
            (function() {
                // Проверяем "Thinking..."
                const thinking = document.querySelector('[data-thinking], .thinking, [role="status"]');
                if (thinking) {
                    const thinkingText = thinking.textContent?.trim() || '';
                    if (thinkingText.includes('Thinking') || thinkingText.includes('...')) {
                        return '⏰ AI всё ещё думает... Попробуйте упростить запрос.';
                    }
                }
                
                // Ищем ответ AI
                const assistant = document.querySelector('.chat-assistant');
                if (!assistant) return '';
                
                const paragraphs = assistant.querySelectorAll('p');
                let text = '';
                for (const p of paragraphs) {
                    const t = p.textContent?.trim() || '';
                    if (t) {
                        text += t + '\\n\\n';
                    }
                }
                return text.trim();
            })();
            """
            
            response = js(js_response)
            
            if not response or len(response) < 5:
                await status_msg.edit_text("⏳ AI думает, жду ещё 10 секунд...")
                await asyncio.sleep(10)
                response = js(js_response)

            if not response or len(response) < 5:
                await status_msg.edit_text("❌ Не удалось получить ответ от Z.ai. Попробуйте упростить запрос.")
                return

            if response.startswith("⏰"):
                await status_msg.edit_text(response)
                return

            if len(response) > 4000:
                response = response[:3950] + "\n\n... (ответ обрезан)"

            header = f"🤖 **Z.ai ответ**\n"
            header += f"📌 Запрос: {query[:100]}\n"
            header += f"🔍 Поиск: {'✅ Включен' if _search_enabled else '❌ Выключен'}\n"
            header += f"🤖 Модель: GLM-5.2 (если доступна)\n\n"
            
            full_response = header + response
            
            await status_msg.edit_text(full_response, parse_mode=None)

            try:
                close_tab(current_tab())
            except:
                pass

        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

    except Exception as e:
        logger.error(f"❌ Ошибка в /z: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tabs(update, context):
    try:
        tab_list = list_tabs()
        if not tab_list:
            await update.message.reply_text("📭 Нет открытых вкладок")
            return

        current = current_tab()
        response = "📑 Список вкладок:\n\n"
        for i, tab in enumerate(tab_list, 1):
            if tab == current:
                response += f"✅ {i}. {tab} (текущая)\n"
            else:
                response += f"🔲 {i}. {tab}\n"

        response += "\n/tab_new - открыть новую\n/tab_close <номер> - закрыть\n/tab_switch <номер> - переключиться"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_new(update, context):
    try:
        new_tab()
        await update.message.reply_text("✅ Новая вкладка открыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_close(update, context):
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_close 1")
            return

        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return

        tabs_list = list_tabs()
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return

        tab_id = tabs_list[tab_num]
        if tab_id == current_tab() and len(tabs_list) > 1:
            await update.message.reply_text("❌ Нельзя закрыть текущую вкладку")
            return

        close_tab(tab_id)
        await update.message.reply_text(f"✅ Вкладка {tab_num + 1} закрыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_switch(update, context):
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_switch 2")
            return

        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return

        tabs_list = list_tabs()
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return

        switch_tab(tabs_list[tab_num])
        await update.message.reply_text(f"✅ Переключился на вкладку {tab_num + 1}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

    os.environ["BU_CDP_URL"] = "http://localhost:9222"
    ensure_daemon()
    logger.info("✅ Браузер готов")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom))
    app.add_handler(CommandHandler("z", z))
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("tab_new", tab_new))
    app.add_handler(CommandHandler("tab_close", tab_close))
    app.add_handler(CommandHandler("tab_switch", tab_switch))
    app.add_handler(CommandHandler("log", log))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()