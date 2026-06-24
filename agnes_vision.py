import os
import base64
import json
import asyncio
from io import BytesIO
from openai import OpenAI
from playwright.async_api import async_playwright

# ============ ПОДКЛЮЧЕНИЕ AGNES AI ============
AGNES_API_KEY = os.getenv("AGNES_API_KEY")
if not AGNES_API_KEY:
    raise ValueError("❌ AGNES_API_KEY не найден! Получи на platform.agnes-ai.com")

client = OpenAI(
    api_key=AGNES_API_KEY,
    base_url="https://apihub.agnes-ai.com/v1"
)

# ============ ОСНОВНЫЕ ФУНКЦИИ ============

async def analyze_screenshot(screenshot_bytes: bytes, question: str) -> str:
    """
    Отправляет скриншот в Agnes AI и получает ответ
    """
    try:
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        response = client.chat.completions.create(
            model="agnes-2.0-flash",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return f"❌ Ошибка: {e}"

async def describe_page(screenshot_bytes: bytes) -> str:
    """Описывает страницу"""
    question = """
    Опиши эту страницу максимально подробно:
    
    1. Что это за сайт?
    2. Какие основные элементы ты видишь?
    3. Есть ли кнопки? Какие?
    4. Есть ли поля ввода?
    5. Что написано в заголовках?
    6. Какие цвета и дизайн?
    7. Где расположены основные элементы?
    
    Будь кратким, но информативным.
    """
    return await analyze_screenshot(screenshot_bytes, question)

async def find_element(screenshot_bytes: bytes, description: str) -> dict:
    """
    Ищет элемент на странице по описанию
    
    Возвращает: {"found": bool, "x": int, "y": int, "description": str}
    """
    question = f"""
    Найди на этом скриншоте: {description}
    
    Верни ТОЛЬКО JSON с координатами:
    {{
        "found": true/false,
        "x": число (координата X в пикселях),
        "y": число (координата Y в пикселях),
        "description": "краткое описание того, что нашёл"
    }}
    
    Если не нашёл, верни: {{"found": false}}
    """
    
    try:
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        response = client.chat.completions.create(
            model="agnes-2.0-flash",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        return {"found": False, "error": str(e)}

async def find_text_on_image(screenshot_bytes: bytes) -> str:
    """Находит и читает текст на изображении"""
    question = """
    Прочитай весь текст, который видишь на этом скриншоте.
    Если есть кнопки, поля ввода, заголовки — тоже прочитай.
    Верни все тексты в виде списка.
    """
    return await analyze_screenshot(screenshot_bytes, question)

async def analyze_meme(screenshot_bytes: bytes) -> str:
    """Анализирует мем или картинку"""
    question = """
    Опиши что изображено на этой картинке.
    Если это мем — объясни его смысл.
    Если это пост — опиши о чём он.
    Если это фото — опиши что на нём.
    """
    return await analyze_screenshot(screenshot_bytes, question)

async def find_posts_with_images(screenshot_bytes: bytes) -> str:
    """Находит посты с изображениями на странице"""
    question = """
    Найди на этой странице посты, у которых есть изображения.
    Для каждого поста укажи:
    - Автор
    - Описание
    - Есть ли изображение
    
    Верни список найденных постов.
    """
    return await analyze_screenshot(screenshot_bytes, question)

# ============ ИНТЕГРАЦИЯ С PLAYWRIGHT ============

async def vision_analyze_page(page, question: str = None) -> dict:
    """
    Анализирует текущую страницу через машинное зрение
    
    Args:
        page: Playwright page
        question: вопрос к ИИ (если None — просто опишет страницу)
    
    Returns:
        dict: { "description": str, "screenshot": bytes, "elements": list }
    """
    # Делаем скриншот
    screenshot = await page.screenshot(full_page=True)
    
    # Анализируем
    if question:
        answer = await analyze_screenshot(screenshot, question)
    else:
        answer = await describe_page(screenshot)
    
    return {
        "description": answer,
        "screenshot": screenshot
    }

async def vision_find_and_click(page, element_description: str) -> dict:
    """
    Находит элемент через машинное зрение и кликает по нему
    
    Returns:
        dict: {"success": bool, "message": str, "screenshot": bytes}
    """
    # Делаем скриншот
    screenshot = await page.screenshot(full_page=True)
    
    # Ищем элемент
    result = await find_element(screenshot, element_description)
    
    if result.get("found"):
        x = result.get("x", 0)
        y = result.get("y", 0)
        
        # Кликаем по координатам
        await page.mouse.click(x, y)
        await page.wait_for_timeout(500)
        
        # Делаем скриншот результата
        result_screenshot = await page.screenshot(full_page=True)
        
        return {
            "success": True,
            "message": f"✅ Нашёл и нажал: {result.get('description', '')}",
            "screenshot": result_screenshot,
            "coordinates": {"x": x, "y": y}
        }
    else:
        return {
            "success": False,
            "message": f"❌ Не нашёл: {element_description}",
            "screenshot": screenshot
        }

# ============ КОМАНДА ДЛЯ БОТА ============

async def vision_command(update, context):
    """
    Команда /vision — показывает что видит Agnes AI на странице
    """
    user_id = update.effective_user.id
    
    try:
        from bot import user_sessions
        if user_id not in user_sessions:
            await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
            return
        
        session = user_sessions[user_id]
        page = session["page"]
        
        await update.message.reply_text("👁️ Анализирую страницу через Agnes AI...")
        
        # Анализируем
        result = await vision_analyze_page(page)
        
        # Отправляем описание
        await update.message.reply_text(
            f"📄 **Agnes AI видит:**\n\n{result['description'][:3000]}",
            parse_mode="Markdown"
        )
        
        # Отправляем скриншот
        await update.message.reply_photo(
            photo=BytesIO(result['screenshot']),
            caption="📸 Скриншот страницы"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def vision_click_command(update, context):
    """
    Команда /vclick <описание> — кликает по элементу
    """
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Укажи что искать:\n"
            "/vclick синяя кнопка\n"
            "/vclick иконка лупы\n"
            "/vclick кнопка Войти"
        )
        return
    
    description = ' '.join(args)
    
    try:
        from bot import user_sessions
        if user_id not in user_sessions:
            await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
            return
        
        session = user_sessions[user_id]
        page = session["page"]
        
        await update.message.reply_text(f"🔍 Ищу: {description}...")
        
        result = await vision_find_and_click(page, description)
        
        # Отправляем результат
        if result["success"]:
            await update.message.reply_text(result["message"])
        else:
            await update.message.reply_text(result["message"])
        
        # Отправляем скриншот
        await update.message.reply_photo(
            photo=BytesIO(result["screenshot"]),
            caption="📸 Результат"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def vision_ask_command(update, context):
    """
    Команда /vask <вопрос> — задаёт вопрос о странице
    """
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Задай вопрос:\n"
            "/vask что написано на странице?\n"
            "/vask есть ли здесь кнопка Google?"
        )
        return
    
    question = ' '.join(args)
    
    try:
        from bot import user_sessions
        if user_id not in user_sessions:
            await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
            return
        
        session = user_sessions[user_id]
        page = session["page"]
        
        await update.message.reply_text(f"🤔 Думаю над вопросом: {question}...")
        
        # Делаем скриншот и анализируем
        screenshot = await page.screenshot(full_page=True)
        answer = await analyze_screenshot(screenshot, question)
        
        # Отправляем ответ
        await update.message.reply_text(
            f"💬 **Ответ:**\n\n{answer[:3000]}",
            parse_mode="Markdown"
        )
        
        # Отправляем скриншот
        await update.message.reply_photo(
            photo=BytesIO(screenshot),
            caption="📸 Скриншот страницы"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")