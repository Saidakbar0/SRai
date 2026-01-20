import os
import asyncio
import tempfile
from datetime import datetime

from fastapi import FastAPI, Request
import uvicorn

from telegram import Update, Bot
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

from openai import OpenAI
from tabulate import tabulate

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://xxx.onrender.com

bot = Bot(token=TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
You are a multimodal AI assistant.

Rules:
- Answer in Uzbek unless user asks otherwise
- Use Markdown formatting
- Use code blocks for bash/code
- Use tables when helpful
- Use links when relevant
- If user asks for bash, respond with ```bash
"""

# ================= MEMORY =================
user_memory = {}
logs = []

# ================= MARKDOWN ESCAPE =================
def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    for ch in escape_chars:
        text = text.replace(ch, f"\\{ch}")
    return text

# ================= LOGGER =================
def log_event(user, user_id, action, status, detail):
    logs.append([
        datetime.now().strftime("%H:%M:%S"),
        user,
        user_id,
        action,
        status,
        detail[:30]
    ])

    os.system("clear")
    print("🤖 TELEGRAM AI BOT — REAL TIME MONITOR\n")
    print(tabulate(
        logs[-15:],
        headers=["Time", "User", "User ID", "Action", "Status", "Detail"],
        tablefmt="grid"
    ))

# ================= IMAGE =================
async def generate_image(prompt):
    return client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024"
    ).data[0].url

# ================= SPEECH TO TEXT =================
async def speech_to_text(path):
    with open(path, "rb") as f:
        return client.audio.transcriptions.create(
            file=f,
            model="gpt-4o-transcribe"
        ).text

# ================= GPT =================
async def get_gpt_reply(user_id):
    history = user_memory.get(user_id, [])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-20:]

    response = await asyncio.to_thread(
        lambda: client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )
    )

    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    user_memory[user_id] = history
    return reply

# ================= HANDLERS =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username or "unknown"
    user_id = update.effective_user.id
    text = update.message.text
    lower = text.lower()

    # ===== STICKER =====
    if "stiker" in lower:
        await update.message.reply_sticker(
            sticker="CAACAgIAAxkBAAEKQdJl1"
        )
        log_event(user, user_id, "STICKER", "OK", "sent")
        return

    # ===== IMAGE =====
    if any(k in lower for k in ["rasm", "chiz", "logo", "image"]):
        log_event(user, user_id, "IMAGE", "RUNNING", text)
        try:
            image_url = await generate_image(text)
            await update.message.reply_photo(image_url)
            log_event(user, user_id, "IMAGE", "OK", "sent")
        except Exception as e:
            log_event(user, user_id, "IMAGE", "ERROR", str(e))
            await update.message.reply_text("⚠️ Rasm yaratib bo‘lmadi.")
        return

    log_event(user, user_id, "TEXT", "OK", text)

    history = user_memory.get(user_id, [])
    history.append({"role": "user", "content": text})
    user_memory[user_id] = history

    reply = await get_gpt_reply(user_id)

    await update.message.reply_text(
        escape_markdown(reply),
        parse_mode="MarkdownV2",
        disable_web_page_preview=False
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username or "unknown"
    user_id = update.effective_user.id

    log_event(user, user_id, "VOICE", "RUNNING", "download")

    voice = update.message.voice
    file = await voice.get_file()

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        await file.download_to_drive(f.name)
        text = await speech_to_text(f.name)

    log_event(user, user_id, "VOICE→TEXT", "OK", text)

    history = user_memory.get(user_id, [])
    history.append({"role": "user", "content": text})
    user_memory[user_id] = history

    reply = await get_gpt_reply(user_id)

    await update.message.reply_text(
        escape_markdown(reply),
        parse_mode="MarkdownV2"
    )

# ================= FASTAPI =================
app = FastAPI()
telegram_app: Application | None = None

@app.on_event("startup")
async def startup():
    global telegram_app

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

    telegram_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    telegram_app.add_handler(
        MessageHandler(filters.VOICE, handle_voice)
    )

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

    print("🤖 Telegram Webhook o‘rnatildi va bot tayyor")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app.get("/")
def health():
    return {"status": "ok", "mode": "webhook"}

# ================= MAIN =================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
