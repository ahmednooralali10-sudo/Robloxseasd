import os
import json
import time
import uuid
import threading
import logging
import html
from datetime import datetime
from flask import Flask
import telebot
from telebot import types

# ============================================================
# XORE FILE 😘 - File & Digital Store Bot
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "VISITTTTTBOT").replace("@", "").strip()
ADMIN_IDS = {x.strip() for x in os.getenv("ADMIN_IDS", "7075895496").split(",") if x.strip()}
BOT_LINK = f"https://t.me/{BOT_USERNAME}"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables.")

DB_FILE = os.getenv("DB_FILE", "database.json")
PORT = int(os.getenv("PORT", "10000"))
DB_LOCK = threading.RLock()
PURCHASE_LOCK = threading.RLock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Telegram animated message effect (🔥 by default).
# Override it from Render with MESSAGE_EFFECT_ID if Telegram changes the ID.
MESSAGE_EFFECT_ID = os.getenv("MESSAGE_EFFECT_ID", "5104841245755180586").strip()

# Apply the effect automatically to bot text messages in private chats.
# Telegram only allows message effects in private 1-to-1 chats.
_original_send_message = bot.send_message
def _xore_send_message(chat_id, text, *args, **kwargs):
    if MESSAGE_EFFECT_ID and "message_effect_id" not in kwargs:
        try:
            numeric_chat_id = int(chat_id)
            if numeric_chat_id > 0:
                kwargs["message_effect_id"] = MESSAGE_EFFECT_ID
        except (TypeError, ValueError):
            pass
    try:
        return _original_send_message(chat_id, text, *args, **kwargs)
    except Exception as exc:
        # Compatibility fallback: if this Telegram/client/library combination
        # rejects the effect, resend the same message without it.
        if "message_effect_id" in kwargs:
            kwargs.pop("message_effect_id", None)
            logging.warning("Message effect fallback: %s", exc)
            return _original_send_message(chat_id, text, *args, **kwargs)
        raise

bot.send_message = _xore_send_message

# =========================
# COLORED TELEGRAM BUTTONS
# =========================
def _button_style(text="", callback_data=""):
    s = f"{text} {callback_data}".lower()
    danger = ("حذف", "حظر", "إلغاء", "تنظيف", "صيانة", "delete", "del", "ban", "remove", "rmch", "delf", "delstore")
    success = ("شراء", "الحصول", "إضافة", "تأكيد", "تحقق", "فك حظر", "مجاني", "buy_", "add_", "chk_")
    if any(w in s for w in danger): return "danger"
    if any(w in s for w in success): return "success"
    return "primary"

def inline_button(text, **kwargs):
    kwargs.setdefault("style", _button_style(text, kwargs.get("callback_data", "")))
    return types.InlineKeyboardButton(text, **kwargs)

def reply_button(text, style=None):
    return types.KeyboardButton(text, style=style or _button_style(text, ""))

states = {}


# ============================================================
# WEB / HEALTH
# ============================================================

@app.get("/")
def home():
    return {"ok": True, "bot": BOT_USERNAME, "name": "XORE FILE", "version": "7.0"}

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().isoformat()}


# ============================================================
# DATABASE
# ============================================================

def default_db():
    return {
        "channels": [],
        "files": {},
        "store": {},
        "users": {},
        "banned": [],
        "groups": {},
        "coupons": {},
        "admin_logs": [],
        "settings": {
            "maintenance": False,
            "welcome": (
                "✨ <b>أهلاً بك في XORE FILE 😘</b>\n\n"
                "📦 ملفات ومنتجات رقمية في مكان واحد.\n"
                "⭐ اجمع النقاط واحصل على المنتجات بسهولة."
            ),
            "developer_url": "https://t.me/xsaudi96",
            "channel_url": "https://t.me/mf5rt1",
            "daily_points": 10,
            "join_points": 15,
            "referral_points": 10
        },
        "stats": {
            "joins": 0,
            "files_sent": 0,
            "store_sales": 0
        }
    }


def merge_dict(base, incoming):
    if not isinstance(base, dict) or not isinstance(incoming, dict):
        return incoming
    result = dict(base)
    for key, value in incoming.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def load_db():
    data = default_db()
    if not os.path.exists(DB_FILE):
        return data
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return merge_dict(data, json.load(f))
    except Exception:
        logging.exception("Failed to load database")
        return data


db = load_db()

# Database migration / repair. Older versions may have saved channels as a dict,
# which causes: 'dict' object has no attribute 'append'. Normalize it to a list.
def repair_database():
    channels = db.get("channels", [])
    if isinstance(channels, dict):
        normalized = []
        for key, value in channels.items():
            candidate = value
            if isinstance(value, dict):
                candidate = value.get("id", value.get("chat_id", key))
            elif value in (None, "", False, True):
                candidate = key
            try:
                candidate = int(candidate)
            except (TypeError, ValueError):
                candidate = str(candidate).strip()
                if candidate and not candidate.startswith("@") and not candidate.startswith("-"):
                    candidate = "@" + candidate
            if candidate not in normalized:
                normalized.append(candidate)
        db["channels"] = normalized
    elif not isinstance(channels, list):
        db["channels"] = []

    # Make sure critical collections keep the expected type.
    for key in ("files", "store", "users", "groups", "coupons"):
        if not isinstance(db.get(key), dict):
            db[key] = {}
    for key in ("banned", "admin_logs"):
        if not isinstance(db.get(key), list):
            db[key] = []

repair_database()


def save_db():
    with DB_LOCK:
        tmp = DB_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DB_FILE)
        except Exception:
            logging.exception("Failed to save database")


# ============================================================
# HELPERS
# ============================================================

def esc(value):
    return html.escape(str(value or ""))


def is_admin(user_id):
    return str(user_id) in ADMIN_IDS


def is_banned(user_id):
    return str(user_id) in db.get("banned", [])


def set_state(user_id, **kwargs):
    states[int(user_id)] = kwargs


def state(user_id):
    return states.get(int(user_id), {})


def clear_state(user_id):
    states.pop(int(user_id), None)


