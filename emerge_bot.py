from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatAction
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, CallbackQueryHandler, Filters
from queue import Queue
import logging, os, threading

# === CONFIG ===
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")
PORT = int(os.getenv("PORT", "5050"))
OWNER_ID = int(os.getenv("OWNER_ID", "7075667441"))

# === APP & BOT ===
app = Flask(__name__)
bot = Bot(TOKEN)
update_queue = Queue()
dp = Dispatcher(bot, update_queue, workers=4, use_context=True)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# === MENU ===
MAIN_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎟 Tickets", callback_data="tickets"),
     InlineKeyboardButton("🛍 Merch", callback_data="merch")],
    [InlineKeyboardButton("🎮 Emerge Games", callback_data="games"),
     InlineKeyboardButton("👗 Designers", callback_data="designers")],
    [InlineKeyboardButton("🎵 Music", callback_data="music"),
     InlineKeyboardButton("💡 Ideas / Feedback", callback_data="ideas")],
    [InlineKeyboardButton("🎁 Promotions", callback_data="promotions"),
     InlineKeyboardButton("⭐ Special Order", callback_data="special")],
    [InlineKeyboardButton("📩 Submit Talent", callback_data="submit"),
     InlineKeyboardButton("📦 Order Status", callback_data="status")],
    [InlineKeyboardButton("📖 FAQ", callback_data="faq"),
     InlineKeyboardButton("📞 Support", callback_data="support")],
    [InlineKeyboardButton("💳 Tip / Donate", callback_data="tip"),
     InlineKeyboardButton("⚖️ Terms", callback_data="terms")]
])

# === DM TEXTS ===
DM_TEXTS = {
    "tickets": "🎟️ Great choice! Here’s how to secure tickets.\n\nAccepted payment methods: Telebirr, M-Pesa, Card, PayPal, Cash.",
    "merch": "🛍️ Merch: browse our exclusive items and limited drops.\n\nAccepted payment methods: Telebirr, M-Pesa, Card, PayPal, Cash.",
    "games": "🎮 Join Emerge Games: we’ll DM brackets, rules, and prize details. Reply if you want to captain a team.",
    "designers": "👗 Discover designers. We’ll DM their lookbooks, sizes, and availability.",
    "music": "🎵 Set times, headliners, and afters. We’ll DM RSVP links and alerts.",
    "ideas": "💡 Drop your idea here as a reply. We’ll tag, triage, and follow up.",
    "promotions": "🎁 Current promos & codes—watch this DM for time-limited drops.",
    "special": "⭐ Special Order: tell us what you need, and we’ll customize it for you.\n\nAccepted payment methods: Telebirr, M-Pesa, Card, PayPal, Cash.",
    "submit": "📩 Submit talent: send EPK/links/reel here. We’ll review & reply.",
    "status": "📦 Send your order # here and we’ll fetch live status.",
    "faq": "📖 FAQ headed your way. Ask follow-ups in this DM.",
    "support": "📞 Support: describe the issue here; I’ll triage to the right team.\n\nAccepted payment methods: Telebirr, M-Pesa, Card, PayPal, Cash.",
    "tip": "💳 Thanks for supporting the community! Accepted: Telebirr, M-Pesa, Card, PayPal, Cash.",
    "terms": "⚖️ We’ll DM the latest terms & policies for your records."
}

# === COMMANDS ===
def start(update, context):
    chat_id = update.effective_chat.id
    context.bot.send_message(chat_id=chat_id, text="Welcome to Emerge! Tap /menu to get started.")

def menu(update, context):
    chat_id = update.effective_chat.id
    context.bot.send_message(chat_id=chat_id, text="📌 Main Menu — choose an option:", reply_markup=MAIN_KB)

def admin(update, context):
    if update.effective_user.id != OWNER_ID:
        update.message.reply_text("⛔ Unauthorized")
        return
    update.message.reply_text("🔑 Admin panel placeholder. (Designer uploads, shops, ticket reports will live here.)")

# === CALLBACK HANDLER ===
def on_callback(update, context):
    q = getattr(update, "callback_query", None)
    if not q: return
    data = getattr(q, "data", None)
    user_id = getattr(q.from_user, "id", None)

    try: q.answer()
    except Exception as e: logging.warning(f"q.answer failed: {e}")

    # group ack
    try:
        if q.message and q.message.chat and q.message.message_id:
            context.bot.send_message(chat_id=q.message.chat.id,
                                     reply_to_message_id=q.message.message_id,
                                     text="✅ I’ve sent you a DM with next steps. Check your inbox! ✉️")
    except Exception as e: logging.warning(f"group ack failed: {e}")

    # DM
    msg = DM_TEXTS.get(data, "I’ll DM you details for your selection.")
    try:
        if user_id:
            context.bot.send_message(chat_id=user_id, text=msg)
    except Exception as e: logging.error(f"DM send failed: {e}")

# === TEXT HANDLER (keywords in group) ===
KEYWORDS = {
    "ticket": "tickets",
    "merch": "merch",
    "support": "support",
    "special": "special",
    "donate": "tip",
}
def handle_text(update, context):
    msg = update.message
    if not msg or not msg.text: return
    text = msg.text.lower()
    if msg.chat.type in ("group","supergroup"):
        for kw, route in KEYWORDS.items():
            if kw in text:
                try:
                    context.bot.send_message(chat_id=msg.chat.id,
                        reply_to_message_id=msg.message_id,
                        text=f"✅ I’ll DM you about {kw}. Check your inbox! ✉️")
                    context.bot.send_message(chat_id=msg.from_user.id, text=DM_TEXTS[route])
                except Exception as e: logging.warning(f"keyword→DM failed: {e}")
                return

# === ROUTES ===
@app.route("/tg", methods=["POST"])
def tg_webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        dp.process_update(update)
    except Exception as e:
        logging.exception(f"update error: {e}")
    return "ok"

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok"

# === HANDLERS ===
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("menu", menu))
dp.add_handler(CommandHandler("admin", admin))
dp.add_handler(MessageHandler(Filters.regex(r"^/menu(@[A-Za-z0-9_]+)?$"), menu))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
dp.add_handler(CallbackQueryHandler(on_callback))

# === MAIN ===
if __name__ == "__main__":
    def run_polling():
        import time
        logging.info("🔁 Starting long polling (webhook can stay disabled)")
        while True:
            try:
                bot.delete_webhook(drop_pending_updates=True)
                for update in bot.get_updates(offset=None, timeout=30):
                    dp.process_update(update)
            except Exception as e:
                logging.warning(f"polling error: {e}")
                time.sleep(3)

    threading.Thread(target=run_polling, daemon=True).start()
    print("🚀 Emerge Assistant Bot is running…")
    app.run(host="0.0.0.0", port=PORT)
