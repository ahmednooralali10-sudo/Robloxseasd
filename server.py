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
BOT_USERNAME = "@VISITTTTTBOT"
BOT_LINK = f"https://t.me/{BOT_USERNAME.replace('@', '')}"
ADMINS = ["7075895496"]

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

def get_default_db():
    return {
        "channels": [], 
        "files": {}, 
        "users": {}, 
        "banned": [], 
        "groups": {},
        "settings": {
            "maintenance": False, 
            "welcome": "أهلاً بك! اذا تبي تحط قناتك في اشتراك اجباري او تنشر ملف تواصل مع المطور @xsaudi96", 
            "daily_file": None, 
            "btn1_text": "📢 قناة المطور", 
            "btn1_url": "https://t.me/mf5rt1",
            "btn2_text": "➕ أضفني لقناتك",
            "btn2_url": f"https://t.me/{BOT_USERNAME.replace('@', '')}?startgroup=true"
        },
        "stats": {"joins": 0, "files_sent": 0}
    }

def load_db():
    default_db = get_default_db()
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: 
                loaded_db = json.load(f)
                
            # إصلاح تلقائي: التأكد أن الأنواع تطابق الافتراضي (عشان نصلح مشكلة الـ dict)
            for key, default_val in default_db.items():
                if key not in loaded_db:
                    loaded_db[key] = default_val
                elif type(loaded_db[key]) != type(default_val):
                    # إذا كان النوع غلط (زي channels صار dict)، نرجعه list
                    loaded_db[key] = default_val
                elif isinstance(default_val, dict):
                    for subkey, subval in default_val.items():
                        if subkey not in loaded_db[key]:
                            loaded_db[key][subkey] = subval
            return loaded_db
        except Exception as e: 
            print(f"DB Load Error (Corrupted File): {e}")
    return default_db

def save_db():
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f: 
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"DB Save Error: {e}")

db = load_db()
if "files" not in db: db["files"] = {}
admin_states = {}

# ================== دوال مساعدة ==================
def is_admin(u): return str(u) in ADMINS
def is_banned(u): return str(u) in db.get("banned", [])

def check_sub(u):
    if not db.get("channels"): return True
    for ch in db["channels"]:
        try:
            if bot.get_chat_member(ch, u).status in ['left', 'kicked']: return False
        except: return False
    return True

def get_admin_kb():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("📤 رفع ملف واحد", "📦 رفع ملفات متعددة")
    m.add("📋 إدارة الملفات", "📢 الإذاعة")
    m.add("⚙️ القنوات", "📊 الإحصائيات")
    m.add("🚫 الحظر", "🛠️ الإعدادات")
    m.add("💾 نسخ احتياطي", "📜 السجل")
    m.add("🔙 إلغاء العملية الحالية")
    return m

def get_user_kb():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("📊 إحصائياتي", "📞 تواصل مع المطور")
    return m

def log_action(action, user_id, details=""):
    logging.info(f"ACTION: {action} | USER: {user_id} | {details}")

# ================== تتبع القنوات ==================
@bot.my_chat_member_handler()
def track_groups(message: types.ChatMemberUpdated):
    try:
        if message.chat.type in ['group', 'supergroup', 'channel']:
            if message.new_chat_member.status in ['member', 'administrator']:
                if "groups" not in db or not isinstance(db["groups"], dict): db["groups"] = {}
                db["groups"][str(message.chat.id)] = message.chat.title
                save_db()
                bot.send_message(message.chat.id, "✅ تم إضافة البوت بنجاح! أي إذاعة من المطور راح توصل هنا.")
            elif message.new_chat_member.status in ['left', 'kicked']:
                if "groups" in db and str(message.chat.id) in db["groups"]:
                    del db["groups"][str(message.chat.id)]
                    save_db()
    except: pass

# ================== زر الإلغاء ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🔙 إلغاء العملية الحالية")
def cancel_state(m):
    if m.from_user.id in admin_states:
        del admin_states[m.from_user.id]
    bot.send_message(m.chat.id, "✅ تم إلغاء العملية الحالية.", reply_markup=get_admin_kb())

