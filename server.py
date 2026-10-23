import os
import json
import time
import uuid
import threading
import logging
from datetime import datetime
from flask import Flask
import telebot
from telebot import types

# ================== الإعدادات ==================
BOT_TOKEN = "8730263970:AAHTcWNLwUOCBnXWsPbG_vho68cGEoFZy4M"
ADMIN_ID = "7075895496"
BOT_USERNAME = "@VISITTTTTBOT"
BOT_LINK = f"https://t.me/{BOT_USERNAME.replace('@', '')}"

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index(): return "Pro File Bot is Online!"

def keep_alive():
    def run():
        try: app.run(host="0.0.0.0", port=10000, debug=False)
        except: pass
    threading.Thread(target=run, daemon=True).start()

bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(filename="logs.txt", level=logging.INFO, format='%(asctime)s - %(message)s')

# ================== قاعدة البيانات ==================
DB_FILE = "database.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {
        "channels": [], "files": {}, "users": {}, "banned": [], 
        "settings": {"maintenance": False, "welcome": "أهلاً بك! يرجى فتح رابط الملف للتحميل.", "daily_file": None},
        "stats": {"joins": 0, "files_sent": 0}
    }

def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(db, f, ensure_ascii=False, indent=4)

db = load_db()
admin_states = {}

# ================== دوال ==================
def is_admin(u): return str(u) == ADMIN_ID
def is_banned(u): return str(u) in db["banned"]

def check_sub(u):
    if not db["channels"]: return True
    for ch in db["channels"]:
        try:
            if bot.get_chat_member(ch, u).status in ['left', 'kicked']: return False
        except: return False
    return True

def get_admin_kb():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("📤 إضافة ملف", "📋 إدارة الملفات")
    m.add("⚙️ القنوات", "📊 الإحصائيات")
    m.add("📢 إذاعة", "💣 سبام إذاعة")
    m.add("🚫 الحظر", "🛠️ الإعدادات")
    m.add("🎁 الملف اليومي", "📜 سجل العمليات")
    m.add("👥 إدارة المستخدمين", "💾 النسخ الاحتياطي")
    return m

# ================== أوامر المستخدم ==================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = str(message.from_user.id)
    
    if is_banned(uid): return bot.send_message(message.chat.id, "🚫 أنت محظور.")
    if db["settings"]["maintenance"] and not is_admin(uid): return bot.send_message(message.chat.id, "🛠️ البوت في صيانة.")

    if uid not in db["users"]:
        db["users"][uid] = {"joined": datetime.now().strftime("%Y-%m-%d"), "downloads": 0, "lang": "ar"}
        db["stats"]["joins"] += 1
        save_db()
        try: bot.send_message(ADMIN_ID, f"👤 مستخدم جديد:\n{message.from_user.first_name}\n`{uid}`", parse_mode="Markdown")
        except: pass

    if is_admin(uid):
        return bot.send_message(message.chat.id, f"👑 لوحة تحكم {BOT_USERNAME}", reply_markup=get_admin_kb())
    
    args = message.text.split()
    if len(args) > 1:
        fid = args[1]
        if fid in db["files"]:
            if not check_sub(uid):
                m = types.InlineKeyboardMarkup()
                for ch in db["channels"]:
                    try:
                        chat = bot.get_chat(ch)
                        m.add(types.InlineKeyboardButton(f"📢 {chat.title}", url=chat.invite_link or f"https://t.me/{chat.username}"))
                    except: pass
                m.add(types.InlineKeyboardButton("✅ تحقق", callback_data=f"chk_{fid}"))
                return bot.send_message(message.chat.id, "⚠️ يجب الاشتراك أولاً:", reply_markup=m)
            return send_file(uid, fid)
        else: return bot.send_message(message.chat.id, "❌ الملف غير موجود.")
    
    bot.send_message(message.chat.id, db["settings"]["welcome"])

