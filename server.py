import os
import json
import time
import uuid
import shutil
import threading
import logging
from datetime import datetime
from flask import Flask
import telebot
from telebot import types

# =========================================================
# XORE / PRO FILE & STORE BOT
# =========================================================

# =========================
# SECURITY / CONFIG
# =========================

# لا تضع التوكن الحقيقي هنا.
# ضعه في Environment Variables:
# BOT_TOKEN=123456:ABC...
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN غير موجود.\n"
        "أضف BOT_TOKEN إلى Environment Variables."
    )

BOT_USERNAME = os.environ.get(
    "BOT_USERNAME",
    "VISITTTTTBOT"
).replace("@", "").strip()

BOT_LINK = f"https://t.me/{BOT_USERNAME}"

# يمكن إضافة أكثر من مشرف:
# ADMIN_IDS=7075895496,123456789
ADMIN_IDS_ENV = os.environ.get(
    "ADMIN_IDS",
    "7075895496"
)

ADMINS = [
    x.strip()
    for x in ADMIN_IDS_ENV.split(",")
    if x.strip().isdigit()
]

DB_FILE = os.environ.get("DB_FILE", "database.json")
LOG_FILE = os.environ.get("LOG_FILE", "logs.txt")

DB_LOCK = threading.RLock()

# =========================
# FLASK KEEP ALIVE
# =========================

app = Flask(__name__)


@app.route("/")
def index():
    return {
        "status": "online",
        "bot": BOT_USERNAME,
        "version": "6.0"
    }


@app.route("/health")
def health():
    return {
        "ok": True,
        "time": datetime.now().isoformat()
    }


def keep_alive():
    def run():
        try:
            port = int(os.environ.get("PORT", "10000"))
            app.run(
                host="0.0.0.0",
                port=port,
                debug=False,
                use_reloader=False
            )
        except Exception:
            logging.exception("Flask Error")

    threading.Thread(
        target=run,
        daemon=True
    ).start()


# =========================
# LOGGING
# =========================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)


# =========================
# TELEGRAM
# =========================

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode=None
)


# =========================
# DATABASE
# =========================

def get_default_db():
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

            "welcome":
                "🔥 أهلاً بك في بوت الملفات والمتجر الرقمي!\n\n"
                "اختر ما يناسبك من الأزرار بالأسفل:",

            "btn1_text": "📢 قناة المطور",
            "btn1_url": "https://t.me/mf5rt1",

            "btn2_text": "➕ أضفني لقناتك",
            "btn2_url":
                f"https://t.me/{BOT_USERNAME}?startgroup=true",

            "developer_url":
                "https://t.me/xsaudi96",

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


def deep_merge(default, loaded):
    if not isinstance(default, dict):
        return loaded

    if not isinstance(loaded, dict):
        loaded = {}

    result = dict(default)

    for key, value in loaded.items():

        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(
                result[key],
                value
            )
        else:
            result[key] = value

    return result