def ensure_user(tg_user):
    uid = str(tg_user.id)
    created = uid not in db["users"]

    if created:
        db["users"][uid] = {
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username": tg_user.username or "",
            "first_name": tg_user.first_name or "",
            "downloads": 0,
            "points": int(db["settings"].get("join_points", 15)),
            "last_daily": "",
            "referred_by": None,
            "purchases": []
        }
        db["stats"]["joins"] = int(db["stats"].get("joins", 0)) + 1
    else:
        u = db["users"][uid]
        u["username"] = tg_user.username or ""
        u["first_name"] = tg_user.first_name or ""
        u.setdefault("downloads", 0)
        u.setdefault("points", 0)
        u.setdefault("last_daily", "")
        u.setdefault("purchases", [])

    save_db()
    return created


def log_admin(admin_id, action):
    db.setdefault("admin_logs", []).append(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {admin_id}: {action}"
    )
    db["admin_logs"] = db["admin_logs"][-500:]
    save_db()


def media_info(message):
    if message.content_type == "document":
        return message.document.file_id, message.document.file_name or "file.bin", "document"
    if message.content_type == "photo":
        return message.photo[-1].file_id, "photo.jpg", "photo"
    if message.content_type == "video":
        return message.video.file_id, getattr(message.video, "file_name", None) or "video.mp4", "video"
    if message.content_type == "audio":
        return message.audio.file_id, getattr(message.audio, "file_name", None) or "audio.mp3", "audio"
    return None, None, None


