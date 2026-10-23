import os
import json
import time
import threading
import logging
from flask import Flask
import telebot
from telebot import types

# ================== إعدادات البوت الأساسي (الماستر) ==================
MASTER_TOKEN = "8730263970:AAHTcWNLwUOCBnXWsPbG_vho68cGEoFZy4M" 
ADMIN_ID = 7075895496 

# ================== Flask (لإبقاء السيرفر شغال) ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "Multi-Bot Manager is Online"

def keep_alive():
    def run():
        try: app.run(host="0.0.0.0", port=10000, debug=False)
        except: pass
    threading.Thread(target=run, daemon=True).start()

# ================== قاعدة البيانات ==================
DB_FILE = "bots_data.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {}

def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(db, f, ensure_ascii=False, indent=4)

db = load_db() # { token: { "name": "", "channels": [], "running": True } }

# ================== البوت الأساسي ==================
master_bot = telebot.TeleBot(MASTER_TOKEN)
admin_states = {}
active_bots = {} # لحفظ البوتات الشغالة في الذاكرة

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================== دوال مساعدة ==================
def get_master_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ إضافة بوت جديد", "📋 قائمة البوتات")
    markup.add("⚙️ إدارة القنوات", "🗑️ حذف بوت")
    return markup

def start_new_bot(token, bot_info):
    if token in active_bots: return
    
    try:
        new_bot = telebot.TeleBot(token)
        
        @new_bot.message_handler(commands=['start'])
        def sub_start(message):
            # التحقق من الاشتراك
            if bot_info["channels"]:
                not_joined = []
                for ch in bot_info["channels"]:
                    try:
                        member = new_bot.get_chat_member(ch, message.from_user.id)
                        if member.status in ['left', 'kicked']: not_joined.append(ch)
                    except: not_joined.append(ch)
                
                if not_joined:
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    for ch in bot_info["channels"]:
                        try:
                            chat_info = new_bot.get_chat(ch)
                            link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
                            markup.add(types.InlineKeyboardButton(text=f"📢 اشترك في {chat_info.title}", url=link))
                        except: pass
                    markup.add(types.InlineKeyboardButton(text="✅ تحقق", callback_data="check_sub"))
                    new_bot.send_message(message.chat.id, f"⚠️ عذراً {message.from_user.first_name}، يجب الاشتراك في القنوات أولاً:", reply_markup=markup)
                    return

            # بعد الاشتراك، تطلع الأزرار
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add("🏪 المتجر", "💎 نقاطي")
            markup.add("🎁 هدية", "ℹ️ معلومات")
            new_bot.send_message(message.chat.id, f"👋 أهلاً بك في {bot_info['name']}!\n\nاختر من الأزرار:", reply_markup=markup)
            
        @new_bot.callback_query_handler(func=lambda call: call.data == "check_sub")
        def sub_check(call):
            sub_start(call.message)
            new_bot.answer_callback_query(call.id, "✅ تم التحقق.")

        # تشغيل البوت في الخلفية
        active_bots[token] = new_bot
        threading.Thread(target=new_bot.infinity_polling, kwargs={'timeout': 60, 'long_polling_timeout': 60}, daemon=True).start()
        logging.info(f"Bot {bot_info['name']} started successfully.")
        
    except Exception as e:
        logging.error(f"Failed to start bot {token}: {e}")

# ================== أوامر البوت الماستر ==================
@master_bot.message_handler(commands=['start'])
def master_start(message):
    if message.from_user.id != ADMIN_ID: return
    master_bot.send_message(message.chat.id, "👑 أهلاً بك في لوحة تحكم البوتات.\nاختر من الأزرار:", reply_markup=get_master_keyboard())

@master_bot.message_handler(func=lambda message: message.text == "➕ إضافة بوت جديد")
def add_bot_start(message):
    if message.from_user.id != ADMIN_ID: return
    admin_states[message.from_user.id] = {"step": "add_token"}
    master_bot.send_message(message.chat.id, "🔑 أرسل توكن البوت الجديد (من @BotFather):")

@master_bot.message_handler(func=lambda message: admin_states.get(message.from_user.id, {}).get("step") == "add_token")
def add_bot_token(message):
    token = message.text.strip()
    if ":" not in token:
        return master_bot.send_message(message.chat.id, "❌ توكن غير صحيح، جرب مرة ثانية.")
    
    try:
        temp_bot = telebot.TeleBot(token)
        bot_info = temp_bot.get_me()
        
        db[token] = {
            "name": bot_info.first_name,
            "channels": [],
            "running": True
        }
        save_db()
        
        # تشغيل البوت مباشرة
        start_new_bot(token, db[token])
        
        admin_states[message.from_user.id] = {"step": None}
        master_bot.send_message(message.chat.id, f"✅ تم إضافة وتشغيل البوت: @{bot_info.username}\n\nالحين تقدر تضيف قنوات اشتراك له.", reply_markup=get_master_keyboard())
        
    except Exception as e:
        master_bot.send_message(message.chat.id, f"❌ فشل الاتصال بالبوت، تأكد من التوكن.\n{e}")

