import os
import logging
import asyncio
import sqlite3
import io
from PIL import Image
from rembg import remove
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# ==================== БАЗА ДАННЫХ ====================
def get_db():
    return sqlite3.connect('bot_data.db')

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS backgrounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("✅ База данных инициализирована")

async def count_bgs():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM backgrounds")
    count = c.fetchone()[0]
    conn.close()
    return count

# ==================== ХРАНИЛИЩЕ СЕССИЙ ====================
user_sessions = {}

# ==================== КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 Бот для замены фона!\n\n"
        "/swap - заменить фон (сначала объект, потом фон)\n"
        "/savebg - сохранить фото как фон\n"
        "/listbg - сколько фонов сохранено\n"
        "/delbg <ID> - удалить фон\n"
        "/clearbg - удалить все фоны\n"
        "/cancel - отменить операцию"
    )

async def swap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = {'step': 'waiting_for_object'}
    
    await update.message.reply_text(
        "🖼️ Отправь мне **фото с объектом**, "
        "а потом отправь **фото для нового фона**.\n\n"
        "Я вырежу объект и помещу его на новый фон!\n"
        "Чтобы отменить - /cancel"
    )

async def save_bg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Отправь мне фото, и я сохраню его как фон!")
    context.user_data['waiting_for_save_bg'] = True

async def list_bgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = await count_bgs()
    await update.message.reply_text(
        f"📁 В базе {count} фонов.\n\n"
        "Чтобы добавить - /savebg\n"
        "Чтобы удалить - /delbg <ID>"
    )

async def delete_bg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /delbg <ID>\nПример: /delbg 5")
        return
    
    try:
        bg_id = int(context.args[0])
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM backgrounds WHERE id = ?", (bg_id,))
        conn.commit()
        deleted = c.rowcount > 0
        conn.close()
        
        if deleted:
            await update.message.reply_text(f"✅ Фон #{bg_id} удалён")
        else:
            await update.message.reply_text(f"❌ Фон #{bg_id} не найден")
            
    except ValueError:
        await update.message.reply_text("❌ Введи число")

async def clear_bgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM backgrounds")
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑️ Все фоны удалены!")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions.pop(user_id, None)
    context.user_data.pop('waiting_for_save_bg', None)
    await update.message.reply_text("✅ Отменено!")

# ==================== ОБРАБОТЧИК ФОТО ====================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        file_id = photo_file.file_id
        
        # ===== РЕЖИМ: Сохранение фона =====
        if context.user_data.get('waiting_for_save_bg'):
            conn = get_db()
            c = conn.cursor()
            c.execute("INSERT INTO backgrounds (file_id) VALUES (?)", (file_id,))
            conn.commit()
            bg_id = c.lastrowid
            conn.close()
            
            await update.message.reply_text(
                f"✅ Фото сохранено как фон #{bg_id}!\n"
                f"Всего фонов: {await count_bgs()}"
            )
            context.user_data['waiting_for_save_bg'] = False
            return
        
        # ===== РЕЖИМ: Замена фона (/swap) =====
        if session:
            if session['step'] == 'waiting_for_object':
                user_sessions[user_id]['object_file_id'] = file_id
                user_sessions[user_id]['step'] = 'waiting_for_background'
                
                await update.message.reply_text(
                    "✅ Объект сохранён!\n"
                    "Теперь отправь **фото для нового фона**"
                )
                
            elif session['step'] == 'waiting_for_background':
                object_file_id = session.get('object_file_id')
                if not object_file_id:
                    await update.message.reply_text("❌ Ошибка: объект не найден. Начни заново: /swap")
                    user_sessions.pop(user_id, None)
                    return
                
                msg = await update.message.reply_text("🎨 Обрабатываю... (5-10 секунд)")
                
                # Скачиваем объект
                object_file = await context.bot.get_file(object_file_id)
                object_bytes = await object_file.download_as_bytearray()
                
                # Скачиваем фон
                bg_file = await context.bot.get_file(file_id)
                bg_bytes = await bg_file.download_as_bytearray()
                
                # Вырезаем объект через rembg
                object_img = Image.open(io.BytesIO(object_bytes))
                object_no_bg = remove(object_img)
                
                # Открываем фон
                bg_img = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
                
                # Ресайзим объект под размер фона
                bg_width, bg_height = bg_img.size
                object_no_bg = object_no_bg.resize((bg_width, bg_height), Image.LANCZOS)
                
                # Накладываем объект на фон
                bg_img.paste(object_no_bg, (0, 0), object_no_bg)
                
                # Сохраняем результат
                result_img = io.BytesIO()
                bg_img.save(result_img, format="PNG")
                result_img.seek(0)
                
                # Отправляем результат
                await msg.delete()
                await update.message.reply_photo(
                    photo=result_img,
                    caption="✅ Готово! Используй /swap, чтобы сделать ещё"
                )
                
                user_sessions.pop(user_id, None)
            return
        
        # ===== Если просто фото =====
        await update.message.reply_text(
            "📸 Хочешь заменить фон?\n"
            "Используй /swap\n\n"
            "Или сохранить фото как фон? /savebg"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:150]}")
        user_sessions.pop(user_id, None)
        context.user_data.pop('waiting_for_save_bg', None)

# ==================== ЗАПУСК ====================
async def main():
    init_db()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("swap", swap_command))
    app.add_handler(CommandHandler("savebg", save_bg))
    app.add_handler(CommandHandler("listbg", list_bgs))
    app.add_handler(CommandHandler("delbg", delete_bg))
    app.add_handler(CommandHandler("clearbg", clear_bgs))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    
    logging.info("🚀 Бот запущен")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logging.info("⏹️ Остановка...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())