def load_db():

    default = get_default_db()

    if not os.path.exists(DB_FILE):
        return default

    try:
        with open(
            DB_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            loaded = json.load(f)

        return deep_merge(
            default,
            loaded
        )

    except Exception:
        logging.exception(
            "Database load error"
        )

        return default


db = load_db()


def save_db():

    with DB_LOCK:

        try:

            temp_file = DB_FILE + ".tmp"

            with open(
                temp_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    db,
                    f,
                    ensure_ascii=False,
                    indent=4
                )

            os.replace(
                temp_file,
                DB_FILE
            )

        except Exception:
            logging.exception(
                "Database save error"
            )


# =========================
# STATES
# =========================

states = {}


def set_state(user_id, **data):
    states[int(user_id)] = data


def get_state(user_id):
    return states.get(
        int(user_id),
        {}
    )


def clear_state(user_id):
    states.pop(
        int(user_id),
        None
    )


# =========================
# HELPERS
# =========================

def is_admin(user_id):
    return str(user_id) in ADMINS


def is_banned(user_id):
    return str(user_id) in db.get(
        "banned",
        []
    )


def ensure_user(user):

    uid = str(user.id)

    created = False

    if uid not in db["users"]:

        db["users"][uid] = {
            "joined":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

            "username":
                user.username or "",

            "first_name":
                user.first_name or "",

            "downloads": 0,
            "points":
                db["settings"].get(
                    "join_points",
                    15
                ),

            "last_daily": "",
            "referred_by": None
        }

        db["stats"]["joins"] = (
            db["stats"].get(
                "joins",
                0
            ) + 1
        )

        created = True

    else:

        db["users"][uid]["username"] = (
            user.username or ""
        )

        db["users"][uid]["first_name"] = (
            user.first_name or ""
        )

    save_db()

    return created


def get_file_info(message):

    if message.content_type == "document":

        return (
            message.document.file_id,
            message.document.file_name
            or "file.bin",
            "document"
        )

    elif message.content_type == "video":

        return (
            message.video.file_id,
            getattr(
                message.video,
                "file_name",
                None
            ) or "video.mp4",
            "video"
        )

    elif message.content_type == "audio":

        return (
            message.audio.file_id,
            getattr(
                message.audio,
                "file_name",
                None
            ) or "audio.mp3",
            "audio"
        )

    elif message.content_type == "photo":

        return (
            message.photo[-1].file_id,
            "photo.jpg",
            "photo"
        )

    return None, None, None


def send_media(
    chat_id,
    file_id,
    file_type,
    caption="",
    reply_markup=None
):

    try:

        if file_type == "photo":

            return bot.send_photo(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

        elif file_type == "video":

            return bot.send_video(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

        elif file_type == "audio":

            return bot.send_audio(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

        else:

            return bot.send_document(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

    except Exception:
        logging.exception(
            "send_media error"
        )

        raise


def log_admin_action(
    admin_id,
    action
):

    entry = (
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"Admin {admin_id}: {action}"
    )

    db.setdefault(
        "admin_logs",
        []
    ).append(entry)

    # منع تضخم الملف
    if len(db["admin_logs"]) > 1000:
        db["admin_logs"] = (
            db["admin_logs"][-1000:]
        )

    save_db()


# =========================
# SUBSCRIPTION
# =========================

def check_sub(user_id):

    channels = db.get(
        "channels",
        []
    )

    if not channels:
        return True

    for channel in channels:

        try:

            member = bot.get_chat_member(
                channel,
                user_id
            )

            if member.status in [
                "left",
                "kicked"
            ]:
                return False

        except Exception:

            return False

    return True


def subscription_keyboard(fid):

    markup = types.InlineKeyboardMarkup(
        row_width=1
    )

    for channel in db.get(
        "channels",
        []
    ):

        try:

            chat = bot.get_chat(
                channel
            )

            url = None

            if getattr(
                chat,
                "username",
                None
            ):

                url = (
                    f"https://t.me/"
                    f"{chat.username}"
                )

            elif getattr(
                chat,
                "invite_link",
                None
            ):

                url = chat.invite_link

            if url:

                markup.add(
                    types.InlineKeyboardButton(
                        f"📢 {chat.title}",
                        url=url
                    )
                )

        except Exception:
            pass

    markup.add(
        types.InlineKeyboardButton(
            "🔄 تحقق من الاشتراك",
            callback_data=f"chk_{fid}"
        )
    )

    return markup


# =========================
# KEYBOARDS
# =========================

def get_admin_kb():

    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    kb.row(
        "📤 رفع ملف واحد",
        "📦 رفع ملفات متعددة"
    )

    kb.row(
        "🛒 إضافة للمتجر",
        "📋 إدارة المتجر"
    )

    kb.row(
        "📋 إدارة الملفات",
        "🎟️ إنشاء كوبون نقاط"
    )

    kb.row(
        "🔍 بحث عن مستخدم",
        "📢 الإذاعة"
    )

    kb.row(
        "⚙️ القنوات",
        "📊 الإحصائيات"
    )

    kb.row(
        "🚫 الحظر",
        "🛠️ الإعدادات المتقدمة"
    )

    kb.row(
        "📂 تصدير المستخدمين",
        "💾 نسخ احتياطي"
    )

    kb.row(
        "📜 سجل المشرفين",
        "🧹 تنظيف السجل"
    )

    kb.row(
        "🔙 إلغاء العملية الحالية"
    )

    return kb


def get_user_kb():

    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    kb.row(
        "🛒 المتجر الرقمي",
        "📊 إحصائياتي ونقاطي"
    )

    kb.row(
        "🎁 تسجيل الدخول اليومي",
        "🎟️ إدخال كوبون"
    )

    kb.row(
        "🔍 بحث عن ملف",
        "📞 تواصل مع المطور"
    )

    return kb


# =========================
# GROUP TRACKING
# =========================

@bot.my_chat_member_handler()
def track_groups(update):

    try:

        chat = update.chat

        if chat.type not in [
            "group",
            "supergroup",
            "channel"
        ]:
            return

        status = (
            update.new_chat_member.status
        )

        cid = str(chat.id)

        if status in [
            "member",
            "administrator"
        ]:

            db["groups"][cid] = (
                chat.title or "Unknown"
            )

            save_db()

        elif status in [
            "left",
            "kicked"
        ]:

            db["groups"].pop(
                cid,
                None
            )

            save_db()

    except Exception:
        logging.exception(
            "track_groups error"
        )


# =========================
# CANCEL
# =========================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "🔙 إلغاء العملية الحالية"
)
def cancel_admin_state(m):

    clear_state(
        m.from_user.id
    )

    bot.send_message(
        m.chat.id,
        "✅ تم إلغاء العملية الحالية.",
        reply_markup=get_admin_kb()
    )


# =========================
# START
# =========================

@bot.message_handler(
    commands=["start"]
)
def start_cmd(message):

    uid = str(
        message.from_user.id
    )

    if is_banned(uid):

        return bot.send_message(
            message.chat.id,
            "🚫 أنت محظور من استخدام البوت."
        )

    if (
        db["settings"].get(
            "maintenance"
        )
        and not is_admin(uid)
    ):

        return bot.send_message(
            message.chat.id,
            "🛠️ البوت في وضع الصيانة حالياً."
        )

    is_new = ensure_user(
        message.from_user
    )

    args = message.text.split(
        maxsplit=1
    )

    param = (
        args[1].strip()
        if len(args) > 1
        else None
    )

    # =================
    # REFERRAL
    # =================

    if (
        is_new
        and param
        and param.startswith("ref_")
    ):

        ref_id = param[4:]

        if (
            ref_id != uid
            and ref_id in db["users"]
        ):

            db["users"][uid][
                "referred_by"
            ] = ref_id

            reward = (
                db["settings"].get(
                    "referral_points",
                    10
                )
            )

            db["users"][ref_id][
                "points"
            ] = (
                db["users"][ref_id].get(
                    "points",
                    0
                )
                + reward
            )

            save_db()

            try:

                bot.send_message(
                    ref_id,
                    f"🎁 مستخدم جديد انضم من رابطك!\n"
                    f"⭐ حصلت على +{reward} نقاط."
                )

            except Exception:
                pass

    # =================
    # ADMIN HOME
    # =================

    if (
        is_admin(uid)
        and not param
    ):

        return bot.send_message(
            message.chat.id,
            "👑 أهلاً بك في لوحة تحكم الإدارة.",
            reply_markup=get_admin_kb()
        )

    # =================
    # STORE LINK
    # =================

    if (
        param
        and param.startswith("store_")
    ):

        item_id = param[6:]

        item = db.get(
            "store",
            {}
        ).get(item_id)

        if not item:

            return bot.send_message(
                message.chat.id,
                "❌ المنتج غير موجود أو تم حذفه."
            )

        price = int(
            item.get(
                "price",
                0
            )
        )

        price_text = (
            f"⭐ {price} نقاط"
            if price > 0
            else "🎁 مجاني"
        )

        kb = types.InlineKeyboardMarkup()

        kb.add(
            types.InlineKeyboardButton(
                f"🛒 الحصول على المنتج ({price_text})",
                callback_data=f"buy_{item_id}"
            )
        )

        caption = (
            f"🛒 <b>{item.get('name', 'منتج')}</b>\n\n"
            f"📝 {item.get('desc', '')}\n\n"
            f"💰 السعر: {price_text}"
        )

        try:

            send_media(
                message.chat.id,
                item["file_id"],
                item.get(
                    "file_type",
                    "document"
                ),
                caption,
                kb
            )

        except Exception:

            bot.send_message(
                message.chat.id,
                caption,
                parse_mode="HTML",
                reply_markup=kb
            )

        return

    # =================
    # FILE LINK
    # =================

    if (
        param
        and not param.startswith("ref_")
    ):

        fid = param

        if fid not in db.get(
            "files",
            {}
        ):

            return bot.send_message(
                message.chat.id,
                "❌ الملف غير موجود أو تم حذفه."
            )

        if not check_sub(
            message.from_user.id
        ):

            return bot.send_message(
                message.chat.id,
                "🔥 يجب الاشتراك في القنوات أولاً:",
                reply_markup=subscription_keyboard(
                    fid
                )
            )

        return send_file(
            message.chat.id,
            fid
        )

    # =================
    # NORMAL HOME
    # =================

    text = db["settings"].get(
        "welcome",
        "أهلاً بك!"
    )

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    kb.add(
        types.InlineKeyboardButton(
            "🔗 رابط الإحالة الخاص بك",
            callback_data="my_ref_link"
        )
    )

    developer_url = (
        db["settings"].get(
            "developer_url"
        )
    )

    if developer_url:

        kb.add(
            types.InlineKeyboardButton(
                "📞 تواصل مع المطور",
                url=developer_url
            )
        )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=kb
    )

    bot.send_message(
        message.chat.id,
        "اختر من القائمة:",
        reply_markup=get_user_kb()
    )


# =========================================================
# FILE SENDING
# =========================================================

def send_file(
    chat_id,
    fid
):

    file_data = db.get(
        "files",
        {}
    ).get(fid)

    if not file_data:

        return bot.send_message(
            chat_id,
            "❌ الملف غير موجود."
        )

    kb = types.InlineKeyboardMarkup(
        row_width=2
    )

    btn1_text = (
        db["settings"].get(
            "btn1_text",
            "📢 قناة المطور"
        )
    )

    btn1_url = (
        db["settings"].get(
            "btn1_url"
        )
    )

    btn2_text = (
        db["settings"].get(
            "btn2_text",
            "➕ أضفني لقناتك"
        )
    )

    btn2_url = (
        db["settings"].get(
            "btn2_url"
        )
    )

    buttons = []

    if btn1_url:

        buttons.append(
            types.InlineKeyboardButton(
                btn1_text,
                url=btn1_url
            )
        )

    if btn2_url:

        buttons.append(
            types.InlineKeyboardButton(
                btn2_text,
                url=btn2_url
            )
        )

    if buttons:
        kb.row(*buttons)

    try:

        send_media(
            chat_id,
            file_data["file_id"],
            file_data.get(
                "file_type",
                "document"
            ),
            file_data.get(
                "desc",
                ""
            ),
            kb
        )

        file_data["downloads"] = (
            file_data.get(
                "downloads",
                0
            ) + 1
        )

        db["stats"]["files_sent"] = (
            db["stats"].get(
                "files_sent",
                0
            ) + 1
        )

        uid = str(chat_id)

        if uid in db["users"]:

            db["users"][uid][
                "downloads"
            ] = (
                db["users"][uid].get(
                    "downloads",
                    0
                ) + 1
            )

        save_db()

    except Exception:

        bot.send_message(
            chat_id,
            "⚠️ حدث خطأ أثناء إرسال الملف."
        )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith("chk_")
)
def check_subscription_cb(call):

    fid = call.data[4:]

    if check_sub(
        call.from_user.id
    ):

        try:

            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )

        except Exception:
            pass

        send_file(
            call.message.chat.id,
            fid
        )

    else:

        bot.answer_callback_query(
            call.id,
            "❌ لم تشترك في جميع القنوات.",
            show_alert=True
        )


# =========================================================
# STORE
# =========================================================

@bot.message_handler(
    func=lambda m:
        m.text == "🛒 المتجر الرقمي"
)
def user_store_menu(m):

    ensure_user(
        m.from_user
    )

    show_store_page(
        m.chat.id,
        0
    )


def show_store_page(
    chat_id,
    page
):

    items = list(
        db.get(
            "store",
            {}
        ).items()
    )

    if not items:

        return bot.send_message(
            chat_id,
            "🛍️ المتجر فارغ حالياً."
        )

    per_page = 8

    total_pages = max(
        1,
        (
            len(items)
            + per_page
            - 1
        ) // per_page
    )

    page = max(
        0,
        min(
            page,
            total_pages - 1
        )
    )

    start = (
        page
        * per_page
    )

    chunk = items[
        start:
        start + per_page
    ]

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    for item_id, item in chunk:

        price = int(
            item.get(
                "price",
                0
            )
        )

        price_text = (
            f"⭐ {price}"
            if price > 0
            else "🎁 مجاني"
        )

        kb.add(
            types.InlineKeyboardButton(
                f"📦 {item.get('name', 'منتج')} • {price_text}",
                callback_data=f"buy_{item_id}"
            )
        )

    nav = []

    if page > 0:

        nav.append(
            types.InlineKeyboardButton(
                "⬅️ السابق",
                callback_data=f"storepg_{page - 1}"
            )
        )

    if page + 1 < total_pages:

        nav.append(
            types.InlineKeyboardButton(
                "التالي ➡️",
                callback_data=f"storepg_{page + 1}"
            )
        )

    if nav:
        kb.row(*nav)

    bot.send_message(
        chat_id,
        f"🛒 <b>المتجر الرقمي</b>\n\n"
        f"📄 الصفحة {page + 1}/{total_pages}",
        parse_mode="HTML",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith(
            "storepg_"
        )
)
def store_page_nav(call):

    try:
        page = int(
            call.data[
                len("storepg_"):
            ]
        )
    except ValueError:
        return

    bot.answer_callback_query(
        call.id
    )

    try:

        bot.delete_message(
            call.message.chat.id,
            call.message.message_id
        )

    except Exception:
        pass

    show_store_page(
        call.message.chat.id,
        page
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith("buy_")
)
def buy_store_item(call):

    ensure_user(
        call.from_user
    )

    item_id = call.data[4:]

    item = db.get(
        "store",
        {}
    ).get(item_id)

    if not item:

        return bot.answer_callback_query(
            call.id,
            "❌ المنتج غير موجود.",
            show_alert=True
        )

    uid = str(
        call.from_user.id
    )

    user = db["users"][uid]

    price = max(
        0,
        int(
            item.get(
                "price",
                0
            )
        )
    )

    points = int(
        user.get(
            "points",
            0
        )
    )

    if points < price:

        return bot.answer_callback_query(
            call.id,
            f"❌ رصيدك {points} نقطة، "
            f"والمنتج يحتاج {price}.",
            show_alert=True
        )

    # خصم بعد التأكد من إمكانية الإرسال
    try:

        send_media(
            call.message.chat.id,
            item["file_id"],
            item.get(
                "file_type",
                "document"
            ),
            (
                f"📦 <b>{item.get('name', 'منتج')}</b>\n\n"
                f"{item.get('desc', '')}"
            )
        )

    except Exception:

        return bot.answer_callback_query(
            call.id,
            "❌ تعذر إرسال المنتج.",
            show_alert=True
        )

    if price:

        db["users"][uid][
            "points"
        ] -= price

    db["stats"]["store_sales"] = (
        db["stats"].get(
            "store_sales",
            0
        ) + 1
    )

    save_db()

    bot.answer_callback_query(
        call.id,
        "✅ تم الحصول على المنتج."
    )


# =========================================================
# ADMIN ADD STORE ITEM
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "🛒 إضافة للمتجر"
)
def add_store_start(m):

    set_state(
        m.from_user.id,
        step="store_name"
    )

    bot.send_message(
        m.chat.id,
        "🛒 أرسل اسم المنتج:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "store_name",
    content_types=["text"]
)
def add_store_name(m):

    state = get_state(
        m.from_user.id
    )

    state["name"] = m.text.strip()
    state["step"] = "store_desc"

    bot.send_message(
        m.chat.id,
        "📝 أرسل وصف المنتج:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "store_desc",
    content_types=["text"]
)
def add_store_desc(m):

    state = get_state(
        m.from_user.id
    )

    state["desc"] = m.text
    state["step"] = "store_price"

    bot.send_message(
        m.chat.id,
        "💰 أرسل السعر بالنقاط.\n"
        "اكتب 0 للمنتج المجاني:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "store_price",
    content_types=["text"]
)
def add_store_price(m):

    try:

        price = int(
            m.text.strip()
        )

        if price < 0:
            raise ValueError

    except ValueError:

        return bot.send_message(
            m.chat.id,
            "❌ السعر يجب أن يكون 0 أو أكثر."
        )

    state = get_state(
        m.from_user.id
    )

    state["price"] = price
    state["step"] = "store_file"

    bot.send_message(
        m.chat.id,
        "📁 أرسل ملف/صورة/فيديو/صوت المنتج:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "store_file",
    content_types=[
        "document",
        "photo",
        "video",
        "audio"
    ]
)
def add_store_file(m):

    file_id, filename, file_type = (
        get_file_info(m)
    )

    if not file_id:

        return bot.send_message(
            m.chat.id,
            "❌ نوع الملف غير مدعوم."
        )

    state = get_state(
        m.from_user.id
    )

    item_id = uuid.uuid4().hex[:8]

    db["store"][item_id] = {
        "name": state["name"],
        "desc": state["desc"],
        "price": state["price"],
        "file_id": file_id,
        "file_type": file_type,
        "filename": filename,
        "date":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        "sales": 0
    }

    save_db()

    log_admin_action(
        m.from_user.id,
        f"Added store item {item_id}"
    )

    clear_state(
        m.from_user.id
    )

    link = (
        f"{BOT_LINK}"
        f"?start=store_{item_id}"
    )

    bot.send_message(
        m.chat.id,
        "✅ <b>تم إضافة المنتج.</b>\n\n"
        f"🔗 <code>{link}</code>",
        parse_mode="HTML",
        reply_markup=get_admin_kb()
    )


