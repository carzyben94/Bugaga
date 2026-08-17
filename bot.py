import os
import re
import asyncio
import logging
import httpx
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import dspy
from dspy import Signature, InputField, OutputField

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# TokenRouter (ключ вшит, как ты просил)
TOKENROUTER_API_KEY = "REDACTED"
TOKENROUTER_BASE_URL = "https://api.tokenrouter.com/v1"
MODEL_NAME = "qwen/qwen3.8-max-free"

# GitHub
# ⚠️ GITHUB_TOKEN настоятельно рекомендую положить в env var!
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME", "your-username/your-repo")  # ← замени!
BRANCH = "main"
BOT_FILE = "bot.py"
REQUIREMENTS_FILE = "requirements.txt"

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

# ============================================================
# КЛИЕНТ TOKENROUTER (OpenAI SDK — для /models и чата)
# ============================================================

from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url=TOKENROUTER_BASE_URL,
    api_key=TOKENROUTER_API_KEY,
)

SYSTEM_PROMPT = "Ты полезный и дружелюбный ассистент в Telegram. Отвечай кратко и по делу."

# ============================================================
# КЛИЕНТ GITHUB (PyGithub)
# ============================================================

gh_client = None
repo = None

if GITHUB_TOKEN:
    try:
        from github import Github, GithubException
        gh_client = Github(GITHUB_TOKEN)
        repo = gh_client.get_repo(REPO_NAME)
        logger.info("✅ GitHub подключён: %s", REPO_NAME)
    except Exception as e:
        logger.error("❌ Ошибка подключения к GitHub: %s", e)
        repo = None
else:
    logger.warning("⚠️ GITHUB_TOKEN не задан — /rewrite и /set_dspy будут недоступны")


def read_repo_file(path: str) -> str:
    content_file = repo.get_contents(path, ref=BRANCH)
    return content_file.decoded_content.decode("utf-8")


def commit_repo_file(path: str, content: str, message: str) -> None:
    content_file = repo.get_contents(path, ref=BRANCH)
    repo.update_file(
        path=path,
        message=message,
        content=content,
        sha=content_file.sha,
        branch=BRANCH,
    )


# ============================================================
# БЕЗОПАСНОСТЬ КОДА
# ============================================================

FORBIDDEN_PATTERNS = [
    r"os\.system\(",
    r"subprocess\.run\(",
    r"subprocess\.Popen\(",
    r"subprocess\.call\(",
    r"\beval\(",
    r"\bexec\(",
    r"__import__\(",
    r"import\s+subprocess",
    r"from\s+subprocess",
    r"import\s+pty",
    r"from\s+pty",
]


def contains_forbidden_code(code: str) -> bool:
    return any(re.search(p, code) for p in FORBIDDEN_PATTERNS)


def validate_python_code(code: str) -> None:
    compile(code, BOT_FILE, "exec")


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def mask_secrets(code: str) -> str:
    """Маскируем ключи, чтобы LLM не вернула их в коммит."""
    masked = code
    masked = re.sub(
        r'(TOKENROUTER_API_KEY\s*=\s*["\'])([^"\']+)(["\'])',
        r"\1REDACTED\3",
        masked,
    )
    masked = re.sub(
        r'(GITHUB_TOKEN\s*=\s*["\'])([^"\']+)(["\'])',
        r"\1REDACTED\3",
        masked,
    )
    return masked


# ============================================================
# DSPY: КАСТОМНЫЙ LM ДЛЯ TOKENROUTER
# ============================================================

