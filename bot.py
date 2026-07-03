import os
import sys
import subprocess
import logging
import asyncio
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== ПРОВЕРКА БИБЛИОТЕК ==========
PYDOLL_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False
CHROMIUM_INSTALLED = False
CHROMIUM_PATH = None

try:
    import pydoll
    PYDOLL_AVAILABLE = True
except:
    pass

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except:
    pass

# Chromium
try:
    r = subprocess.run(['chromium', '--version'], capture_output=True, text=True)
    if r.returncode == 0:
        CHROMIUM_INSTALLED = True
        CHROMIUM_PATH = '/usr/bin/chromium'
except:
    pass

# ========== КУКИ ==========
COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
browser_data = None
pydoll_browser = None
pydoll_tab = None
engine_mode = "pydoll"
login_status = {'is_logged_in': False, 'username': None}

# ========== БРАУЗЕР ==========
async def get_browser():
    global pydoll_browser, pydoll_tab, CHROMIUM_PATH
    
    if pydoll_browser and pydoll_tab:
        try:
            await pydoll_tab.execute_script('1')
            return pydoll_tab
        except:
            pass
    
    try:
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions
        
        options = ChromiumOptions()
        if CHROMIUM_PATH:
            options.binary_location = CHROMIUM_PATH
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        
        pydoll_browser = Chrome(options=options)
        pydoll_tab = await pydoll_browser.start()
        
        # Устанавливаем куки
        await pydoll_tab.go_to('https://x.com')
        await asyncio.sleep(2)
        for cookie in COOKIES:
            try:
                await pydoll_tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie['path']
                )
            except:
                pass
        
        return pydoll_tab
    except Exception as e:
        logger.error(f"Browser error: {e}")
        return None

async def close_browser():
    global pydoll_browser, pydoll_tab
    if pydoll_browser:
        try:
            await pydoll_browser.close()
        except:
            pass
        pydoll_browser = None
        pydoll_tab = None

async def execute_js(script):
    page = await get_browser()
    if page is None:
        return None
    try:
        if hasattr(page, 'execute_script'):
            return await page.execute_script(script)
        elif hasattr(page, 'evaluate'):
            return await page.evaluate(script)
    except Exception as e:
        logger.error(f"JS error: {e}")
        return None

# ========== /LOGIN ==========
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Не удалось запустить браузер")
            return
        
        await page.go_to('https://x.com')
        await asyncio.sleep(3)
        
        auth = await execute_js('''
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [k,v] = c.trim().split('=');
                    acc[k]=v;
                    return acc;
                }, {});
                const hasAuth = !!cookies.auth_token;
                let username = null;
                const profile = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profile) {
                    const href = profile.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                return { hasAuth, username, isLoggedIn: hasAuth };
            }
        ''')
        
        if auth and auth.get('isLoggedIn'):
            login_status['is_logged_in'] = True
            login_status['username'] = auth.get('username')
            await msg.edit_text(f"✅ Авторизован! @{auth.get('username', '')}")
        else:
            login_status['is_logged_in'] = False
            await msg.edit_text("❌ Не авторизован. Обновите куки")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== /DIAGNOS ==========