# =========================================================
# MANAGE STORE
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📋 إدارة المتجر"
)
def manage_store(m):

    items = db.get(
        "store",
        {}
    )

    if not items:

        return bot.send_message(
            m.chat.id,
            "⚠️ المتجر فارغ."
        )

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    for item_id, item in list(
        items.items()
    )[:50]:

        kb.add(
            types.InlineKeyboardButton(
                f"🗑️ {item.get('name', item_id)}",
                callback_data=f"delstore_{item_id}"
            )
        )

    bot.send_message(
        m.chat.id,
        "📋 إدارة المتجر:",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith(
            "delstore_"
        )
)
def delete_store_item(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    item_id = call.data[
        len("delstore_"):
    ]

    if item_id in db["store"]:

        name = db["store"][
            item_id
        ].get(
            "name",
            item_id
        )

        del db["store"][item_id]

        save_db()

        log_admin_action(
            call.from_user.id,
            f"Deleted store item {name}"
        )

    bot.answer_callback_query(
        call.id,
        "✅ تم الحذف."
    )

    try:

        bot.edit_message_text(
            "✅ تم حذف المنتج.",
            call.message.chat.id,
            call.message.message_id
        )

    except Exception:
        pass


# =========================================================
# COUPONS
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "🎟️ إنشاء كوبون نقاط"
)
def coupon_start(m):

    set_state(
        m.from_user.id,
        step="coupon_code"
    )

    bot.send_message(
        m.chat.id,
        "🎟️ أرسل كود الكوبون:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "coupon_code",
    content_types=["text"]
)
def coupon_code(m):

    code = (
        m.text.strip().upper()
    )

    if len(code) < 2:

        return bot.send_message(
            m.chat.id,
            "❌ الكود قصير جداً."
        )

    state = get_state(
        m.from_user.id
    )

    state["code"] = code
    state["step"] = "coupon_points"

    bot.send_message(
        m.chat.id,
        "⭐ أرسل عدد النقاط:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "coupon_points",
    content_types=["text"]
)
def coupon_points(m):

    try:

        points = int(
            m.text.strip()
        )

        if points <= 0:
            raise ValueError

    except ValueError:

        return bot.send_message(
            m.chat.id,
            "❌ أدخل عدداً أكبر من صفر."
        )

    state = get_state(
        m.from_user.id
    )

    code = state["code"]

    db["coupons"][code] = {
        "points": points,
        "used_by": [],
        "created_at":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
    }

    save_db()

    clear_state(
        m.from_user.id
    )

    log_admin_action(
        m.from_user.id,
        f"Created coupon {code}"
    )

    bot.send_message(
        m.chat.id,
        f"✅ تم إنشاء الكوبون.\n\n"
        f"🎟️ <code>{code}</code>\n"
        f"⭐ {points} نقطة",
        parse_mode="HTML",
        reply_markup=get_admin_kb()
    )