class TokenRouterLM(dspy.LM):
    """DSPy-совместимый LM для OpenAI-подобного TokenRouter API."""

    def __init__(
        self,
        model=MODEL_NAME,
        api_key=TOKENROUTER_API_KEY,
        base_url=TOKENROUTER_BASE_URL,
        **kwargs,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = kwargs.get("temperature", 0.1)
        self.max_tokens = kwargs.get("max_tokens", 8000)

        super().__init__(
            model=model,
            model_type="chat",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            cache=False,
        )
        self.provider = "tokenrouter"

    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            raise RuntimeError("TOKENROUTER_API_KEY не задан")

        params = {**self.kwargs, **kwargs}
        api_messages = messages or [{"role": "user", "content": prompt or ""}]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get("temperature", self.temperature),
            "max_tokens": params.get("max_tokens", self.max_tokens),
        }

        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=30, read=180, write=30, pool=30)
            ) as http:
                resp = http.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text[:2000]
            raise RuntimeError(f"TokenRouter HTTP {e.response.status_code}: {body}") from e
        except Exception as e:
            raise RuntimeError(f"TokenRouter API error: {e}") from e

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"TokenRouter вернул пустой ответ: {data}")

        msg = choices[0].get("message") or {}
        return [msg.get("content") or ""]

    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)


# ============================================================
# DSPY: СИГНАТУРА И CHAIN-OF-THOUGHT
# ============================================================

class RewriteCodeTask(Signature):
    """
    Точный переписыватель Python-кода Telegram-бота.

    Стратегия:
    1. Проанализируй инструкцию и текущий код.
    2. Определи, какие части нужно изменить, добавить или удалить.
    3. Сохрани ВСЕ остальные части кода без изменений.
    4. Не удаляй импорты, если они не противоречат инструкции.
    5. Не выдумывай новые функции, если пользователь о них не просил.
    6. Возвращай ПОЛНЫЙ файл, готовый к запуску.
    7. Не оборачивай ответ в ```markdown.
    8. Значения секретов оставь как REDACTED — их не нужно трогать.
    """

    instruction = InputField(desc="Что именно нужно изменить в коде")
    current_code = InputField(desc="Полный текущий код Python-файла (с маскированными секретами)")
    updated_code = OutputField(desc="Полный обновлённый Python-код БЕЗ markdown-обёрток")


rewrite_module = None


def init_dspy() -> bool:
    """Инициализирует DSPy и ChainOfThought-модуль."""
    global rewrite_module

    if not TOKENROUTER_API_KEY:
        logger.warning("TOKENROUTER_API_KEY не задан — DSPy не активен")
        return False

    try:
        lm = TokenRouterLM(
            model=MODEL_NAME,
            api_key=TOKENROUTER_API_KEY,
            temperature=0.1,
            max_tokens=8000,
        )
        dspy.configure(lm=lm)

        rewrite_module = dspy.ChainOfThought(RewriteCodeTask)

        logger.info("✅ DSPy инициализирован (model=%s)", MODEL_NAME)
        return True
    except Exception:
        logger.exception("DSPy init error")
        rewrite_module = None
        return False


def _rewrite_sync(instruction: str, current_code: str) -> str:
    if not rewrite_module:
        raise RuntimeError("DSPy не инициализирован")
    result = rewrite_module(instruction=instruction, current_code=current_code)
    updated = getattr(result, "updated_code", None)
    if updated is None and isinstance(result, dict):
        updated = result.get("updated_code")
    if updated is None:
        updated = str(result)
    return str(updated).strip()


async def rewrite_code_async(instruction: str, current_code: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _rewrite_sync, instruction, current_code)


# ============================================================
# TELEGRAM: ХЕНДЛЕРЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Привет! Я работаю на модели {MODEL_NAME} через TokenRouter.\n\n"
        "Команды:\n"
        "/models — список доступных моделей\n"
        "/rewrite <инструкция> — переписать мой код через DSPy\n"
        "/set_dspy <версия> — обновить версию dspy-ai в requirements\n\n"
        "Просто напиши сообщение — отвечу!"
    )


