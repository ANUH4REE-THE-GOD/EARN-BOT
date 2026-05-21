from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient
import random
import string
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================

TOKEN = "8648638779:AAHqrt2XY0mtQaSiUm2IGH6Ufq7qP3HU76g"
ADMIN_ID = 8575787439
BOT_USERNAME = "FreeRedeemCodez1Robot"

CHANNELS = [
    {"id": -1002490723980, "url": "https://t.me/+VqJTt74UgI4xOTI1", "name": "Channel 1"},
    {"id": -1003599814306, "url": "https://t.me/+f1s1iq_weZk5OGRl", "name": "Channel 2"},
]

LOG_CHANNEL = -1003792761013
IMAGE_URL = "https://i.ibb.co/W4SpQX1C/IMG-20260521-090418-265.jpg"
POINTS_PER_REFERRAL = 20
MINIMUM_WITHDRAW = 100
MONGO_URL = "mongodb+srv://rewardbot:Ashu%40123@cluster0.n6okp9q.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# ==================== MONGO ====================

client = MongoClient(MONGO_URL)
db = client["rewardbot"]
users_col = db["users"]
withdraw_col = db["withdraws"]
gift_col = db["gifts"]

# Indexes for performance
users_col.create_index("user_id", unique=True)
gift_col.create_index("code", unique=True)

# ==================== HELPERS ====================

def generate_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "GIFT" + "".join(random.choices(chars, k=length))

def get_user(user_id: int) -> dict:
    return users_col.find_one({"user_id": user_id}) or {}

def ensure_user(user_id: int, referrer_id: int | None = None) -> dict:
    data = users_col.find_one({"user_id": user_id})
    if not data:
        invited_by = referrer_id if referrer_id and referrer_id != user_id else None
        users_col.insert_one({
            "user_id": user_id,
            "points": 0,
            "referrals": 0,
            "invited_by": invited_by,
            "verified": 0,
            "banned": 0,
            "claimed_gifts": [],
        })
        data = users_col.find_one({"user_id": user_id})
    return data

def is_banned(user_id: int) -> bool:
    data = users_col.find_one({"user_id": user_id})
    return bool(data and data.get("banned") == 1)

