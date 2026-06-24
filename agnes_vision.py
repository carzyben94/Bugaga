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

async def vision_analyze_page(page, question: str = None) -> dict:
    screenshot = await page.screenshot(full_page=True)
    
    if question:
        answer = await analyze_screenshot(screenshot, question)
    else:
        answer = await describe_page(screenshot)
    
    return {
        "description": answer,
        "screenshot": screenshot
    }

async def vision_find_and_click(page, element_description: str) -> dict:
    screenshot = await page.screenshot(full_page=True)
    
    result = await find_element(screenshot, element_description)
    
    if result.get("found"):
        x = result.get("x", 0)
        y = result.get("y", 0)
        
        await page.mouse.click(x, y)
        await page.wait_for_timeout(500)
        
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

# ============ КОМАНДЫ ДЛЯ БОТА ============

async def vision_command(update, context):
    """/vision — описать страницу"""
    if 'page' not in context.user_data:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    page = context.user_data['page']
    
    await update.message.reply_text("👁️ Анализирую страницу через Agnes AI...")
    
    try:
        result = await vision_analyze_page(page)
        
        await update.message.reply_text(
            f"📄 **Agnes AI видит:**\n\n{result['description'][:3000]}",
            parse_mode="Markdown"
        )
        
        await update.message.reply_photo(
            photo=BytesIO(result['screenshot']),
            caption="📸 Скриншот страницы"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def vision_click_command(update, context):
    """/vclick <описание> — кликнуть по элементу"""
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
    
    if 'page' not in context.user_data:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    page = context.user_data['page']
    
    await update.message.reply_text(f"🔍 Ищу: {description}...")
    
    try:
        result = await vision_find_and_click(page, description)
        
        if result["success"]:
            await update.message.reply_text(result["message"])
        else:
            await update.message.reply_text(result["message"])
        
        await update.message.reply_photo(
            photo=BytesIO(result["screenshot"]),
            caption="📸 Результат"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def vision_ask_command(update, context):
    """/vask <вопрос> — задать вопрос о странице"""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Задай вопрос:\n"
            "/vask что написано на странице?\n"
            "/vask есть ли здесь кнопка Google?"
        )
        return
    
    question = ' '.join(args)
    
    if 'page' not in context.user_data:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    page = context.user_data['page']
    
    await update.message.reply_text(f"🤔 Думаю над вопросом: {question}...")
    
    try:
        screenshot = await page.screenshot(full_page=True)
        answer = await analyze_screenshot(screenshot, question)
        
        await update.message.reply_text(
            f"💬 **Ответ:**\n\n{answer[:3000]}",
            parse_mode="Markdown"
        )
        
        await update.message.reply_photo(
            photo=BytesIO(screenshot),
            caption="📸 Скриншот страницы"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")