# ================== أوامر المستخدم ==================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = str(message.from_user.id)
    
    if is_banned(uid): return bot.send_message(message.chat.id, "🚫 أنت محظور.")
    if db["settings"].get("maintenance") and not is_admin(uid): return bot.send_message(message.chat.id, "🛠️ البوت في صيانة حالياً.")

    if uid not in db.get("users", {}):
        if "users" not in db or not isinstance(db["users"], dict): db["users"] = {}
        db["users"][uid] = {"joined": datetime.now().strftime("%Y-%m-%d"), "downloads": 0}
        if "stats" in db: db["stats"]["joins"] = db["stats"].get("joins", 0) + 1
        save_db()
        try: bot.send_message(ADMINS[0], f"👤 مستخدم جديد:\n{message.from_user.first_name}\n`{uid}`", parse_mode="Markdown")
        except: pass

    if is_admin(uid):
        return bot.send_message(message.chat.id, f"👑 أهلاً بك في لوحة تحكم الإدارة.", reply_markup=get_admin_kb())
    
    args = message.text.split()
    if len(args) > 1:
        fid = args[1]
        if fid in db.get("files", {}):
            if not check_sub(uid):
                m = types.InlineKeyboardMarkup(row_width=1)
                for ch in db.get("channels", []):
                    try:
                        chat = bot.get_chat(ch)
                        m.add(types.InlineKeyboardButton(f"📢 {chat.title}", url=chat.invite_link or f"https://t.me/{chat.username}"))
                    except: pass
                m.add(types.InlineKeyboardButton("✅ تحقق", callback_data=f"chk_{fid}"))
                return bot.send_message(message.chat.id, "⚠️ يجب الاشتراك أولاً:", reply_markup=m)
            return send_file(uid, fid)
        else: return bot.send_message(message.chat.id, "❌ الملف غير موجود أو تم حذفه.")
    
    text = db["settings"].get("welcome", "أهلاً بك!")
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("📞 تواصل مع المطور @xsaudi96", url="https://t.me/xsaudi96"))
    bot.send_message(message.chat.id, text, reply_markup=m)
    bot.send_message(message.chat.id, "اختر من الأزرار:", reply_markup=get_user_kb())

