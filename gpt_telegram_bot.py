import os
import asyncio
from datetime import datetime

from fastapi import FastAPI, Request
import uvicorn

from telegram import Update, Bot
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from openai import OpenAI
from tabulate import tabulate
from dotenv import load_dotenv

# ================= LOAD ENV =================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not WEBHOOK_URL:
    raise RuntimeError("❌ ENV o‘zgaruvchilar yetarli emas")

bot = Bot(token=TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# ================= FASTAPI =================
app = FastAPI()
telegram_app: Application | None = None

# ================= MEMORY =================
user_memory = {}
logs = []

# ================= STICKER & GIF =================
STICKER_OK = "CAACAgIAAxkBAAEF0GZlWwABjv0AAe8k7t7Jm0X5AAEAAcYAAj8uAAFXg0wYkzYwLh8E"
STICKER_LAUGH = "CAACAgIAAxkBAAEF0GhlWwABk4mAAQAB3hZAAcWcAAEAAcYAAk0AAyJ6y1Zs8hE"

GIF_LAUGH = "https://media.giphy.com/media/10JhviFuU2gWD6/giphy.gif"

# ================= LOGGER =================
def log_event(user, uid, action, text):
    logs.append([
        datetime.now().strftime("%H:%M:%S"),
        user,
        uid,
        action,
        text
    ])

    os.system("clear")
    print(tabulate(
        logs[-15:],
        headers=["Time", "User", "ID", "Action", "Message"],
        tablefmt="grid",
        maxcolwidths=[8, 12, 10, 12, 80]
    ))

# ================= HELPERS =================
def is_identity_q(text: str) -> bool:
    return "kim yaratgan" in text.lower() or "qachon yaratilgan" in text.lower()

def identity_answer() -> str:
    return (
        "🤖 *Men SvRvS_3003 tomonidan yaratilgan AI yordamchiman.*\n\n"
        "• Birinchi marta: *2025-yilda ishga tushirilganman*\n"
        "• Hozirgacha: *doimiy takomillashtirib kelinmoqda*\n"
        "• Telegram uchun maxsus sozlanganman\n"
    )

def is_fun(text: str) -> bool:
    return any(k in text.lower() for k in ["haha", "😂", "kul", "qiziq"])

def is_sticker_request(text: str) -> bool:
    return "stiker" in text.lower()

def safe_markdown(text: str) -> str:
    for ch in ["_", "*", "`"]:
        text = text.replace(ch, f"\\{ch}")
    return text

# ================= GPT =================
async def gpt_reply(uid: int):
    history = user_memory.get(uid, [])
    messages = [
        {
            "role": "system",
            "content": (
                "Sen SvRvS_3003 tomonidan yaratilgan AI botsan. "
                "2025-yilda ishga tushirilgansan. "
                "Hech qachon OpenAI deb aytma."
            )
        }
    ] + history[-20:]

    try:
        resp = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages
            )
        )
        reply = resp.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        user_memory[uid] = history
        return reply

    except Exception as e:
        return "⚠️ Hozircha AI band, birozdan keyin urinib ko‘ring."

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *SR AI Bot*\n\n"
        "Men quyidagilarni qila olaman:\n"
        "• Oddiy suhbat\n"
        "• Bash / kodni to‘g‘ri formatda chiqarish\n"
        "• Jadval, link, Markdown\n"
        "• Kulgi uchun GIF va stiker\n"
        "• Suhbatni eslab qolish\n\n"
        "_2025-yildan beri rivojlantirilmoqda_",
        parse_mode="Markdown"
    )

# ================= TEXT =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    uid = update.effective_user.id
    text = update.message.text

    log_event(user, uid, "TEXT", text)

    if is_identity_q(text):
        await update.message.reply_text(identity_answer(), parse_mode="Markdown")
        return

    if is_sticker_request(text):
        await update.message.reply_sticker(STICKER_OK)
        return

    if is_fun(text):
        await update.message.reply_animation(GIF_LAUGH)
        await update.message.reply_sticker(STICKER_LAUGH)
        return

    user_memory.setdefault(uid, []).append({"role": "user", "content": text})
    reply = await gpt_reply(uid)

    await update.message.reply_text(
        safe_markdown(reply),
        parse_mode="Markdown"
    )

# ================= STARTUP =================
@app.on_event("startup")
async def startup():
    global telegram_app

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

    print("✅ Telegram webhook o‘rnatildi")

# ================= WEBHOOK =================
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app.get("/")
def health():
    return {"status": "ok"}

# ================= MAIN =================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