@master_bot.message_handler(func=lambda message: message.text == "📋 قائمة البوتات")
def list_bots(message):
    if message.from_user.id != ADMIN_ID: return
    if not db:
        return master_bot.send_message(message.chat.id, "⚠️ لا توجد بوتات مضافة.")
    
    text = "📋 <b>البوتات المضافة:</b>\n\n"
    for token, info in db.items():
        status = "🟢 شغال" if token in active_bots else "🔴 متوقف"
        text += f"👤 <b>{info['name']}</b>\n🔑 <code>{token[:10]}...</code>\n📢 قنوات: {len(info['channels'])}\nالحالة: {status}\n\n"
    
    master_bot.send_message(message.chat.id, text, parse_mode="HTML")

@master_bot.message_handler(func=lambda message: message.text == "⚙️ إدارة القنوات")
def manage_channels(message):
    if message.from_user.id != ADMIN_ID: return
    if not db:
        return master_bot.send_message(message.chat.id, "⚠️ أضف بوت أولاً.")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for token, info in db.items():
        markup.add(types.InlineKeyboardButton(text=f"⚙️ {info['name']}", callback_data=f"mng_{token}"))
    
    master_bot.send_message(message.chat.id, "اختر البوت اللي تبي تدير قنواته:", reply_markup=markup)

@master_bot.callback_query_handler(func=lambda call: call.data.startswith("mng_"))
def manage_bot_channels(call):
    token = call.data.split("_")[1]
    bot_info = db.get(token)
    if not bot_info: return
    
    text = f"⚙️ <b>قنوات البوت: {bot_info['name']}</b>\n\n"
    if not bot_info['channels']:
        text += "لا توجد قنوات مضافة.\n"
    else:
        for ch in bot_info['channels']:
            text += f"- <code>{ch}</code>\n"
            
    text += "\nللإضافة: أرسل يوزر القناة (مثال: `@my_channel`).\nملاحظة: تأكد أن البوت أدمن في القناة."
    
    master_bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    admin_states[call.from_user.id] = {"step": "add_channel", "token": token}

@master_bot.message_handler(func=lambda message: admin_states.get(message.from_user.id, {}).get("step") == "add_channel")
def add_channel_to_bot(message):
    state = admin_states[message.from_user.id]
    token = state["token"]
    channel = message.text.strip()
    
    if not channel.startswith('@'):
        return master_bot.send_message(message.chat.id, "❌ أرسل يوزر القناة بشكل صحيح (يبدأ بـ @).")
    
    if token not in db: return
    
    if channel in db[token]["channels"]:
        return master_bot.send_message(message.chat.id, "⚠️ القناة مضافة مسبقاً.")
        
    db[token]["channels"].append(channel)
    save_db()
    
    # تحديث معلومات البوت الشغال في الذاكرة
    if token in active_bots:
        # ملاحظة: البوت الشغال ما يقدر يحدث المتغير إلا بإعادة تشغيل، بس بنسويها بسيطة
        pass
        
    admin_states[message.from_user.id] = {"step": None}
    master_bot.send_message(message.chat.id, f"✅ تم إضافة القناة {channel} للبوت {db[token]['name']}.", reply_markup=get_master_keyboard())

@master_bot.message_handler(func=lambda message: message.text == "🗑️ حذف بوت")
def delete_bot_menu(message):
    if message.from_user.id != ADMIN_ID: return
    if not db:
        return master_bot.send_message(message.chat.id, "⚠️ لا توجد بوتات.")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for token, info in db.items():
        markup.add(types.InlineKeyboardButton(text=f"❌ حذف {info['name']}", callback_data=f"del_{token}"))
    
    master_bot.send_message(message.chat.id, "اختر البوت اللي تبي تحذفه:", reply_markup=markup)

@master_bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def delete_bot_execute(call):
    token = call.data.split("_")[1]
    if token in db:
        name = db[token]["name"]
        del db[token]
        save_db()
        
        # إيقاف البوت (إذا كان شغال)
        if token in active_bots:
            try: active_bots[token].stop_polling()
            except: pass
            del active_bots[token]
            
        master_bot.edit_message_text(f"✅ تم حذف البوت {name}.", call.message.chat.id, call.message.message_id)

# ================== تشغيل النظام ==================
if __name__ == "__main__":
    keep_alive()
    
    # تشغيل جميع البوتات المحفوظة مسبقاً
    for token, info in db.items():
        start_new_bot(token, info)
        
    logging.info("Master Bot started...")
    master_bot.infinity_polling(timeout=60, long_polling_timeout=60)