@bot.message_handler(func=lambda m: m.text == "📊 إحصائياتي")
def user_stats(m):
    uid = str(m.from_user.id)
    user = db.get("users", {}).get(uid, {})
    downloads = user.get("downloads", 0)
    joined = user.get("joined", "غير معروف")
    bot.send_message(m.chat.id, f"👤 <b>إحصائياتك:</b>\n\n📥 التحميلات: {downloads}\n📅 تاريخ الانضمام: {joined}", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📞 تواصل مع المطور")
def contact_dev(m):
    bot.send_message(m.chat.id, "📞 للتواصل مع المطور، اضغط على الرابط التالي:\n@xsaudi96", reply_markup=get_user_kb())

def send_file(chat_id, fid):
    f = db["files"].get(fid)
    if not f: return
    try: 
        m = types.InlineKeyboardMarkup(row_width=2)
        btn1 = db["settings"].get("btn1_text", "📢 قناة المطور")
        btn2 = db["settings"].get("btn2_text", "➕ أضفني لقناتك")
        
        m.add(
            types.InlineKeyboardButton(text=btn1, url=db["settings"].get("btn1_url", "https://t.me")),
            types.InlineKeyboardButton(text=btn2, url=db["settings"].get("btn2_url", "https://t.me"))
        )
        
        bot.send_document(chat_id, f["file_id"], caption=f.get("desc", ""), reply_markup=m)
        if "stats" in db: db["stats"]["files_sent"] = db["stats"].get("files_sent", 0) + 1
        if str(chat_id) in db.get("users", {}): db["users"][str(chat_id)]["downloads"] = db["users"][str(chat_id)].get("downloads", 0) + 1
        save_db()
        log_action("DOWNLOAD", chat_id, f"File: {fid}")
    except: bot.send_message(chat_id, "⚠️ خطأ في الإرسال.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("chk_"))
def check_cb(call):
    fid = call.data.split("_")[1]
    if check_sub(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_file(call.from_user.id, fid)
    else: bot.answer_callback_query(call.id, "❌ لم تشترك بعد.", show_alert=True)

# ================== إدارة القنوات (المصححة) ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "⚙️ القنوات")
def mng_ch(m):
    text = "⚙️ <b>قنوات الاشتراك الإجباري:</b>\n"
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("➕ إضافة قناة", callback_data="add_c"))
    for ch in db.get("channels", []):
        text += f"- {ch}\n"
        mark.add(types.InlineKeyboardButton(f"❌ حذف {ch}", callback_data=f"delc_{ch}"))
    if not db.get("channels"): text += "لا توجد قنوات مضافة.\n"
    bot.send_message(m.chat.id, text, reply_markup=mark, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "add_c")
def add_c_cb(call):
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except: pass
    admin_states[call.from_user.id] = {"step": "add_c"}
    bot.send_message(call.message.chat.id, "أرسل يوزر القناة (مثال: @my_channel):\n\n⚠️ <i>تنبيه: يجب أن يكون البوت مشرفاً في القناة أولاً!</i>", parse_mode="HTML")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "add_c")
def add_c_proc(m):
    if m.text == "🔙 إلغاء العملية الحالية": return
    ch = m.text.strip()
    if not ch.startswith('@'):
        return bot.send_message(m.chat.id, "❌ يجب أن يبدأ يوزر القناة بـ @. جرب مرة ثانية أو اضغط إلغاء.")
    try:
        bot_member = bot.get_chat_member(ch, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            return bot.send_message(m.chat.id, "❌ البوت ليس مشرفاً في هذه القناة! قم بإضافة البوت كمشرف (Admin) في القناة أولاً، ثم أرسل اليوزر مرة ثانية.")
        
        # الحماية الجديدة: التأكد أن القنوات قائمة (list) مو قاموس
        if "channels" not in db or not isinstance(db["channels"], list): 
            db["channels"] = []
            
        if ch in db["channels"]:
            bot.send_message(m.chat.id, "⚠️ هذه القناة مضافة مسبقاً.", reply_markup=get_admin_kb())
        else:
            db["channels"].append(ch)
            save_db()
            bot.send_message(m.chat.id, f"✅ تمت إضافة القناة {ch} بنجاح.", reply_markup=get_admin_kb())
            
        del admin_states[m.from_user.id]
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delc_"))
def del_c_cb(call):
    ch = call.data.split("_")[1]
    if ch in db.get("channels", []): 
        db["channels"].remove(ch)
        save_db()
        bot.edit_message_text(f"✅ تم حذف القناة {ch}.", call.message.chat.id, call.message.message_id)

# ================== رفع الملفات ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📤 رفع ملف واحد")
def add_single_start(m):
    admin_states[m.from_user.id] = {"step": "single_desc"}
    bot.send_message(m.chat.id, "📝 أرسل <b>الوصف</b> أولاً:", parse_mode="HTML")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "single_desc", content_types=['text'])
def add_single_desc(m):
    if m.text == "🔙 إلغاء العملية الحالية": return
    admin_states[m.from_user.id] = {"step": "single_file", "desc": m.text}
    bot.send_message(m.chat.id, "📤 الحين أرسل الملف:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "single_file", content_types=['document', 'video', 'audio', 'photo'])
def add_single_file(m):
    try:
        fid = str(uuid.uuid4())[:8]
        name, file_id = "ملف", None
        if m.content_type == 'document': file_id, name = m.document.file_id, m.document.file_name or "ملف.zip"
        elif m.content_type == 'video': file_id, name = m.video.file_id, "فيديو.mp4"
        elif m.content_type == 'audio': file_id, name = m.audio.file_id, "صوت.mp3"
        elif m.content_type == 'photo': file_id, name = m.photo[-1].file_id, "صورة.jpg"
        
        if not file_id: return bot.send_message(m.chat.id, "❌ خطأ في الملف.")
        desc = admin_states[m.from_user.id]["desc"]
        if "files" not in db or not isinstance(db["files"], dict): db["files"] = {}
        db["files"][fid] = {"file_id": file_id, "name": name, "desc": desc, "date": datetime.now().strftime("%Y-%m-%d"), "downloads": 0}
        save_db()
        del admin_states[m.from_user.id]
        bot.send_message(m.chat.id, f"✅ <b>تم الرفع!</b>\n\n📄 {name}\n🔗 <code>{BOT_LINK}?start={fid}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ خطأ: {e}")
        if m.from_user.id in admin_states: del admin_states[m.from_user.id]

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📦 رفع ملفات متعددة")
def add_batch_start(m):
    admin_states[m.from_user.id] = {"step": "batch_desc"}
    bot.send_message(m.chat.id, "📝 أرسل <b>الوصف</b> للجميع:", parse_mode="HTML")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "batch_desc", content_types=['text'])
def add_batch_desc(m):
    if m.text == "🔙 إلغاء العملية الحالية": return
    admin_states[m.from_user.id] = {"step": "batch_files", "desc": m.text, "count": 0}
    bot.send_message(m.chat.id, "📤 أرسل الملفات.. لما تخلص /done")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "batch_files", content_types=['document', 'video', 'audio', 'photo'])
