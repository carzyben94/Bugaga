import os
import subprocess
import tempfile
import base64
import asyncio
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

class BrowserHarnessCLI:
    """Обертка для browser-harness через CLI"""
    
    def __init__(self):
        self.browser_process = None
        self.temp_script = None
        
    def run_script(self, script: str, timeout: int = 60) -> str:
        """Запускает скрипт в browser-harness"""
        try:
            result = subprocess.run(
                ["browser-harness"],
                input=script,
                text=True,
                capture_output=True,
                timeout=timeout,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise RuntimeError(f"Harness error: {error_msg}")
                
            return result.stdout
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Harness timeout (60s)")
        except FileNotFoundError:
            raise RuntimeError("browser-harness not found in PATH")
        except Exception as e:
            raise RuntimeError(f"Harness error: {str(e)}")
    
    def new_tab(self, url: str) -> str:
        """Открывает новую вкладку"""
        script = f"""
new_tab("{url}")
wait_for_load()
print(page_info())
"""
        return self.run_script(script)
    
    def screenshot(self) -> bytes:
        """Делает скриншот и возвращает как bytes"""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            script = f"""
capture_screenshot("{tmp_path}")
print("SCREENSHOT_SAVED")
"""
            self.run_script(script)
            
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def get_content(self) -> str:
        """Получает HTML содержимое страницы"""
        script = """
html = js("document.documentElement.outerHTML")
print(html)
"""
        return self.run_script(script)
    
    def click(self, x: int, y: int) -> str:
        """Клик по координатам"""
        script = f"""
click_at_xy({x}, {y})
capture_screenshot("click_result.png")
print("Clicked at ({}, {})".format({x}, {y}))
"""
        return self.run_script(script)
    
    def fill(self, selector: str, text: str) -> str:
        """Заполняет поле"""
        script = f"""
fill_input("{selector}", "{text}")
print("Filled {}".format("{selector}"))
"""
        return self.run_script(script)
    
    def execute_js(self, code: str) -> str:
        """Выполняет JavaScript"""
        # Экранируем кавычки в коде
        code_escaped = code.replace('"', '\\"')
        script = f"""
result = js("{code_escaped}")
print(result)
"""
        return self.run_script(script)
    
    def get_page_info(self) -> dict:
        """Получает информацию о странице"""
        script = """
info = page_info()
print(info)
"""
        output = self.run_script(script)
        try:
            # Парсим JSON вывод
            return json.loads(output)
        except:
            return {"raw": output}

# Глобальный экземпляр
browser = BrowserHarnessCLI()

# ============ BOT COMMANDS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Browser Harness Bot\n"
        "Команды:\n"
        "/navigate <url> - открыть страницу\n"
        "/screenshot - скриншот\n"
        "/html - получить HTML\n"
        "/click <x> <y> - кликнуть\n"
        "/fill <selector> <text> - заполнить\n"
        "/js <code> - выполнить JS\n"
        "/info - информация о странице"
    )

async def navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /navigate https://example.com")
        return
    
    url = context.args[0]
    try:
        result = browser.new_tab(url)
        await update.message.reply_text(f"✅ Открыто: {url}\n\n{result[:500]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        img_bytes = browser.screenshot()
        await update.message.reply_photo(img_bytes, caption="📸 Скриншот")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def get_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        html = browser.get_content()
        # Обрезаем длинный HTML
        if len(html) > 4000:
            html = html[:4000] + "... (обрезано)"
        await update.message.reply_text(f"📄 HTML:\n\n{html}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def click_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите координаты: /click 100 200")
        return
    
    try:
        x, y = int(context.args[0]), int(context.args[1])
        result = browser.click(x, y)
        await update.message.reply_text(f"✅ Клик по ({x}, {y})\n\n{result}")
    except ValueError:
        await update.message.reply_text("❌ Координаты должны быть числами")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def fill_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите: /fill #input текст")
        return
    
    selector = context.args[0]
    text = ' '.join(context.args[1:])
    
    try:
        result = browser.fill(selector, text)
        await update.message.reply_text(f"✅ Заполнено: {selector}\n\n{result}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def execute_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите JS код: /js document.title")
        return
    
    code = ' '.join(context.args)
    try:
        result = browser.execute_js(code)
        await update.message.reply_text(f"📝 Результат:\n\n{result[:500]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        info = browser.get_page_info()
        info_text = json.dumps(info, indent=2, ensure_ascii=False)
        await update.message.reply_text(f"📊 Информация:\n\n{info_text[:500]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ============ MAIN ============

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return
    
    # Проверяем доступность browser-harness
    try:
        test_result = subprocess.run(
            ["browser-harness", "--help"],
            capture_output=True,
            timeout=5
        )
        if test_result.returncode != 0:
            print("⚠️ browser-harness недоступен, будут проблемы с командами")
        else:
            print("✅ browser-harness доступен")
    except FileNotFoundError:
        print("❌ browser-harness не найден в PATH")
        print("   Установите: uv tool install browser-harness")
        return
    
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("navigate", navigate))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("html", get_html))
    app.add_handler(CommandHandler("click", click_element))
    app.add_handler(CommandHandler("fill", fill_field))
    app.add_handler(CommandHandler("js", execute_js))
    app.add_handler(CommandHandler("info", get_info))
    
    print("🤖 Бот запущен, ожидаем сообщения...")
    app.run_polling()

if __name__ == "__main__":
    main()