@bot.message_handler(
    func=lambda m:
        m.text
        == "🎟️ إدخال كوبون"
)
def redeem_start(m):

    ensure_user(
        m.from_user
    )

    set_state(
        m.from_user.id,
        step="redeem_coupon"
    )

    bot.send_message(
        m.chat.id,
        "🎟️ أرسل الكوبون:"
    )


@bot.message_handler(
    func=lambda m:
        get_state(
            m.from_user.id
        ).get("step")
        == "redeem_coupon",
    content_types=["text"]
)
def redeem_coupon(m):

    uid = str(
        m.from_user.id
    )

    ensure_user(
        m.from_user
    )

    code = (
        m.text.strip().upper()
    )

    clear_state(
        m.from_user.id
    )

    coupon = db.get(
        "coupons",
        {}
    ).get(code)

    if not coupon:

        return bot.send_message(
            m.chat.id,
            "❌ الكوبون غير صالح."
        )

    used_by = coupon.setdefault(
        "used_by",
        []
    )

    if uid in used_by:

        return bot.send_message(
            m.chat.id,
            "⚠️ استخدمت هذا الكوبون مسبقاً."
        )

    used_by.append(uid)

    points = int(
        coupon.get(
            "points",
            0
        )
    )

    db["users"][uid]["points"] = (
        db["users"][uid].get(
            "points",
            0
        ) + points
    )

    save_db()

    bot.send_message(
        m.chat.id,
        f"🎉 تم إضافة {points} نقطة إلى حسابك."
    )


