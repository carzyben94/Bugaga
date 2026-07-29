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
# ФУНКЦИЯ ПАРСИНГА DOM
# ============================================================

def parse_dom():
    """Парсит DOM страницы и возвращает JSON"""
    try:
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
        
        const selectors = [
            'button',
            'input:not([type="hidden"])',
            'a[href]',
            'form',
            'select',
            'textarea',
            '[role="button"]',
            '[role="link"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[contenteditable="true"]'
        ];
        
        const all = new Set(document.querySelectorAll(selectors.join(',')));
        document.querySelectorAll('[onclick], [data-testid], [data-test], [data-cy], [data-qa]').forEach(el => all.add(el));
        
        for (const el of all) {
            const info = {
                tag: el.tagName.toLowerCase(),
                text: el.textContent?.trim() || '',
                value: el.value || '',
                placeholder: el.placeholder || '',
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                className: el.className || '',
                href: el.href || '',
                src: el.src || '',
                alt: el.alt || '',
                title: el.title || '',
                disabled: el.disabled || false,
                readonly: el.readOnly || false,
                required: el.required || false,
                checked: el.checked || false,
                selected: el.selected || false,
                visible: el.offsetParent !== null,
                attributes: {},
                dataAttributes: {}
            };
            
            for (const attr of el.attributes) {
                info.attributes[attr.name] = attr.value;
                if (attr.name.startsWith('data-')) {
                    info.dataAttributes[attr.name] = attr.value;
                }
            }
            
            const tag = info.tag;
            if (tag === 'button' || (el.hasAttribute('role') && el.getAttribute('role') === 'button')) {
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
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга DOM: {e}")
        return None

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 **Браузер бот**\n\n"
        "/dom <url> — скачать DOM в JSON\n"
        "/zai — открыть Z.ai, ввести запрос, подождать 20 сек, скачать DOM\n"
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
    """Парсит DOM и отправляет JSON файл"""
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

        result = parse_dom()

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

async def zai(update, context):
    """
    Открывает Z.ai, вводит запрос "привет как дела",
    ждёт 20 секунд, скачивает DOM
    """
    try:
        status_msg = await update.message.reply_text("🤖 Открываю Z.ai...")

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
            
            # Небольшая пауза для загрузки страницы
            await asyncio.sleep(2)

            # JavaScript для ввода текста и отправки
            js_code = """
            (function() {
                // Находим поле ввода
                const input = document.querySelector('#chat-input, textarea, [contenteditable="true"]');
                if (!input) return 'Поле ввода не найдено';
                
                // Очищаем и вводим текст
                input.value = '';
                input.focus();
                
                const query = 'привет как дела';
                for (let i = 0; i < query.length; i++) {
                    input.value += query[i];
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                }
                
                // Ищем кнопку отправки
                const sendBtn = document.querySelector('#send-message-button, button[type="submit"]');
                if (sendBtn && !sendBtn.disabled) {
                    sendBtn.click();
                } else {
                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                }
                
                return 'Запрос отправлен';
            })();
            """
            
            result = js(js_code)
            await status_msg.edit_text(f"✅ {result}")

            # Ждём 20 секунд пока AI ответит
            await status_msg.edit_text("⏳ Жду 20 секунд пока AI ответит...")
            await asyncio.sleep(20)

            # Парсим DOM
            await status_msg.edit_text("📊 Парсинг DOM...")
            dom_result = parse_dom()

            if not dom_result:
                await status_msg.edit_text("❌ Не удалось получить данные DOM")
                return

            try:
                dom_data = json.loads(dom_result)
            except:
                await status_msg.edit_text("❌ Ошибка парсинга JSON")
                return

            timestamp = int(time.time())
            filename = f"dom_zai_{timestamp}.json"
            file_path = os.path.join(LOGS_DIR, filename)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(dom_data, f, ensure_ascii=False, indent=2)

            with open(file_path, 'rb') as f:
                await status_msg.edit_text("📄 Отправляю DOM в JSON...")
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📊 DOM страницы Z.ai\nURL: {dom_data.get('page', {}).get('url', 'unknown')}"
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

            # Закрываем вкладку
            try:
                close_tab(current_tab())
            except:
                pass

        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

    except Exception as e:
        logger.error(f"❌ Ошибка в /zai: {e}")
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
    app.add_handler(CommandHandler("zai", zai))
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("tab_new", tab_new))
    app.add_handler(CommandHandler("tab_close", tab_close))
    app.add_handler(CommandHandler("tab_switch", tab_switch))
    app.add_handler(CommandHandler("log", log))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()