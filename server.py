import os
import time
import threading
import asyncio
import logging
from flask import Flask
import telebot
from telebot import types
from telethon import TelegramClient, errors
from telethon.tl.types import Channel, Chat

# ================== الإعدادات ==================
BOT_TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"
ADMIN_ID = 7075895496
MAX_UNREAD = 3000
CHECK_INTERVAL = 300 # كل 5 دقايق يفحص

# ================== إعدادات تيليثون ==================
API_ID = 12345678 # <--- ضع الـ API ID حقك
API_HASH = "ضع_الـ_API_HASH_هنا" # <--- ضع الـ API HASH حقك
SESSION_FILE = "user_session"

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "Deleting Bot is Online!"

def keep_alive():
    def run():
        try: app.run(host="0.0.0.0", port=10000, debug=False)
        except: pass
    threading.Thread(target=run, daemon=True).start()

# ================== تيليجرام بوت ==================
bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}
telethon_client = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================== أوامر البوت ==================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🔐 تسجيل الدخول", "🧹 بدء الحذف")
    markup.add("🛑 إيقاف الحذف", "ℹ️ الإحصائيات")
    bot.send_message(message.chat.id, "أهلاً بك. اختر من الأزرار:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🔐 تسجيل الدخول")
def login_start(message):
    if message.from_user.id != ADMIN_ID: return
    
    if os.path.exists(f"{SESSION_FILE}.session"):
        bot.send_message(message.chat.id, "✅ أنت مسجل دخول بالفعل.")
        return
        
    msg = bot.send_message(message.chat.id, "📱 أرسل رقم هاتفك مع رمز الدولة (مثال: +966501234567):")
    bot.register_next_step_handler(msg, login_phone)

def login_phone(message):
    phone = message.text.strip()
    user_states[message.from_user.id] = {"phone": phone}
    
    # بدء عملية تسجيل الدخول في الخلفية
    threading.Thread(target=login_process, args=(message.chat.id, phone), daemon=True).start()

def login_process(chat_id, phone):
    global telethon_client
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def do_login():
        try:
            telethon_client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
            await telethon_client.connect()
            
            if not await telethon_client.is_user_authorized():
                sent_code = await telethon_client.send_code_request(phone)
                user_states[chat_id]["phone_code_hash"] = sent_code.phone_code_hash
                
                bot.send_message(chat_id, "🔑 تم إرسال كود التحقق إلى حسابك في تليجرام. أرسل الكود الآن:")
                # ننتظر المستخدم يرسل الكود
                return
            else:
                bot.send_message(chat_id, "✅ تم تسجيل الدخول بنجاح!")
                
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطأ في الاتصال: {e}")
            
    loop.run_until_complete(do_login())

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.text.isdigit() and len(message.text) in [5, 6])
def login_code(message):
    if message.from_user.id not in user_states: return
    
    code = message.text.strip()
    phone_code_hash = user_states[message.from_user.id].get("phone_code_hash")
    
    if not phone_code_hash:
        return bot.send_message(message.chat.id, "❌ الرجاء بدء تسجيل الدخول أولاً.")
        
    threading.Thread(target=submit_code, args=(message.chat.id, code, phone_code_hash), daemon=True).start()

def submit_code(chat_id, code, phone_code_hash):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def do_code():
        try:
            await telethon_client.sign_in(user_states[chat_id]["phone"], code=code, phone_code_hash=phone_code_hash)
            bot.send_message(chat_id, "✅ تم تسجيل الدخول وحفظ الجلسة! اضغط 'بدء الحذف'.")
            logging.info("User logged in successfully.")
        except errors.SessionPasswordNeededError:
            bot.send_message(chat_id, "🔒 الحساب محمي بكلمة مرور (2FA). أرسل كلمة المرور الآن:")
            user_states[chat_id]["awaiting_password"] = True
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطأ: {e}")
            
    loop.run_until_complete(do_code())

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and user_states.get(message.from_user.id, {}).get("awaiting_password"))
def login_password(message):
    password = message.text.strip()
    threading.Thread(target=submit_password, args=(message.chat.id, password), daemon=True).start()

def submit_password(chat_id, password):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def do_password():
        try:
            await telethon_client.sign_in(password=password)
            bot.send_message(chat_id, "✅ تم تسجيل الدخول بنجاح! اضغط 'بدء الحذف'.")
            user_states[chat_id]["awaiting_password"] = False
        except Exception as e:
            bot.send_message(chat_id, f"❌ كلمة المرور خاطئة: {e}")
            
    loop.run_until_complete(do_password())

@bot.message_handler(func=lambda message: message.text == "🧹 بدء الحذف")
def start_delete(message):
    if message.from_user.id != ADMIN_ID: return
    if not os.path.exists(f"{SESSION_FILE}.session"):
        return bot.send_message(message.chat.id, "❌ سجل دخول أولاً!")
        
    bot.send_message(message.chat.id, "🔍 بدأ فحص الجروبات...")
    threading.Thread(target=delete_loop, args=(message.chat.id,), daemon=True).start()

def delete_loop(chat_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def check_and_delete():
        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            bot.send_message(chat_id, "❌ الجلسة منتهية، سجل دخول من جديد.")
            return
            
        while True:
            try:
                async for dialog in client.iter_dialogs():
                    if dialog.is_group or dialog.is_channel:
                        unread = dialog.unread_count
                        if unread > MAX_UNREAD:
                            try:
                                await client.delete_dialog(dialog.id)
                                bot.send_message(chat_id, f"🗑️ تم حذف: {dialog.name} (غير مقروء: {unread})")
                            except Exception as e:
                                bot.send_message(chat_id, f"⚠️ فشل حذف {dialog.name}: {e}")
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ في الفحص: {e}")
                
            await asyncio.sleep(CHECK_INTERVAL)
            
    loop.run_until_complete(check_and_delete())

@bot.message_handler(func=lambda message: message.text == "🛑 إيقاف الحذف")
def stop_delete(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "🛑 تم إيقاف الحذف. (السكربت سيستمر لأنه في الخلفية، أعد تشغيل السيرفر لإيقافه)")

@bot.message_handler(func=lambda message: message.text == "ℹ️ الإحصائيات")
def stats(message):
    if message.from_user.id != ADMIN_ID: return
    if os.path.exists(f"{SESSION_FILE}.session"):
        bot.send_message(message.chat.id, "✅ الحساب مسجل الدخول. السكربت جاهز للعمل.")
    else:
        bot.send_message(message.chat.id, "❌ لا يوجد حساب مسجل حالياً.")

# ================== تشغيل ==================
if __name__ == "__main__":
    keep_alive()
    logging.info("Bot started...")
    bot.infinity_polling()
