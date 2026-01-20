import os
import asyncio
import tempfile
import time
from datetime import datetime
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)
from tabulate import tabulate

# ================= CONFIG =================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
You are a multimodal AI assistant.
Answer clearly in Uzbek unless user asks otherwise.
"""

# ================= MEMORY =================
user_memory = {}
logs = []  # terminal jadvali uchun

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
        logs[-15:],  # oxirgi 15 ta
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

    if any(k in lower for k in ["rasm", "chiz", "logo", "image"]):
        log_event(user, user_id, "IMAGE REQUEST", "RUNNING", text)

        try:
            image_url = await generate_image(text)
            await update.message.reply_photo(image_url)
            log_event(user, user_id, "IMAGE REQUEST", "OK", "image sent")
        except Exception as e:
            log_event(user, user_id, "IMAGE REQUEST", "ERROR", str(e))
            await update.message.reply_text(
                "⚠️ Rasm yaratish hozircha mavjud emas."
            )
        return

    log_event(user, user_id, "TEXT MESSAGE", "OK", text)

    history = user_memory.get(user_id, [])
    history.append({"role": "user", "content": text})
    user_memory[user_id] = history

    reply = await get_gpt_reply(user_id)
    await update.message.reply_text(reply)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username or "unknown"
    user_id = update.effective_user.id

    log_event(user, user_id, "VOICE MESSAGE", "RUNNING", "downloading")

    voice = update.message.voice
    file = await voice.get_file()

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        await file.download_to_drive(f.name)
        text = await speech_to_text(f.name)

    log_event(user, user_id, "VOICE → TEXT", "OK", f"{len(text.split())} words")

    history = user_memory.get(user_id, [])
    history.append({"role": "user", "content": text})
    user_memory[user_id] = history

    reply = await get_gpt_reply(user_id)
    await update.message.reply_text(reply)

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    os.system("clear")
    print("🤖 Telegram AI Bot ishga tushdi...\n")
    app.run_polling()

if __name__ == "__main__":
    main()