async def diagnos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔬 Диагностика...")
    
    log_file = f"diagnos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    lines = []
    
    def log(t):
        lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {t}")
        logger.info(t)
    
    results = {}
    solutions = {}
    
    try:
        log("=== ДИАГНОСТИКА ===")
        
        # 1. Система
        log(f"Python: {sys.version.split()[0]}")
        log(f"Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
        log(f"Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}")
        log(f"Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
        log(f"Авторизация: {'✅' if login_status['is_logged_in'] else '❌'}")
        
        # 2. Браузер
        page = await get_browser()
        if page is None:
            log("❌ Браузер не запущен")
            results["browser"] = "❌ Не запущен"
            solutions["browser"] = "Используйте /login"
        else:
            log("✅ Браузер запущен")
            results["browser"] = "✅ Работает"
            solutions["browser"] = "OK"
            
            # 3. Shadow DOM
            try:
                shadow = await page.execute_script("""
                    document.querySelectorAll('*').filter(el => el.shadowRoot).length
                """)
                if shadow and shadow > 0:
                    results["shadow"] = f"✅ {shadow} элементов"
                    solutions["shadow"] = "Shadow DOM доступен"
                else:
                    results["shadow"] = "⚠️ Не найдены"
                    solutions["shadow"] = "Используйте работающий вариант"
            except Exception as e:
                results["shadow"] = f"❌ {str(e)[:30]}"
                solutions["shadow"] = "Используйте альтернативный метод"
            
            # 4. API
            try:
                api = await page.execute_script("""
                    (async () => {
                        try {
                            const r = await fetch('https://x.com/i/api/1.1/onboarding/task.json',
                                {credentials: 'include', headers: {'Accept': 'application/json'}});
                            return { ok: r.ok, status: r.status };
                        } catch(e) { return { error: e.message }; }
                    })()
                """)
                if api and api.get('ok'):
                    results["api"] = f"✅ Статус {api.get('status')}"
                    solutions["api"] = "API работает"
                else:
                    results["api"] = f"⚠️ Статус {api.get('status', 'unknown')}"
                    solutions["api"] = "Проверьте авторизацию и куки"
            except Exception as e:
                results["api"] = f"❌ {str(e)[:30]}"
                solutions["api"] = "Проверьте авторизацию и куки"
            
            # 5. Extract
            try:
                extracted = await page.execute_script("""
                    document.querySelectorAll('[data-testid="tweet"]').length
                """)
                if extracted and extracted > 0:
                    results["extract"] = f"✅ {extracted} твитов"
                    solutions["extract"] = "Extract работает"
                else:
                    results["extract"] = "⚠️ Нет данных"
                    solutions["extract"] = "Используйте работающий вариант"
            except Exception as e:
                results["extract"] = f"❌ {str(e)[:30]}"
                solutions["extract"] = "Используйте работающий вариант"
            
            # 6. Search
            try:
                await page.go_to("https://x.com/search?q=python&src=typed_query")
                await asyncio.sleep(1.5)
                found = await page.execute_script("""
                    document.querySelectorAll('[data-testid="tweet"]').length
                """)
                if found and found > 0:
                    results["search"] = f"✅ {found} результатов"
                    solutions["search"] = "Поиск работает. Используйте /search <запрос>"
                else:
                    results["search"] = "⚠️ Нет результатов"
                    solutions["search"] = "Попробуйте другой запрос"
            except Exception as e:
                results["search"] = f"❌ {str(e)[:30]}"
                solutions["search"] = "Проверьте соединение"
            
            # 7. Tweets
            try:
                await page.go_to("https://x.com/elonmusk")
                await asyncio.sleep(1.5)
                found = await page.execute_script("""
                    document.querySelectorAll('[data-testid="tweet"]').length
                """)
                if found and found > 0:
                    results["tweets"] = f"✅ {found} твитов"
                    solutions["tweets"] = "Парсинг работает. Используйте /tweets <username>"
                else:
                    results["tweets"] = "⚠️ Нет твитов"
                    solutions["tweets"] = "Проверьте имя пользователя"
            except Exception as e:
                results["tweets"] = f"❌ {str(e)[:30]}"
                solutions["tweets"] = "Проверьте имя пользователя"
        
        # ============================================================
        # ОТЧЕТ
        # ============================================================
        success_count = sum(1 for s in results.values() if "✅" in str(s))
        total = len(results)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        report = "🔬 **ДИАГНОСТИКА ЗАВЕРШЕНА**\n\n"
        report += "📊 **Результаты:**\n"
        for cmd, status in results.items():
            emoji = "✅" if "✅" in str(status) else ("⚠️" if "⚠️" in str(status) else "❌")
            report += f"  {emoji} {cmd.upper()}: {status}\n"
        
        report += f"\n✅ Успешно: {success_count}/{total}\n\n"
        
        report += "📋 **РЕШЕНИЯ:**\n"
        for cmd, solution in solutions.items():
            report += f"  💡 {cmd.upper()}: {solution}\n"
        
        if success_count == total:
            report += "\n🎉 **ВСЕ КОМАНДЫ РАБОТАЮТ!**"
        elif success_count >= total // 2:
            report += "\n\n⚠️ **НЕКОТОРЫЕ КОМАНДЫ НЕ РАБОТАЮТ**"
            report += "\n📋 Проверьте лог-файл для деталей"
        else:
            report += "\n\n❌ **БОЛЬШИНСТВО КОМАНД НЕ РАБОТАЮТ**"
            report += "\n📋 Проверьте лог-файл для деталей"
        
        await msg.edit_text(report)
        await update.message.reply_document(
            document=open(log_file, 'rb'),
            caption=f"📋 Лог диагностики\n{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("diagnos", diagnos))
    
    print("✅ Бот запущен!")
    print("Команды: /login, /diagnos")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()