# =========================================================
# USER STATS
# =========================================================

@bot.message_handler(
    func=lambda m:
        m.text
        == "📊 إحصائياتي ونقاطي"
)
def user_stats(m):

    ensure_user(
        m.from_user
    )

    uid = str(
        m.from_user.id
    )

    user = db["users"][uid]

    bot.send_message(
        m.chat.id,
        "👤 <b>ملفك الشخصي</b>\n\n"
        f"🆔 <code>{uid}</code>\n"
        f"📥 التحميلات: {user.get('downloads', 0)}\n"
        f"⭐ النقاط: {user.get('points', 0)}\n"
        f"📅 الانضمام: {user.get('joined', '-')}",
        parse_mode="HTML"
    )


# =========================================================
# DAILY
# =========================================================

@bot.message_handler(
    func=lambda m:
        m.text
        == "🎁 تسجيل الدخول اليومي"
)
def daily_bonus(m):

    ensure_user(
        m.from_user
    )

    uid = str(
        m.from_user.id
    )

    user = db["users"][uid]

    today = (
        datetime.now().strftime(
            "%Y-%m-%d"
        )
    )

    if (
        user.get("last_daily")
        == today
    ):

        return bot.send_message(
            m.chat.id,
            "⏳ أخذت مكافأة اليوم بالفعل."
        )

    bonus = int(
        db["settings"].get(
            "daily_points",
            10
        )
    )

    user["points"] = (
        user.get(
            "points",
            0
        ) + bonus
    )

    user["last_daily"] = today

    save_db()

    bot.send_message(
        m.chat.id,
        f"🎁 حصلت على +{bonus} نقاط."
    )


# =========================================================
# REFERRAL
# =========================================================

@bot.callback_query_handler(
    func=lambda c:
        c.data
        == "my_ref_link"
)
def ref_link(call):

    link = (
        f"{BOT_LINK}"
        f"?start=ref_{call.from_user.id}"
    )

    bot.answer_callback_query(
        call.id
    )

    bot.send_message(
        call.message.chat.id,
        "🔗 <b>رابط الإحالة:</b>\n\n"
        f"<code>{link}</code>",
        parse_mode="HTML"
    )


# =========================================================
# USER FILE SEARCH
# =========================================================

@bot.message_handler(
    func=lambda m:
        m.text
        == "🔍 بحث عن ملف"
)
def user_file_search_start(m):

    set_state(
        m.from_user.id,
        step="user_search_file"
    )

    bot.send_message(
        m.chat.id,
        "🔍 اكتب اسم الملف:"
    )


@bot.message_handler(
    func=lambda m:
        get_state(
            m.from_user.id
        ).get("step")
        == "user_search_file",
    content_types=["text"]
)
def user_file_search(m):

    query = (
        m.text.strip().lower()
    )

    clear_state(
        m.from_user.id
    )

    results = []

    for fid, info in db.get(
        "files",
        {}
    ).items():

        if query in (
            info.get(
                "name",
                ""
            ).lower()
        ):

            results.append(
                (fid, info)
            )

    if not results:

        return bot.send_message(
            m.chat.id,
            "❌ لم أجد ملفاً بهذا الاسم.",
            reply_markup=get_user_kb()
        )

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    for fid, info in results[:20]:

        kb.add(
            types.InlineKeyboardButton(
                f"📄 {info.get('name', 'ملف')[:40]}",
                url=f"{BOT_LINK}?start={fid}"
            )
        )

    bot.send_message(
        m.chat.id,
        f"🔍 النتائج: {len(results)}",
        reply_markup=kb
    )


# =========================================================
# CONTACT / TICKETS
# =========================================================

@bot.message_handler(
    func=lambda m:
        m.text
        == "📞 تواصل مع المطور"
)
def contact_start(m):

    set_state(
        m.from_user.id,
        step="user_ticket"
    )

    bot.send_message(
        m.chat.id,
        "💬 أرسل رسالتك للمطور:"
    )


@bot.message_handler(
    func=lambda m:
        get_state(
            m.from_user.id
        ).get("step")
        == "user_ticket",
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio",
        "voice"
    ]
)
def handle_ticket(m):

    uid = m.from_user.id

    clear_state(uid)

    for admin in ADMINS:

        try:

            bot.forward_message(
                admin,
                m.chat.id,
                m.message_id
            )

            kb = (
                types.InlineKeyboardMarkup()
            )

            kb.add(
                types.InlineKeyboardButton(
                    "💬 الرد",
                    callback_data=f"reply_{uid}"
                )
            )

            bot.send_message(
                admin,
                f"📩 رسالة من المستخدم:\n"
                f"<code>{uid}</code>",
                parse_mode="HTML",
                reply_markup=kb
            )

        except Exception:
            logging.exception(
                "ticket forward error"
            )

    bot.send_message(
        m.chat.id,
        "✅ تم إرسال رسالتك."
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith("reply_")
)
def admin_reply_start(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    uid = call.data[6:]

    set_state(
        call.from_user.id,
        step="admin_reply",
        target_uid=uid
    )

    bot.send_message(
        call.message.chat.id,
        f"💬 أرسل ردك للمستخدم:\n"
        f"<code>{uid}</code>",
        parse_mode="HTML"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "admin_reply",
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio",
        "voice"
    ]
)
def admin_reply_send(m):

    state = get_state(
        m.from_user.id
    )

    target = state.get(
        "target_uid"
    )

    clear_state(
        m.from_user.id
    )

    try:

        bot.send_message(
            target,
            "💬 <b>رد من الإدارة:</b>",
            parse_mode="HTML"
        )

        bot.copy_message(
            target,
            m.chat.id,
            m.message_id
        )

        bot.send_message(
            m.chat.id,
            "✅ تم إرسال الرد."
        )

    except Exception as e:

        bot.send_message(
            m.chat.id,
            f"❌ فشل الإرسال:\n{e}"
        )