def send_file(chat_id, fid):
    f = db["files"].get(fid)
    if not f: return
    try: 
        bot.send_document(chat_id, f["file_id"], caption=f"📁 {f['name']}")
        db["stats"]["files_sent"] += 1
        if str(chat_id) in db["users"]: db["users"][str(chat_id)]["downloads"] += 1
        save_db()
    except: bot.send_message(chat_id, "⚠️ خطأ في الإرسال.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("chk_"))
def check_cb(call):
    fid = call.data.split("_")[1]
    if check_sub(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_file(call.from_user.id, fid)
    else: bot.answer_callback_query(call.id, "❌ لم تشترك.", show_alert=True)

# ================== إدارة الملفات ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📤 إضافة ملف")
def add_f_start(m):
    admin_states[m.from_user.id] = {"step": "add_f"}
    bot.send_message(m.chat.id, "📤 أرسل الملف:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "add_f", content_types=['document', 'video', 'audio', 'photo'])
def add_f_proc(m):
    fid = str(uuid.uuid4())[:8]
    name, file_id = "ملف", None
    if m.content_type == 'document': file_id, name = m.document.file_id, m.document.file_name
    elif m.content_type == 'video': file_id, name = m.video.file_id, "فيديو.mp4"
    elif m.content_type == 'audio': file_id, name = m.audio.file_id, "صوت.mp3"
    elif m.content_type == 'photo': file_id, name = m.photo[-1].file_id, "صورة.jpg"
    
    db["files"][fid] = {"file_id": file_id, "name": name, "date": datetime.now().strftime("%Y-%m-%d"), "downloads": 0}
    save_db()
    bot.send_message(m.chat.id, f"✅ تم الرفع!\nالرابط:\n<code>{BOT_LINK}?start={fid}</code>", parse_mode="HTML")
    del admin_states[m.from_user.id]

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📋 إدارة الملفات")
def list_files(m):
    if not db["files"]: return bot.send_message(m.chat.id, "⚠️ لا توجد ملفات.")
    mark = types.InlineKeyboardMarkup(row_width=1)
    for fid, info in list(db["files"].items())[-10:]:
        mark.add(types.InlineKeyboardButton(f"📄 {info['name'][:20]}", callback_data=f"v_{fid}"))
    bot.send_message(m.chat.id, "📋 آخر 10 ملفات:", reply_markup=mark)

@bot.callback_query_handler(func=lambda call: call.data.startswith("v_"))
def view_file(call):
    fid = call.data.split("_")[1]
    f = db["files"].get(fid)
    if not f: return
    link = f"{BOT_LINK}?start={fid}"
    mark = types.InlineKeyboardMarkup(row_width=1)
    mark.add(types.InlineKeyboardButton("🗑️ حذف", callback_data=f"delf_{fid}"))
    bot.edit_message_text(f"📄 <b>{f['name']}</b>\n📥 التحميلات: {f.get('downloads', 0)}\n📅 التاريخ: {f['date']}\n\nالرابط:\n<code>{link}</code>", call.message.chat.id, call.message.message_id, reply_markup=mark, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delf_"))
def del_file(call):
    fid = call.data.split("_")[1]
    if fid in db["files"]:
        del db["files"][fid]
        save_db()
        bot.edit_message_text("✅ تم الحذف.", call.message.chat.id, call.message.message_id)

# ================== القنوات ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "⚙️ القنوات")
def mng_ch(m):
    text = "⚙️ <b>القنوات:</b>\n"
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("➕ إضافة", callback_data="add_c"))
    for ch in db["channels"]:
        text += f"- {ch}\n"
        mark.add(types.InlineKeyboardButton(f"❌ {ch}", callback_data=f"delc_{ch}"))
    bot.send_message(m.chat.id, text, reply_markup=mark, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "add_c")
def add_c_cb(call):
    admin_states[call.from_user.id] = {"step": "add_c"}
    bot.send_message(call.message.chat.id, "أرسل يوزر القناة (@name):")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "add_c")
def add_c_proc(m):
    ch = m.text.strip()
    if ch.startswith('@') and ch not in db["channels"]:
        db["channels"].append(ch)
        save_db()
        bot.send_message(m.chat.id, "✅ تم.")
    else: bot.send_message(m.chat.id, "❌ خطأ.")
    del admin_states[m.from_user.id]

@bot.callback_query_handler(func=lambda call: call.data.startswith("delc_"))
def del_c_cb(call):
    ch = call.data.split("_")[1]
    if ch in db["channels"]:
        db["channels"].remove(ch)
        save_db()
        bot.edit_message_text("✅ تم الحذف.", call.message.chat.id, call.message.message_id)

# ================== الإحصائيات والإعدادات ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📊 الإحصائيات")
def stats(m):
    text = f"👥 المستخدمين: {len(db['users'])}\n📁 الملفات: {len(db['files'])}\n📢 القنوات: {len(db['channels'])}\n🚫 المحظورين: {len(db['banned'])}\n📥 التحميلات: {db['stats']['files_sent']}"
    bot.send_message(m.chat.id, f"📊 <b>الإحصائيات:</b>\n\n{text}", parse_mode="HTML")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🛠️ الإعدادات")
def settings(m):
    maint = "🟢 شغال" if not db["settings"]["maintenance"] else "🔴 صيانة"
    mark = types.InlineKeyboardMarkup(row_width=1)
    mark.add(types.InlineKeyboardButton(f"وضع الصيانة: {maint}", callback_data="t_maint"))
    mark.add(types.InlineKeyboardButton("✏️ تغيير الترحيب", callback_data="c_welc"))
    bot.send_message(m.chat.id, "🛠️ الإعدادات:", reply_markup=mark)

@bot.callback_query_handler(func=lambda call: call.data == "t_maint")
def t_maint(call):
    db["settings"]["maintenance"] = not db["settings"]["maintenance"]
    save_db(); settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "c_welc")
def c_welc(call):
    admin_states[call.from_user.id] = {"step": "welc"}
    bot.send_message(call.message.chat.id, "أرسل الرسالة الجديدة:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "welc")
def set_welc(m):
    db["settings"]["welcome"] = m.text
    save_db()
    bot.send_message(m.chat.id, "✅ تم.")
    del admin_states[m.from_user.id]

# ================== الحظر والمستخدمين ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🚫 الحظر")
def ban_menu(m):
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("➕ حظر", callback_data="ban_u"))
    for uid in db["banned"]: mark.add(types.InlineKeyboardButton(f"✅ {uid}", callback_data=f"unban_{uid}"))
    bot.send_message(m.chat.id, "🚫 المحظورين:", reply_markup=mark)

@bot.callback_query_handler(func=lambda call: call.data == "ban_u")
def ban_cb(call):
    admin_states[call.from_user.id] = {"step": "ban"}
    bot.send_message(call.message.chat.id, "أرسل آيدي المستخدم:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "ban")
def ban_proc(m):
    uid = m.text.strip()
    if uid not in db["banned"]: db["banned"].append(uid); save_db()
    bot.send_message(m.chat.id, "✅ تم.")
    del admin_states[m.from_user.id]

@bot.callback_query_handler(func=lambda call: call.data.startswith("unban_"))
def unban_cb(call):
    uid = call.data.split("_")[1]
    if uid in db["banned"]: db["banned"].remove(uid); save_db()
    bot.edit_message_text("✅ تم.", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "👥 إدارة المستخدمين")
def mng_users(m):
    text = f"👥 إجمالي المستخدمين: {len(db['users'])}\n\nآخر 5 مستخدمين:\n"
    for uid, info in list(db["users"].items())[-5:]:
        text += f"`{uid}` - تحميلات: {info['downloads']}\n"
    bot.send_message(m.chat.id, text, parse_mode="Markdown")

# ================== الملف اليومي ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🎁 الملف اليومي")
def daily_menu(m):
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("➕ تعيين ملف كهدية", callback_data="set_daily"))
    if db["settings"]["daily_file"]:
        fid = db["settings"]["daily_file"]
        mark.add(types.InlineKeyboardButton("❌ إلغاء الهدية", callback_data="rem_daily"))
        name = db["files"].get(fid, {}).get("name", "غير معروف")
        bot.send_message(m.chat.id, f"🎁 الهدية اليومية الحالية: {name}", reply_markup=mark)
    else:
        bot.send_message(m.chat.id, "🎁 لا يوجد هدية يومية.", reply_markup=mark)

@bot.callback_query_handler(func=lambda call: call.data == "set_daily")
def set_daily_cb(call):
    admin_states[call.from_user.id] = {"step": "set_daily"}
    bot.send_message(call.message.chat.id, "أرسل آيدي الملف (من قائمة الملفات):")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "set_daily")