def add_batch_files(m):
    try:
        fid = str(uuid.uuid4())[:8]
        name, file_id = "ملف", None
        if m.content_type == 'document': file_id, name = m.document.file_id, m.document.file_name or "ملف.zip"
        elif m.content_type == 'video': file_id, name = m.video.file_id, "فيديو.mp4"
        elif m.content_type == 'audio': file_id, name = m.audio.file_id, "صوت.mp3"
        elif m.content_type == 'photo': file_id, name = m.photo[-1].file_id, "صورة.jpg"
        
        desc = admin_states[m.from_user.id]["desc"]
        if "files" not in db or not isinstance(db["files"], dict): db["files"] = {}
        db["files"][fid] = {"file_id": file_id, "name": name, "desc": desc, "date": datetime.now().strftime("%Y-%m-%d"), "downloads": 0}
        save_db()
        admin_states[m.from_user.id]["count"] += 1
        bot.send_message(m.chat.id, f"✅ {name} ({admin_states[m.from_user.id]['count']}).")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ خطأ، أرسل /done للإنهاء.")
        if m.from_user.id in admin_states: del admin_states[m.from_user.id]

@bot.message_handler(commands=['done'])
def done_adding(m):
    if not is_admin(m.from_user.id): return
    state = admin_states.get(m.from_user.id, {})
    if state.get("step") == "batch_files":
        count = state["count"]
        del admin_states[m.from_user.id]
        bot.send_message(m.chat.id, f"🎉 تم رفع {count} ملف.", reply_markup=get_admin_kb())

# ================== إدارة الملفات والإذاعة والإعدادات ==================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📋 إدارة الملفات")
def list_files(m):
    if not db.get("files"): return bot.send_message(m.chat.id, "⚠️ لا توجد ملفات.")
    show_files_page(m.chat.id, 0)

