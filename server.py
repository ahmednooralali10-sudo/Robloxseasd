import os
import threading
import requests
import telebot
from telebot import types
from flask import Flask
from tiktok_api import TT_Content_Scraper

# --- الإعدادات ---
BOT_TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"  # -
ADMIN_ID = 7075895496        # <--- الآيدي حقك

# --- Flask للسيرفر ---
app = Flask(__name__)

@app.route("/")
def index():
    return "TikTok Bot is running!"

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000))
    t.daemon = True
    t.start()

# --- إعدادات البوت ---
bot = telebot.TeleBot(BOT_TOKEN)

# --- دالة جلب معلومات تيك توك ---
def get_tiktok_info(username):
    try:
        scraper = TT_Content_Scraper(
            wait_time=0.35,
            output_files_fp="tiktok_data/",
            progress_file_fn="tiktok_data/progress.db",
            clear_console=False,
        )
        scraper.add_objects(ids=[username], title="user_lookup", type="user")
        scraper.scrape_pending(scrape_files=False)
        
        # البحث عن الملف اللي تم إنشاؤه
        import json
        import glob
        files = glob.glob(f"tiktok_data/user_metadata/{username}.json")
        if not files:
            return None
            
        with open(files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        info = {
            "username": data.get("uniqueId", username),
            "nickname": data.get("nickname", "N/A"),
            "region": data.get("region", "N/A"),
            "followers": data.get("followerCount", 0),
            "following": data.get("followingCount", 0),
            "likes": data.get("heartCount", 0),
            "videos": data.get("videoCount", 0),
            "verified": "✅" if data.get("verified", False) else "❌",
            "private": "🔒" if data.get("privateAccount", False) else "🔓",
            "bio": data.get("signature", "N/A"),
            "created": data.get("createTime", "N/A"),
            "avatar": data.get("avatarLarger", "N/A"),
            "secUid": data.get("secUid", "N/A"),
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
        "أهلاً بك في بوت تيك توك.\nاضغط الزر تحت وأرسل اسم المستخدم (بدون @) عشان يجيب لك كل المعلومات.",
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