def set_daily_proc(m):
    fid = m.text.strip()
    if fid in db["files"]:
        db["settings"]["daily_file"] = fid
        save_db()
        bot.send_message(m.chat.id, "✅ تم تعيين الهدية.")
    else: bot.send_message(m.chat.id, "❌ الملف غير موجود.")
    del admin_states[m.from_user.id]

@bot.callback_query_handler(func=lambda call: call.data == "rem_daily")
def rem_daily_cb(call):
    db["settings"]["daily_file"] = None
    save_db()
    bot.edit_message_text("✅ تم إلغاء الهدية اليومية.", call.message.chat.id, call.message.message_id)

# ================== الإذاعة والسبام ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📢 إذاعة")
def bc_start(m):
    admin_states[m.from_user.id] = {"step": "bc"}
    bot.send_message(m.chat.id, "📢 أرسل الرسالة:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "bc", content_types=['text', 'photo', 'video', 'document'])
def bc_send(m):
    del admin_states[m.from_user.id]
    msg = bot.send_message(m.chat.id, "⏳ جاري الإرسال...")
    count = 0
    for uid in db["users"].keys():
        if uid == ADMIN_ID: continue
        try: bot.copy_message(uid, m.chat.id, m.message_id); count += 1
        except: pass
    bot.edit_message_text(f"✅ تم لـ {count}.", m.chat.id, msg.message_id)

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "💣 سبام إذاعة")
def spam_start(m):
    admin_states[m.from_user.id] = {"step": "spam_msg"}
    bot.send_message(m.chat.id, "💣 أرسل الرسالة:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "spam_msg", content_types=['text', 'photo', 'video', 'document'])
def spam_cnt(m):
    admin_states[m.from_user.id] = {"step": "spam_cnt", "msg_id": m.message_id, "chat_id": m.chat.id}
    bot.send_message(m.chat.id, "🔢 كم عدد المرات؟:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "spam_cnt")
def spam_exec(m):
    st = admin_states[m.from_user.id]
    del admin_states[m.from_user.id]
    try: c = int(m.text.strip())
    except: return bot.send_message(m.chat.id, "❌ خطأ.")
    msg = bot.send_message(m.chat.id, f"⏳ جاري الإرسال {c} مرة...")
    def th():
        for _ in range(c):
            for uid in db["users"].keys():
                if uid == ADMIN_ID: continue
                try: bot.copy_message(uid, st["chat_id"], st["msg_id"])
                except: pass
            time.sleep(0.1)
        bot.edit_message_text(f"✅ تم السبام {c} مرة.", m.chat.id, msg.message_id)
    threading.Thread(target=th, daemon=True).start()

# ================== السجل والنسخ الاحتياطي ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📜 سجل العمليات")
def logs(m):
    try:
        with open("logs.txt") as f: lines = f.readlines()[-15:]
        bot.send_message(m.chat.id, "📜 آخر 15 عملية:\n\n<code>" + "".join(lines) + "</code>", parse_mode="HTML")
    except: bot.send_message(m.chat.id, "❌ لا يوجد.")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "💾 النسخ الاحتياطي")
def backup(m):
    try:
        with open("database.json", "rb") as f:
            bot.send_document(m.chat.id, f, caption="✅ نسخة احتياطية لقاعدة البيانات.")
    except: bot.send_message(m.chat.id, "❌ خطأ.")

# ================== التشغيل ==================
def start_polling():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    keep_alive()
    logging.info("Bot Started")
    threading.Thread(target=start_polling, daemon=True).start()
    while True: time.sleep(60)
