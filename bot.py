import os
import asyncio
import json
import base64
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from browser import ChromiumBrowser
from agent import (
    get_response,
    parse_response,
    parse_command,
    clear_memory,
    add_log,
    get_logs,
    clear_logs,
    get_memory_stats,
    flush_pending_saves,
    get_protocols_stats,
    parse_xbrief_plan,
    parse_simple_command
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

keep_browser = False
browser_instance = None

async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Бот-агент с xBRIEF\n\n"
        "/start — справка\n"
        "/clear — очистить память\n"
        "/logai — логи\n"
        "/logclear — очистить логи\n"
        "/keep — удержание браузера\n"
        "/close — закрыть браузер\n"
        "/status — статус\n"
        "/debug_x — диагностика X.com"
    )

async def status(update: Update, context):
    global keep_browser, browser_instance
    stats = get_memory_stats()
    logs = get_logs()
    proto_stats = get_protocols_stats()
    
    text = (
        f"📊 **Статус бота**\n"
        f"========================\n\n"
        f"🧠 **Агент:**\n"
        f"  • Память: {stats['history_count']}/{stats['max_history']}\n"
        f"  • Ошибок: {'Есть ❌' if stats['last_error'] else 'Нет ✅'}\n"
        f"  • Логов: {len(logs)}\n\n"
        f"📁 **Протоколы:**\n"
        f"  • CDP Browser: {'✅' if proto_stats['browser']['loaded'] else '❌'} "
        f"({proto_stats['browser']['domains']} доменов, {proto_stats['browser']['commands']} команд)\n"
        f"  • CDP JS: {'✅' if proto_stats['js']['loaded'] else '❌'} "
        f"({proto_stats['js']['domains']} доменов, {proto_stats['js']['commands']} команд)\n"
        f"  • xBRIEF: {'✅' if proto_stats['xbrief']['loaded'] else '❌'}\n"
        f"  • browser-logic: {'✅' if proto_stats['browser_logic']['loaded'] else '❌'}\n"
        f"  • browser-harness: {'✅' if proto_stats['browser_harness']['loaded'] else '❌'} "
        f"({proto_stats['browser_harness']['total_methods']} методов, {proto_stats['browser_harness']['total_domains']} доменов)\n"
        f"  • x-com-extraction: {'✅' if proto_stats['x_extraction']['loaded'] else '❌'}\n\n"
        f"🌐 **Браузер:**\n"
        f"  • Удержание: {'ВКЛ ✅' if keep_browser else 'ВЫКЛ ❌'}\n"
        f"  • Экземпляр: {'Запущен ✅' if browser_instance else 'Не запущен ⚪'}\n\n"
        f"📦 **Система:**\n"
        f"  • Python: {sys.version.split()[0]}\n"
        f"  • GitHub: {'✅' if os.environ.get('GITHUB_TOKEN') else '❌'}\n"
        f"  • Agnes API: {'✅' if os.environ.get('AGNES_API_KEY') else '❌'}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def debug_x(update: Update, context):
    """Диагностика X.com — проверяет куки, селекторы и состояние страницы"""
    global keep_browser, browser_instance
    
    await update.message.reply_text("🔍 Проверяю состояние X.com...")
    
    if not browser_instance or not browser_instance.websocket:
        await update.message.reply_text("❌ Браузер не запущен. Используй /keep для запуска.")
        return
    
    text = "📊 **ДИАГНОСТИКА X.COM**\n"
    text += "========================\n\n"
    
    try:
        # ===== 1. КУКИ =====
        cookies_result = await browser_instance.send_command("Network.getCookies")
        all_cookies = cookies_result.get("cookies", [])
        x_cookies = [c for c in all_cookies if "x.com" in c.get("domain", "") or "twitter.com" in c.get("domain", "")]
        
        text += "🍪 **Куки для X.com:**\n"
        text += f"  • Всего кук: {len(x_cookies)}\n"
        
        auth_cookie = next((c for c in x_cookies if c.get("name") == "auth_token"), None)
        if auth_cookie:
            text += f"  • auth_token: ✅ есть\n"
            text += f"    ({auth_cookie.get('value')[:30]}...)\n"
        else:
            text += f"  • auth_token: ❌ НЕТ\n"
        
        ct0_cookie = next((c for c in x_cookies if c.get("name") == "ct0"), None)
        if ct0_cookie:
            text += f"  • ct0: ✅ есть\n"
        else:
            text += f"  • ct0: ❌ НЕТ\n"
        
        guest_cookie = next((c for c in x_cookies if c.get("name") == "guest_id"), None)
        if guest_cookie:
            text += f"  • guest_id: ✅ есть\n"
        else:
            text += f"  • guest_id: ❌ НЕТ\n"
        
        text += "\n"
        
        # ===== 2. ТЕКУЩАЯ СТРАНИЦА =====
        url = await browser_instance.evaluate("window.location.href")
        title = await browser_instance.evaluate("document.title")
        body_len = await browser_instance.evaluate("document.body?.innerText?.length || 0")
        has_login = await browser_instance.evaluate("document.body?.innerText?.includes('Sign in') || document.body?.innerText?.includes('Войти') || false")
        
        text += "📄 **Текущая страница:**\n"
        text += f"  • URL: {url}\n"
        text += f"  • Заголовок: {title}\n"
        text += f"  • Текст: {body_len:,} символов\n"
        
        if has_login:
            text += "  • ⚠️ Страница требует ВХОДА!\n"
        else:
            text += "  • ✅ Страница загружена\n"
        text += "\n"
        
        # ===== 3. ЭЛЕМЕНТЫ X.COM =====
        js = """
        (function() {
            return {
                hasUserName: !!document.querySelector('[data-testid="User-Name"]'),
                hasUserDescription: !!document.querySelector('[data-testid="UserDescription"]'),
                hasFollowers: !!document.querySelector('a[href$="/followers"]'),
                hasFollowing: !!document.querySelector('a[href$="/following"]'),
                hasTweet: !!document.querySelector('article[data-testid="tweet"]'),
                tweetCount: document.querySelectorAll('article[data-testid="tweet"]').length,
                hasSearchInput: !!document.querySelector('[data-testid="SearchBox"]'),
                hasProfileAvatar: !!document.querySelector('img[alt*="avatar"]'),
                bodyText: document.body?.innerText?.slice(0, 200) || ''
            };
        })()
        """
        elements = await browser_instance.evaluate(js)
        
        text += "🔍 **Элементы X.com:**\n"
        text += f"  • User-Name: {'✅' if elements.get('hasUserName') else '❌'}\n"
        text += f"  • UserDescription: {'✅' if elements.get('hasUserDescription') else '❌'}\n"
        text += f"  • Followers: {'✅' if elements.get('hasFollowers') else '❌'}\n"
        text += f"  • Following: {'✅' if elements.get('hasFollowing') else '❌'}\n"
        text += f"  • Tweet: {'✅' if elements.get('hasTweet') else '❌'} ({elements.get('tweetCount', 0)})\n"
        text += f"  • SearchBox: {'✅' if elements.get('hasSearchInput') else '❌'}\n"
        text += f"  • ProfileAvatar: {'✅' if elements.get('hasProfileAvatar') else '❌'}\n"
        
        body_preview = elements.get('bodyText', '')[:100]
        if body_preview:
            text += f"\n📝 **Текст страницы (первые 100 символов):**\n"
            text += f"  {body_preview}...\n"
        
    except Exception as e:
        text += f"\n❌ **Ошибка диагностики:**\n{str(e)}"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def toggle_keep_browser(update: Update, context):
    global keep_browser
    keep_browser = not keep_browser
    await update.message.reply_text(f"🔄 Удержание: {'ВКЛ' if keep_browser else 'ВЫКЛ'}")

async def close_browser_command(update: Update, context):
    global browser_instance, keep_browser
    if browser_instance:
        await browser_instance.disconnect()
        browser_instance.close()
        browser_instance = None
        keep_browser = False
        add_log("browser_closed", "Закрыт", "info")
        flush_pending_saves()
        await update.message.reply_text("🛑 Браузер закрыт, данные сохранены")
    else:
        await update.message.reply_text("❌ Браузер не запущен")

async def clear(update: Update, context):
    clear_memory()
    await update.message.reply_text("🧹 Память очищена")

async def show_logs(update: Update, context):
    logs = get_logs()
    if not logs:
        await update.message.reply_text("📭 Логов нет")
        return
    lines = []
    for log in logs[-20:]:
        timestamp = log.get("timestamp", "")[11:19]
        action = log.get("action", "")
        details = log.get("details", "")
        status = log.get("status", "")
        emoji = "✅" if status == "success" else "❌" if status == "error" else "ℹ️"
        lines.append(f"{timestamp} {emoji} {action}: {details}")
    await update.message.reply_text("\n".join(lines))

async def clear_logs_command(update: Update, context):
    clear_logs()
    await update.message.reply_text("🧹 Логи очищены")

async def get_browser():
    global browser_instance
    if keep_browser:
        if browser_instance is None:
            browser_instance = ChromiumBrowser()
            browser_instance.launch(headless=True)
            await browser_instance.connect()
            add_log("browser_kept", "Удержан", "success")
        return browser_instance
    else:
        browser = ChromiumBrowser()
        browser.launch(headless=True)
        await browser.connect()
        return browser

async def format_runtime_result(value) -> str:
    if value is None:
        return "📊 Результат: пусто"
    
    if isinstance(value, dict):
        text = "📊 **Результат:**\n\n"
        name = value.get('name', '')
        username = value.get('username', '')
        bio = value.get('bio', '')
        followers = value.get('followers', '')
        following = value.get('following', '')
        posts = value.get('posts', '')
        joined = value.get('joined', '')
        
        if username:
            text += f"👤 **{name}** (@{username})\n\n"
        if bio:
            text += f"📝 {bio}\n\n"
        if followers:
            text += f"👥 Подписчики: **{followers}**\n"
        if following:
            text += f"📌 Подписки: **{following}**\n"
        if posts:
            text += f"📊 Постов: **{posts}**\n"
        if joined:
            text += f"📅 Присоединился: {joined}\n"
        
        if not username:
            for key, val in value.items():
                if isinstance(val, (int, float)):
                    text += f"• **{key}**: {val:,}\n"
                else:
                    text += f"• **{key}**: {val}\n"
        return text
    
    elif isinstance(value, list):
        if not value:
            return "📊 Результат: пусто"
        
        text = "📊 **Результат:**\n\n"
        for i, item in enumerate(value[:10], 1):
            if isinstance(item, dict):
                author = item.get('author', item.get('username', 'Неизвестно'))
                text_content = item.get('text', item.get('name', str(item)))[:80]
                likes = item.get('likes', '')
                retweets = item.get('retweets', '')
                
                text += f"{i}. **{author}**: {text_content}"
                if likes:
                    text += f" ❤️ {likes}"
                if retweets:
                    text += f" 🔁 {retweets}"
                text += "\n"
            else:
                text += f"{i}. {item}\n"
        
        if len(value) > 10:
            text += f"\n... и ещё {len(value) - 10} результатов"
        return text
    
    else:
        return f"📊 {value}"

async def execute_xbrief_plan(update: Update, plan: Dict) -> bool:
    items = plan.get("plan", {}).get("items", [])
    edges = plan.get("plan", {}).get("edges", [])
    
    order = []
    if edges:
        for edge in edges:
            if edge.get("type") == "blocks":
                if edge["from"] not in order:
                    order.append(edge["from"])
                if edge["to"] not in order:
                    order.append(edge["to"])
    else:
        order = [item["id"] for item in items]
    
    browser = None
    results = []
    
    for item_id in order:
        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            continue
        
        if item.get("status") == "done":
            continue
            
        method = item.get("title")
        params = item.get("params", {})
        
        await update.message.reply_text(f"⚡ {method} (шаг {order.index(item_id) + 1}/{len(order)})")
        
        try:
            if not browser:
                browser = await get_browser()
            
            # ===== ОБРАБОТКА СПЕЦИАЛЬНЫХ МЕТОДОВ =====
            if method == "extract":
                model_name = params.get("model")
                timeout = params.get("timeout", 10)
                result = await browser.extract(model_name, timeout)
                formatted = await format_runtime_result(result)
                await update.message.reply_text(formatted, parse_mode="Markdown")
                item["status"] = "done"
                results.append({"id": item_id, "status": "done"})
                continue
            
            elif method == "extract_all":
                model_name = params.get("model")
                limit = params.get("limit", 20)
                timeout = params.get("timeout", 10)
                result = await browser.extract_all(model_name, timeout, limit)
                formatted = await format_runtime_result(result)
                await update.message.reply_text(formatted, parse_mode="Markdown")
                item["status"] = "done"
                results.append({"id": item_id, "status": "done"})
                continue
            
            elif method == "wait":
                selector = params.get("selector")
                timeout = params.get("timeout", 10)
                await browser.wait_for_element(selector, timeout)
                await update.message.reply_text(f"⏳ Элемент найден: {selector}")
                item["status"] = "done"
                results.append({"id": item_id, "status": "done"})
                continue
            
            # ===== ОБЫЧНЫЕ CDP-КОМАНДЫ =====
            result = await browser.send_command(method, params)
            
            item["status"] = "done"
            results.append({"id": item_id, "status": "done"})
            
            if method == "Page.captureScreenshot":
                if "result" in result and "data" in result["result"]:
                    img_data = base64.b64decode(result["result"]["data"])
                    await update.message.reply_photo(photo=img_data, caption="📸 Скриншот")
                else:
                    await update.message.reply_text("✅ Скриншот сделан")
            elif method == "Page.navigate":
                await asyncio.sleep(1)
                title = await browser.evaluate("document.title")
                await update.message.reply_text(f"✅ {params.get('url')}\n📄 {title}")
            elif method == "Runtime.evaluate":
                value = result.get("result", {}).get("result", {}).get("value")
                formatted = await format_runtime_result(value)
                await update.message.reply_text(formatted, parse_mode="Markdown")
            else:
                await update.message.reply_text("✅ Выполнено")
                
        except Exception as e:
            item["status"] = "failed"
            await update.message.reply_text(f"❌ Ошибка в шаге {item_id}: {str(e)}")
            if browser and not keep_browser:
                await browser.disconnect()
                browser.close()
            return False
    
    if browser and not keep_browser:
        await browser.disconnect()
        browser.close()
    
    narratives = plan.get("plan", {}).get("narratives", {})
    if narratives.get("Outcome"):
        await update.message.reply_text(f"📋 **Итог:** {narratives['Outcome']}")
    
    return True

async def execute_with_retry(update: Update, user_text: str, max_retries: int = 2) -> bool:
    add_log("user_input", user_text, "info")
    for attempt in range(max_retries + 1):
        try:
            agent_response = await get_response(user_text)
            parsed = parse_response(agent_response)
            
            if not parsed:
                add_log("agent_response", agent_response[:100], "info")
                await update.message.reply_text(agent_response)
                return True
            
            if parsed.get("type") == "xbrief":
                add_log("xbrief_plan", "Получен xBRIEF план", "info")
                return await execute_xbrief_plan(update, parsed["data"])
            else:
                cmd = parsed["data"]
                method = cmd.get("method")
                params = cmd.get("params", {})
                
                add_log("command", f"{method}", "info")
                await update.message.reply_text(f"⚡ {method}")
                
                browser = await get_browser()
                result = await browser.send_command(method, params)
                add_log("success", method, "success")
                
                if method == "Page.captureScreenshot":
                    if "result" in result and "data" in result["result"]:
                        img_data = base64.b64decode(result["result"]["data"])
                        await update.message.reply_photo(photo=img_data, caption="📸 Скриншот")
                    else:
                        await update.message.reply_text("✅ Скриншот сделан")
                elif method == "Page.navigate":
                    await asyncio.sleep(1)
                    title = await browser.evaluate("document.title")
                    await update.message.reply_text(f"✅ {params.get('url')}\n📄 {title}")
                elif method == "Runtime.evaluate":
                    value = result.get("result", {}).get("result", {}).get("value")
                    formatted = await format_runtime_result(value)
                    await update.message.reply_text(formatted, parse_mode="Markdown")
                else:
                    await update.message.reply_text("✅ Выполнено")
                
                if not keep_browser:
                    await browser.disconnect()
                    browser.close()
                return True
                
        except Exception as e:
            error_msg = str(e)
            add_log("error", error_msg[:150], "error")
            await update.message.reply_text(f"❌ {error_msg}")
            if attempt < max_retries:
                await update.message.reply_text(f"🔄 Попытка {attempt+2}/{max_retries+1}")
            else:
                await update.message.reply_text("❌ Не удалось выполнить")
            continue
    return False

async def handle_message(update: Update, context):
    user_text = update.message.text
    await update.message.reply_text("🤔 Думаю...")
    await execute_with_retry(update, user_text)

def main():
    add_log("bot_started", "Бот запущен", "success")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("logai", show_logs))
    app.add_handler(CommandHandler("logclear", clear_logs_command))
    app.add_handler(CommandHandler("keep", toggle_keep_browser))
    app.add_handler(CommandHandler("close", close_browser_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("debug_x", debug_x))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен с xBRIEF")
    app.run_polling()

if __name__ == "__main__":
    main()