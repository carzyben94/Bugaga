import os
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт модулей
from browser import Browser
from eval import Eval
from accessibility import Accessibility
from ai import AI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/browser - открыть ссылку\n"
        "/tab - показать вкладки\n"
        "/accessibility - проверить доступность\n"
        "/ask - спросить AI\n"
        "/close - закрыть браузер"
    )

async def browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите ссылку\nПример: /browser x.com")
            return
        
        url = context.args[0]
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        browser = context.user_data.get('browser')
        
        if not browser:
            browser = await Browser().start()
            context.user_data['browser'] = browser
            context.user_data['eval'] = Eval(browser)
            context.user_data['accessibility'] = Accessibility(browser, context.user_data['eval'])
            context.user_data['ai'] = AI(browser, context.user_data['eval'], context.user_data['accessibility'])
        
        await browser.goto(url)
        
        screenshot_data = await browser.screenshot()
        image_bytes = base64.b64decode(screenshot_data)
        
        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"✅ {url}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        if 'browser' in context.user_data:
            try:
                await context.user_data['browser'].close()
            except:
                pass
            context.user_data['browser'] = None
            context.user_data['eval'] = None
            context.user_data['accessibility'] = None
            context.user_data['ai'] = None

async def tab_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        browser = context.user_data.get('browser')
        if not browser:
            await update.message.reply_text("❌ Браузер не запущен")
            return
        
        tabs = await browser.send("Target.getTargets")
        
        if not tabs or 'targetInfos' not in tabs:
            await update.message.reply_text("❌ Нет активных вкладок")
            return
        
        tab_list = []
        for i, target in enumerate(tabs['targetInfos'], 1):
            url = target.get('url', 'about:blank')
            title = target.get('title', 'Без названия')
            tab_list.append(f"{i}. {title}\n   {url}")
        
        if not tab_list:
            await update.message.reply_text("❌ Нет активных вкладок")
            return
        
        text = "📑 Активные вкладки:\n\n" + "\n\n".join(tab_list)
        await update.message.reply_text(text[:4096])
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def accessibility_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        acc = context.user_data.get('accessibility')
        if not acc:
            await update.message.reply_text("❌ Сначала запустите браузер командой /browser")
            return
        
        await update.message.reply_text("🔍 Проверяю доступность страницы...")
        
        headings = await acc.check_heading_hierarchy()
        images = await acc.check_images_alt()
        aria = await acc.check_aria_labels()
        elements = await acc.get_elements_with_refs()
        
        report = "📊 **Отчет по доступности:**\n\n"
        
        report += f"**Заголовки:** {headings.get('total', 0)} найдено\n"
        if headings.get('issues'):
            report += f"⚠️ {len(headings['issues'])} проблем\n"
        else:
            report += "✅ Иерархия корректна\n"
        
        report += f"\n**Изображения:** {images.get('total', 0)} всего\n"
        report += f"✅ С alt: {images.get('passed', 0)}\n"
        report += f"❌ Без alt: {images.get('failed', 0)}\n"
        
        report += f"\n**ARIA-метки:** {aria.get('total', 0)} элементов\n"
        report += f"✅ С метками: {aria.get('has_aria', 0)}\n"
        if aria.get('issues'):
            report += f"⚠️ {len(aria['issues'])} элементов без меток\n"
        
        report += f"\n**Интерактивные элементы:** {len(elements)} найдено\n"
        if elements:
            refs = [el['ref'] for el in elements[:10]]
            report += f"🔗 Рефы: {', '.join(refs)}"
            if len(elements) > 10:
                report += f" и еще {len(elements)-10}"
        
        await update.message.reply_text(report, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Напишите запрос\nПример: /ask что на странице?")
            return
        
        query = " ".join(context.args)
        
        ai = context.user_data.get('ai')
        if not ai:
            await update.message.reply_text("❌ Сначала запустите браузер командой /browser")
            return
        
        await update.message.reply_text("🤔 Думаю...")
        response = await ai.ask(query)
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser = context.user_data.get('browser')
    if browser:
        await browser.close()
        context.user_data['browser'] = None
        context.user_data['eval'] = None
        context.user_data['accessibility'] = None
        context.user_data['ai'] = None
        await update.message.reply_text("✅ Готово!")
    else:
        await update.message.reply_text("❌")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser", browser_cmd))
    app.add_handler(CommandHandler("tab", tab_cmd))
    app.add_handler(CommandHandler("accessibility", accessibility_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("close", close_cmd))
    
    print("✅ Бот запущен!")
    print("📋 Команды: /browser, /tab, /accessibility, /ask, /close")
    app.run_polling()

if __name__ == "__main__":
    main()