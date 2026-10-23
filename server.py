import os
import json
import time
import uuid
import threading
import logging
from flask import Flask
import telebot
from telebot import types

# ================== إعدادات البوت ==================
BOT_TOKEN = "8730263970:AAHTcWNLwUOCBnXWsPbG_vho68cGEoFZy4M" # <-- التوكن حق بوتك
ADMIN_ID = 7075895496 # <-- الآيدي حقك
BOT_LINK = "https://t.me/VISITTTTTBOT" # <-- رابط البوت

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "File Store Bot is Online!"

def keep_alive():
    def run():
        try: app.run(host="0.0.0.0", port=10000, debug=False)
        except: pass
    threading.Thread(target=run, daemon=True).start()

bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================== قاعدة البيانات ==================
DB_FILE = "data.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {"channels": [], "files": {}}

def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(db, f, ensure_ascii=False, indent=4)

db = load_db() # { "channels": ["@ch1"], "files": { "uuid": {"file_id": "xxx", "name": "xxx"} } }
admin_states = {}

# ================== دوال مساعدة ==================
def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

def check_sub(user_id):
    if not db["channels"]: return True
    for ch in db["channels"]:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📤 إضافة ملف", "⚙️ إدارة القنوات")
    markup.add("📋 قائمة الملفات", "ℹ️ معلومات البوت")
    return markup

# ================== أوامر الأدمن ==================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "👑 أهلاً بك في لوحة تحكم البوت.", reply_markup=get_admin_keyboard())
        return
    
    # إذا كان المستخدم العادي داخل من رابط ملف
    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]
        if file_id in db["files"]:
            if not check_sub(message.from_user.id):
                markup = types.InlineKeyboardMarkup(row_width=1)
                for ch in db["channels"]:
                    try:
                        chat_info = bot.get_chat(ch)
                        link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
                        markup.add(types.InlineKeyboardButton(text=f"📢 اشترك في {chat_info.title}", url=link))
                    except: pass
                markup.add(types.InlineKeyboardButton(text="✅ تحقق", callback_data=f"check_{file_id}"))
                bot.send_message(message.chat.id, "⚠️ عذراً، يجب الاشتراك في القنوات التالية أولاً لتحميل الملف:", reply_markup=markup)
                return
            else:
                send_file_to_user(message.chat.id, file_id)
                return
        else:
            bot.send_message(message.chat.id, "❌ الملف غير موجود أو تم حذفه.")
            return

    # إذا كان مستخدم عادي وما دخل من رابط
    bot.send_message(message.chat.id, "👋 أهلاً بك. يرجى فتح رابط الملف للتحميل.")

def send_file_to_user(chat_id, file_id):
    file_info = db["files"].get(file_id)
    if not file_info:
        bot.send_message(chat_id, "❌ الملف غير موجود.")
        return
    try:
        bot.send_document(chat_id, file_info["file_id"], caption=f"📁 الملف: {file_info['name']}")
    except:
        bot.send_message(chat_id, "⚠️ حدث خطأ أثناء إرسال الملف.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
def check_sub_callback(call):
    file_id = call.data.split("_")[1]
    if check_sub(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_file_to_user(call.from_user.id, file_id)
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك بعد في جميع القنوات.", show_alert=True)

# ================== إضافة ملفات ==================
@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📤 إضافة ملف")
def add_file_start(message):
    admin_states[message.from_user.id] = {"step": "add_file"}
    bot.send_message(message.chat.id, "📤 أرسل الملف الآن (مستند، فيديو، صورة..):")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and admin_states.get(message.from_user.id, {}).get("step") == "add_file", content_types=['document', 'video', 'audio', 'photo'])
def add_file_process(message):
    try:
        file_id = None
        file_name = "ملف غير معروف"
        
        if message.content_type == 'document':
            file_id = message.document.file_id
            file_name = message.document.file_name
        elif message.content_type == 'video':
            file_id = message.video.file_id
            file_name = "فيديو.mp4"
        elif message.content_type == 'audio':
            file_id = message.audio.file_id
            file_name = message.audio.title or "صوت.mp3"
        elif message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            file_name = "صورة.jpg"
            
        if not file_id:
            return bot.send_message(message.chat.id, "❌ لم يتم استلام الملف بشكل صحيح.")
            
        unique_id = str(uuid.uuid4())[:8]
        db["files"][unique_id] = {"file_id": file_id, "name": file_name}
        save_db()
        
        link = f"{BOT_LINK}?start={unique_id}"
        
        text = f"✅ <b>تم إضافة الملف بنجاح!</b>\n\n📁 الاسم: <b>{file_name}</b>\n🔗 رابط المشاركة:\n<code>{link}</code>"
        bot.send_message(message.chat.id, text, parse_mode="HTML")
        del admin_states[message.from_user.id]
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {e}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📋 قائمة الملفات")
def list_files(message):
    if not db["files"]:
        return bot.send_message(message.chat.id, "⚠️ لا توجد ملفات مضافة.")
    
    text = "📋 <b>الملفات المضافة:</b>\n\n"
    for fid, info in db["files"].items():
        link = f"{BOT_LINK}?start={fid}"
        text += f"📄 <b>{info['name']}</b>\n🔗 <a href='{link}'>رابط التحميل</a>\n\n"
    
    bot.send_message(message.chat.id, text, parse_mode="HTML", disable_web_page_preview=True)

# ================== إدارة القنوات ==================
@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "⚙️ إدارة القنوات")
def manage_channels(message):
    text = "⚙️ <b>القنوات الحالية:</b>\n"
    if not db["channels"]: text += "لا توجد قنوات مضافة.\n"
    for ch in db["channels"]:
        text += f"- <code>{ch}</code>\n"
    
    text += "\nلإضافة قناة: أرسل يوزر القناة (مثال: <code>@my_channel</code>).\nملاحظة: تأكد أن البوت أدمن في القناة."
    bot.send_message(message.chat.id, text, parse_mode="HTML")
    admin_states[message.from_user.id] = {"step": "add_channel"}

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and admin_states.get(message.from_user.id, {}).get("step") == "add_channel")
def add_channel_process(message):
    ch = message.text.strip()
    if not ch.startswith('@'):
        return bot.send_message(message.chat.id, "❌ يوزر القناة يجب أن يبدأ بـ @.")
    
    if ch not in db["channels"]:
        db["channels"].append(ch)
        save_db()
        bot.send_message(message.chat.id, f"✅ تم إضافة القناة {ch}.")
    else:
        bot.send_message(message.chat.id, "⚠️ القناة مضافة مسبقاً.")
    
    del admin_states[message.from_user.id]

# ================== معلومات البوت ==================
@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "ℹ️ معلومات البوت")
def info_bot(message):
    text = f"🤖 <b>معلومات البوت:</b>\n\n📁 عدد الملفات: {len(db['files'])}\n📢 عدد القنوات: {len(db['channels'])}"
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# ================== تشغيل ==================
def start_bot_polling():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Polling crashed: {e}")
            time.sleep(5)

if __name__ == "__main__":
    keep_alive()
    logging.info("File Store Bot Started...")
    threading.Thread(target=start_bot_polling, daemon=True).start()
    while True: time.sleep(60)