def send_media(chat_id, file_id, media_type="document", caption="", reply_markup=None):
    kwargs = dict(caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    if media_type == "photo":
        return bot.send_photo(chat_id, file_id, **kwargs)
    if media_type == "video":
        return bot.send_video(chat_id, file_id, **kwargs)
    if media_type == "audio":
        return bot.send_audio(chat_id, file_id, **kwargs)
    return bot.send_document(chat_id, file_id, **kwargs)


def answer(call, text="", alert=False):
    try:
        bot.answer_callback_query(call.id, text, show_alert=alert)
    except Exception:
        pass


# ============================================================
# KEYBOARDS
# ============================================================

def user_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("🛍️ المتجر الرقمي", "👤 حسابي")
    kb.row("🎁 المكافأة اليومية", "🎟️ استخدام كوبون")
    kb.row("🔎 البحث عن ملف", "💌 تواصل مع المطور")
    return kb


def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📤 رفع ملف", "📦 رفع متعدد")
    kb.row("🛍️ إضافة منتج", "🗂️ إدارة المتجر")
    kb.row("📁 إدارة الملفات", "🎟️ إنشاء كوبون")
    kb.row("📣 إذاعة", "🔎 بحث مستخدم")
    kb.row("📡 القنوات", "🚫 الحظر")
    kb.row("📊 الإحصائيات", "⚙️ الإعدادات")
    kb.row("💾 نسخة احتياطية", "📄 تصدير المستخدمين")
    kb.row("📜 سجل الإدارة", "🧹 مسح السجل")
    kb.row("❌ إلغاء العملية")
    return kb


# ============================================================
# FORCED SUBSCRIPTION
# ============================================================

def check_sub(user_id):
    if is_admin(user_id):
        return True

    for channel_id in db.get("channels", []):
        try:
            member = bot.get_chat_member(channel_id, int(user_id))
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logging.warning("Subscription check failed: %s", e)
            return False
    return True


def sub_keyboard(payload):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for channel_id in db.get("channels", []):
        try:
            chat = bot.get_chat(channel_id)
            if getattr(chat, "username", None):
                url = f"https://t.me/{chat.username}"
            else:
                url = getattr(chat, "invite_link", None)
            if url:
                kb.add(inline_button(f"📢 {chat.title}", url=url))
        except Exception:
            pass
    kb.add(inline_button("🔄 تحقق من الاشتراك", callback_data=f"subcheck:{payload}"))
    return kb


def require_sub(chat_id, user_id, payload):
    if check_sub(user_id):
        return True
    bot.send_message(
        chat_id,
        "🔒 <b>الاشتراك مطلوب</b>\n\nاشترك في القنوات ثم اضغط «تحقق من الاشتراك».",
        parse_mode="HTML",
        reply_markup=sub_keyboard(payload)
    )
    return False


# ============================================================
# START
# ============================================================

@bot.message_handler(commands=["start"])
def start(message):
    uid = str(message.from_user.id)

    if is_banned(uid):
        return bot.send_message(message.chat.id, "🚫 تم حظرك من استخدام البوت.")

    if db["settings"].get("maintenance") and not is_admin(uid):
        return bot.send_message(message.chat.id, "🛠️ البوت تحت الصيانة حالياً.")

    created = ensure_user(message.from_user)
    parts = message.text.split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else ""

    if created and param.startswith("ref_"):
        ref = param[4:]
        if ref != uid and ref in db["users"]:
            db["users"][uid]["referred_by"] = ref
            reward = int(db["settings"].get("referral_points", 10))
            db["users"][ref]["points"] = int(db["users"][ref].get("points", 0)) + reward
            save_db()
            try:
                bot.send_message(ref, f"🎉 شخص دخل من رابطك!\n⭐ حصلت على +{reward} نقاط.")
            except Exception:
                pass

    if param.startswith("store_"):
        item_id = param[6:]
        if not require_sub(message.chat.id, message.from_user.id, f"store:{item_id}"):
            return
        return show_product(message.chat.id, item_id)

    if param and not param.startswith("ref_"):
        if param not in db.get("files", {}):
            return bot.send_message(message.chat.id, "❌ الملف غير موجود أو تم حذفه.")
        if not require_sub(message.chat.id, message.from_user.id, f"file:{param}"):
            return
        return send_public_file(message.chat.id, param)

    if is_admin(uid):
        return bot.send_message(
            message.chat.id,
            "👑 <b>لوحة إدارة XORE FILE</b>\n\nاختر العملية المطلوبة:",
            parse_mode="HTML",
            reply_markup=admin_kb()
        )

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(inline_button("🔗 رابط الإحالة", callback_data="myref"))
    if db["settings"].get("channel_url"):
        kb.add(inline_button("📢 قناة المطور", url=db["settings"]["channel_url"]))

    bot.send_message(
        message.chat.id,
        db["settings"].get("welcome", "أهلاً بك"),
        parse_mode="HTML",
        reply_markup=kb
    )
    bot.send_message(message.chat.id, "👇 اختر من القائمة:", reply_markup=user_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("subcheck:"))
def subscription_check(call):
    payload = call.data.split(":", 1)[1]
    if not check_sub(call.from_user.id):
        return answer(call, "❌ لم تشترك في جميع القنوات بعد.", True)

    answer(call, "✅ تم التحقق")
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    kind, value = payload.split(":", 1)
    if kind == "store":
        show_product(call.message.chat.id, value)
    elif kind == "file":
        send_public_file(call.message.chat.id, value)


# ============================================================
# PUBLIC FILES
# ============================================================

def send_public_file(chat_id, fid):
    item = db.get("files", {}).get(fid)
    if not item:
        return bot.send_message(chat_id, "❌ الملف غير موجود.")

    kb = types.InlineKeyboardMarkup(row_width=2)
    if db["settings"].get("channel_url"):
        kb.add(inline_button("📢 القناة", url=db["settings"]["channel_url"]))
    kb.add(inline_button("➕ أضف البوت", url=f"{BOT_LINK}?startgroup=true"))

    try:
        send_media(
            chat_id,
            item["file_id"],
            item.get("file_type", "document"),
            esc(item.get("desc", "")),
            kb
        )
        item["downloads"] = int(item.get("downloads", 0)) + 1
        db["stats"]["files_sent"] = int(db["stats"].get("files_sent", 0)) + 1
        uid = str(chat_id)
        if uid in db["users"]:
            db["users"][uid]["downloads"] = int(db["users"][uid].get("downloads", 0)) + 1
        save_db()
    except Exception:
        logging.exception("File send failed")
        bot.send_message(chat_id, "⚠️ تعذر إرسال الملف.")


# ============================================================
# STORE - FILE IS SECRET UNTIL PURCHASE
# ============================================================

@bot.message_handler(func=lambda m: m.text == "🛍️ المتجر الرقمي")
def store_menu(message):
    ensure_user(message.from_user)
    show_store_page(message.chat.id, 0)


def show_store_page(chat_id, page=0):
    items = list(db.get("store", {}).items())
    if not items:
        return bot.send_message(chat_id, "🛍️ المتجر فارغ حالياً.")

    per_page = 8
    pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = items[page * per_page:(page + 1) * per_page]

    kb = types.InlineKeyboardMarkup(row_width=1)
    for item_id, item in chunk:
        price = max(0, int(item.get("price", 0)))
        label = "🎁 مجاني" if price == 0 else f"⭐ {price} نقطة"
        kb.add(inline_button(
            f"📦 {item.get('name', 'منتج')} • {label}",
            callback_data=f"product:{item_id}"
        ))

    nav = []
    if page > 0:
        nav.append(inline_button("⬅️ السابق", callback_data=f"storepage:{page-1}"))
    if page + 1 < pages:
        nav.append(inline_button("التالي ➡️", callback_data=f"storepage:{page+1}"))
    if nav:
        kb.row(*nav)

    bot.send_message(
        chat_id,
        f"🛍️ <b>XORE STORE</b>\n\n"
        f"🔐 الملفات مخفية حتى نجاح عملية الشراء.\n"
        f"📄 الصفحة {page+1}/{pages}",
        parse_mode="HTML",
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("storepage:"))
def store_page(call):
    answer(call)
    try:
        page = int(call.data.split(":", 1)[1])
    except ValueError:
        return
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    show_store_page(call.message.chat.id, page)


@bot.callback_query_handler(func=lambda c: c.data.startswith("product:"))
def product_callback(call):
    answer(call)
    item_id = call.data.split(":", 1)[1]
    show_product(call.message.chat.id, item_id)


def show_product(chat_id, item_id):
    item = db.get("store", {}).get(item_id)
    if not item:
        return bot.send_message(chat_id, "❌ المنتج غير موجود.")

    price = max(0, int(item.get("price", 0)))
    price_text = "🎁 مجاني" if price == 0 else f"⭐ {price} نقطة"

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(inline_button(
        "🎁 الحصول على المنتج" if price == 0 else f"🛒 شراء • {price} نقطة",
        callback_data=f"buy:{item_id}"
    ))
    kb.add(inline_button("🔗 مشاركة المنتج", switch_inline_query=f"{BOT_LINK}?start=store_{item_id}"))

    text = (
        f"╭─────〔 🛍️ <b>المنتج</b> 〕─────╮\n\n"
        f"📦 <b>{esc(item.get('name', 'منتج'))}</b>\n\n"
        f"📝 <b>الوصف:</b>\n{esc(item.get('desc', 'لا يوجد وصف'))}\n\n"
        f"💰 <b>السعر:</b> {price_text}\n"
        f"🛒 <b>المبيعات:</b> {int(item.get('sales', 0))}\n\n"
        f"🔐 <b>الملف سري</b>\n"
        f"لن يتم إرسال الملف إلا بعد نجاح عملية الشراء.\n\n"
        f"╰────────────────────╯"
    )
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("buy:"))
def buy_product(call):
    ensure_user(call.from_user)
    uid = str(call.from_user.id)
    item_id = call.data.split(":", 1)[1]

    if not require_sub(call.message.chat.id, call.from_user.id, f"store:{item_id}"):
        return answer(call)

    with PURCHASE_LOCK:
        item = db.get("store", {}).get(item_id)
        if not item:
            return answer(call, "❌ المنتج غير موجود.", True)

        price = max(0, int(item.get("price", 0)))
        user = db["users"][uid]
        points = max(0, int(user.get("points", 0)))

        # Zero points can ONLY get a free item.
        if price > 0 and points < price:
            return answer(
                call,
                f"❌ نقاطك لا تكفي!\n\n⭐ رصيدك: {points}\n💰 السعر: {price}\n➖ ينقصك: {price-points}",
                True
            )

        # Deduct first. If Telegram fails to deliver, refund.
        if price > 0:
            user["points"] = points - price
            save_db()

        try:
            send_media(
                call.message.chat.id,
                item["file_id"],
                item.get("file_type", "document"),
                (
                    f"✅ <b>تم تسليم المنتج</b>\n\n"
                    f"📦 {esc(item.get('name', 'منتج'))}\n"
                    f"💰 المدفوع: {price} نقطة\n"
                    f"⭐ رصيدك: {user.get('points', 0)}"
                )
            )
        except Exception:
            logging.exception("Product delivery failed")
            if price > 0:
                user["points"] = points
                save_db()
            return answer(call, "❌ فشل إرسال الملف وتمت إعادة نقاطك.", True)

        item["sales"] = int(item.get("sales", 0)) + 1
        db["stats"]["store_sales"] = int(db["stats"].get("store_sales", 0)) + 1
        user.setdefault("purchases", []).append({
            "item_id": item_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "price": price
        })
        user["purchases"] = user["purchases"][-100:]
        save_db()

    answer(call, "✅ تم الشراء وإرسال الملف.")


