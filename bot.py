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
from bson import ObjectId
import random
import string
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================

TOKEN        = "8994134922:AAEzbgLS4FUUpmJ3uQSWQPqDZ-pSLDZamuU"
ADMIN_ID     = 8575787439
BOT_USERNAME = "FreeRedeemCodez1Robot"

CHANNELS = [
    {"id": -1003745950290, "url": "https://t.me/+Lypb3Q0meWc5YzU1", "name": "Channel 1"},
    {"id": -1003599814306, "url": "https://t.me/+f1s1iq_weZk5OGRl", "name": "Channel 2"},
]

LOG_CHANNEL         = -1003792761013
IMAGE_URL           = "https://i.ibb.co/W4SpQX1C/IMG-20260521-090418-265.jpg"
POINTS_PER_REFERRAL = 20
MINIMUM_WITHDRAW    = 100
GPLAY_ALLOWED       = [100, 200, 500, 1000]

MONGO_URL = "mongodb+srv://rewardbot:Ashu%40123@cluster0.n6okp9q.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# ==================== MONGO ====================

client       = MongoClient(MONGO_URL)
db           = client["rewardbot"]
users_col    = db["users"]
withdraw_col = db["withdraws"]
gift_col     = db["gifts"]

users_col.create_index("user_id", unique=True)
gift_col.create_index("code", unique=True)

# ==================== HELPERS ====================

def clear_states(context: ContextTypes.DEFAULT_TYPE):
    """Clear all user states cleanly."""
    keys = [
        "state",
        "claimgift",
        "withdraw",
        "withdraw_method",
        "set_upi",
        "gpmail",
        "broadcast",
        "ban",
        "unban",
        "giftcreate",
        "send_code",
        "reject_reason",
        "payout_wid",
        "payout_uid",
        "payout_amount",
        "gplay_amount",
    ]
    for k in keys:
        context.user_data.pop(k, None)


def generate_gift_code() -> str:
    chars = string.ascii_uppercase + string.digits
    code  = "GIFT" + "".join(random.choices(chars, k=8))
    while gift_col.find_one({"code": code}):
        code = "GIFT" + "".join(random.choices(chars, k=8))
    return code


def get_user(user_id: int) -> dict:
    return users_col.find_one({"user_id": user_id}) or {}


def ensure_user(user_id: int, referrer_id: int | None = None) -> dict:
    data = users_col.find_one({"user_id": user_id})
    if not data:
        invited_by = referrer_id if referrer_id and referrer_id != user_id else None
        users_col.insert_one({
            "user_id":       user_id,
            "points":        0,
            "referrals":     0,
            "invited_by":    invited_by,
            "verified":      0,
            "banned":        0,
            "claimed_gifts": [],
            "upi":           None,
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
        [InlineKeyboardButton(f" Join {ch['name']}", url=ch["url"])]
        for ch in CHANNELS
    ]
    buttons.append([InlineKeyboardButton("✅ I Joined — Verify", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)


def main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton("💰 Wallet"),       KeyboardButton("🧧 Red Envelope")],
        [KeyboardButton("👥 Referral Link"), KeyboardButton("💎 Withdraw")],
        [KeyboardButton("🏦 Set UPI"),       KeyboardButton("☎️ Support")],
        [KeyboardButton("🏠 Home")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def admin_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🎁 Generate Gift Code",  callback_data="admin_gencode")],
        [InlineKeyboardButton("📢 Broadcast",           callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",            callback_data="admin_ban")],
        [InlineKeyboardButton("✅ Unban User",           callback_data="admin_unban")],
        [InlineKeyboardButton("👥 Total Users",         callback_data="admin_users")],
        [InlineKeyboardButton("💸 Pending Withdrawals", callback_data="admin_pending")],
    ]
    return InlineKeyboardMarkup(kb)


def withdraw_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 UPI",              callback_data="wmethod_upi")],
        [InlineKeyboardButton("🎁 Google Play Code", callback_data="wmethod_gplay")],
    ])


def withdraw_keyboard_gplay(wid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ SEND CODE", callback_data=f"pay_sendcode_{wid}"),
        InlineKeyboardButton("❌ REJECT",    callback_data=f"pay_reject_{wid}"),
    ]])


