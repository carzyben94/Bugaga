# bot.py
import os
import sys
import stat
import time
import logging
import json
import httpx
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# НАСТРОЙКА
# ============================================================

agent_workspace = "/app/browser-harness/agent-workspace"
sys.path.insert(0, agent_workspace)

helpers_file = os.path.join(agent_workspace, "agent_helpers.py")
os.makedirs(agent_workspace, exist_ok=True)
if not os.path.exists(helpers_file):
    with open(helpers_file, "w") as f:
        f.write('"""Agent-editable browser helpers."""\n')
os.chmod(agent_workspace, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
os.chmod(helpers_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)

os.environ["BH_AGENT_WORKSPACE"] = "/app/browser-harness/agent-workspace"

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

logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)
logging.getLogger("telegram.ext").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)
logger.info("✅ Бот запускается...")

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, js,
    list_tabs, current_tab, close_tab, switch_tab
)
from browser_harness.admin import ensure_daemon

# ============================================================
# ПРОВЕРКА БРАУЗЕРА
# ============================================================

def ensure_browser_ready():
    """Проверяет и перезапускает браузер при необходимости"""
    try:
        resp = httpx.get("http://localhost:9222/json/list", timeout=3.0)
        pages = resp.json()
        if pages:
            logger.info("✅ Браузер работает")
            return True
        else:
            logger.warning("⚠️ Браузер не отвечает, перезапускаю...")
            ensure_daemon()
            time.sleep(3)
            return True
    except Exception as e:
        logger.warning(f"⚠️ Браузер недоступен: {e}, перезапускаю...")
        ensure_daemon()
        time.sleep(3)
        return True

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 **Браузер**\n\n"
        "/dom <url> — парсинг DOM\n"
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
    """Парсит DOM указанной страницы"""
    try:
        ensure_browser_ready()

        if not context.args:
            await update.message.reply_text(
                "❌ Укажите URL\n"
                "Пример: /dom https://example.com\n"
                "Пример: /dom meduza.io"
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
            await status_msg.edit_text("✅ Страница загружена, парсинг...")
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return

        # JavaScript для сбора DOM
        js_code = """
        function getElementInfo(el) {
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
                const name = attr.name;
                const value = attr.value;
                info.attributes[name] = value;
                if (name.startsWith('data-')) {
                    info.dataAttributes[name] = value;
                }
            }
            
            return info;
        }
        
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
        
        const allElements = document.querySelectorAll(selectors.join(','));
        const extraSet = new Set(allElements);
        
        const extraElements = document.querySelectorAll('[onclick], [data-testid], [data-test], [data-cy], [data-qa]');
        for (const el of extraElements) {
            if (!extraSet.has(el)) {
                extraSet.add(el);
            }
        }
        
        for (const el of extraSet) {
            const info = getElementInfo(el);
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
        
        const pageInfo = {
            url: window.location.href,
            title: document.title,
            timestamp: Date.now()
        };
        
        return JSON.stringify({ page: pageInfo, elements: elements }, null, 2);
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
        stats = "📊 **Статистика DOM:**\n\n"
        total = 0
        for key, value in elements.items():
            if value:
                count = len(value)
                total += count
                stats += f"• {key}: {count}\n"
        stats += f"\n**Всего: {total}**"

        await update.message.reply_text(stats, parse_mode='Markdown')

        try:
            os.remove(file_path)
        except:
            pass

    except Exception as e:
        logger.error(f"❌ Ошибка в /dom: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tabs(update, context):
    """Показать список всех вкладок"""
    try:
        ensure_browser_ready()
        
        tab_list = list_tabs()
        if not tab_list:
            await update.message.reply_text("📭 Нет открытых вкладок")
            return

        current = current_tab()
        response = "📑 **Список вкладок:**\n\n"
        for i, tab in enumerate(tab_list, 1):
            if tab == current:
                response += f"✅ {i}. {tab} (текущая)\n"
            else:
                response += f"🔲 {i}. {tab}\n"

        response += "\n/tab_new — открыть новую\n"
        response += "/tab_close <номер> — закрыть\n"
        response += "/tab_switch <номер> — переключиться"

        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_new(update, context):
    """Открыть новую вкладку"""
    try:
        ensure_browser_ready()
        new_tab()
        await update.message.reply_text("✅ Новая вкладка открыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_close(update, context):
    """Закрыть вкладку по номеру"""
    try:
        ensure_browser_ready()
        
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
        current = current_tab()

        if tab_id == current and len(tabs_list) > 1:
            await update.message.reply_text("❌ Нельзя закрыть текущую вкладку. Сначала переключитесь на другую.")
            return

        close_tab(tab_id)
        await update.message.reply_text(f"✅ Вкладка {tab_num + 1} закрыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_switch(update, context):
    """Переключиться на вкладку по номеру"""
    try:
        ensure_browser_ready()
        
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

        tab_id = tabs_list[tab_num]
        switch_tab(tab_id)
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
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("tab_new", tab_new))
    app.add_handler(CommandHandler("tab_close", tab_close))
    app.add_handler(CommandHandler("tab_switch", tab_switch))
    app.add_handler(CommandHandler("log", log))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()