async def check_join(bot, user_id: int, channel_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def all_joined(bot, user_id: int) -> bool:
    for ch in CHANNELS:
        if not await check_join(bot, user_id, ch["id"]):
            return False
    return True

# ==================== KEYBOARDS ====================

def join_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch["url"])]
        for ch in CHANNELS
    ]
    buttons.append([InlineKeyboardButton("✅ I Joined — Verify", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)

def main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton("💰 Wallet"), KeyboardButton("🧧 Red Envelope")],
        [KeyboardButton("👥 Referral Link"), KeyboardButton("💎 Withdraw")],
        [KeyboardButton("🎁 Gift Code"), KeyboardButton("☎️ Support")],
        [KeyboardButton("🏠 Home")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🎁 Generate Gift Code", callback_data="admin_gencode")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton("👥 Total Users", callback_data="admin_users")],
        [InlineKeyboardButton("💸 Pending Withdraws", callback_data="admin_pending")],
    ]
    return InlineKeyboardMarkup(kb)

# ==================== /start ====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    referrer = None
    if context.args:
        try:
            referrer = int(context.args[0])
        except ValueError:
            pass

    ensure_user(user_id, referrer)

    if is_banned(user_id):
        await update.message.reply_text("🚫 You are banned from this bot.")
        return

    caption = (
        "💎 *FREE PLAY STORE CODES*\n\n"
        "🔥 Premium Rewards\n"
        "⚡ Instant Verification\n"
        "📈 Daily Giveaways\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "➊ Join Both Channels\n"
        "➋ Click Verify\n"
        "➌ Unlock Rewards"
    )
    await update.message.reply_photo(
        photo=IMAGE_URL,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=join_keyboard(),
    )

# ==================== /admin ====================

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total = users_col.count_documents({})
    pending = withdraw_col.count_documents({"status": "pending"})
    banned = users_col.count_documents({"banned": 1})
    await update.message.reply_text(
        f"⚙️ *ADMIN PANEL*\n\n"
        f"👥 Total Users: `{total}`\n"
        f"💸 Pending Withdraws: `{pending}`\n"
        f"🚫 Banned Users: `{banned}`",
        parse_mode="Markdown",
        reply_markup=admin_keyboard(),
    )

# ==================== VERIFY CALLBACK ====================

async def cb_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if is_banned(user_id):
        await query.answer("🚫 You are banned.", show_alert=True)
        return

    if not await all_joined(context.bot, user_id):
        await query.edit_message_caption(
            caption="❌ *Please join ALL channels first, then click Verify.*",
            parse_mode="Markdown",
            reply_markup=join_keyboard(),
        )
        return

    user_data = get_user(user_id)

    if user_data.get("verified") == 0:
        users_col.update_one({"user_id": user_id}, {"$set": {"verified": 1}})

        invited_by = user_data.get("invited_by")
        if invited_by:
            users_col.update_one(
                {"user_id": invited_by},
                {"$inc": {"points": POINTS_PER_REFERRAL, "referrals": 1}},
            )
            try:
                await context.bot.send_message(
                    invited_by,
                    f"🎉 *New Referral!*\n\n"
                    f"👤 User: `{user_id}`\n"
                    f"💰 +{POINTS_PER_REFERRAL} Points added to your wallet!",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    await query.edit_message_caption(
        caption="✅ *Verification Successful!*\n\n💎 Reward access unlocked.",
        parse_mode="Markdown",
    )
    await query.message.reply_text(
        "🏠 *Main Menu*",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )

# ==================== ADMIN CALLBACKS ====================

async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Admins only.", show_alert=True)
        return

    data = query.data

    if data == "admin_gencode":
        context.user_data.clear()
        context.user_data["state"] = "await_gift_amount"
        await query.message.reply_text(
            "🎁 *Generate Gift Code*\n\nSend the number of points for this code:\n\nExample: `100`",
            parse_mode="Markdown",
        )

    elif data == "admin_broadcast":
        context.user_data.clear()
        context.user_data["state"] = "await_broadcast"
        await query.message.reply_text(
            "📢 *Broadcast*\n\nSend the message to broadcast to all users:",
            parse_mode="Markdown",
        )

    elif data == "admin_ban":
        context.user_data.clear()
        context.user_data["state"] = "await_ban_id"
        await query.message.reply_text(
            "🚫 *Ban User*\n\nSend the User ID to ban:",
            parse_mode="Markdown",
        )

    elif data == "admin_unban":
        context.user_data.clear()
        context.user_data["state"] = "await_unban_id"
        await query.message.reply_text(
            "✅ *Unban User*\n\nSend the User ID to unban:",
            parse_mode="Markdown",
        )

    elif data == "admin_users":
        total = users_col.count_documents({})
        verified = users_col.count_documents({"verified": 1})
        banned = users_col.count_documents({"banned": 1})
        await query.message.reply_text(
            f"👥 *User Stats*\n\n"
            f"Total: `{total}`\n"
            f"Verified: `{verified}`\n"
            f"Banned: `{banned}`",
            parse_mode="Markdown",
        )

    elif data == "admin_pending":
        pending = list(withdraw_col.find({"status": "pending"}).limit(10))
        if not pending:
            await query.message.reply_text("✅ No pending withdrawals.")
            return
        lines = ["💸 *Pending Withdrawals (latest 10)*\n"]
        for w in pending:
            lines.append(
                f"👤 `{w['user_id']}` | ⭐ {w['amount']} pts | 💳 `{w['upi_id']}`"
            )
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ==================== MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if is_banned(user_id):
        await update.message.reply_text("🚫 You are banned from this bot.")
        return

    ensure_user(user_id)
    state = context.user_data.get("state", "")

    # ── Admin states ────────────────────────────────────────────────────────

    if user_id == ADMIN_ID:

        if state == "await_gift_amount":
            try:
                amount = int(text)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Enter a valid positive number.")
                return

            code = generate_code()
            # Ensure uniqueness
            while gift_col.find_one({"code": code}):
                code = generate_code()

            gift_col.insert_one({"code": code, "points": amount, "claimed": False, "claimed_by": None})
            context.user_data.clear()
            await update.message.reply_text(
                f"🎁 *Gift Code Generated*\n\n"
                f"🧧 Code: `{code}`\n"
                f"⭐ Reward: `{amount}` Points\n\n"
                f"Share this code with users via Red Envelope.",
                parse_mode="Markdown",
            )
            return

        if state == "await_broadcast":
            users = list(users_col.find({"banned": 0}))
            success, fail = 0, 0
            for u in users:
                try:
                    await context.bot.send_message(u["user_id"], text)
                    success += 1
                except Exception:
                    fail += 1
            context.user_data.clear()
            await update.message.reply_text(
                f"📢 *Broadcast Done*\n\n✅ Sent: `{success}`\n❌ Failed: `{fail}`",
                parse_mode="Markdown",
            )
            return

        if state == "await_ban_id":
            try:
                target = int(text)
            except ValueError:
                await update.message.reply_text("❌ Invalid User ID.")
                return
            users_col.update_one({"user_id": target}, {"$set": {"banned": 1}}, upsert=True)
            try:
                await context.bot.send_message(
                    target,
                    "🚫 *You have been banned* from this bot.\n\nReason: Violation of rules.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            context.user_data.clear()
            await update.message.reply_text(f"✅ User `{target}` has been banned.", parse_mode="Markdown")
            return

        if state == "await_unban_id":
            try:
                target = int(text)
            except ValueError:
                await update.message.reply_text("❌ Invalid User ID.")
                return
            users_col.update_one({"user_id": target}, {"$set": {"banned": 0}})
            try:
                await context.bot.send_message(
                    target,
                    "✅ *You have been unbanned.* Welcome back!",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            context.user_data.clear()
            await update.message.reply_text(f"✅ User `{target}` has been unbanned.", parse_mode="Markdown")
            return

    # ── User states ─────────────────────────────────────────────────────────

    if state == "await_gift_code":
        code = text.upper().strip()
        gift = gift_col.find_one({"code": code})

        if not gift:
            await update.message.reply_text("❌ *Invalid gift code.* Please check and try again.", parse_mode="Markdown")
            context.user_data.clear()
            return

        if gift.get("claimed"):
            await update.message.reply_text("❌ *This code has already been claimed.*", parse_mode="Markdown")
            context.user_data.clear()
            return

        # Prevent double-claim per user
        user_data = get_user(user_id)
        if code in (user_data.get("claimed_gifts") or []):
            await update.message.reply_text("❌ *You have already claimed this code.*", parse_mode="Markdown")
            context.user_data.clear()
            return

        reward = gift["points"]
        users_col.update_one(
            {"user_id": user_id},
            {
                "$inc": {"points": reward},
                "$push": {"claimed_gifts": code},
            },
        )
        gift_col.update_one(
            {"code": code},
            {"$set": {"claimed": True, "claimed_by": user_id}},
        )
        context.user_data.clear()
        await update.message.reply_text(
            f"🎉 *Red Envelope Opened!*\n\n⭐ +{reward} Points added to your wallet!",
            parse_mode="Markdown",
        )
        return

    if state == "await_withdraw":
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ Wrong format.\n\nSend: `amount upi_id`\nExample: `100 test@upi`",
                parse_mode="Markdown",
            )
            return

        try:
            amount = int(parts[0])
        except ValueError:
            await update.message.reply_text("❌ Amount must be a number.", parse_mode="Markdown")
            return

        upi_id = parts[1]

        if amount < MINIMUM_WITHDRAW:
            await update.message.reply_text(
                f"❌ Minimum withdraw is *{MINIMUM_WITHDRAW} points*.",
                parse_mode="Markdown",
            )
            return

        user_data = get_user(user_id)
        balance = user_data.get("points", 0)

        if balance < amount:
            await update.message.reply_text(
                f"❌ Insufficient balance.\n\n💰 Your balance: *{balance} points*",
                parse_mode="Markdown",
            )
            return

        # Deduct points atomically
        result = users_col.update_one(
            {"user_id": user_id, "points": {"$gte": amount}},
            {"$inc": {"points": -amount}},
        )

        if result.modified_count == 0:
            await update.message.reply_text("❌ Failed to deduct points. Try again.", parse_mode="Markdown")
            return

        # Log withdrawal
        withdraw_col.insert_one({
            "user_id": user_id,
            "amount": amount,
            "upi_id": upi_id,
            "status": "pending",
        })

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ *Withdrawal Request Submitted!*\n\n"
            f"⭐ Amount: `{amount}` points\n"
            f"💳 UPI: `{upi_id}`\n"
            f"📋 Status: Pending",
            parse_mode="Markdown",
        )

        # Notify admin
        admin_msg = (
            f"💸 *New Withdrawal Request*\n\n"
            f"👤 User: `{user_id}`\n"
            f"⭐ Amount: `{amount}` points\n"
            f"💳 UPI ID: `{upi_id}`"
        )
        try:
            await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
        except Exception:
            pass

        # Log to channel
        try:
            await context.bot.send_message(LOG_CHANNEL, admin_msg, parse_mode="Markdown")
        except Exception:
            pass

        return

    # ── Menu buttons ─────────────────────────────────────────────────────────

    if text == "💰 Wallet":
        user_data = get_user(user_id)
        points = user_data.get("points", 0)
        referrals = user_data.get("referrals", 0)
        await update.message.reply_text(
            f"💰 *Your Wallet*\n\n"
            f"👥 Referrals: `{referrals}`\n"
            f"⭐ Points: `{points}`\n\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"🎁 Per Referral: `{POINTS_PER_REFERRAL}`\n"
            f"💎 Minimum Withdraw: `{MINIMUM_WITHDRAW}`",
            parse_mode="Markdown",
        )

    elif text == "🧧 Red Envelope":
        context.user_data.clear()
        context.user_data["state"] = "await_gift_code"
        await update.message.reply_text(
            "🧧 *Red Envelope*\n\nSend your gift code to claim rewards:",
            parse_mode="Markdown",
        )

    elif text == "👥 Referral Link":
        user_data = get_user(user_id)
        points = user_data.get("points", 0)
        referrals = user_data.get("referrals", 0)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        await update.message.reply_text(
            f"👥 *Your Referral Link*\n\n"
            f"`{link}`\n\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"👤 Referrals: `{referrals}`\n"
            f"⭐ Points: `{points}`\n\n"
            f"🎁 Earn *{POINTS_PER_REFERRAL} points* per referral",
            parse_mode="Markdown",
        )

    elif text == "💎 Withdraw":
        user_data = get_user(user_id)
        points = user_data.get("points", 0)
        if points < MINIMUM_WITHDRAW:
            await update.message.reply_text(
                f"❌ You need at least *{MINIMUM_WITHDRAW} points* to withdraw.\n\n"
                f"💰 Your balance: `{points}` points",
                parse_mode="Markdown",
            )
            return
        context.user_data.clear()
        context.user_data["state"] = "await_withdraw"
        await update.message.reply_text(
            f"💎 *Withdraw Request*\n\n"
            f"💰 Your Balance: `{points}` points\n"
            f"📋 Minimum: `{MINIMUM_WITHDRAW}` points\n\n"
            f"Send your request in this format:\n"
            f"`amount upi_id`\n\n"
            f"Example:\n`100 yourname@upi`",
            parse_mode="Markdown",
        )

    elif text == "🎁 Gift Code":
        context.user_data.clear()
        context.user_data["state"] = "await_gift_code"
        await update.message.reply_text(
            "🎁 *Gift Code*\n\nSend your gift code to redeem points:",
            parse_mode="Markdown",
        )

    elif text == "☎️ Support":
        await update.message.reply_text(
            "☎️ *Support*\n\n👤 Contact: @Genzayu",
            parse_mode="Markdown",
        )

    elif text == "🏠 Home":
        context.user_data.clear()
        caption = (
            "💎 *FREE PLAY STORE REDEEM CODES*\n\n"
            "🔥 Daily Premium Rewards\n"
            "⚡ Instant Withdraw System\n"
            "✅ Trusted Reward Community\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🎁 *Available Rewards:*\n\n"
            "• Play Store Codes\n"
            "• Premium Gift Codes\n"
            "• Daily Giveaway Access\n"
            "• Referral Rewards\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "👥 Invite Friends & Earn More"
        )
        await update.message.reply_photo(
            photo=IMAGE_URL,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

# ==================== MAIN ====================

def main():
    app = Application.builder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))

    # Callbacks — specific patterns first, catch-all admin last
    app.add_handler(CallbackQueryHandler(cb_verify, pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(cb_admin, pattern="^admin_"))

    # Single message handler — handles all states and menu buttons
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Bot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
