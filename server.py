import os
import threading
import requests
import datetime
from flask import Flask
import telebot
from telebot import types
from user_agent import generate_user_agent

# --- الإعدادات ---
BOT_TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"
ADMIN_ID = 7075895496

# --- Flask للسيرفر ---
app = Flask(__name__)

@app.route("/")
def index():
    return "TikTok Bot is running perfectly!"

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000))
    t.daemon = True
    t.start()

# --- إعدادات البوت ---
bot = telebot.TeleBot(BOT_TOKEN)

# --- دالة جلب معلومات تيك توك ---
def get_tiktok_info(username):
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": generate_user_agent(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        
        session.get(f"https://www.tiktok.com/@{username}", timeout=10)
        
        url = f"https://www.tiktok.com/api/user/detail/?uniqueId={username}&aid=1988"
        r = session.get(url, timeout=15)
        
        if r.status_code != 200:
            return {"error": f"فشل الاتصال، كود: {r.status_code}"}
            
        data = r.json()
        
        if "userInfo" not in data or "user" not in data["userInfo"]:
            return {"error": "الحساب غير موجود أو محظور."}
            
        user = data["userInfo"]["user"]
        stats = data["userInfo"]["stats"]
        
        create_time = user.get("createTime", 0)
        try:
            created_date = datetime.datetime.utcfromtimestamp(create_time).strftime('%Y-%m-%d')
        except:
            created_date = "Unknown"
            
        info = {
            "username": user.get("uniqueId", username),
            "nickname": user.get("nickname", "N/A"),
            "region": user.get("region", "N/A"),
            "followers": stats.get("followerCount", 0),
            "following": stats.get("followingCount", 0),
            "likes": stats.get("heartCount", 0),
            "videos": stats.get("videoCount", 0),
            "verified": "✅" if user.get("verified", False) else "❌",
            "private": "🔒" if user.get("privateAccount", False) else "🔓",
            "bio": user.get("signature", "N/A"),
            "created": created_date,
            "id": user.get("id", "N/A")
        }
        return info
    except Exception as e:
        return {"error": str(e)}

# --- أوامر البوت ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "عذراً، هذا البوت خاص.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    btn = types.KeyboardButton("🔍 جلب معلومات حساب")
    markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "أهلاً بك في بوت تيك توك (نسخة ALPHA XK).\nاضغط الزر تحت وأرسل اسم المستخدم (بدون @) عشان يجيب لك كل المعلومات (الدولة، المتابعين، والايدي المخفي).",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == "🔍 جلب معلومات حساب")
def ask_username(message):
    msg = bot.reply_to(message, "أرسل اسم المستخدم (مثال: charlidamelio)")
    bot.register_next_step_handler(msg, process_username)

def process_username(message):
    username = message.text.strip().replace("@", "")
    if not username:
        bot.reply_to(message, "اسم المستخدم فاضي، جرب مرة ثانية.")
        return
        
    bot.reply_to(message, f"⏳ جاري جلب معلومات الحساب: @{username} ...")
    
    info = get_tiktok_info(username)
    
    if not info:
        bot.reply_to(message, f"❌ ما لقيت حساب باسم: @{username}")
        return
        
    if "error" in info:
        bot.reply_to(message, f"❌ خطأ: {info['error']}")
        return
        
    text = f"""
<b>📊 معلومات حساب تيك توك</b>

👤 <b>Username:</b> <code>@{info['username']}</code>
📛 <b>Nickname:</b> <code>{info['nickname']}</code>
🌍 <b>الدولة (Region):</b> <code>{info['region']}</code>
🆔 <b>ID:</b> <code>{info['id']}</code>
✅ <b>موثق:</b> {info['verified']}
🔒 <b>خاص:</b> {info['private']}

📈 <b>الإحصائيات:</b>
👥 المتابعين: <code>{info['followers']:,}</code>
👣 يتابع: <code>{info['following']:,}</code>
❤️ اللايكات: <code>{info['likes']:,}</code>
🎬 الفيديوهات: <code>{info['videos']:,}</code>

📅 <b>تاريخ الإنشاء:</b> <code>{info['created']}</code>
📝 <b>البايو:</b> {info['bio']}
🔗 <b>الرابط:</b> https://www.tiktok.com/@{info['username']}
"""
    bot.send_message(message.chat.id, text, parse_mode="HTML", disable_web_page_preview=True)

# --- تشغيل ---
if __name__ == "__main__":
    keep_alive()
    print("TikTok Bot is running...")
    bot.infinity_polling()
