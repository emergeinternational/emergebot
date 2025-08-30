
# emerge_bot.py
# Emerge Assistant – PTB v13.x + Flask(wsgi) + long-polling
# Stable, DM-first UX, deep-link fallbacks, designer onboarding, admin panel.
# Env:
#   BOT_TOKEN, PORT=5050, ADMIN_USER_IDS="7075667441"
# Optional URLs:
#   TICKETS_URL, SHOP_URL, MUSIC_URL, IDEAS_URL, PROMOS_URL, SPECIAL_URL,
#   SUBMIT_URL, ORDER_URL, FAQ_URL, SUPPORT_URL, DONATE_URL, TERMS_URL

import os, logging, threading, time
from typing import Dict, Any, Optional, List

from flask import Flask, request
from telegram import (
    Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, TelegramError, ParseMode
)
from telegram.ext import (
    Dispatcher, CommandHandler, MessageHandler, CallbackQueryHandler, Filters
)

# -------------------------
# Config
# -------------------------
TOKEN = (os.environ.get("BOT_TOKEN") or "").strip()
if not TOKEN:
    raise SystemExit("BOT_TOKEN missing")

PORT = int(os.environ.get("PORT", "5050"))
ADMIN_IDS = {
    int(x) for x in (os.environ.get("ADMIN_USER_IDS", "") or "")
    .replace(" ", "").split(",") if x
}

URLS = {
    "tickets":  os.environ.get("TICKETS_URL",  "https://emergeglobally.com/tickets"),
    "shop":     os.environ.get("SHOP_URL",     "https://emergeglobally.com/shop"),
    "music":    os.environ.get("MUSIC_URL",    "https://emergeglobally.com/music"),
    "ideas":    os.environ.get("IDEAS_URL",    "https://emergeglobally.com/ideas"),
    "promos":   os.environ.get("PROMOS_URL",   "https://emergeglobally.com/promos"),
    "special":  os.environ.get("SPECIAL_URL",  "https://emergeglobally.com/special-order"),
    "submit":   os.environ.get("SUBMIT_URL",   "https://emergeglobally.com/casting"),
    "order":    os.environ.get("ORDER_URL",    "https://emergeglobally.com/order"),
    "faq":      os.environ.get("FAQ_URL",      "https://emergeglobally.com/faq"),
    "support":  os.environ.get("SUPPORT_URL",  "https://emergeglobally.com/support"),
    "donate":   os.environ.get("DONATE_URL",   "https://emergeglobally.com/donate"),
    "terms":    os.environ.get("TERMS_URL",    "https://emergeglobally.com/terms"),
}

# Keywords shown on the main inline menu
KEY_ROUTES = {
    "tickets":   "🎟 Tickets",
    "shop":      "🛒 Shop",
    "games":     "🎮 Emerge Games",
    "designers": "👗 Designers",
    "music":     "🎵 Music",
    "ideas":     "💡 Ideas / Feedback",
    "promotions":"🎁 Promotions",
    "special":   "⭐ Special Order",
    "submit":    "✉️ Submit Talent",
    "order":     "📦 Order Status",
    "faq":       "📖 FAQ",
    "support":   "📞 Support",
    "donate":    "💸 Tip / Donate",
    "terms":     "⚖️ Terms",
}

# Designer brand list (public “Designers” browse)
DESIGNER_BRANDS = [
    "NEDF", "SOAM DESIGN", "TIGI’S DESIGN", "HILORE", "BENAQFKOT DESIGN"
]

# In-memory store for Designer Portal onboarding (simple, survives per-process)
designer_submissions: Dict[int, Dict[str, Any]] = {}

# Flask & Telegram bot
app = Flask(__name__)
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot, update_queue=None, workers=4, use_context=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -------------------------
# Helpers
# -------------------------
def main_menu_markup() -> InlineKeyboardMarkup:
    rows = [
        ["tickets","shop"],
        ["games","designers"],
        ["music","ideas"],
        ["promotions","special"],
        ["submit","order"],
        ["faq","support"],
        ["donate","terms"]
    ]
    kb = [[InlineKeyboardButton(KEY_ROUTES[k], callback_data=k) for k in row] for row in rows]
    return InlineKeyboardMarkup(kb)

