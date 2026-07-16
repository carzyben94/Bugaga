import os
import logging
import base64
import asyncio
import json
import re
import zipfile
from datetime import datetime
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from browser import Browser
from eval import Eval
from accessibility import Accessibility
from ai import AIAgent
from tester import ElementTester
from site_map import SiteMap
from hermes_agent import HermesAgent
from orchestrator import Orchestrator
from viewer import PageViewer

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

browser = None
orchestrator = None
viewer = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Привет! Я Луи!**\n\n"
        "Я — твой AI-помощник для работы с X.com.\n\n"
        "📋 **Команды:**\n"
        "  /view — открыть окно просмотра страницы\n"
        "  /view_close — закрыть окно просмотра\n"
        "  /louis_log — скачать детальный лог моих действий (JSON)\n"
        "  /louis_log 50 — скачать последние 50 действий\n"
        "  /log_clear — очистить мой лог\n\n"
        "💡 **Просто напиши, что нужно сделать.**\n\n"
        "Примеры:\n"
        "  открой x.com\n"
        "  перейди в обзор\n"
        "  опубликуй пост 'Привет мир!'\n"
        "  сделай скрин\n"
        "  какие кнопки видишь\n"
        "  нажми на главную\n\n"
        "🔥 Я сам пойму, что ты хочешь!"
    )


async def view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открыть окно просмотра страницы (с редактированием)"""
    global browser, orchestrator, viewer
    
    user_id = update.effective_user.id
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        if viewer is None:
            eval = Eval(browser)
            viewer = PageViewer(browser, eval)
            logger.info("✅ Окно просмотра создано")
        
        # Делаем скриншот
        result = await viewer.capture()
        
        if result.get("success"):
            photo_bytes = base64.b64decode(result["screenshot"])
            
            caption = (
                f"🖥️ **Окно просмотра**\n"
                f"🔗 {result.get('url', 'Неизвестно')}\n"
                f"📄 {result.get('title', 'Без заголовка')}\n"
                f"🕐 {result.get('timestamp', '')[:19]}\n\n"
                f"💡 Команды:\n"
                f"  /view — обновить окно\n"
                f"  /view_close — закрыть окно"
            )
            
            msg = await update.message.reply_photo(
                photo=photo_bytes,
                caption=caption
            )
            
            viewer.chat_id = update.effective_chat.id
            viewer.message_id = msg.message_id
            
            logger.info(f"User {user_id} открыл окно просмотра")
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Ошибка')}")
        
    except Exception as e:
        logger.error(f"Ошибка окна просмотра: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def view_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть окно просмотра"""
    global viewer
    
    viewer = None
    await update.message.reply_text("🖥️ Окно просмотра закрыто")