# =========================================================
# SINGLE FILE UPLOAD
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📤 رفع ملف واحد"
)
def single_start(m):

    set_state(
        m.from_user.id,
        step="single_desc"
    )

    bot.send_message(
        m.chat.id,
        "📝 أرسل وصف الملف:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "single_desc",
    content_types=["text"]
)
def single_desc(m):

    state = get_state(
        m.from_user.id
    )

    state["desc"] = m.text
    state["step"] = "single_file"

    bot.send_message(
        m.chat.id,
        "📤 أرسل الملف الآن:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "single_file",
    content_types=[
        "document",
        "video",
        "audio",
        "photo"
    ]
)
def single_file(m):

    file_id, name, file_type = (
        get_file_info(m)
    )

    if not file_id:

        return

    state = get_state(
        m.from_user.id
    )

    fid = uuid.uuid4().hex[:8]

    db["files"][fid] = {
        "file_id": file_id,
        "file_type": file_type,
        "name": name,
        "desc": state.get(
            "desc",
            ""
        ),
        "date":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        "downloads": 0
    }

    save_db()

    log_admin_action(
        m.from_user.id,
        f"Uploaded file {fid}: {name}"
    )

    clear_state(
        m.from_user.id
    )

    bot.send_message(
        m.chat.id,
        "✅ تم الرفع.\n\n"
        f"🔗 <code>{BOT_LINK}?start={fid}</code>",
        parse_mode="HTML",
        reply_markup=get_admin_kb()
    )


# =========================================================
# BATCH UPLOAD
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📦 رفع ملفات متعددة"
)
def batch_start(m):

    set_state(
        m.from_user.id,
        step="batch_desc"
    )

    bot.send_message(
        m.chat.id,
        "📝 أرسل الوصف الموحد:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "batch_desc",
    content_types=["text"]
)
def batch_desc(m):

    state = get_state(
        m.from_user.id
    )

    state["desc"] = m.text
    state["step"] = "batch_files"
    state["count"] = 0
    state["links"] = []

    bot.send_message(
        m.chat.id,
        "📦 أرسل الملفات واحداً واحداً.\n\n"
        "عند الانتهاء أرسل:\n"
        "/done"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "batch_files",
    content_types=[
        "document",
        "video",
        "audio",
        "photo"
    ]
)
def batch_file(m):

    file_id, name, file_type = (
        get_file_info(m)
    )

    if not file_id:
        return

    state = get_state(
        m.from_user.id
    )

    fid = uuid.uuid4().hex[:8]

    db["files"][fid] = {
        "file_id": file_id,
        "file_type": file_type,
        "name": name,
        "desc": state.get(
            "desc",
            ""
        ),
        "date":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        "downloads": 0
    }

    state["count"] += 1

    state["links"].append(
        f"{BOT_LINK}?start={fid}"
    )

    save_db()

    bot.send_message(
        m.chat.id,
        f"✅ #{state['count']} • {name}"
    )


@bot.message_handler(
    commands=["done"]
)
def batch_done(m):

    if not is_admin(
        m.from_user.id
    ):
        return

    state = get_state(
        m.from_user.id
    )

    if state.get(
        "step"
    ) != "batch_files":

        return

    count = state.get(
        "count",
        0
    )

    links = state.get(
        "links",
        []
    )

    clear_state(
        m.from_user.id
    )

    text = (
        f"🎉 تم رفع {count} ملف."
    )

    if links:

        text += (
            "\n\n🔗 الروابط:\n"
            + "\n".join(
                links[:30]
            )
        )

    bot.send_message(
        m.chat.id,
        text,
        reply_markup=get_admin_kb()
    )


# =========================================================
# FILE MANAGEMENT
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📋 إدارة الملفات"
)
def manage_files(m):

    if not db.get(
        "files"
    ):

        return bot.send_message(
            m.chat.id,
            "⚠️ لا توجد ملفات."
        )

    show_files_page(
        m.chat.id,
        0
    )