def withdraw_keyboard_upi(wid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ MARK PAID", callback_data=f"pay_markpaid_{wid}"),
        InlineKeyboardButton("❌ REJECT",    callback_data=f"pay_reject_{wid}"),
    ]])

# ==================== /start ====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
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
    total   = users_col.count_documents({})
    pending = withdraw_col.count_documents({"status": "pending"})
    banned  = users_col.count_documents({"banned": 1})
    await update.message.reply_text(
        f"⚙️ *ADMIN PANEL*\n\n"
        f"👥 Total Users: `{total}`\n"
        f"💸 Pending Withdrawals: `{pending}`\n"
        f"🚫 Banned Users: `{banned}`",
        parse_mode="Markdown",
        reply_markup=admin_keyboard(),
    )

# ==================== VERIFY CALLBACK ====================

async def cb_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
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

# ==================== WITHDRAW METHOD CALLBACK ====================

async def cb_withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if is_banned(user_id):
        return

    method = "gplay" if query.data == "wmethod_gplay" else "upi"
    clear_states(context)
    context.user_data["withdraw_method"] = method

    user_data = get_user(user_id)
    points    = user_data.get("points", 0)

    if method == "upi":
        saved_upi = user_data.get("upi")
        if not saved_upi:
            await query.message.reply_text(
                "❌ *No UPI ID saved.*\n\n"
                "Please tap 🏦 *Set UPI* first to save your UPI ID before withdrawing.",
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
            return

        context.user_data["state"] = "await_withdraw_amount_upi"
        await query.message.reply_text(
            f"💸 *UPI Withdraw*\n\n"
            f"💰 Your Balance: `{points}` points\n"
            f"🏦 UPI: `{saved_upi}`\n\n"
            f"Send the amount to withdraw:\nExample: `100`",
            parse_mode="Markdown",
        )
    else:
        context.user_data["state"] = "await_withdraw_amount_gplay"
        allowed = " | ".join([f"`{a}`" for a in GPLAY_ALLOWED])
        await query.message.reply_text(
            f"🎁 *Google Play Code Withdraw*\n\n"
            f"💰 Your Balance: `{points}` points\n\n"
            f"Allowed amounts: {allowed}\n\n"
            f"Send the amount:",
            parse_mode="Markdown",
        )

# ==================== PAYOUT MANAGEMENT CALLBACKS ====================

async def cb_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Admins only.", show_alert=True)
        return

    data   = query.data   # pay_sendcode_<wid> / pay_markpaid_<wid> / pay_reject_<wid>
    parts  = data.split("_", 2)
    action = parts[1]
    wid    = parts[2]

    try:
        w = withdraw_col.find_one({"_id": ObjectId(wid)})
    except Exception:
        await query.answer("❌ Invalid withdraw ID.", show_alert=True)
        return

    if not w:
        await query.answer("❌ Withdrawal not found.", show_alert=True)
        return

    if w.get("status") != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer(f"⚠️ Already processed: {w.get('status')}", show_alert=True)
        return

    # ── MARK PAID (UPI) ──────────────────────────────────────────────
    if action == "markpaid":
        withdraw_col.update_one(
            {"_id": ObjectId(wid)},
            {"$set": {"status": "completed"}},
        )
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ *Marked as Paid*\n\n"
            f"👤 User: `{w['user_id']}`\n"
            f"⭐ Amount: `{w['amount']}` points\n"
            f"💳 UPI: `{w.get('upi_id', '—')}`",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                w["user_id"],
                "✅ *Your UPI Withdrawal Has Been Paid!*\n\n"
                f"⭐ Amount: `{w['amount']}` points\n"
                f"💳 UPI ID: `{w.get('upi_id', '—')}`\n\n"
                "Thank you for using our platform! 🎉",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    # ── SEND CODE (Google Play) ──────────────────────────────────────
    elif action == "sendcode":
        clear_states(context)
        context.user_data["state"]         = "await_redeem_code"
        context.user_data["payout_wid"]    = wid
        context.user_data["payout_uid"]    = w["user_id"]
        context.user_data["payout_amount"] = w["amount"]
        await query.message.reply_text(
            f"🎮 *Send Redeem Code*\n\n"
            f"👤 For user: `{w['user_id']}`\n"
            f"⭐ Amount: `{w['amount']}` points\n\n"
            f"Send the Google Play redeem code now:\n"
            f"Example: `ABCD-EFGH-IJKL`",
            parse_mode="Markdown",
        )

    # ── REJECT ───────────────────────────────────────────────────────
    elif action == "reject":
        clear_states(context)
        context.user_data["state"]         = "await_reject_reason"
        context.user_data["payout_wid"]    = wid
        context.user_data["payout_uid"]    = w["user_id"]
        context.user_data["payout_amount"] = w["amount"]
        await query.message.reply_text(
            f"❌ *Reject Withdrawal*\n\n"
            f"👤 User: `{w['user_id']}`\n"
            f"⭐ Amount: `{w['amount']}` points\n\n"
            f"Send the rejection reason:",
            parse_mode="Markdown",
        )

# ==================== ADMIN PANEL CALLBACKS ====================

async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Admins only.", show_alert=True)
        return

    data = query.data

    if data == "admin_gencode":
        clear_states(context)
        context.user_data["state"] = "await_gift_amount"
        await query.message.reply_text(
            "🎁 *Generate Gift Code*\n\n"
            "Send the points value for this code:\n\nExample: `500`",
            parse_mode="Markdown",
        )

    elif data == "admin_broadcast":
        clear_states(context)
        context.user_data["state"] = "await_broadcast"
        await query.message.reply_text(
            "📢 *Broadcast*\n\nSend the message to broadcast to all users:",
            parse_mode="Markdown",
        )

    elif data == "admin_ban":
        clear_states(context)
        context.user_data["state"] = "await_ban_id"
        await query.message.reply_text(
            "🚫 *Ban User*\n\nSend the User ID to ban:",
            parse_mode="Markdown",
        )

    elif data == "admin_unban":
        clear_states(context)
        context.user_data["state"] = "await_unban_id"
        await query.message.reply_text(
            "✅ *Unban User*\n\nSend the User ID to unban:",
            parse_mode="Markdown",
        )

    elif data == "admin_users":
        total    = users_col.count_documents({})
        verified = users_col.count_documents({"verified": 1})
        banned   = users_col.count_documents({"banned": 1})
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
            dest = w.get("upi_id") or w.get("method", "—")
            lines.append(
                f"👤 `{w['user_id']}` | ⭐ {w['amount']} pts | `{dest}`"
            )
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ==================== SINGLE MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()

    if is_banned(user_id):
        await update.message.reply_text("🚫 You are banned from this bot.")
        return

    ensure_user(user_id)

    # Menu button labels — clear state before handling any menu tap
    MENU_BUTTONS = {
        "💰 Wallet",
        "🧧 Red Envelope",
        "👥 Referral Link",
        "💎 Withdraw",
        "🏦 Set UPI",
        "☎️ Support",
        "🏠 Home",
    }
    if text in MENU_BUTTONS:
        clear_states(context)

    state = context.user_data.get("state", "")

    # ════════════════════════════════════════════════════════════════
    # ADMIN STATES — checked first, always return after handling
    # ════════════════════════════════════════════════════════════════

    if user_id == ADMIN_ID and state:

        # ── Generate Gift Code ───────────────────────────────────────
        if state == "await_gift_amount":
            try:
                amount = int(text)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text(
                    "❌ *Invalid amount.*\n\nSend a positive number.\nExample: `500`",
                    parse_mode="Markdown",
                )
                return
            code = generate_gift_code()
            gift_col.insert_one({"code": code, "amount": amount, "claimed": []})
            clear_states(context)
            await update.message.reply_text(
                f"✅ *Gift Code Generated*\n\n"
                f"🎁 Code: `{code}`\n"
                f"💎 Amount: `{amount}` Points\n\n"
                f"Share this code via Red Envelope 🧧",
                parse_mode="Markdown",
            )
            return

        # ── Broadcast ────────────────────────────────────────────────
        if state == "await_broadcast":
            all_users         = list(users_col.find({"banned": {"$ne": 1}}))
            success, fail     = 0, 0
            for u in all_users:
                try:
                    await context.bot.send_message(u["user_id"], text)
                    success += 1
                except Exception:
                    fail += 1
            clear_states(context)
            await update.message.reply_text(
                f"📢 *Broadcast Complete*\n\n"
                f"✅ Delivered: `{success}`\n"
                f"❌ Failed: `{fail}`",
                parse_mode="Markdown",
            )
            return

        # ── Ban ──────────────────────────────────────────────────────
        if state == "await_ban_id":
            try:
                target = int(text)
            except ValueError:
                await update.message.reply_text(
                    "❌ *Invalid User ID.* Send a numeric ID.",
                    parse_mode="Markdown",
                )
                return
            users_col.update_one({"user_id": target}, {"$set": {"banned": 1}}, upsert=True)
            try:
                await context.bot.send_message(
                    target,
                    "🚫 *You have been banned from this bot.*",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            clear_states(context)
            await update.message.reply_text(
                f"✅ User `{target}` has been *banned*.",
                parse_mode="Markdown",
            )
            return

        # ── Unban ────────────────────────────────────────────────────
        if state == "await_unban_id":
            try:
                target = int(text)
            except ValueError:
                await update.message.reply_text(
                    "❌ *Invalid User ID.* Send a numeric ID.",
                    parse_mode="Markdown",
                )
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
            clear_states(context)
            await update.message.reply_text(
                f"✅ User `{target}` has been *unbanned*.",
                parse_mode="Markdown",
            )
            return

        # ── Send redeem code to user (Google Play payout) ────────────
        if state == "await_redeem_code":
            redeem_code = text.strip()
            wid         = context.user_data.get("payout_wid")
            target_uid  = context.user_data.get("payout_uid")
            amount      = context.user_data.get("payout_amount")

            withdraw_col.update_one(
                {"_id": ObjectId(wid)},
                {"$set": {"status": "completed", "redeem_code": redeem_code}},
            )
            clear_states(context)

            await update.message.reply_text(
                f"✅ *Code Sent to User `{target_uid}`*",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    target_uid,
                    f"🎉 *Withdraw Completed!*\n\n"
                    f"━━━━━━━━━━━━━━\n\n"
                    f"🏦 Method:\nGoogle Play Code\n\n"
                    f"⭐ Points Redeemed: `{amount}`\n\n"
                    f"🎁 Your Redeem Code:\n\n"
                    f"`{redeem_code}`\n\n"
                    f"━━━━━━━━━━━━━━\n\n"
                    f"Thank you! Enjoy your reward 🎮",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            return

        # ── Reject reason ────────────────────────────────────────────
        if state == "await_reject_reason":
            reason     = text.strip()
            wid        = context.user_data.get("payout_wid")
            target_uid = context.user_data.get("payout_uid")
            amount     = context.user_data.get("payout_amount")

            users_col.update_one(
                {"user_id": target_uid},
                {"$inc": {"points": amount}},
            )
            withdraw_col.update_one(
                {"_id": ObjectId(wid)},
                {"$set": {"status": "rejected", "reject_reason": reason}},
            )
            clear_states(context)

            await update.message.reply_text(
                f"✅ *Withdrawal Rejected*\n\n"
                f"👤 User: `{target_uid}`\n"
                f"⭐ `{amount}` points refunded.",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    target_uid,
                    f"❌ *Withdraw Rejected*\n\n"
                    f"━━━━━━━━━━━━━━\n\n"
                    f"Reason:\n{reason}\n\n"
                    f"━━━━━━━━━━━━━━\n\n"
                    f"⭐ `{amount}` points have been refunded to your wallet.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            return

    # ════════════════════════════════════════════════════════════════
    # USER STATES
    # ════════════════════════════════════════════════════════════════

    # Re-read state (may have been cleared above for menu buttons)
    state = context.user_data.get("state", "")

    # ── Set UPI (state) ──────────────────────────────────────────────
    if state == "await_set_upi":
        upi_id = text.strip()
        if not upi_id or " " in upi_id:
            await update.message.reply_text(
                "❌ *Invalid UPI ID.* Please send a valid UPI ID.\nExample: `yourname@upi`",
                parse_mode="Markdown",
            )
            return
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"upi": upi_id}},
        )
        clear_states(context)
        await update.message.reply_text(
            f"✅ *UPI Saved!*\n\n"
            f"🏦 UPI ID: `{upi_id}`\n\n"
            f"You can now use UPI withdrawal.",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    # ── Red Envelope / Gift Code ─────────────────────────────────────
    if state == "await_gift_code":
        code = text.upper().strip()

        # Only process messages that start with GIFT
        if not code.startswith("GIFT"):
            await update.message.reply_text(
                "❌ *Invalid gift code.*\n\n"
                "Gift codes start with `GIFT`\nExample: `GIFT4821ABCD`",
                parse_mode="Markdown",
            )
            return

        gift = gift_col.find_one({"code": code})

        if not gift:
            await update.message.reply_text(
                "❌ *Invalid gift code.*\nCheck the code and try again.",
                parse_mode="Markdown",
            )
            clear_states(context)
            return

        claimed_by = gift.get("claimed") or []
        if user_id in claimed_by:
            await update.message.reply_text(
                "❌ *You have already claimed this code.*",
                parse_mode="Markdown",
            )
            clear_states(context)
            return

        reward = gift.get("amount", 0)
        users_col.update_one(
            {"user_id": user_id},
            {
                "$inc":      {"points": reward},
                "$addToSet": {"claimed_gifts": code},
            },
        )
        gift_col.update_one({"code": code}, {"$push": {"claimed": user_id}})
        clear_states(context)
        await update.message.reply_text(
            f"🎉 *Red Envelope Opened!*\n\n"
            f"🧧 Code: `{code}`\n"
            f"⭐ +{reward} Points added to your wallet!",
            parse_mode="Markdown",
        )
        return

    # ── UPI Withdraw amount ──────────────────────────────────────────
    if state == "await_withdraw_amount_upi":
        try:
            amount = int(text.strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ *Invalid amount.* Send a positive number.\nExample: `100`",
                parse_mode="Markdown",
            )
            return

        if amount < MINIMUM_WITHDRAW:
            await update.message.reply_text(
                f"❌ Minimum withdrawal is *{MINIMUM_WITHDRAW} points*.",
                parse_mode="Markdown",
            )
            return

        user_data = get_user(user_id)
        balance   = user_data.get("points", 0)
        upi_id    = user_data.get("upi")

        if not upi_id:
            await update.message.reply_text(
                "❌ *No UPI ID saved.* Please tap 🏦 Set UPI first.",
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
            clear_states(context)
            return

        if balance < amount:
            await update.message.reply_text(
                f"❌ *Insufficient balance.*\n\n"
                f"💰 Your balance: `{balance}` points\n"
                f"💎 Requested: `{amount}` points",
                parse_mode="Markdown",
            )
            return

        result = users_col.update_one(
            {"user_id": user_id, "points": {"$gte": amount}},
            {"$inc": {"points": -amount}},
        )
        if result.modified_count == 0:
            await update.message.reply_text(
                "❌ *Deduction failed.* Please try again.",
                parse_mode="Markdown",
            )
            return

        doc = {
            "user_id": user_id,
            "amount":  amount,
            "method":  "upi",
            "upi_id":  upi_id,
            "status":  "pending",
        }
        result = withdraw_col.insert_one(doc)
        wid    = str(result.inserted_id)
        clear_states(context)

        await update.message.reply_text(
            f"✅ *Withdrawal Request Submitted!*\n\n"
            f"⭐ Amount: `{amount}` points\n"
            f"🏦 Method: UPI\n"
            f"💳 UPI: `{upi_id}`\n"
            f"📋 Status: *Pending*\n\n"
            f"You will be notified once processed.",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        log_text = (
            f"💸 *NEW WITHDRAW REQUEST*\n\n"
            f"👤 User ID:\n`{user_id}`\n\n"
            f"💰 Amount:\n`{amount}`\n\n"
            f"🏦 Method:\nUPI\n\n"
            f"💳 UPI:\n`{upi_id}`"
        )
        try:
            await context.bot.send_message(
                ADMIN_ID, log_text,
                parse_mode="Markdown",
                reply_markup=withdraw_keyboard_upi(wid),
            )
        except Exception:
            pass
        try:
            await context.bot.send_message(LOG_CHANNEL, log_text, parse_mode="Markdown")
        except Exception:
            pass
        return

    # ── Google Play Withdraw amount ──────────────────────────────────
    if state == "await_withdraw_amount_gplay":
        try:
            amount = int(text.strip())
            if amount not in GPLAY_ALLOWED:
                raise ValueError
        except ValueError:
            allowed = ", ".join([f"`{a}`" for a in GPLAY_ALLOWED])
            await update.message.reply_text(
                f"❌ *Invalid amount.*\n\nAllowed amounts: {allowed}",
                parse_mode="Markdown",
            )
            return

        user_data = get_user(user_id)
        balance   = user_data.get("points", 0)

        if balance < amount:
            await update.message.reply_text(
                f"❌ *Insufficient balance.*\n\n"
                f"💰 Your balance: `{balance}` points\n"
                f"💎 Requested: `{amount}` points",
                parse_mode="Markdown",
            )
            return

        context.user_data["gplay_amount"] = amount
        context.user_data["state"]        = "await_gmail"
        await update.message.reply_text(
            f"📧 *Send your Gmail address*\n\n"
            f"The Google Play code will be sent to this Gmail.\n\n"
            f"Example: `yourname@gmail.com`",
            parse_mode="Markdown",
        )
        return

    # ── Gmail for Google Play ────────────────────────────────────────
    if state == "await_gmail":
        gmail  = text.strip()
        amount = context.user_data.get("gplay_amount")

        if not gmail or "@" not in gmail:
            await update.message.reply_text(
                "❌ *Invalid Gmail.* Please send a valid Gmail address.",
                parse_mode="Markdown",
            )
            return

        if not amount:
            await update.message.reply_text(
                "❌ Session expired. Please start withdrawal again.",
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
            clear_states(context)
            return

        user_data = get_user(user_id)
        balance   = user_data.get("points", 0)

        if balance < amount:
            await update.message.reply_text(
                f"❌ *Insufficient balance.*\n\n"
                f"💰 Your balance: `{balance}` points",
                parse_mode="Markdown",
            )
            clear_states(context)
            return

        result = users_col.update_one(
            {"user_id": user_id, "points": {"$gte": amount}},
            {"$inc": {"points": -amount}},
        )
        if result.modified_count == 0:
            await update.message.reply_text(
                "❌ *Deduction failed.* Please try again.",
                parse_mode="Markdown",
            )
            clear_states(context)
            return

        doc = {
            "user_id": user_id,
            "amount":  amount,
            "method":  "gplay",
            "gmail":   gmail,
            "status":  "pending",
        }
        result = withdraw_col.insert_one(doc)
        wid    = str(result.inserted_id)
        clear_states(context)

        await update.message.reply_text(
            f"✅ *Withdrawal Request Submitted!*\n\n"
            f"⭐ Amount: `{amount}` points\n"
            f"🏦 Method: Google Play Code\n"
            f"📧 Gmail: `{gmail}`\n"
            f"📋 Status: *Pending*\n\n"
            f"You will be notified once processed.",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        log_text = (
            f"💸 *NEW WITHDRAW REQUEST*\n\n"
            f"👤 User ID:\n`{user_id}`\n\n"
            f"💰 Amount:\n`{amount}`\n\n"
            f"🏦 Method:\nGoogle Play Code\n\n"
            f"📧 Gmail:\n`{gmail}`"
        )
        try:
            await context.bot.send_message(
                ADMIN_ID, log_text,
                parse_mode="Markdown",
                reply_markup=withdraw_keyboard_gplay(wid),
            )
        except Exception:
            pass
        try:
            await context.bot.send_message(LOG_CHANNEL, log_text, parse_mode="Markdown")
        except Exception:
            pass
        return

    # ════════════════════════════════════════════════════════════════
    # MENU BUTTONS
    # ════════════════════════════════════════════════════════════════

    if text == "💰 Wallet":
        user_data = get_user(user_id)
        points    = user_data.get("points", 0)
        referrals = user_data.get("referrals", 0)
        upi       = user_data.get("upi") or "Not set"
        await update.message.reply_text(
            f"💰 *Your Wallet*\n\n"
            f"👥 Referrals: `{referrals}`\n"
            f"⭐ Points: `{points}`\n"
            f"🏦 UPI: `{upi}`\n\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"🎁 Per Referral: `{POINTS_PER_REFERRAL}`\n"
            f"💎 Minimum Withdraw: `{MINIMUM_WITHDRAW}`",
            parse_mode="Markdown",
        )

    elif text == "🧧 Red Envelope":
        context.user_data["state"] = "await_gift_code"
        await update.message.reply_text(
            "🧧 *Red Envelope*\n\n"
            "Send your gift code to claim your reward:\n\n"
            "Gift codes start with `GIFT`\nExample: `GIFT4821ABCD`",
            parse_mode="Markdown",
        )

    elif text == "👥 Referral Link":
        user_data = get_user(user_id)
        points    = user_data.get("points", 0)
        referrals = user_data.get("referrals", 0)
        link      = f"https://t.me/{BOT_USERNAME}?start={user_id}"
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
        points    = user_data.get("points", 0)
        if points < MINIMUM_WITHDRAW:
            await update.message.reply_text(
                f"❌ You need at least *{MINIMUM_WITHDRAW} points* to withdraw.\n\n"
                f"💰 Your balance: `{points}` points",
                parse_mode="Markdown",
            )
            return
        await update.message.reply_text(
            f"💎 *Withdraw Request*\n\n"
            f"💰 Your Balance: `{points}` points\n"
            f"📋 Minimum: `{MINIMUM_WITHDRAW}` points\n\n"
            f"Choose your withdrawal method:",
            parse_mode="Markdown",
            reply_markup=withdraw_method_keyboard(),
        )

    elif text == "🏦 Set UPI":
        context.user_data["state"] = "await_set_upi"
        user_data = get_user(user_id)
        current   = user_data.get("upi")
        note      = f"\n\nCurrent UPI: `{current}`" if current else ""
        await update.message.reply_text(
            f"🏦 *Set UPI ID*{note}\n\n"
            f"Send your UPI ID:\nExample: `yourname@upi`",
            parse_mode="Markdown",
        )

    elif text == "☎️ Support":
        await update.message.reply_text(
            "☎️ *Support*\n\n👤 Contact: @Genzayu",
            parse_mode="Markdown",
        )

    elif text == "🏠 Home":
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

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))

    # Callbacks — most specific patterns first
    app.add_handler(CallbackQueryHandler(cb_verify,          pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_method, pattern="^wmethod_"))
    app.add_handler(CallbackQueryHandler(cb_payout,          pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(cb_admin,           pattern="^admin_"))

    # Single message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