def dm_or_deeplink(context, user_id: int, text: str, route_hint: str,
                   group_chat_id: Optional[int] = None,
                   reply_to_message_id: Optional[int] = None) -> bool:
    """
    Try to DM the user. If the user hasn't started the bot:
    post a deep-link button back in the group (if provided).
    """
    try:
        context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN)
        return True
    except TelegramError:
        if group_chat_id:
            try:
                deep = f"https://t.me/{context.bot.username}?start={route_hint}"
                btn = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔒 Open chat & Press Start", url=deep)]]
                )
                context.bot.send_message(
                    chat_id=group_chat_id,
                    text="For your privacy, continue in DM.\nTap below and press **Start**.",
                    reply_to_message_id=reply_to_message_id,
                    reply_markup=btn,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass
        return False

def auto_delete(context, chat_id: int, message_id: int, delay: int = 15):
    """Silently delete a message after `delay` seconds to keep groups tidy."""
    def _delete():
        time.sleep(delay)
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
    threading.Thread(target=_delete, daemon=True).start()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS if ADMIN_IDS else False

# -------------------------
# Rich replies per route (DM-first)
# -------------------------
def dm_block_for(route: str) -> str:
    if route == "tickets":
        return (
            f"🎟 **Tickets — American Invasion**\n"
            f"• View availability & buy → {URLS['tickets']}\n"
            f"• Accepted payments: **Telebirr, M-Pesa, Card, PayPal, Cash, Bank Transfer**\n"
            f"• Refund/transfer: subject to event policy.\n"
            f"_If you haven’t started a private chat yet, tap the button and press Start._"
        )
    if route == "shop":
        return (
            f"🛒 **Shop — Exclusive drops**\n"
            f"Browse looks & sizes. Reply with your picks and size.\n"
            f"• Shop now → {URLS['shop']}\n"
            f"• Payments: Telebirr, M-Pesa, Card, PayPal, Cash, Bank Transfer\n"
            f"• Delivery options may vary by item."
        )
    if route == "designers":
        # send list; they can reply with a brand name (we just confirm for now)
        brands = "\n".join([f"• {b}" for b in DESIGNER_BRANDS])
        return (
            "👗 **Designers — Browse brands**\n"
            f"{brands}\n\n"
            "Reply with the designer you want to view, and I’ll send their current looks."
        )
    if route == "support":
        return (
            f"📞 **Support**\n"
            f"Reply with your issue (order # if you have it), or use the form:\n"
            f"{URLS['support']}\n"
            f"_We reply within 24h._"
        )
    if route == "faq":
        return (
            "📖 **FAQ — Quick Answers**\n"
            "1) Tickets: check availability & rules on the ticket page.\n"
            "2) Delivery: varies by item/city; ask support if unsure.\n"
            "3) Returns: apparel returns subject to policy.\n"
            "4) Sizing: DM your measurements; we’ll help.\n"
            "5) Support: reply here or use the form.\n"
            f"Full FAQ → {URLS['faq']}"
        )
    if route == "terms":
        return (
            f"⚖️ **Terms & Policies**\n"
            f"Read our terms, privacy, and refund policies.\n"
            f"→ {URLS['terms']}\n"
            "We respect your privacy; your info is used to fulfill orders and improve your experience."
        )
    if route == "ideas":
        return f"💡 Share feedback & ideas → {URLS['ideas']}"
    if route == "promotions":
        return f"🎁 Current promos → {URLS['promos']}"
    if route == "special":
        return (
            "⭐ **Special Order**\n"
            "Reply with a reference photo, size, budget, and timeline.\n"
            "We’ll confirm details within 24–48h."
        )
    if route == "submit":
        return (
            f"✉️ **Submit Talent**\n"
            "Tell us your role (model/artist/DJ/designer), and include:\n"
            "• Models: 3 pro images\n"
            "• Artists/DJs: link to reel/EPK\n"
            "• Designers: lookbook or 3 product shots\n"
            f"Direct link → {URLS['submit']}\n"
            "_We review weekly and reach out if it’s a fit._"
        )
    if route == "order":
        return f"📦 **Order Status** — Track here: {URLS['order']}"
    if route == "music":
        return f"🎵 **Music** — Listen here: {URLS['music']}"
    if route == "donate":
        return f"💸 **Tip / Donate** — {URLS['donate']}"
    if route == "games":
        return "🎮 **Emerge Games** — Coming soon. Stay tuned!"
    return "ℹ️ More info coming soon."

# -------------------------
# Handlers
# -------------------------
def start(update, context):
    """Supports deep-link start like: /start RSVP-EVT2025"""
    chat = update.effective_chat
    user = update.effective_user
    args = (context.args or [])
    if args and args[0].upper().startswith("RSVP"):
        # RSVP connection confirmation
        msg = (
            f"🎉 You’re connected, {user.first_name}!\n"
            "You’ll receive priority updates for American Invasion.\n"
            "_This isn’t your ticket — watch DM for confirmations._"
        )
        context.bot.send_message(chat_id=chat.id, text=msg, parse_mode=ParseMode.MARKDOWN)
    context.bot.send_message(chat_id=chat.id, text="📌 Main Menu — choose an option:", reply_markup=main_menu_markup())

def menu(update, context):
    chat_id = update.effective_chat.id
    context.bot.send_message(chat_id=chat_id, text="📌 Main Menu — choose an option:", reply_markup=main_menu_markup())

def greet_new_member(update, context):
    chat = update.effective_chat
    for u in (update.message.new_chat_members or []):
        if u.is_bot: continue
        text = (
            f"🎉 Welcome, {u.first_name}!\n"
            "This is the official Emerge community. Don’t miss **American Invasion Weekend** 🇺🇸🔥\n"
            "Type /menu to see tickets, shop, designers, music and more."
        )
        context.bot.send_message(chat_id=chat.id, text=text, parse_mode=ParseMode.MARKDOWN)

def on_text(update, context):
    msg = update.message
    chat = update.effective_chat
    txt  = (msg.text or "").lower().strip()

    if chat.type in ("group","supergroup"):
        matched = None
        for key in KEY_ROUTES.keys():
            if key in txt:
                matched = key
                break
        if matched:
            # brief note in group + auto-delete
            try:
                ack = context.bot.send_message(
                    chat_id=chat.id,
                    text=f"✅ I’ll DM you info about {KEY_ROUTES[matched]}."
                )
                auto_delete(context, chat_id=chat.id, message_id=ack.message_id, delay=15)
            except Exception:
                pass
            # DM or deep-link
            block = dm_block_for(matched)
            dm_or_deeplink(
                context,
                user_id=msg.from_user.id,
                text=block,
                route_hint=matched,
                group_chat_id=chat.id,
                reply_to_message_id=msg.message_id
            )
            return

    # private default echo
    if chat.type == "private":
        context.bot.send_message(chat_id=chat.id, text="Got it! Type /menu to browse options.")

def on_callback(update, context):
    q = update.callback_query
    data = (q.data or "").lower()
    user = update.effective_user
    chat = update.effective_chat
    q.answer()
    # DM-first for all menu buttons
    text = dm_block_for(data)
    if chat.type in ("group","supergroup"):
        # short ack + auto-delete
        try:
            ack = context.bot.send_message(chat_id=chat.id, text="📩 I’ll send you the details in DM.")
            auto_delete(context, chat_id=chat.id, message_id=ack.message_id, delay=12)
        except Exception:
            pass
        dm_or_deeplink(
            context,
            user_id=user.id,
            text=text,
            route_hint=data,
            group_chat_id=chat.id,
            reply_to_message_id=q.message.message_id
        )
    else:
        context.bot.send_message(chat_id=chat.id, text=text, parse_mode=ParseMode.MARKDOWN)

# -------------------------
# Designer Portal (command only, DM)
# -------------------------
def cmd_designer_portal(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != "private":
        # push to DM
        dm_or_deeplink(context, user_id=user.id,
                       text="Please continue in DM to set up your brand.",
                       route_hint="designer_portal",
                       group_chat_id=chat.id,
                       reply_to_message_id=getattr(update.message, "message_id", None))
        return
    # start/reset flow
    designer_submissions[user.id] = {"state":"brand_name"}
    hello = (
        f"👋 Hi {user.first_name}!\n\n"
        "👗 **Designer Portal — let’s get you live.**\n"
        "I’ll collect a few details to open your store.\n\n"
        "1) Reply with your **brand name**\n"
        "2) Send a **logo (.png, transparent if possible)**\n"
        "3) Send **1–3 product photos**\n"
        "4) Choose **shipping** (local delivery, pickup, worldwide)\n"
        "5) Choose **payout** (Telebirr / M-Pesa / bank / transfer)\n\n"
        "_Questions? Reply 'support' anytime._"
    )
    context.bot.send_message(chat_id=chat.id, text=hello, parse_mode=ParseMode.MARKDOWN)

def designer_portal_flow(update, context):
    """Processes inbound messages during designer onboarding in DM."""
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    uid = user.id
    if uid not in designer_submissions:
        return  # not in a flow

    entry = designer_submissions[uid]
    state = entry.get("state")

    txt = (update.message.text or "").strip() if update.message else ""
    photos = update.message.photo if update.message else None
    doc = update.message.document if update.message else None

    # support escape
    if txt.lower() == "support":
        context.bot.send_message(chat_id=uid, text=f"📞 Support → {URLS['support']}")
        return

    if state == "brand_name":
        if not txt:
            context.bot.send_message(chat_id=uid, text="Please send a text brand name.")
            return
        entry["brand"] = txt
        entry["state"] = "logo"
        context.bot.send_message(chat_id=uid, text="Got it. Now send your **logo (.png)**.", parse_mode=ParseMode.MARKDOWN)
        return

    if state == "logo":
        # accept photo or document
        file_id = None
        if photos:
            file_id = photos[-1].file_id
        elif doc and (doc.mime_type or "").startswith("image/"):
            file_id = doc.file_id
        if not file_id:
            context.bot.send_message(chat_id=uid, text="Please send a PNG logo (photo or file).")
            return
        entry["logo_file_id"] = file_id
        entry["state"] = "products"
        context.bot.send_message(chat_id=uid, text="✅ Logo received.\nSend **1–3 product photos**.", parse_mode=ParseMode.MARKDOWN)
        return

    if state == "products":
        # collect up to 3 images
        collected: List[str] = entry.get("product_file_ids", [])
        if photos:
            collected.append(photos[-1].file_id)
        elif doc and (doc.mime_type or "").startswith("image/"):
            collected.append(doc.file_id)
        else:
            context.bot.send_message(chat_id=uid, text="Please send product photos (image files).")
            return
        entry["product_file_ids"] = collected
        if len(collected) < 3:
            context.bot.send_message(chat_id=uid, text=f"Got it ({len(collected)}/3). Send more or type 'done' to continue.")
            return
        # move on
        entry["state"] = "shipping"
        context.bot.send_message(chat_id=uid, text="✅ Photos received.\nChoose shipping: local delivery, pickup, worldwide.")
        return

    if state == "products" and txt.lower() == "done":
        entry["state"] = "shipping"
        context.bot.send_message(chat_id=uid, text="✅ Photos received.\nChoose shipping: local delivery, pickup, worldwide.")
        return

    if state == "shipping":
        if not txt:
            context.bot.send_message(chat_id=uid, text="Type one: local delivery / pickup / worldwide.")
            return
        entry["shipping"] = txt
        entry["state"] = "payout"
        context.bot.send_message(chat_id=uid, text="Choose payout: Telebirr / M-Pesa / bank / transfer.")
        return

    if state == "payout":
        if not txt:
            context.bot.send_message(chat_id=uid, text="Type one: Telebirr / M-Pesa / bank / transfer.")
            return
        entry["payout"] = txt
        entry["state"] = "submitted"

        # notify admin(s)
        summary = (
            "🆕 **Designer Submission**\n"
            f"User: {user.first_name} (id {uid})\n"
            f"Brand: {entry.get('brand')}\n"
            f"Shipping: {entry.get('shipping')}\n"
            f"Payout: {entry.get('payout')}\n"
            f"Products: {len(entry.get('product_file_ids',[]))}\n"
        )
        for aid in ADMIN_IDS:
            try:
                context.bot.send_message(chat_id=aid, text=summary, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass

        # confirmation to designer
        context.bot.send_message(
            chat_id=uid,
            text=(
                "✅ Thanks! Your brand is submitted for review.\n"
                "We’ll enable your store and DM you with access. You can manage items right here."
            )
        )
        return

# -------------------------
# Admin (restricted)
# -------------------------
def cmd_admin(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != "private":
        context.bot.send_message(chat_id=chat.id, text="Open a private chat and try /admin again.")
        return
    if not is_admin(user.id):
        context.bot.send_message(chat_id=chat.id, text="Not authorized.")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("RSVPs (soon)", callback_data="admin:rsvps")],
        [InlineKeyboardButton("Designer Submissions", callback_data="admin:designers")],
        [InlineKeyboardButton("Payments Help", callback_data="admin:payments")]
    ])
    context.bot.send_message(
        chat_id=chat.id,
        text="🛠 **Admin Panel**\nChoose an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )

def on_admin_callback(update, context):
    q = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    q.answer()

    if chat.type != "private" or not is_admin(user.id):
        return

    data = q.data or ""
    if data == "admin:rsvps":
        context.bot.send_message(chat_id=chat.id, text="RSVP list coming soon (Supabase hook).")
    elif data == "admin:designers":
        # dump current in-memory submissions
        if not designer_submissions:
            context.bot.send_message(chat_id=chat.id, text="No designer submissions yet.")
        else:
            lines = []
            for uid, ent in designer_submissions.items():
                if ent.get("state") == "submitted":
                    lines.append(f"• {ent.get('brand')} (uid {uid}) — {len(ent.get('product_file_ids',[]))} photos")
            if lines:
                context.bot.send_message(chat_id=chat.id, text="Submitted:\n" + "\n".join(lines))
            else:
                context.bot.send_message(chat_id=chat.id, text="No completed submissions yet.")
    elif data == "admin:payments":
        context.bot.send_message(
            chat_id=chat.id,
            text=(
                "Payment options supported across the bot:\n"
                "• Telebirr, M-Pesa, Card, PayPal, Cash (in-person), Bank Transfer.\n"
                "When a user chooses, DM them step-by-step instructions."
            )
        )

# -------------------------
# Routes & Registration
# -------------------------
def _register_handlers(d):
    if getattr(d, "emg_handlers_registered", False):
        return
    d.add_handler(CommandHandler("start", start))
    d.add_handler(CommandHandler("menu",  menu))
    d.add_handler(CommandHandler("admin", cmd_admin))
    d.add_handler(CommandHandler("designer_portal", cmd_designer_portal))
    d.add_handler(CallbackQueryHandler(on_admin_callback, pattern=r"^admin:"))
    d.add_handler(CallbackQueryHandler(on_callback, pattern=r"^(?!admin:).+"))
    d.add_handler(MessageHandler(Filters.status_update.new_chat_members, greet_new_member))
    d.add_handler(MessageHandler(Filters.private & (Filters.text | Filters.photo | Filters.document), designer_portal_flow))
    d.add_handler(MessageHandler(Filters.text & ~Filters.command, on_text))
    d.emg_handlers_registered = True

# initial registration on the global dp
_register_handlers(dp)

# -------------------------
# Flask endpoints
# -------------------------
# -------------------------
@app.route("/tg", methods=["POST"])
def tg_post():
    data = request.get_json(force=True)
    logging.info(f"📥 Incoming update: {data}")
    update = Update.de_json(data, bot)
    dp.process_update(update)
    return "ok"

@app.route("/tg", methods=["GET"])
def tg_get():
    return "ok"

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok"

@app.route("/", methods=["GET"])
def root_ok():
    return "Emerge Bot Running"

# -------------------------
# Long-polling (network-flaky safe)
# -------------------------
def _polling():
    """Start PTB polling in a side thread, robust to flaky links."""
    try:
        from telegram.ext import Updater
        global dp
        dp.bot.get_me(timeout=20)
        up = Updater(TOKEN, use_context=True)
        # use the Updater's dispatcher going forward
        dp = up.dispatcher
        _register_handlers(dp)
        up.start_polling(drop_pending_updates=True, timeout=30)
        logging.info("🔁 Polling thread started (no idle in thread)")
        # keep thread alive without idle() (signals not allowed here)
        while True:
            time.sleep(60)
    except Exception as e:
        logging.warning(f"Polling thread error: {e}")
if __name__ == "__main__":
    # Start long polling in background thread
    t = threading.Thread(target=_polling, daemon=True)
    t.start()

    from waitress import serve
    logging.info("🚀 Emerge Assistant Bot is starting…")
    logging.info(f"🌐 Serving Flask via waitress on 0.0.0.0:{PORT}")
    try:
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except Exception:
        # dev fallback
        app.run(host="0.0.0.0", port=PORT)