# ============================================================
# ADD STORE ITEM
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🛍️ إضافة منتج")
def add_product_start(m):
    set_state(m.from_user.id, step="product_name")
    bot.send_message(m.chat.id, "🛍️ <b>إضافة منتج جديد</b>\n\n1️⃣ أرسل اسم المنتج:", parse_mode="HTML")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "product_name", content_types=["text"])
def add_product_name(m):
    s = state(m.from_user.id)
    s["name"] = m.text.strip()
    s["step"] = "product_desc"
    bot.send_message(m.chat.id, "2️⃣ 📝 أرسل وصف المنتج:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "product_desc", content_types=["text"])
def add_product_desc(m):
    s = state(m.from_user.id)
    s["desc"] = m.text
    s["step"] = "product_price"
    bot.send_message(m.chat.id, "3️⃣ 💰 أرسل السعر بالنقاط.\n\nاكتب <b>0</b> إذا كان مجانياً:", parse_mode="HTML")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "product_price", content_types=["text"])
def add_product_price(m):
    try:
        price = int(m.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        return bot.send_message(m.chat.id, "❌ أرسل رقماً صحيحاً 0 أو أكبر.")

    s = state(m.from_user.id)
    s["price"] = price
    s["step"] = "product_file"
    bot.send_message(
        m.chat.id,
        "4️⃣ 🔐 <b>أرسل ملف المنتج</b>\n\n"
        "يدعم: 📄 ملف / 🖼️ صورة / 🎥 فيديو / 🎵 صوت\n\n"
        "لن يظهر هذا الملف للمستخدم إلا بعد الشراء.",
        parse_mode="HTML"
    )


@bot.message_handler(
    func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "product_file",
    content_types=["document", "photo", "video", "audio"]
)
def add_product_file(m):
    file_id, filename, file_type = media_info(m)
    if not file_id:
        return bot.send_message(m.chat.id, "❌ نوع الملف غير مدعوم.")

    s = state(m.from_user.id)
    item_id = uuid.uuid4().hex[:8]

    db["store"][item_id] = {
        "name": s["name"],
        "desc": s["desc"],
        "price": s["price"],
        "file_id": file_id,
        "file_type": file_type,
        "filename": filename,
        "sales": 0,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_db()
    log_admin(m.from_user.id, f"Added product {item_id} / {s['name']}")
    clear_state(m.from_user.id)

    link = f"{BOT_LINK}?start=store_{item_id}"
    bot.send_message(
        m.chat.id,
        f"✅ <b>تم إضافة المنتج بنجاح</b>\n\n"
        f"📦 {esc(db['store'][item_id]['name'])}\n"
        f"🔐 الملف محفوظ بشكل سري داخل البوت.\n\n"
        f"🔗 رابط المنتج:\n<code>{link}</code>",
        parse_mode="HTML",
        reply_markup=admin_kb()
    )


# ============================================================
# MANAGE STORE
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🗂️ إدارة المتجر")
def manage_store(m):
    if not db.get("store"):
        return bot.send_message(m.chat.id, "🛍️ لا توجد منتجات.")
    kb = types.InlineKeyboardMarkup(row_width=1)
    for item_id, item in list(db["store"].items())[:80]:
        kb.add(inline_button(
            f"⚙️ {item.get('name','منتج')} • ⭐{item.get('price',0)}",
            callback_data=f"manageproduct:{item_id}"
        ))
    bot.send_message(m.chat.id, "🗂️ <b>إدارة المتجر</b>", parse_mode="HTML", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("manageproduct:"))
def manage_product(call):
    if not is_admin(call.from_user.id):
        return answer(call, "غير مصرح.", True)
    item_id = call.data.split(":", 1)[1]
    item = db.get("store", {}).get(item_id)
    if not item:
        return answer(call, "المنتج غير موجود.", True)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(inline_button("👁️ معاينة", callback_data=f"product:{item_id}"))
    kb.add(inline_button("🗑️ حذف المنتج", callback_data=f"delproduct:{item_id}"))
    bot.send_message(
        call.message.chat.id,
        f"📦 <b>{esc(item.get('name'))}</b>\n"
        f"💰 {item.get('price',0)} نقطة\n"
        f"🛒 {item.get('sales',0)} عملية",
        parse_mode="HTML",
        reply_markup=kb
    )
    answer(call)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delproduct:"))
def delete_product(call):
    if not is_admin(call.from_user.id):
        return answer(call, "غير مصرح.", True)
    item_id = call.data.split(":", 1)[1]
    item = db.get("store", {}).pop(item_id, None)
    if item:
        save_db()
        log_admin(call.from_user.id, f"Deleted product {item_id}")
    answer(call, "✅ تم حذف المنتج.")
    try:
        bot.edit_message_text("✅ تم حذف المنتج.", call.message.chat.id, call.message.message_id)
    except Exception:
        pass


# ============================================================
# USER PROFILE / DAILY / REFERRAL
# ============================================================

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def profile(m):
    ensure_user(m.from_user)
    uid = str(m.from_user.id)
    u = db["users"][uid]
    bot.send_message(
        m.chat.id,
        f"╭────〔 👤 <b>حسابي</b> 〕────╮\n\n"
        f"🆔 <code>{uid}</code>\n"
        f"⭐ النقاط: <b>{u.get('points',0)}</b>\n"
        f"📥 التحميلات: {u.get('downloads',0)}\n"
        f"🛍️ المشتريات: {len(u.get('purchases',[]))}\n"
        f"📅 الانضمام: {esc(u.get('joined','-'))}\n\n"
        f"╰────────────────╯",
        parse_mode="HTML"
    )


@bot.message_handler(func=lambda m: m.text == "🎁 المكافأة اليومية")
def daily(m):
    ensure_user(m.from_user)
    uid = str(m.from_user.id)
    u = db["users"][uid]
    today = datetime.now().strftime("%Y-%m-%d")
    if u.get("last_daily") == today:
        return bot.send_message(m.chat.id, "⏳ أخذت مكافأة اليوم بالفعل. ارجع بكرة 😏")
    reward = max(0, int(db["settings"].get("daily_points", 10)))
    u["points"] = int(u.get("points", 0)) + reward
    u["last_daily"] = today
    save_db()
    bot.send_message(m.chat.id, f"🎁 مبروك! حصلت على <b>+{reward}</b> نقاط.", parse_mode="HTML")


@bot.callback_query_handler(func=lambda c: c.data == "myref")
def my_ref(call):
    answer(call)
    bot.send_message(
        call.message.chat.id,
        f"🔗 <b>رابط إحالتك</b>\n\n<code>{BOT_LINK}?start=ref_{call.from_user.id}</code>",
        parse_mode="HTML"
    )


# ============================================================
# COUPONS
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🎟️ إنشاء كوبون")
def coupon_admin_start(m):
    set_state(m.from_user.id, step="coupon_code")
    bot.send_message(m.chat.id, "🎟️ أرسل كود الكوبون:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "coupon_code", content_types=["text"])
def coupon_code(m):
    code = m.text.strip().upper()
    if not code:
        return
    s = state(m.from_user.id)
    s["code"] = code
    s["step"] = "coupon_points"
    bot.send_message(m.chat.id, "⭐ أرسل عدد النقاط:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "coupon_points", content_types=["text"])
def coupon_points(m):
    try:
        pts = int(m.text.strip())
        if pts <= 0:
            raise ValueError
    except ValueError:
        return bot.send_message(m.chat.id, "❌ أرسل رقماً أكبر من صفر.")
    s = state(m.from_user.id)
    db["coupons"][s["code"]] = {"points": pts, "used_by": []}
    save_db()
    code = s["code"]
    clear_state(m.from_user.id)
    bot.send_message(m.chat.id, f"✅ الكوبون: <code>{esc(code)}</code>\n⭐ {pts} نقطة", parse_mode="HTML", reply_markup=admin_kb())


@bot.message_handler(func=lambda m: m.text == "🎟️ استخدام كوبون")
def coupon_user_start(m):
    ensure_user(m.from_user)
    set_state(m.from_user.id, step="redeem_coupon")
    bot.send_message(m.chat.id, "🎟️ أرسل الكوبون:")


@bot.message_handler(func=lambda m: state(m.from_user.id).get("step") == "redeem_coupon", content_types=["text"])
def redeem_coupon(m):
    ensure_user(m.from_user)
    uid = str(m.from_user.id)
    code = m.text.strip().upper()
    clear_state(m.from_user.id)
    coupon = db.get("coupons", {}).get(code)
    if not coupon:
        return bot.send_message(m.chat.id, "❌ الكوبون غير صحيح.")
    coupon.setdefault("used_by", [])
    if uid in coupon["used_by"]:
        return bot.send_message(m.chat.id, "⚠️ استخدمت هذا الكوبون من قبل.")
    coupon["used_by"].append(uid)
    pts = int(coupon.get("points", 0))
    db["users"][uid]["points"] = int(db["users"][uid].get("points", 0)) + pts
    save_db()
    bot.send_message(m.chat.id, f"🎉 تم إضافة <b>+{pts}</b> نقطة.", parse_mode="HTML")


# ============================================================
# SEARCH PUBLIC FILE
# ============================================================

@bot.message_handler(func=lambda m: m.text == "🔎 البحث عن ملف")
def search_file_start(m):
    set_state(m.from_user.id, step="search_file")
    bot.send_message(m.chat.id, "🔎 اكتب جزءاً من اسم الملف:")


@bot.message_handler(func=lambda m: state(m.from_user.id).get("step") == "search_file", content_types=["text"])
def search_file(m):
    query = m.text.strip().lower()
    clear_state(m.from_user.id)
    results = [
        (fid, f) for fid, f in db.get("files", {}).items()
        if query in str(f.get("name", "")).lower()
    ]
    if not results:
        return bot.send_message(m.chat.id, "❌ ما لقيت ملف مطابق.", reply_markup=user_kb())
    kb = types.InlineKeyboardMarkup(row_width=1)
    for fid, f in results[:20]:
        kb.add(inline_button(f"📄 {f.get('name','ملف')[:40]}", url=f"{BOT_LINK}?start={fid}"))
    bot.send_message(m.chat.id, f"🔎 النتائج ({len(results)}):", reply_markup=kb)


# ============================================================
# CONTACT / TICKETS
# ============================================================

@bot.message_handler(func=lambda m: m.text == "💌 تواصل مع المطور")
def ticket_start(m):
    set_state(m.from_user.id, step="ticket")
    bot.send_message(m.chat.id, "💌 أرسل رسالتك للمطور:")


@bot.message_handler(
    func=lambda m: state(m.from_user.id).get("step") == "ticket",
    content_types=["text", "photo", "video", "document", "audio", "voice"]
)
def ticket_send(m):
    uid = m.from_user.id
    clear_state(uid)
    for admin in ADMIN_IDS:
        try:
            bot.forward_message(admin, m.chat.id, m.message_id)
            kb = types.InlineKeyboardMarkup()
            kb.add(inline_button("↩️ الرد على المستخدم", callback_data=f"reply:{uid}"))
            bot.send_message(admin, f"💌 رسالة من <code>{uid}</code>", parse_mode="HTML", reply_markup=kb)
        except Exception:
            logging.exception("Ticket forwarding failed")
    bot.send_message(m.chat.id, "✅ تم إرسال رسالتك.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("reply:"))
def reply_start(call):
    if not is_admin(call.from_user.id):
        return answer(call, "غير مصرح.", True)
    target = call.data.split(":", 1)[1]
    set_state(call.from_user.id, step="admin_reply", target=target)
    answer(call)
    bot.send_message(call.message.chat.id, f"↩️ أرسل ردك للمستخدم <code>{target}</code>:", parse_mode="HTML")


@bot.message_handler(
    func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "admin_reply",
    content_types=["text", "photo", "video", "document", "audio", "voice"]
)
def reply_send(m):
    target = state(m.from_user.id).get("target")
    clear_state(m.from_user.id)
    try:
        bot.send_message(target, "💌 <b>رد من إدارة XORE FILE:</b>", parse_mode="HTML")
        bot.copy_message(target, m.chat.id, m.message_id)
        bot.send_message(m.chat.id, "✅ تم إرسال الرد.")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ تعذر الإرسال: {esc(e)}", parse_mode="HTML")


# ============================================================
# UPLOAD PUBLIC FILE / BATCH
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📤 رفع ملف")
def upload_start(m):
    set_state(m.from_user.id, step="file_desc")
    bot.send_message(m.chat.id, "📝 أرسل وصف الملف:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "file_desc", content_types=["text"])
def upload_desc(m):
    s = state(m.from_user.id)
    s["desc"] = m.text
    s["step"] = "file_upload"
    bot.send_message(m.chat.id, "📤 أرسل الملف / الصورة / الفيديو / الصوت:")


@bot.message_handler(
    func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "file_upload",
    content_types=["document", "photo", "video", "audio"]
)
def upload_file(m):
    file_id, name, file_type = media_info(m)
    fid = uuid.uuid4().hex[:8]
    s = state(m.from_user.id)
    db["files"][fid] = {
        "file_id": file_id, "file_type": file_type, "name": name,
        "desc": s.get("desc", ""), "downloads": 0,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_db()
    clear_state(m.from_user.id)
    log_admin(m.from_user.id, f"Uploaded file {fid}")
    bot.send_message(m.chat.id, f"✅ تم الرفع.\n🔗 <code>{BOT_LINK}?start={fid}</code>", parse_mode="HTML", reply_markup=admin_kb())


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📦 رفع متعدد")
def batch_start(m):
    set_state(m.from_user.id, step="batch_desc")
    bot.send_message(m.chat.id, "📝 أرسل الوصف الموحد للملفات:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "batch_desc", content_types=["text"])
def batch_desc(m):
    s = state(m.from_user.id)
    s.update(step="batch_files", desc=m.text, count=0, links=[])
    bot.send_message(m.chat.id, "📦 أرسل الملفات تباعاً.\nعند الانتهاء أرسل /done")


@bot.message_handler(
    func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "batch_files",
    content_types=["document", "photo", "video", "audio"]
)
def batch_file(m):
    file_id, name, file_type = media_info(m)
    fid = uuid.uuid4().hex[:8]
    s = state(m.from_user.id)
    db["files"][fid] = {
        "file_id": file_id, "file_type": file_type, "name": name,
        "desc": s.get("desc", ""), "downloads": 0,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    s["count"] += 1
    s["links"].append(f"{BOT_LINK}?start={fid}")
    save_db()
    bot.send_message(m.chat.id, f"✅ تم حفظ #{s['count']} • {esc(name)}", parse_mode="HTML")


@bot.message_handler(commands=["done"])
def batch_done(m):
    if not is_admin(m.from_user.id):
        return
    s = state(m.from_user.id)
    if s.get("step") != "batch_files":
        return
    count = s.get("count", 0)
    links = s.get("links", [])
    clear_state(m.from_user.id)
    text = f"🎉 تم رفع {count} ملف."
    if links:
        text += "\n\n" + "\n".join(links[:25])
    bot.send_message(m.chat.id, text, reply_markup=admin_kb())


# ============================================================
# MANAGE PUBLIC FILES
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📁 إدارة الملفات")
def manage_files(m):
    if not db.get("files"):
        return bot.send_message(m.chat.id, "📁 لا توجد ملفات.")
    show_files_page(m.chat.id, 0)


def show_files_page(chat_id, page):
    items = list(db.get("files", {}).items())
    per_page = 6
    pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    kb = types.InlineKeyboardMarkup(row_width=1)
    for fid, item in items[page*per_page:(page+1)*per_page]:
        kb.add(inline_button(f"📄 {item.get('name','ملف')[:35]}", callback_data=f"filemanage:{fid}"))
    nav = []
    if page > 0:
        nav.append(inline_button("⬅️", callback_data=f"filespage:{page-1}"))
    if page + 1 < pages:
        nav.append(inline_button("➡️", callback_data=f"filespage:{page+1}"))
    if nav:
        kb.row(*nav)
    bot.send_message(chat_id, f"📁 الملفات • {page+1}/{pages}", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("filespage:"))
def files_page(call):
    if not is_admin(call.from_user.id):
        return
    answer(call)
    page = int(call.data.split(":", 1)[1])
    show_files_page(call.message.chat.id, page)


@bot.callback_query_handler(func=lambda c: c.data.startswith("filemanage:"))
def file_manage(call):
    if not is_admin(call.from_user.id):
        return
    fid = call.data.split(":", 1)[1]
    item = db.get("files", {}).get(fid)
    if not item:
        return answer(call, "غير موجود.", True)
    kb = types.InlineKeyboardMarkup()
    kb.add(inline_button("🗑️ حذف", callback_data=f"delfile:{fid}"))
    bot.send_message(
        call.message.chat.id,
        f"📄 <b>{esc(item.get('name'))}</b>\n📥 {item.get('downloads',0)} تحميل\n"
        f"🔗 <code>{BOT_LINK}?start={fid}</code>",
        parse_mode="HTML", reply_markup=kb
    )
    answer(call)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delfile:"))
def delete_file(call):
    if not is_admin(call.from_user.id):
        return
    fid = call.data.split(":", 1)[1]
    db.get("files", {}).pop(fid, None)
    save_db()
    answer(call, "✅ تم الحذف.")
    try:
        bot.edit_message_text("✅ تم حذف الملف.", call.message.chat.id, call.message.message_id)
    except Exception:
        pass


# ============================================================
# CHANNELS - FIXED
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📡 القنوات")
def channels_menu(m):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(inline_button("➕ إضافة قناة", callback_data="channel:add"))
    kb.add(inline_button("📋 عرض / حذف القنوات", callback_data="channel:list"))
    bot.send_message(
        m.chat.id,
        "📡 <b>إدارة الاشتراك الإجباري</b>\n\n"
        "⚠️ يجب إضافة البوت للقناة ورفعه مشرفاً.",
        parse_mode="HTML", reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data == "channel:add")
def channel_add_start(call):
    if not is_admin(call.from_user.id):
        return
    answer(call)
    set_state(call.from_user.id, step="add_channel")
    bot.send_message(
        call.message.chat.id,
        "📢 أرسل معرف القناة مثل:\n<code>@mf5rt</code>\n\n"
        "أو ID قناة خاصة مثل:\n<code>-1001234567890</code>\n\n"
        "👑 تأكد أن البوت مشرف بالقناة.",
        parse_mode="HTML"
    )


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "add_channel", content_types=["text"])
def channel_add_save(m):
    raw = m.text.strip()
    if raw.startswith("-100"):
        try:
            target = int(raw)
        except ValueError:
            return bot.send_message(m.chat.id, "❌ ID غير صحيح.")
    else:
        target = raw if raw.startswith("@") else "@" + raw

    try:
        chat = bot.get_chat(target)
        me = bot.get_me()
        member = bot.get_chat_member(chat.id, me.id)
        if member.status not in ("administrator", "creator"):
            return bot.send_message(
                m.chat.id,
                "❌ البوت وصل للقناة لكنه <b>ليس مشرفاً</b>.\nارفعه مشرف ثم أرسل القناة مرة ثانية.",
                parse_mode="HTML"
            )

        channel_id = chat.id
        if channel_id not in db["channels"]:
            db["channels"].append(channel_id)
            save_db()

        clear_state(m.from_user.id)
        uname = f"@{chat.username}" if getattr(chat, "username", None) else "قناة خاصة"
        bot.send_message(
            m.chat.id,
            f"✅ <b>تمت إضافة القناة</b>\n\n📢 {esc(chat.title)}\n🔗 {esc(uname)}\n🆔 <code>{chat.id}</code>",
            parse_mode="HTML", reply_markup=admin_kb()
        )
    except Exception as e:
        bot.send_message(
            m.chat.id,
            "❌ <b>تعذر إضافة القناة</b>\n\n"
            "تأكد من:\n"
            "• المعرف صحيح.\n"
            "• البوت موجود بالقناة.\n"
            "• البوت مشرف.\n"
            "• للقناة الخاصة استخدم ID يبدأ بـ -100.\n\n"
            f"⚙️ <code>{esc(e)}</code>",
            parse_mode="HTML"
        )


@bot.callback_query_handler(func=lambda c: c.data == "channel:list")
def channel_list(call):
    if not is_admin(call.from_user.id):
        return
    answer(call)
    channels = db.get("channels", [])
    if not channels:
        return bot.send_message(call.message.chat.id, "📭 لا توجد قنوات إجبارية.")
    kb = types.InlineKeyboardMarkup(row_width=1)
    for channel_id in channels:
        try:
            chat = bot.get_chat(channel_id)
            title = chat.title
        except Exception:
            title = str(channel_id)
        kb.add(inline_button(f"🗑️ {title}", callback_data=f"channelremove:{channel_id}"))
    bot.send_message(call.message.chat.id, "📋 اضغط على القناة لحذفها:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("channelremove:"))
def channel_remove(call):
    if not is_admin(call.from_user.id):
        return
    raw = call.data.split(":", 1)[1]
    try:
        cid = int(raw)
    except ValueError:
        cid = raw
    if cid in db.get("channels", []):
        db["channels"].remove(cid)
        save_db()
    answer(call, "✅ تم حذف القناة.")
    try:
        bot.edit_message_text("✅ تم حذف القناة من الاشتراك الإجباري.", call.message.chat.id, call.message.message_id)
    except Exception:
        pass


# ============================================================
# BROADCAST
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📣 إذاعة")
def broadcast_start(m):
    set_state(m.from_user.id, step="broadcast")
    bot.send_message(m.chat.id, "📣 أرسل الرسالة التي تريد إذاعتها:")


@bot.message_handler(
    func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "broadcast",
    content_types=["text", "photo", "video", "document", "audio"]
)
def broadcast_send(m):
    clear_state(m.from_user.id)
    status = bot.send_message(m.chat.id, "⏳ جاري الإرسال...")
    ok = fail = 0
    for uid in list(db.get("users", {}).keys()):
        try:
            bot.copy_message(uid, m.chat.id, m.message_id)
            ok += 1
        except Exception:
            fail += 1
        time.sleep(0.04)
    bot.edit_message_text(f"✅ تم: {ok}\n❌ فشل: {fail}", m.chat.id, status.message_id)
    log_admin(m.from_user.id, f"Broadcast ok={ok}, fail={fail}")


# ============================================================
# ADMIN USER SEARCH
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🔎 بحث مستخدم")
def user_search_start(m):
    set_state(m.from_user.id, step="admin_user_search")
    bot.send_message(m.chat.id, "🔎 أرسل ID المستخدم أو @username:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "admin_user_search", content_types=["text"])
def user_search(m):
    q = m.text.strip().replace("@", "").lower()
    clear_state(m.from_user.id)
    found = None
    for uid, u in db.get("users", {}).items():
        if uid == q or str(u.get("username", "")).lower() == q:
            found = (uid, u)
            break
    if not found:
        return bot.send_message(m.chat.id, "❌ المستخدم غير موجود.")
    uid, u = found
    bot.send_message(
        m.chat.id,
        f"👤 <b>{esc(u.get('first_name',''))}</b>\n"
        f"🆔 <code>{uid}</code>\n"
        f"🔗 @{esc(u.get('username',''))}\n"
        f"⭐ {u.get('points',0)} نقطة\n"
        f"📥 {u.get('downloads',0)} تحميل\n"
        f"🛍️ {len(u.get('purchases',[]))} مشتريات",
        parse_mode="HTML"
    )


# ============================================================
# BAN
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🚫 الحظر")
def ban_menu(m):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        inline_button("🚫 حظر", callback_data="ban:start"),
        inline_button("✅ فك الحظر", callback_data="unban:start")
    )
    bot.send_message(m.chat.id, "🚫 إدارة الحظر:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data in ("ban:start", "unban:start"))
def ban_start(call):
    if not is_admin(call.from_user.id):
        return
    action_name = "ban" if call.data.startswith("ban:") else "unban"
    set_state(call.from_user.id, step="ban_user", action=action_name)
    answer(call)
    bot.send_message(call.message.chat.id, "🆔 أرسل ID المستخدم:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "ban_user", content_types=["text"])
def ban_save(m):
    uid = m.text.strip()
    s = state(m.from_user.id)
    clear_state(m.from_user.id)
    if not uid.isdigit():
        return bot.send_message(m.chat.id, "❌ ID غير صحيح.")
    if s.get("action") == "ban":
        if uid not in db["banned"]:
            db["banned"].append(uid)
        text = "🚫 تم حظر المستخدم."
    else:
        if uid in db["banned"]:
            db["banned"].remove(uid)
        text = "✅ تم فك الحظر."
    save_db()
    bot.send_message(m.chat.id, text)


# ============================================================
# SETTINGS
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "⚙️ الإعدادات")
def settings_menu(m):
    maintenance = bool(db["settings"].get("maintenance"))
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(inline_button(
        "🟢 إيقاف الصيانة" if maintenance else "🔴 تشغيل الصيانة",
        callback_data="settings:maintenance"
    ))
    kb.add(inline_button("🎁 تعديل نقاط اليومية", callback_data="settings:daily"))
    kb.add(inline_button("📝 تعديل الترحيب", callback_data="settings:welcome"))
    bot.send_message(m.chat.id, "⚙️ <b>إعدادات البوت</b>", parse_mode="HTML", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "settings:maintenance")
def maintenance_toggle(call):
    if not is_admin(call.from_user.id):
        return
    db["settings"]["maintenance"] = not bool(db["settings"].get("maintenance"))
    save_db()
    answer(call, "✅ تم تغيير وضع الصيانة.", True)


@bot.callback_query_handler(func=lambda c: c.data == "settings:daily")
def daily_setting_start(call):
    if not is_admin(call.from_user.id):
        return
    set_state(call.from_user.id, step="set_daily")
    answer(call)
    bot.send_message(call.message.chat.id, "⭐ أرسل عدد نقاط اليومية:")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "set_daily", content_types=["text"])
def daily_setting_save(m):
    try:
        value = int(m.text.strip())
        if value < 0:
            raise ValueError
    except ValueError:
        return bot.send_message(m.chat.id, "❌ رقم غير صحيح.")
    db["settings"]["daily_points"] = value
    save_db()
    clear_state(m.from_user.id)
    bot.send_message(m.chat.id, f"✅ أصبحت اليومية {value} نقطة.")


@bot.callback_query_handler(func=lambda c: c.data == "settings:welcome")
def welcome_setting_start(call):
    if not is_admin(call.from_user.id):
        return
    set_state(call.from_user.id, step="set_welcome")
    answer(call)
    bot.send_message(call.message.chat.id, "📝 أرسل رسالة الترحيب الجديدة.\nيمكنك استخدام HTML بسيط مثل <b>النص</b>.")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state(m.from_user.id).get("step") == "set_welcome", content_types=["text"])
def welcome_setting_save(m):
    db["settings"]["welcome"] = m.text
    save_db()
    clear_state(m.from_user.id)
    bot.send_message(m.chat.id, "✅ تم تحديث رسالة الترحيب.")


# ============================================================
# STATS / BACKUP / EXPORT / LOGS
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📊 الإحصائيات")
def stats(m):
    bot.send_message(
        m.chat.id,
        f"📊 <b>إحصائيات XORE FILE</b>\n\n"
        f"👥 المستخدمون: {len(db.get('users',{}))}\n"
        f"📁 الملفات: {len(db.get('files',{}))}\n"
        f"🛍️ المنتجات: {len(db.get('store',{}))}\n"
        f"🎟️ الكوبونات: {len(db.get('coupons',{}))}\n"
        f"🚫 المحظورون: {len(db.get('banned',[]))}\n"
        f"📡 القنوات: {len(db.get('channels',[]))}\n"
        f"📥 الملفات المرسلة: {db.get('stats',{}).get('files_sent',0)}\n"
        f"🛒 عمليات الشراء: {db.get('stats',{}).get('store_sales',0)}",
        parse_mode="HTML"
    )


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "💾 نسخة احتياطية")
def backup(m):
    save_db()
    try:
        with open(DB_FILE, "rb") as f:
            bot.send_document(m.chat.id, f, caption="💾 نسخة احتياطية من قاعدة البيانات.")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ {esc(e)}", parse_mode="HTML")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📄 تصدير المستخدمين")
def export_users(m):
    path = "users_export.txt"
    try:
        with open(path, "w", encoding="utf-8") as f:
            for uid, u in db.get("users", {}).items():
                f.write(f"{uid} | @{u.get('username','')} | {u.get('first_name','')} | points={u.get('points',0)}\n")
        with open(path, "rb") as f:
            bot.send_document(m.chat.id, f, caption="📄 قائمة المستخدمين.")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📜 سجل الإدارة")
def logs(m):
    rows = db.get("admin_logs", [])
    if not rows:
        return bot.send_message(m.chat.id, "📭 السجل فارغ.")
    text = "\n".join(rows[-25:])
    bot.send_message(m.chat.id, f"📜 <b>آخر العمليات</b>\n\n<code>{esc(text[-3500:])}</code>", parse_mode="HTML")


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🧹 مسح السجل")
def clear_logs(m):
    db["admin_logs"] = []
    save_db()
    bot.send_message(m.chat.id, "🧹 تم مسح السجل.")


# ============================================================
# CANCEL
# ============================================================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "❌ إلغاء العملية")
def cancel(m):
    clear_state(m.from_user.id)
    bot.send_message(m.chat.id, "✅ تم إلغاء العملية.", reply_markup=admin_kb())


# ============================================================
# TRACK GROUPS
# ============================================================

@bot.my_chat_member_handler()
def track_groups(update):
    try:
        if update.chat.type not in ("group", "supergroup", "channel"):
            return
        cid = str(update.chat.id)
        status = update.new_chat_member.status
        if status in ("member", "administrator"):
            db["groups"][cid] = update.chat.title or ""
        elif status in ("left", "kicked"):
            db["groups"].pop(cid, None)
        save_db()
    except Exception:
        logging.exception("Group tracking failed")


# ============================================================
# RUN
# ============================================================

def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def run_bot():
    while True:
        try:
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True,
                allowed_updates=["message", "callback_query", "my_chat_member"]
            )
        except Exception:
            logging.exception("Polling crashed; restarting in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