def show_files_page(
    chat_id,
    page
):

    files = list(
        db.get(
            "files",
            {}
        ).items()
    )

    per_page = 5

    total_pages = max(
        1,
        (
            len(files)
            + per_page
            - 1
        ) // per_page
    )

    page = max(
        0,
        min(
            page,
            total_pages - 1
        )
    )

    start = (
        page
        * per_page
    )

    chunk = files[
        start:
        start + per_page
    ]

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    for fid, info in chunk:

        kb.add(
            types.InlineKeyboardButton(
                f"📄 {info.get('name', 'ملف')[:35]}",
                callback_data=f"v_{fid}"
            )
        )

    nav = []

    if page > 0:

        nav.append(
            types.InlineKeyboardButton(
                "⬅️",
                callback_data=f"pg_{page - 1}"
            )
        )

    if page + 1 < total_pages:

        nav.append(
            types.InlineKeyboardButton(
                "➡️",
                callback_data=f"pg_{page + 1}"
            )
        )

    if nav:
        kb.row(*nav)

    bot.send_message(
        chat_id,
        f"📋 الملفات\n"
        f"صفحة {page + 1}/{total_pages}",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith("pg_")
)
def files_page(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    try:

        page = int(
            call.data[3:]
        )

    except ValueError:
        return

    try:

        bot.delete_message(
            call.message.chat.id,
            call.message.message_id
        )

    except Exception:
        pass

    show_files_page(
        call.message.chat.id,
        page
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith("v_")
)
def view_file(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    fid = call.data[2:]

    info = db.get(
        "files",
        {}
    ).get(fid)

    if not info:

        return bot.answer_callback_query(
            call.id,
            "الملف غير موجود."
        )

    kb = types.InlineKeyboardMarkup()

    kb.add(
        types.InlineKeyboardButton(
            "🗑️ حذف الملف",
            callback_data=f"delf_{fid}"
        )
    )

    bot.edit_message_text(
        f"📄 <b>{info.get('name', 'ملف')}</b>\n\n"
        f"📥 التحميلات: {info.get('downloads', 0)}\n"
        f"📅 {info.get('date', '-')}\n\n"
        f"🔗 <code>{BOT_LINK}?start={fid}</code>",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith("delf_")
)
def delete_file(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    fid = call.data[5:]

    if fid in db["files"]:

        name = db["files"][
            fid
        ].get(
            "name",
            fid
        )

        del db["files"][fid]

        save_db()

        log_admin_action(
            call.from_user.id,
            f"Deleted file {name}"
        )

    bot.edit_message_text(
        "✅ تم حذف الملف.",
        call.message.chat.id,
        call.message.message_id
    )


# =========================================================
# BROADCAST
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📢 الإذاعة"
)
def broadcast_menu(m):

    kb = types.InlineKeyboardMarkup()

    kb.add(
        types.InlineKeyboardButton(
            "👥 إذاعة للمستخدمين",
            callback_data="bc_users"
        )
    )

    bot.send_message(
        m.chat.id,
        "📢 اختر:",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data == "bc_users"
)
def broadcast_start(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    set_state(
        call.from_user.id,
        step="broadcast"
    )

    bot.send_message(
        call.message.chat.id,
        "📢 أرسل الرسالة:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "broadcast",
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio"
    ]
)
def broadcast_send(m):

    clear_state(
        m.from_user.id
    )

    progress = bot.send_message(
        m.chat.id,
        "⏳ جاري الإرسال..."
    )

    success = 0
    failed = 0

    for uid in list(
        db.get(
            "users",
            {}
        ).keys()
    ):

        try:

            bot.copy_message(
                uid,
                m.chat.id,
                m.message_id
            )

            success += 1

        except Exception:

            failed += 1

        time.sleep(0.04)

    bot.edit_message_text(
        f"✅ نجح: {success}\n"
        f"❌ فشل: {failed}",
        m.chat.id,
        progress.message_id
    )

    log_admin_action(
        m.from_user.id,
        f"Broadcast success={success} failed={failed}"
    )


# =========================================================
# ADMIN USER SEARCH
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "🔍 بحث عن مستخدم"
)
def admin_user_search_start(m):

    set_state(
        m.from_user.id,
        step="admin_user_search"
    )

    bot.send_message(
        m.chat.id,
        "🔍 أرسل ID المستخدم أو Username:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "admin_user_search",
    content_types=["text"]
)
def admin_user_search(m):

    query = (
        m.text.strip()
        .replace("@", "")
        .lower()
    )

    clear_state(
        m.from_user.id
    )

    found = None

    for uid, user in db.get(
        "users",
        {}
    ).items():

        username = (
            user.get(
                "username",
                ""
            ).lower()
        )

        if (
            uid == query
            or username == query
        ):

            found = (
                uid,
                user
            )

            break

    if not found:

        return bot.send_message(
            m.chat.id,
            "❌ المستخدم غير موجود."
        )

    uid, user = found

    bot.send_message(
        m.chat.id,
        "👤 <b>المستخدم</b>\n\n"
        f"🆔 <code>{uid}</code>\n"
        f"👤 @{user.get('username', '-')}\n"
        f"⭐ النقاط: {user.get('points', 0)}\n"
        f"📥 التحميلات: {user.get('downloads', 0)}\n"
        f"📅 الانضمام: {user.get('joined', '-')}",
        parse_mode="HTML"
    )


# =========================================================
# CHANNEL MANAGEMENT
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "⚙️ القنوات"
)
def channels_menu(m):

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    kb.add(
        types.InlineKeyboardButton(
            "➕ إضافة قناة",
            callback_data="add_channel"
        )
    )

    kb.add(
        types.InlineKeyboardButton(
            "📋 عرض القنوات",
            callback_data="list_channels"
        )
    )

    bot.send_message(
        m.chat.id,
        "⚙️ إدارة الاشتراك الإجباري:",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data == "add_channel"
)
def add_channel_start(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    set_state(
        call.from_user.id,
        step="add_channel"
    )

    bot.send_message(
        call.message.chat.id,
        "📢 أرسل Username القناة مثل:\n"
        "@channel\n\n"
        "أو ID القناة مثل:\n"
        "-100123456789"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "add_channel",
    content_types=["text"]
)
def add_channel_save(m):

    channel = (
        m.text.strip()
    )

    clear_state(
        m.from_user.id
    )

    if (
        channel.startswith("-")
        and channel[1:].isdigit()
    ):

        channel_value = int(
            channel
        )

    else:

        if not channel.startswith("@"):
            channel = "@" + channel

        channel_value = channel

    try:

        chat = bot.get_chat(
            channel_value
        )

    except Exception as e:

        return bot.send_message(
            m.chat.id,
            f"❌ تعذر الوصول للقناة.\n{e}"
        )

    if (
        channel_value
        not in db["channels"]
    ):

        db["channels"].append(
            channel_value
        )

        save_db()

    bot.send_message(
        m.chat.id,
        f"✅ تمت إضافة:\n"
        f"{chat.title}"
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data == "list_channels"
)
def list_channels(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    channels = db.get(
        "channels",
        []
    )

    if not channels:

        return bot.send_message(
            call.message.chat.id,
            "لا توجد قنوات."
        )

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    for index, channel in enumerate(
        channels
    ):

        try:

            chat = bot.get_chat(
                channel
            )

            name = chat.title

        except Exception:

            name = str(channel)

        kb.add(
            types.InlineKeyboardButton(
                f"🗑️ {name}",
                callback_data=f"rmch_{index}"
            )
        )

    bot.send_message(
        call.message.chat.id,
        "📋 اضغط على قناة لحذفها:",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data.startswith("rmch_")
)
def remove_channel(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    try:

        index = int(
            call.data[5:]
        )

        db["channels"].pop(
            index
        )

        save_db()

        bot.edit_message_text(
            "✅ تم حذف القناة.",
            call.message.chat.id,
            call.message.message_id
        )

    except Exception:

        bot.answer_callback_query(
            call.id,
            "❌ تعذر الحذف."
        )


# =========================================================
# BAN MANAGEMENT
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "🚫 الحظر"
)
def ban_menu(m):

    kb = types.InlineKeyboardMarkup(
        row_width=2
    )

    kb.add(
        types.InlineKeyboardButton(
            "🚫 حظر",
            callback_data="ban_user"
        ),

        types.InlineKeyboardButton(
            "✅ فك حظر",
            callback_data="unban_user"
        )
    )

    bot.send_message(
        m.chat.id,
        "🚫 إدارة الحظر:",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data in [
            "ban_user",
            "unban_user"
        ]
)
def ban_action_start(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    action = (
        "ban"
        if call.data == "ban_user"
        else "unban"
    )

    set_state(
        call.from_user.id,
        step="ban_action",
        action=action
    )

    bot.send_message(
        call.message.chat.id,
        "🆔 أرسل ID المستخدم:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "ban_action",
    content_types=["text"]
)
def ban_action(m):

    state = get_state(
        m.from_user.id
    )

    uid = m.text.strip()

    action = state.get(
        "action"
    )

    clear_state(
        m.from_user.id
    )

    if not uid.isdigit():

        return bot.send_message(
            m.chat.id,
            "❌ ID غير صحيح."
        )

    if action == "ban":

        if uid not in db["banned"]:

            db["banned"].append(
                uid
            )

        text = "🚫 تم حظر المستخدم."

    else:

        if uid in db["banned"]:

            db["banned"].remove(
                uid
            )

        text = "✅ تم فك الحظر."

    save_db()

    log_admin_action(
        m.from_user.id,
        f"{action} user {uid}"
    )

    bot.send_message(
        m.chat.id,
        text
    )


# =========================================================
# SETTINGS
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "🛠️ الإعدادات المتقدمة"
)
def advanced_settings(m):

    maintenance = (
        db["settings"].get(
            "maintenance",
            False
        )
    )

    kb = types.InlineKeyboardMarkup(
        row_width=1
    )

    kb.add(
        types.InlineKeyboardButton(
            (
                "🟢 إيقاف الصيانة"
                if maintenance
                else "🔴 تشغيل الصيانة"
            ),
            callback_data="toggle_maintenance"
        )
    )

    kb.add(
        types.InlineKeyboardButton(
            "🎁 تعديل نقاط اليومية",
            callback_data="set_daily"
        )
    )

    kb.add(
        types.InlineKeyboardButton(
            "📝 تعديل رسالة الترحيب",
            callback_data="set_welcome"
        )
    )

    bot.send_message(
        m.chat.id,
        "🛠️ الإعدادات:",
        reply_markup=kb
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data == "toggle_maintenance"
)
def toggle_maintenance(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    current = bool(
        db["settings"].get(
            "maintenance",
            False
        )
    )

    db["settings"][
        "maintenance"
    ] = not current

    save_db()

    bot.answer_callback_query(
        call.id,
        (
            "تم تشغيل الصيانة"
            if not current
            else "تم إيقاف الصيانة"
        ),
        show_alert=True
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data == "set_daily"
)
def set_daily_start(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    set_state(
        call.from_user.id,
        step="set_daily"
    )

    bot.send_message(
        call.message.chat.id,
        "⭐ أرسل عدد نقاط اليومية:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "set_daily",
    content_types=["text"]
)
def set_daily_save(m):

    try:

        points = int(
            m.text.strip()
        )

        if points < 0:
            raise ValueError

    except ValueError:

        return bot.send_message(
            m.chat.id,
            "❌ رقم غير صحيح."
        )

    db["settings"][
        "daily_points"
    ] = points

    save_db()

    clear_state(
        m.from_user.id
    )

    bot.send_message(
        m.chat.id,
        f"✅ اليومية أصبحت {points} نقطة."
    )


@bot.callback_query_handler(
    func=lambda c:
        c.data == "set_welcome"
)
def set_welcome_start(call):

    if not is_admin(
        call.from_user.id
    ):
        return

    set_state(
        call.from_user.id,
        step="set_welcome"
    )

    bot.send_message(
        call.message.chat.id,
        "📝 أرسل رسالة الترحيب الجديدة:"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and get_state(
            m.from_user.id
        ).get("step")
        == "set_welcome",
    content_types=["text"]
)
def set_welcome_save(m):

    db["settings"][
        "welcome"
    ] = m.text

    save_db()

    clear_state(
        m.from_user.id
    )

    bot.send_message(
        m.chat.id,
        "✅ تم تحديث رسالة الترحيب."
    )


# =========================================================
# STATISTICS
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📊 الإحصائيات"
)
def admin_stats(m):

    bot.send_message(
        m.chat.id,
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👥 المستخدمون: {len(db.get('users', {}))}\n"
        f"📁 الملفات: {len(db.get('files', {}))}\n"
        f"🛒 المنتجات: {len(db.get('store', {}))}\n"
        f"🎟️ الكوبونات: {len(db.get('coupons', {}))}\n"
        f"🚫 المحظورون: {len(db.get('banned', []))}\n"
        f"📢 القنوات: {len(db.get('channels', []))}\n"
        f"📥 الملفات المرسلة: "
        f"{db.get('stats', {}).get('files_sent', 0)}\n"
        f"💰 عمليات المتجر: "
        f"{db.get('stats', {}).get('store_sales', 0)}",
        parse_mode="HTML"
    )


# =========================================================
# EXPORT USERS
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📂 تصدير المستخدمين"
)
def export_users(m):

    filename = (
        "users_export.txt"
    )

    try:

        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as f:

            for uid, user in db.get(
                "users",
                {}
            ).items():

                f.write(
                    f"{uid} | "
                    f"@{user.get('username', '')} | "
                    f"{user.get('first_name', '')} | "
                    f"Points={user.get('points', 0)}\n"
                )

        with open(
            filename,
            "rb"
        ) as f:

            bot.send_document(
                m.chat.id,
                f,
                caption="📂 قائمة المستخدمين."
            )

    except Exception as e:

        bot.send_message(
            m.chat.id,
            f"❌ {e}"
        )

    finally:

        try:
            os.remove(filename)
        except Exception:
            pass


# =========================================================
# BACKUP
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "💾 نسخ احتياطي"
)
def backup_db(m):

    save_db()

    try:

        with open(
            DB_FILE,
            "rb"
        ) as f:

            bot.send_document(
                m.chat.id,
                f,
                caption=(
                    "💾 نسخة احتياطية من قاعدة البيانات."
                )
            )

    except Exception as e:

        bot.send_message(
            m.chat.id,
            f"❌ تعذر إرسال النسخة:\n{e}"
        )


# =========================================================
# ADMIN LOGS
# =========================================================

@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "📜 سجل المشرفين"
)
def admin_logs(m):

    logs = db.get(
        "admin_logs",
        []
    )

    if not logs:

        return bot.send_message(
            m.chat.id,
            "📜 السجل فارغ."
        )

    text = "\n".join(
        logs[-30:]
    )

    if len(text) > 3900:
        text = text[-3900:]

    bot.send_message(
        m.chat.id,
        f"📜 <b>آخر العمليات:</b>\n\n"
        f"<code>{text}</code>",
        parse_mode="HTML"
    )


@bot.message_handler(
    func=lambda m:
        is_admin(m.from_user.id)
        and m.text
        == "🧹 تنظيف السجل"
)
def clear_admin_logs(m):

    db["admin_logs"] = []

    save_db()

    bot.send_message(
        m.chat.id,
        "🧹 تم تنظيف سجل المشرفين."
    )


# =========================================================
# ERROR / POLLING
# =========================================================

def start_polling():

    while True:

        try:

            logging.info(
                "Starting Telegram polling..."
            )

            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True,
                allowed_updates=[
                    "message",
                    "callback_query",
                    "my_chat_member"
                ]
            )

        except KeyboardInterrupt:
            break

        except Exception as e:

            logging.exception(
                f"Polling error: {e}"
            )

            time.sleep(5)


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    logging.info(
        "Pro File & Store Bot v6.0 Started"
    )

    keep_alive()

    start_polling()