async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser, orchestrator
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /screen https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен с маскировкой")
        
        await browser.goto(url)
        screenshot_base64 = await browser.screenshot()
        
        photo_bytes = base64.b64decode(screenshot_base64)
        
        await update.message.reply_photo(
            photo=photo_bytes,
            caption=f"✅ Скриншот {url}\nРазмер: {len(photo_bytes)} байт"
        )
        
        logger.info(f"User {user_id} сделал скриншот {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка скриншота: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
            orchestrator = None
            viewer = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser, orchestrator
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /analyze https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"🔍 Анализирую {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        await browser.goto(url)
        await asyncio.sleep(2)
        
        eval = Eval(browser)
        
        buttons = await eval.get_all_buttons()
        inputs = await eval.get_all_inputs()
        forms = await eval.get_all_forms()
        checkboxes = await eval.get_all_checkboxes()
        selects = await eval.get_all_selects()
        
        response = (
            f"🔄 Кнопок: {len(buttons)}\n"
            f"📝 Полей ввода: {len(inputs)}\n"
            f"📋 Форм: {len(forms)}\n"
            f"☑️ Checkbox/Radio: {len(checkboxes)}\n"
            f"📋 Select: {len(selects)}\n\n"
        )
        
        if buttons:
            response += "🔘 **Кнопки:**\n"
            for i, btn in enumerate(buttons, 1):
                text = btn['text'][:40] if btn['text'] else '[без текста]'
                test_id = btn.get('testId', '')
                if test_id:
                    response += f"  {i}. {text} (testid: {test_id})\n"
                else:
                    response += f"  {i}. {text}\n"
            response += "\n"
        
        if inputs:
            response += "✏️ **Поля ввода:**\n"
            for i, inp in enumerate(inputs, 1):
                desc = (
                    inp.get('ariaLabel') or 
                    inp.get('placeholder') or 
                    inp.get('title') or 
                    inp.get('name') or 
                    inp.get('id') or 
                    '[без имени]'
                )
                desc = desc[:35]
                test_id = inp.get('testId', '')
                
                field_type = inp.get('type', '')
                type_icon = {
                    'text': '📝',
                    'password': '🔒',
                    'email': '📧',
                    'number': '🔢',
                    'tel': '📞',
                    'url': '🔗',
                    'search': '🔍',
                    'textarea': '📄',
                }.get(field_type, '')
                
                if test_id:
                    response += f"  {i}. {type_icon} {desc} (testid: {test_id})\n"
                else:
                    response += f"  {i}. {type_icon} {desc}\n"
            response += "\n"
        
        if forms:
            response += f"📋 **Формы:** {len(forms)}\n"
            for i, form in enumerate(forms[:5], 1):
                action = form.get('action', '')[:40]
                method = form.get('method', 'GET')
                if action:
                    response += f"  {i}. {method} → {action}\n"
                else:
                    response += f"  {i}. {method}\n"
        
        if len(response) > 4000:
            response = response[:4000] + "\n\n... (обрезано)"
        
        await update.message.reply_text(response)
        
        logger.info(f"User {user_id} проанализировал {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка анализа: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
            orchestrator = None
            viewer = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def accessibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser, orchestrator
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /accessibility https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"♿ Собираю Accessibility Tree для {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        await browser.goto(url)
        
        logger.info("⏳ Ожидание загрузки страницы...")
        for _ in range(30):
            try:
                response = await asyncio.wait_for(browser.ws.recv(), timeout=1)
                data = json.loads(response)
                if data.get("method") == "Page.loadEventFired":
                    logger.info("✅ Страница загружена")
                    break
            except asyncio.TimeoutError:
                continue
        else:
            logger.warning("⏱️ Таймаут ожидания загрузки")
        
        await asyncio.sleep(2)
        
        acc = Accessibility(browser)
        await acc.enable()
        await asyncio.sleep(2)
        
        summary = await acc.get_summary()
        
        response = (
            f"♿ **Accessibility Tree**\n\n"
            f"📊 **Всего узлов:** {summary['total_nodes']}\n"
            f"─────────────────\n"
            f"🔘 Кнопок: {summary['buttons']}\n"
            f"📝 Полей ввода: {summary['inputs']}\n"
            f"🔗 Ссылок: {summary['links']}\n"
            f"📌 Заголовков: {summary['headings']}\n"
            f"🏛️ Landmarks: {summary['landmarks']}\n"
            f"🖼️ Изображений: {summary['images']}\n"
            f"📋 Списков: {summary['lists']}\n"
            f"📊 Таблиц: {summary['tables']}\n"
        )
        
        if summary.get('roles'):
            response += "\n📋 **Роли (топ 10):**\n"
            sorted_roles = sorted(summary['roles'].items(), key=lambda x: x[1], reverse=True)[:10]
            for role, count in sorted_roles:
                response += f"  {role}: {count}\n"
        
        if len(response) > 4000:
            response = response[:4000] + "\n\n... (обрезано)"
        
        await update.message.reply_text(response)
        
        logger.info(f"User {user_id} запросил accessibility для {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка Accessibility: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
            orchestrator = None
            viewer = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser, orchestrator
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /test https://example.com")
        return
    
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    user_id = update.effective_user.id
    await update.message.reply_text(f"🧪 Тестирую элементы на {url}...")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        eval = Eval(browser)
        tester = ElementTester(browser, eval)
        
        report = await tester.run_full_test(url)
        
        results = report.get("results", {})
        verified_count = results.get('verified', 0)
        failed_count = results.get('failed', 0)
        total = results.get('total', 0)
        success_rate = f"{verified_count / total * 100:.1f}%" if total > 0 else "0%"
        
        response = (
            f"🧪 **Результаты тестирования**\n\n"
            f"🔗 {url}\n"
            f"📊 **Всего элементов:** {total}\n"
            f"✅ **Работают:** {verified_count}\n"
            f"❌ **Не работают:** {failed_count}\n"
            f"⏭️ **Пропущено:** {results.get('skipped', 0)}\n"
            f"📈 **Успешность:** {success_rate}\n\n"
        )
        
        if results.get('actions'):
            response += "✅ **Проверенные команды (первые 10):**\n"
            for cmd in results['actions'][:10]:
                text = cmd.get('text', cmd.get('name', ''))[:30]
                selector = cmd.get('selector', '')
                if selector:
                    response += f"  🔘 {text}\n"
                    response += f"     → {selector}\n"
            if len(results['actions']) > 10:
                response += f"  ... и ещё {len(results['actions']) - 10} команд\n"
        
        if results.get('failed_elements'):
            response += "\n❌ **Упавшие элементы (первые 5):**\n"
            for el in results['failed_elements'][:5]:
                text = el.get('text', el.get('name', ''))[:30]
                error = el.get('error', 'Неизвестная ошибка')
                response += f"  ❌ {text}: {error}\n"
        
        response += f"\n📸 **Скриншотов:** {report.get('screenshots_count', 0)}\n"
        response += f"💾 **Результаты:** test_results.json, test_logs.txt\n"
        response += f"🗺️ **Карта:** site_map.json\n"
        response += f"\n💡 Теперь AI знает, какие элементы работают!"
        
        await update.message.reply_text(response)
        
        logger.info(f"User {user_id} запустил тест {url}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка тестирования: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
            orchestrator = None
            viewer = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def x(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser, orchestrator
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Укажи действие:\n"
            "/x snapshot <url> — получить снапшот страницы\n"
            "/x click @e1 — кликнуть по элементу\n"
            "/x type @e2 'текст' — ввести текст\n"
            "/x enter @e2 — нажать Enter\n"
            "/x ask 'вопрос' — спросить AI\n"
            "/x chain — выполнить цепочку (пример)\n"
            "/x help — показать это сообщение"
        )
        return
    
    user_id = update.effective_user.id
    command = args[0].lower()
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        eval = Eval(browser)
        acc = Accessibility(browser)
        ai_agent = AIAgent(browser, eval, acc)
        hermes_agent = HermesAgent(browser, acc, eval, ai_agent)
        
        if orchestrator is None:
            orchestrator = Orchestrator(browser, eval, acc, ai_agent, hermes_agent)
            logger.info("✅ Оркестратор создан")
        
        if command == "help":
            await update.message.reply_text(
                "📖 **Команды /x:**\n\n"
                "/x snapshot <url> — получить снапшот страницы с ref\n"
                "/x click @e1 — кликнуть по элементу\n"
                "/x type @e2 'текст' — ввести текст\n"
                "/x enter @e2 — нажать Enter\n"
                "/x ask 'вопрос' — спросить AI\n"
                "/x chain — выполнить цепочку (пример)\n"
            )
        
        elif command == "snapshot":
            url = args[1] if len(args) > 1 else "https://x.com"
            await update.message.reply_text(f"📸 Получаю снапшот {url}...")
            
            result = await orchestrator.snapshot(url)
            
            response = f"📸 **Снапшот страницы**\n\n"
            response += f"🔗 {url}\n"
            response += f"📊 **Интерактивных элементов:** {result['total_elements']}\n\n"
            
            for el in result['elements'][:20]:
                response += f"  {el['ref']}: {el['role']} — {el['name'][:40]}\n"
            
            if result['total_elements'] > 20:
                response += f"\n... и ещё {result['total_elements'] - 20} элементов"
            
            await update.message.reply_text(response)
        
        elif command == "click":
            ref = args[1] if len(args) > 1 else None
            if not ref:
                await update.message.reply_text("❌ Укажи ref: /x click @e1")
                return
            
            result = await orchestrator._click_by_ref(ref)
            if result.get("success"):
                await update.message.reply_text(result["message"])
                
                if result.get("screenshot_before"):
                    with open(result["screenshot_before"], "rb") as f:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"📸 До клика по {ref}"
                        )
                
                if result.get("screenshot_after"):
                    with open(result["screenshot_after"], "rb") as f:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"📸 После клика по {ref}"
                        )
            else:
                await update.message.reply_text(result["message"])
        
        elif command == "type":
            ref = args[1] if len(args) > 1 else None
            text = ' '.join(args[2:]) if len(args) > 2 else None
            if not ref or text is None:
                await update.message.reply_text("❌ Укажи ref и текст: /x type @e2 'текст'")
                return
            
            result = await orchestrator.hermes.type_text(ref, text)
            if result.get("success"):
                await update.message.reply_text(f"✅ Ввод в {ref} выполнен")
            else:
                await update.message.reply_text(f"❌ {result.get('reason')}")
        
        elif command == "enter":
            ref = args[1] if len(args) > 1 else None
            if not ref:
                await update.message.reply_text("❌ Укажи ref: /x enter @e2")
                return
            
            result = await orchestrator.hermes.press_enter(ref)
            if result.get("success"):
                await update.message.reply_text(f"✅ Enter на {ref} выполнен")
            else:
                await update.message.reply_text(f"❌ {result.get('reason')}")
        
        elif command == "ask":
            question = ' '.join(args[1:]) if len(args) > 1 else None
            if not question:
                await update.message.reply_text("❌ Укажи вопрос: /x ask 'как опубликовать пост?'")
                return
            
            await update.message.reply_text("🧠 Думаю...")
            response = await orchestrator.hermes.ask_ai(question)
            await update.message.reply_text(f"🧠 **AI Агент:**\n\n{response}")
        
        elif command == "chain":
            await update.message.reply_text("🔄 Выполняю цепочку...")
            await update.message.reply_text(
                "⚠️ Для цепочки нужны реальные ref из снапшота.\n"
                "Сначала: /x snapshot https://x.com\n"
                "Потом: /x chain @e1 @e2 ..."
            )
        
        else:
            await update.message.reply_text(f"❌ Неизвестная команда: {command}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка X: {error_msg}")
        
        if browser:
            await browser.close()
            browser = None
            orchestrator = None
            viewer = None
        
        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if os.path.exists("test_results.json"):
            with open("test_results.json", "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    caption="📊 Результаты тестирования"
                )
        else:
            await update.message.reply_text("❌ Нет файла test_results.json")
        
        if os.path.exists("test_logs.txt"):
            with open("test_logs.txt", "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"test_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    caption="📋 Логи тестирования"
                )
        
        if os.path.exists("site_map.json"):
            with open("site_map.json", "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"site_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    caption="🗺️ Карта сайта"
                )
        
        if os.path.exists("screenshots") and os.listdir("screenshots"):
            zip_path = f"screenshots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for root, dirs, files in os.walk("screenshots"):
                    for file in files:
                        zipf.write(os.path.join(root, file))
            
            with open(zip_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=zip_path,
                    caption="📸 Скриншоты тестирования"
                )
            
            os.remove(zip_path)
        
        logger.info(f"User {user_id} скачал результаты теста")
        
    except Exception as e:
        logger.error(f"Ошибка скачивания результатов: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser, orchestrator

    user_id = update.effective_user.id
    text = ' '.join(context.args) if context.args else ''

    if not text:
        await update.message.reply_text(
            "🧠 **AI Агент**\n\n"
            "Примеры:\n"
            "  /ai проанализируй https://x.com\n"
            "  /ai структура https://x.com\n"
            "  /ai карта https://x.com\n"
            "  /ai где кнопка Опубликовать на https://x.com\n"
            "  /ai что такое CDP"
        )
        return

    await update.message.reply_text("🧠 Думаю...")

    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")

        eval = Eval(browser)
        acc = Accessibility(browser)
        agent = AIAgent(browser, eval, acc)

        url_match = re.search(r'https?://[^\s]+', text)
        url = url_match.group(0) if url_match else None
        text_lower = text.lower()

        if url and ('карта' in text_lower or 'map' in text_lower or 'слепок' in text_lower):
            result = await agent.build_site_map(url)

        elif url and ('анализ' in text_lower or 'структура' in text_lower or 'проанализируй' in text_lower):
            result = await agent.analyze_structure(url)

        elif url and ('где' in text_lower or 'найти' in text_lower or 'покажи' in text_lower):
            site_map = agent.site_map
            map_data = site_map.get(url)
            if map_data:
                words = text_lower.split()
                found = None
                for word in words:
                    if len(word) > 3:
                        result_search = site_map.find_element(url, word)
                        if result_search:
                            found = result_search
                            break
                
                if found:
                    el = found['element']
                    zone = found['zone']
                    response = f"🔍 **Найдено в карте сайта:**\n\n"
                    response += f"📍 **Зона:** {zone}\n"
                    response += f"📝 **Текст:** {el.get('text', '')}\n"
                    if el.get('testId'):
                        response += f"🔖 **testid:** {el.get('testId')}\n"
                        response += f"🎯 **Селектор:** `[data-testid='{el.get('testId')}']`\n"
                    if el.get('ariaLabel'):
                        response += f"🏷️ **aria-label:** {el.get('ariaLabel')}\n"
                    if el.get('type'):
                        response += f"📌 **Тип:** {el.get('type')}\n"
                    result = response
                else:
                    result = f"❌ Не нашёл элемент по запросу '{text}' в карте сайта {url}\n\n💡 Попробуй: /ai карта {url} — чтобы построить карту"
            else:
                result = f"❌ Нет карты для {url}\n\n💡 Попробуй: /ai карта {url} — чтобы построить карту"

        elif url:
            await browser.goto(url)
            await asyncio.sleep(2)
            title = await eval.get_title()
            buttons = await eval.get_all_buttons()
            inputs = await eval.get_all_inputs()
            links = await eval.get_all_links()
            prompt = f"Страница: {url}\nЗаголовок: {title}\nКнопок: {len(buttons)}\nПолей: {len(inputs)}\nСсылок: {len(links)}\n\nВопрос: {text}"
            result = await agent.ask(prompt)

        else:
            result = await agent.ask(text)

        if len(result) > 4000:
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])
        else:
            await update.message.reply_text(f"🧠 **AI Агент:**\n\n{result}")

        await agent.close()
        logger.info(f"User {user_id} -> AI: {text[:50]}...")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка AI: {error_msg}")

        if browser:
            await browser.close()
            browser = None
            orchestrator = None
            viewer = None

        await update.message.reply_text(f"❌ Ошибка: {error_msg[:100]}")


async def louis_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачать детальный лог действий Луи (JSON)"""
    global orchestrator
    
    user_id = update.effective_user.id
    
    if orchestrator is None:
        await update.message.reply_text("❌ Луи ещё не активен. Напиши что-нибудь, чтобы он запустился.")
        return
    
    args = context.args
    limit = 0
    if args and args[0].isdigit():
        limit = int(args[0])
    
    logs = orchestrator.get_logs(limit) if limit > 0 else orchestrator.action_logs
    
    if not logs:
        await update.message.reply_text("📋 Логов пока нет.")
        return
    
    filename = f"louis_log_detailed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    report = {
        "meta": {
            "total_actions": len(logs),
            "generated_at": datetime.now().isoformat(),
            "url": orchestrator.current_url,
            "agent": "Луи",
            "version": "1.0"
        },
        "statistics": {
            "success": len([l for l in logs if l.get("success")]),
            "failed": len([l for l in logs if not l.get("success")]),
            "actions": {}
        },
        "logs": logs
    }
    
    for log in logs:
        action = log.get("action", "unknown")
        report["statistics"]["actions"][action] = report["statistics"]["actions"].get(action, 0) + 1
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    with open(filename, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=(
                f"📋 **Детальный лог Луи**\n\n"
                f"📊 **Всего действий:** {len(logs)}\n"
                f"✅ **Успешных:** {report['statistics']['success']}\n"
                f"❌ **Ошибок:** {report['statistics']['failed']}\n"
                f"📂 **Файл:** {filename}\n\n"
                f"📌 **Статистика по типам:**\n" +
                "\n".join([f"  {k}: {v}" for k, v in report['statistics']['actions'].items()])
            )
        )
    
    os.remove(filename)
    logger.info(f"User {user_id} скачал детальный лог Луи")


async def louis_log_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить логи Луи"""
    global orchestrator
    
    if orchestrator is None:
        await update.message.reply_text("❌ Луи ещё не активен.")
        return
    
    orchestrator.clear_logs()
    await update.message.reply_text("🗑️ Логи Луи очищены!")


async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачать лог бота (старый)"""
    user_id = update.effective_user.id
    
    try:
        with open("bot.log", "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                caption=f"📋 Лог бота ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
            )
        logger.info(f"User {user_id} скачал лог")
    except FileNotFoundError:
        await update.message.reply_text("❌ Файл лога не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает все текстовые сообщения — Луи общается с пользователем"""
    global browser, orchestrator, viewer
    
    user_id = update.effective_user.id
    text = update.message.text
    
    if not text:
        return
    
    if text.startswith('/'):
        return
    
    await update.message.chat.send_action(action="typing")
    
    try:
        if browser is None:
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
            
            eval = Eval(browser)
            acc = Accessibility(browser)
            ai_agent = AIAgent(browser, eval, acc)
            hermes_agent = HermesAgent(browser, acc, eval, ai_agent)
            orchestrator = Orchestrator(browser, eval, acc, ai_agent, hermes_agent)
            viewer = PageViewer(browser, eval)
            logger.info("✅ Луи готов к работе!")
        
        if orchestrator is None:
            eval = Eval(browser)
            acc = Accessibility(browser)
            ai_agent = AIAgent(browser, eval, acc)
            hermes_agent = HermesAgent(browser, acc, eval, ai_agent)
            orchestrator = Orchestrator(browser, eval, acc, ai_agent, hermes_agent)
        
        if viewer is None:
            eval = Eval(browser)
            viewer = PageViewer(browser, eval)
        
        # ===== ВЫПОЛНЯЕМ КОМАНДУ =====
        result = await orchestrator.execute(text)
        
        # ===== ОТПРАВЛЯЕМ ОТВЕТ =====
        if isinstance(result, dict):
            if result.get("screenshot"):
                photo_bytes = base64.b64decode(result["screenshot"])
                await update.message.reply_photo(
                    photo=photo_bytes,
                    caption=f"📸 {result.get('message', 'Скриншот')}"
                )
            elif result.get("screenshot_before") or result.get("screenshot_after"):
                if result.get("message"):
                    await update.message.reply_text(result["message"])
                
                if result.get("screenshot_before"):
                    with open(result["screenshot_before"], "rb") as f:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"📸 До клика"
                        )
                
                if result.get("screenshot_after"):
                    with open(result["screenshot_after"], "rb") as f:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"📸 После клика"
                        )
            else:
                await update.message.reply_text(result.get("message", "✅ Готово!"))
        elif isinstance(result, str):
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("✅ Готово!")
        
        # ===== ОБНОВЛЕНИЕ ОКНА ТОЛЬКО ЕСЛИ БЫЛО ДЕЙСТВИЕ =====
        action_keywords = [
            "нажми", "клик", "открой", "перейди", "зайди", "опубликуй", 
            "скрин", "сделай", "введи", "напиши", "пост", "твит",
            "удали", "добавь", "покажи", "обнови", "войди", "выйди",
            "запости", "отправь", "выбери", "открой", "закрой"
        ]
        
        was_action = any(keyword in text.lower() for keyword in action_keywords)
        
        if viewer and viewer.chat_id and viewer.message_id and was_action:
            if hasattr(viewer, '_updating') and viewer._updating:
                logger.info("⏳ Окно уже обновляется, пропускаем")
            else:
                logger.info("🔄 Обновление окна просмотра (было действие)")
                view_result = await viewer.update()
                if view_result.get("success"):
                    try:
                        photo_bytes = base64.b64decode(view_result["screenshot"])
                        
                        caption = (
                            f"🖥️ **Окно просмотра**\n"
                            f"🔗 {view_result.get('url', 'Неизвестно')}\n"
                            f"📄 {view_result.get('title', 'Без заголовка')}\n"
                            f"🕐 {view_result.get('timestamp', '')[:19]}\n\n"
                            f"💡 Команды:\n"
                            f"  /view — обновить окно\n"
                            f"  /view_close — закрыть окно"
                        )
                        
                        await context.bot.edit_message_media(
                            chat_id=viewer.chat_id,
                            message_id=viewer.message_id,
                            media=InputMediaPhoto(media=photo_bytes, caption=caption)
                        )
                        logger.info("🔄 Окно просмотра обновлено")
                    except Exception as e:
                        logger.warning(f"Не удалось отредактировать окно: {e}")
                else:
                    logger.warning("❌ Не удалось обновить окно")
        
    except Exception as e:
        logger.error(f"Ошибка в Луи: {e}")
        if viewer and hasattr(viewer, '_updating'):
            viewer._updating = False
        await update.message.reply_text(f"❌ Ой! Что-то пошло не так: {str(e)[:100]}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("view", view))
    app.add_handler(CommandHandler("view_close", view_close))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("accessibility", accessibility))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("x", x))
    app.add_handler(CommandHandler("results", results))
    app.add_handler(CommandHandler("ai", ai))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("louis_log", louis_log))
    app.add_handler(CommandHandler("log_clear", louis_log_clear))
    
    # ===== ЛУИ — ОБРАБАТЫВАЕТ ВСЕ ТЕКСТОВЫЕ СООБЩЕНИЯ =====
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Луи запущен и готов к общению!")
    app.run_polling()


if __name__ == "__main__":
    main()