def show_files_page(chat_id, page):
    files = list(db.get("files", {}).items())
    start = page * 5
    end = start + 5
    chunk = files[start:end]
    mark = types.InlineKeyboardMarkup(row_width=1)
    for fid, info in chunk:
        mark.add(types.InlineKeyboardButton(f"📄 {info.get('name', 'ملف')[:25]}", callback_data=f"v_{fid}"))
    nav = []
    if page > 0: nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=f"pg_{page-1}"))
    if end < len(files): nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=f"pg_{page+1}"))
    if nav: mark.row(*nav)
    bot.send_message(chat_id, f"📋 <b>الملفات (صفحة {page+1}):</b>", reply_markup=mark, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pg_"))
def page_nav(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_files_page(call.message.chat.id, int(call.data.split("_")[1]))

@bot.callback_query_handler(func=lambda call: call.data.startswith("v_"))
def view_file(call):
    fid = call.data.split("_")[1]
    f = db.get("files", {}).get(fid)
    if not f: return
    mark = types.InlineKeyboardMarkup(row_width=1)
    mark.add(types.InlineKeyboardButton("🗑️ حذف", callback_data=f"delf_{fid}"))
    mark.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="pg_0"))
    text = (f"📄 <b>{f.get('name', 'ملف')}</b>\n📥 {f.get('downloads', 0)}\n🔗 <code>{BOT_LINK}?start={fid}</code>")
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=mark, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delf_"))
def del_file(call):
    fid = call.data.split("_")[1]
    if fid in db.get("files", {}):
        del db["files"][fid]; save_db()
        bot.edit_message_text("✅ تم الحذف.", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📢 الإذاعة")
def bc_menu(m):
    mark = types.InlineKeyboardMarkup(row_width=1)
    mark.add(types.InlineKeyboardButton("👥 للمستخدمين", callback_data="bc_users"))
    mark.add(types.InlineKeyboardButton("📢 للقنوات", callback_data="bc_groups"))
    mark.add(types.InlineKeyboardButton("💣 سبام", callback_data="bc_spam"))
    bot.send_message(m.chat.id, "📢 اختر نوع الإذاعة:", reply_markup=mark)

@bot.callback_query_handler(func=lambda call: call.data == "bc_users")
def bc_users_cb(call):
    admin_states[call.from_user.id] = {"step": "bc_users"}
    bot.send_message(call.message.chat.id, "📢 أرسل الرسالة للمستخدمين:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "bc_users", content_types=['text', 'photo', 'video', 'document'])
def bc_users_send(m):
    del admin_states[m.from_user.id]
    msg = bot.send_message(m.chat.id, "⏳ جاري الإرسال...")
    count = 0
    for uid in db.get("users", {}).keys():
        if uid in ADMINS: continue
        try: bot.copy_message(uid, m.chat.id, m.message_id); count += 1; time.sleep(0.05)
        except: pass
    bot.edit_message_text(f"✅ تم لـ {count}.", m.chat.id, msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "bc_groups")
def bc_groups_cb(call):
    admin_states[call.from_user.id] = {"step": "bc_groups"}
    bot.send_message(call.message.chat.id, "📢 أرسل الرسالة للقنوات:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "bc_groups", content_types=['text', 'photo', 'video', 'document'])
def bc_groups_send(m):
    del admin_states[m.from_user.id]
    msg = bot.send_message(m.chat.id, "⏳ جاري الإرسال...")
    count = 0
    for gid in db.get("groups", {}).keys():
        try: bot.copy_message(gid, m.chat.id, m.message_id); count += 1; time.sleep(0.05)
        except: pass
    bot.edit_message_text(f"✅ تم لـ {count}.", m.chat.id, msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "bc_spam")
def bc_spam_cb(call):
    admin_states[call.from_user.id] = {"step": "spam_msg"}
    bot.send_message(call.message.chat.id, "💣 أرسل الرسالة:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "spam_msg", content_types=['text', 'photo', 'video', 'document'])
def spam_cnt(m):
    admin_states[m.from_user.id] = {"step": "spam_cnt", "msg_id": m.message_id, "chat_id": m.chat.id}
    bot.send_message(m.chat.id, "🔢 كم عدد المرات؟:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "spam_cnt")
def spam_exec(m):
    st = admin_states[m.from_user.id]; del admin_states[m.from_user.id]
    try: c = int(m.text.strip())
    except: return bot.send_message(m.chat.id, "❌ خطأ.")
    msg = bot.send_message(m.chat.id, f"⏳ جاري الإرسال {c}...")
    def th():
        for _ in range(c):
            for uid in db.get("users", {}).keys():
                if uid in ADMINS: continue
                try: bot.copy_message(uid, st["chat_id"], st["msg_id"])
                except: pass
            time.sleep(0.1)
        bot.edit_message_text(f"✅ تم {c} مرة.", m.chat.id, msg.message_id)
    threading.Thread(target=th, daemon=True).start()

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📊 الإحصائيات")
def stats(m):
    text = f"👥 المستخدمين: {len(db.get('users', {}))}\n📁 الملفات: {len(db.get('files', {}))}\n📢 القنوات: {len(db.get('groups', {}))}\n🚫 المحظورين: {len(db.get('banned', []))}\n📥 التحميلات: {db.get('stats', {}).get('files_sent', 0)}"
    bot.send_message(m.chat.id, f"📊 <b>الإحصائيات:</b>\n\n{text}", parse_mode="HTML")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🛠️ الإعدادات")
def settings(m):
    maint = "🟢 شغال" if not db["settings"].get("maintenance") else "🔴 صيانة"
    mark = types.InlineKeyboardMarkup(row_width=1)
    mark.add(types.InlineKeyboardButton(f"وضع الصيانة: {maint}", callback_data="t_maint"))
    mark.add(types.InlineKeyboardButton("✏️ تغيير الترحيب", callback_data="c_welc"))
    mark.add(types.InlineKeyboardButton("🔘 إعدادات الأزرار", callback_data="c_btns"))
    bot.send_message(m.chat.id, "🛠️ الإعدادات:", reply_markup=mark)

@bot.callback_query_handler(func=lambda call: call.data == "t_maint")
def t_maint(call):
    db["settings"]["maintenance"] = not db["settings"].get("maintenance", False); save_db(); settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "c_welc")
def c_welc(call):
    admin_states[call.from_user.id] = {"step": "welc"}
    bot.send_message(call.message.chat.id, "أرسل الرسالة الجديدة:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "welc")
def set_welc(m):
    db["settings"]["welcome"] = m.text; save_db(); bot.send_message(m.chat.id, "✅ تم."); del admin_states[m.from_user.id]

@bot.callback_query_handler(func=lambda call: call.data == "c_btns")
def c_btns(call):
    admin_states[call.from_user.id] = {"step": "btn_text"}
    bot.send_message(call.message.chat.id, "أرسل النص والرابط للزر الأول (مفصولين بمسافة):")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "btn_text")
def set_btn(m):
    try:
        text, url = m.text.split()
        db["settings"]["btn1_text"] = text; db["settings"]["btn1_url"] = url; save_db()
        bot.send_message(m.chat.id, "✅ تم.")
    except: bot.send_message(m.chat.id, "❌ خطأ.")
    del admin_states[m.from_user.id]

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🚫 الحظر")
def ban_menu(m):
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("➕ حظر", callback_data="ban_u"))
    for uid in db.get("banned", []): mark.add(types.InlineKeyboardButton(f"✅ {uid}", callback_data=f"unban_{uid}"))
    bot.send_message(m.chat.id, "🚫 المحظورين:", reply_markup=mark)

@bot.callback_query_handler(func=lambda call: call.data == "ban_u")
def ban_cb(call):
    admin_states[call.from_user.id] = {"step": "ban"}
    bot.send_message(call.message.chat.id, "أرسل آيدي المستخدم:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and admin_states.get(m.from_user.id, {}).get("step") == "ban")
def ban_proc(m):
    uid = m.text.strip()
    if uid not in db.get("banned", []): 
        if "banned" not in db or not isinstance(db["banned"], list): db["banned"] = []
        db["banned"].append(uid); save_db()
    bot.send_message(m.chat.id, "✅ تم."); del admin_states[m.from_user.id]

@bot.callback_query_handler(func=lambda call: call.data.startswith("unban_"))
def unban_cb(call):
    uid = call.data.split("_")[1]
    if uid in db.get("banned", []): db["banned"].remove(uid); save_db()
    bot.edit_message_text("✅ تم.", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "💾 نسخ احتياطي")
def backup(m):
    try:
        with open(DB_FILE, "rb") as f: bot.send_document(m.chat.id, f, caption="✅ نسخة احتياطية.")
    except: bot.send_message(m.chat.id, "❌ خطأ.")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "📜 السجل")
def logs(m):
    try:
        with open("logs.txt") as f: lines = f.readlines()[-20:]
        bot.send_message(m.chat.id, "📜 آخر 20 عملية:\n\n<code>" + "".join(lines) + "</code>", parse_mode="HTML")
    except: bot.send_message(m.chat.id, "❌ لا يوجد سجل.")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id), content_types=['document', 'video', 'audio', 'photo'])
def catch_orphan_files(m):
    bot.send_message(m.chat.id, "⚠️ يرجى اختيار نوع الرفع أولاً.")

def start_polling():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e: logging.error(f"Error: {e}"); time.sleep(5)

if __name__ == "__main__":
    keep_alive()
    logging.info("Bot Started")
    threading.Thread(target=start_polling, daemon=True).start()
    while True: time.sleep(60)