async def models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все доступные Qwen-модели."""
    await update.message.chat.send_action("typing")
    try:
        resp = await client.models.list()
        qwen_models = sorted([m.id for m in resp.data if "qwen" in m.id.lower()])

        if not qwen_models:
            await update.message.reply_text("Модели Qwen не найдены.")
            return

        text = "📋 *Доступные Qwen модели:*\n\n" + "\n".join(
            f"• `{m}`" for m in qwen_models
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка получения моделей: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def rewrite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переписать bot.py через DSPy и закоммитить в GitHub."""
    if not repo:
        await update.message.reply_text("⚠️ GitHub не подключён.")
        return

    if not rewrite_module:
        await update.message.reply_text("⚠️ DSPy не инициализирован.")
        return

    instruction = " ".join(context.args).strip() if context.args else ""
    if not instruction:
        await update.message.reply_text(
            "Использование:\n"
            "/rewrite измени SYSTEM_PROMPT на более формальный\n"
            "/rewrite добавь команду /help"
        )
        return

    await update.message.chat.send_action("typing")
    msg = await update.message.reply_text("🧠 DSPy анализирует и переписывает код...")

    try:
        old_code = await asyncio.to_thread(read_repo_file, BOT_FILE)
        masked_old = mask_secrets(old_code)

        new_code = await rewrite_code_async(instruction, masked_old)
        new_code = strip_code_fences(new_code)

        if not new_code:
            await msg.edit_text("⚠️ DSPy вернул пустой код.")
            return

        if new_code.strip() == masked_old.strip():
            await msg.edit_text("Код не изменился.")
            return

        try:
            validate_python_code(new_code)
        except SyntaxError as e:
            await msg.edit_text(f"❌ Синтаксическая ошибка:\n{e}")
            return

        if contains_forbidden_code(new_code):
            await msg.edit_text(
                "❌ В коде найдены опасные конструкции "
                "(eval/exec/os.system/subprocess). Отмена."
            )
            return

        commit_message = f"🧠 DSPy rewrite: {instruction[:80]}"
        await asyncio.to_thread(commit_repo_file, BOT_FILE, new_code, commit_message)

        await msg.edit_text(
            f"✅ Код обновлён на GitHub через DSPy.\n\n"
            f"📝 `{instruction}`\n"
            f"💾 Коммит создан. Бот перезапустится после деплоя.",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Rewrite error: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка:\n{str(e)[:500]}")


async def set_dspy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновить версию dspy-ai в requirements.txt."""
    if not repo:
        await update.message.reply_text("⚠️ GitHub не подключён.")
        return

    if not context.args:
        await update.message.reply_text("Использование:\n/set_dspy 3.3.0b1")
        return

    version = context.args[0].strip()
    await update.message.chat.send_action("typing")

    try:
        old_reqs = await asyncio.to_thread(read_repo_file, REQUIREMENTS_FILE)
        new_reqs = re.sub(
            r"^dspy-ai==.*$",
            f"dspy-ai=={version}",
            old_reqs,
            flags=re.MULTILINE,
        )

        if old_reqs == new_reqs:
            await update.message.reply_text(
                "⚠️ Не нашёл строку `dspy-ai==...` в requirements.txt"
            )
            return

        commit_message = f"⬆️ dspy-ai=={version} from Telegram"
        await asyncio.to_thread(commit_repo_file, REQUIREMENTS_FILE, new_reqs, commit_message)

        await update.message.reply_text(
            f"✅ requirements.txt обновлён:\ndspy-ai=={version}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"set_dspy error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:500]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обычный чат с моделью через TokenRouter."""
    user_text = update.message.text.strip()
    if not user_text:
        return

    await update.message.chat.send_action("typing")

    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )

        reply = response.choices[0].message.content
        if not reply:
            reply = "⚠️ Модель вернула пустой ответ."

        max_len = 4000
        while reply:
            chunk = reply[:max_len]
            reply = reply[max_len:]
            await update.message.reply_text(chunk)

    except Exception as e:
        logger.error(f"Ошибка API: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка:\n{e}")


# ============================================================
# MAIN
# ============================================================

def main():
    logger.info("Инициализация DSPy...")
    dspy_ok = init_dspy()
    logger.info("DSPy: %s", "✅" if dspy_ok else "❌")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("models", models))
    app.add_handler(CommandHandler("rewrite", rewrite))
    app.add_handler(CommandHandler("set_dspy", set_dspy))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()