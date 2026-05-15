import os, sys, json, time, zipfile, shutil, psutil, asyncio, subprocess, traceback, io, re, socket, ast, platform, math
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest
import html
from concurrent.futures import ThreadPoolExecutor
import tempfile

# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = "8682557219:AAE0DTCwCVnbJkq4Kjo7WMbGE6jYgXICEPU"
OWNER_ID = 8636937832
BOTS_DIR = "hosted_bots"
DB_FILE = "database.json"
LOG_FILE = "bot_errors.log"
TEMP_DIR = "temp_uploads"

os.makedirs(BOTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

executor = ThreadPoolExecutor(max_workers=10)

# ═══════════════════════════════════════════
# PREMIUM EMOJIS & STYLING
# ═══════════════════════════════════════════
class E:
    HOME = "◉"
    BACK = "◀"
    ROBOT = "◈"
    CROWN = "♕"
    USER = "◍"
    ID = "⌗"
    USERNAME = "﹫"
    STATUS = "⚡"
    FILES = "🗂️"
    UPLOAD = "⬆️"
    CHECK = "✓"
    SPEED = "⚡"
    STATS = "📊"
    CHANNEL = "📢"
    CHAT = "💬"
    ADMIN = "⚙️"
    STOP = "⏹️"
    RESTART = "🔄"
    DELETE = "🗑️"
    VIEW = "👁️"
    EDIT = "✏️"
    LOGS = "📋"
    RUNNING = "🟢"
    STOPPED = "🔴"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    CLOCK = "⏳"
    SERVER = "🖥️"
    CPU = "💻"
    RAM = "🧠"
    DISK = "💾"
    GLOBE = "🌐"
    LOCK = "🔒"
    UNLOCK = "🔓"
    KEY = "🔑"
    ROCKET = "🚀"
    FIRE = "🔥"
    HEART = "❤️"
    PARTY = "🎉"
    BELL = "🔔"
    PIN = "📌"
    CALENDAR = "📅"
    CHART = "📈"
    MONEY = "💰"
    TROPHY = "🏆"
    LINE = "─"
    DOT = "•"
    STAR = "⭐"
    PREMIUM = "💎"
    VERIFIED = "✔️"
    SPARKLE = "✨"
    BOLT = "⚡"
    INFINITY = "∞"
    MEDAL = "🏅"
    GEM = "💠"
    DIAMOND = "🔷"
    SHIELD = "🛡️"
    HEADPHONE = "🎧"
    MSG = "💬"
    INFO = "ℹ️"
    COMMAND = "⌨️"
    NETWORK = "🌍"
    PING = "📡"
    UPTIME = "⏱️"
    ACTIVE = "🎯"
    TOTAL = "📊"
    DATABASE = "🗄️"
    SYNC = "🔄"
    POWER = "🔋"
    TEMP = "🌡️"
    CLOCK_ICON = "🕐"

def escape_html(text):
    if not text:
        return ""
    return html.escape(str(text), quote=False)

def format_uptime(seconds):
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds//60}m {seconds%60}s"
    elif seconds < 86400:
        return f"{seconds//3600}h {(seconds%3600)//60}m"
    else:
        return f"{seconds//86400}d {(seconds%86400)//3600}h"

def get_bot_uptime():
    try:
        process = psutil.Process()
        start_time = process.create_time()
        return int(time.time() - start_time)
    except:
        return 0

def kill_process_tree(pid):
    """Safely and fully kill a process and all its children (zombie prevention)."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except:
                pass
        parent.kill()
    except:
        pass

async def safe_edit_message(query, text, reply_markup=None, parse_mode=ParseMode.HTML):
    """Safely edits message to prevent 'Message is not modified' error."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise e

# ═══════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════
class Database:
    def __init__(self):
        self.default = {
            "users": {},
            "admins": [OWNER_ID],
            "channels": [],
            "update_channels": [],
            "chat_gcs": [],
            "banned_users": [],
            "log_channel": None,
            "total_uploads": 0,
            "total_deletions": 0,
            "settings": {
                "auto_delete_time": 0,
                "demo_mode": False
            }
        }
        self.data = self.load()
        self._lock = asyncio.Lock()
    
    def load(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, 'r') as f:
                    data = json.load(f)
                for key in self.default:
                    if key not in data:
                        data[key] = self.default[key]
                return data
            except:
                return self.default.copy()
        return self.default.copy()
    
    async def save(self):
        async with self._lock:
            with open(DB_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
    
    def get_user(self, user_id):
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "username": "",
                "first_name": "",
                "last_name": "",
                "uploads_count": 0,
                "max_uploads": 10,
                "bots": {},
                "joined": datetime.now().isoformat(),
                "status": "free",
                "last_active": datetime.now().isoformat()
            }
            asyncio.create_task(self.save())
        return self.data["users"][uid]
    
    def is_admin(self, user_id):
        return user_id in self.data["admins"] or user_id == OWNER_ID
    
    def is_banned(self, user_id):
        return user_id in self.data["banned_users"]
    
    def get_contact_admin(self):
        for admin in self.data["admins"]:
            if admin != OWNER_ID:
                return admin
        return OWNER_ID

db = Database()

running_bots = {}
user_states = {}

# ═══════════════════════════════════════════
# ADVANCED AI: SMART DEPENDENCY MANAGER
# ═══════════════════════════════════════════
class SmartDependencyManager:
    STD_LIBS = {"os", "sys", "json", "time", "zipfile", "shutil", "asyncio", "subprocess", 
                "traceback", "io", "re", "socket", "ast", "platform", "math", "datetime", 
                "random", "logging", "typing", "collections", "itertools", "functools", 
                "pathlib", "urllib", "sqlite3", "threading", "multiprocessing", "hashlib", 
                "base64", "uuid", "abc", "argparse", "html", "tempfile"}

    KNOWN_MAPPINGS = {
        "telegram": "python-telegram-bot",
        "telethon": "Telethon",
        "pyrogram": "Pyrogram",
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "bs4": "beautifulsoup4",
        "dotenv": "python-dotenv",
        "motor": "motor",
        "pymongo": "pymongo",
        "sqlalchemy": "SQLAlchemy",
        "yaml": "PyYAML",
        "dateutil": "python-dateutil",
        "flask": "Flask",
        "discord": "discord.py",
        "requests": "requests",
        "aiohttp": "aiohttp"
    }

    @staticmethod
    def scan_imports(bot_dir):
        imports = set()
        for root, _, files in os.walk(bot_dir):
            if 'venv' in root or '__pycache__' in root:
                continue
            for f in files:
                if f.endswith('.py'):
                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, "r", encoding="utf-8") as file:
                            tree = ast.parse(file.read())
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    imports.add(alias.name.split('.')[0])
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    imports.add(node.module.split('.')[0])
                    except Exception:
                        pass
        
        packages_to_install = set()
        std_libs = SmartDependencyManager.STD_LIBS
        if hasattr(sys, 'stdlib_module_names'):
            std_libs = std_libs.union(sys.stdlib_module_names)

        for imp in imports:
            if imp not in std_libs and not imp.startswith("_"):
                packages_to_install.add(SmartDependencyManager.KNOWN_MAPPINGS.get(imp, imp))
                
        return list(packages_to_install)

# ═══════════════════════════════════════════
# FAST DEPLOYMENT ENGINE (WITH AI AUTO-FIX)
# ═══════════════════════════════════════════
PYTHON_VERSIONS = ["python3.11", "python3.10", "python3.9", "python3", "python"]
START_FILE_PRIORITY = ["main.py", "bot.py", "app.py", "run.py", "server.py", "start.py"]

class FastDeployEngine:
    
    @staticmethod
    async def find_python():
        for py in PYTHON_VERSIONS:
            try:
                proc = await asyncio.create_subprocess_exec(
                    py, "--version", 
                    stdout=asyncio.subprocess.PIPE, 
                    stderr=asyncio.subprocess.PIPE
                )
                await asyncio.wait_for(proc.communicate(), timeout=3)
                if proc.returncode == 0:
                    return py
            except:
                pass
        return sys.executable
    
    @staticmethod
    def detect_start_file(bot_dir):
        for root, _, files in os.walk(bot_dir):
            if 'venv' in root or '__pycache__' in root:
                continue
            for priority in START_FILE_PRIORITY:
                if priority in files:
                    return os.path.join(root, priority)
        for root, _, files in os.walk(bot_dir):
            for f in files:
                if f.endswith('.py') and 'venv' not in root:
                    return os.path.join(root, f)
        return None
    
    @staticmethod
    async def install_dependencies_fast(bot_dir, python_exe, log_lines):
        req_file = None
        for root, _, files in os.walk(bot_dir):
            if 'requirements.txt' in files:
                req_file = os.path.join(root, 'requirements.txt')
                break
        
        if req_file:
            log_lines.append(f"📦 Installing from {os.path.basename(req_file)}...")
            cmd = [python_exe, "-m", "pip", "install", "--no-cache-dir", "-r", req_file]
        else:
            log_lines.append("🔍 No requirements.txt found. AI scanning code for modules...")
            packages = SmartDependencyManager.scan_imports(bot_dir)
            if not packages:
                log_lines.append("✅ No external modules required.")
                return True
            log_lines.append(f"📦 Auto-installing: {', '.join(packages)}")
            cmd = [python_exe, "-m", "pip", "install", "--no-cache-dir"] + packages
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.communicate(), timeout=90)
            
            if proc.returncode == 0:
                log_lines.append("✅ Dependencies installed successfully")
            else:
                log_lines.append("⚠️ Some packages failed, but continuing...")
            return True
        except Exception as e:
            log_lines.append(f"⚠️ Install error: {str(e)[:50]}")
            return True
    
    @staticmethod
    async def deploy_fast(bot_dir, bot_name, user_id, token, status_msg, context):
        log_lines = []
        
        async def update_status(text):
            try:
                await safe_edit_message(status_msg, text[:4000])
            except:
                pass
        
        await update_status(f"{E.ROCKET} <b>DEPLOYING...</b>\n\n✅ Extracted files\n🔍 Detecting framework...")
        
        main_file = FastDeployEngine.detect_start_file(bot_dir)
        if not main_file:
            return {"error": "No .py file found", "logs": log_lines}
        
        log_lines.append(f"✅ Main file: {os.path.basename(main_file)}")
        
        env = os.environ.copy()
        # FIX: Force Python to unbuffer output so logs update immediately
        env["PYTHONUNBUFFERED"] = "1"
        
        if token and re.match(r'^\d{8,12}:[A-Za-z0-9_\-]{35}$', token.strip()):
            env["BOT_TOKEN"] = token.strip()
            with open(os.path.join(bot_dir, ".env"), "w") as f:
                f.write(f"BOT_TOKEN={token.strip()}\n")
            log_lines.append("✅ Token saved")
        
        env_file = os.path.join(bot_dir, ".env")
        if os.path.exists(env_file):
            with open(env_file) as ef:
                for line in ef:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        env[k.strip()] = v.strip()
        
        await update_status(f"{E.ROCKET} <b>DEPLOYING...</b>\n\n✅ Framework detected\n🐍 Installing dependencies...")
        
        python_exe = await FastDeployEngine.find_python()
        log_lines.append(f"✅ Python: {os.path.basename(python_exe)}")
        
        await FastDeployEngine.install_dependencies_fast(bot_dir, python_exe, log_lines)
        
        await update_status(f"{E.ROCKET} <b>LAUNCHING...</b>\n\n✅ Dependencies ready\n🚀 Starting bot...")
        
        main_dir = os.path.dirname(main_file)
        main_filename = os.path.basename(main_file)
        log_path = os.path.join(bot_dir, "bot.log")
        
        MAX_RETRIES = 3
        retry_count = 0
        
        while retry_count < MAX_RETRIES:
            log_f = open(log_path, "a" if retry_count > 0 else "w")
            try:
                process = subprocess.Popen(
                    [python_exe, main_filename],
                    stdout=log_f, stderr=subprocess.STDOUT,
                    cwd=main_dir, env=env, text=True,
                    start_new_session=True
                )
                
                await asyncio.sleep(4)
                
                if process.poll() is None:
                    log_lines.append(f"✅ Bot running! PID: {process.pid}")
                    return {
                        "process": process,
                        "user_id": user_id,
                        "dir": bot_dir,
                        "main_file": main_file,
                        "started": datetime.now().isoformat(),
                        "python": python_exe,
                        "deploy_logs": log_lines,
                    }
                else:
                    log_f.flush()
                    log_f.close()
                    with open(log_path, 'r') as f:
                        error = f.read()[-1500:]
                    
                    # AI CONFLICT DETECTION (New Fix)
                    if "Conflict: terminated by other getUpdates request" in error:
                        conflict_msg = (
                            "🤖 <b>AI DIAGNOSIS: CONFLICT ERROR</b>\n\n"
                            "Your bot token is already running somewhere else (e.g., your phone, local PC, or another host).\n\n"
                            "<b>Fix:</b> Stop the bot on the other device, wait 10 seconds, and try restarting it here."
                        )
                        log_lines.append("❌ AI: Conflict detected. Bot running elsewhere.")
                        return {"error": conflict_msg, "logs": log_lines}

                    # AI MODULE DETECTION
                    match = re.search(r"ModuleNotFoundError: No module named '([^']+)'", error)
                    if not match:
                        match = re.search(r"ImportError: .* module named '([^']+)'", error)
                    
                    if match:
                        missing_module = match.group(1)
                        real_package = SmartDependencyManager.KNOWN_MAPPINGS.get(missing_module, missing_module)
                        log_lines.append(f"🤖 AI Auto-Fix: Installing missing module {real_package}...")
                        await update_status(f"🤖 <b>AI AUTO-FIX TRIGGERED</b>\n\nInstalling missing module: <code>{real_package}</code>")
                        
                        proc = await asyncio.create_subprocess_exec(
                            python_exe, "-m", "pip", "install", real_package,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        await asyncio.wait_for(proc.communicate(), timeout=30)
                        
                        retry_count += 1
                        log_lines.append(f"🔄 Restarting bot (Attempt {retry_count})...")
                        continue
                    else:
                        return {"error": f"Bot crashed immediately:\n<pre>{escape_html(error[-500:])}</pre>", "logs": log_lines}
                    
            except Exception as e:
                log_f.close()
                return {"error": f"Launch error: {str(e)}", "logs": log_lines}

        return {"error": "Bot failed to start after maximum AI Auto-Fix attempts.", "logs": log_lines}

# ═══════════════════════════════════════════
# PREMIUM UI KEYBOARDS
# ═══════════════════════════════════════════

def get_system_stats():
    cpu_percent = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    cpu_bar_length = int(cpu_percent / 10)
    cpu_bar = "█" * cpu_bar_length + "░" * (10 - cpu_bar_length)
    
    ram_percent = ram.percent
    ram_bar_length = int(ram_percent / 10)
    ram_bar = "█" * ram_bar_length + "░" * (10 - ram_bar_length)
    
    disk_percent = disk.percent
    disk_bar_length = int(disk_percent / 10)
    disk_bar = "█" * disk_bar_length + "░" * (10 - disk_bar_length)
    
    return {
        "cpu": cpu_percent, "cpu_bar": cpu_bar,
        "ram": ram_percent, "ram_bar": ram_bar,
        "ram_used": ram.used // (1024**3), "ram_total": ram.total // (1024**3),
        "disk": disk_percent, "disk_bar": disk_bar,
        "disk_used": disk.used // (1024**3), "disk_total": disk.total // (1024**3)
    }

def main_menu_keyboard(user_id):
    contact_admin = db.get_contact_admin()
    keyboard = []
    
    if db.data.get("update_channels") and db.data["update_channels"][0]:
        keyboard.append([InlineKeyboardButton(f"{E.BELL} 【 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ 】 {E.BELL}", url=f"https://t.me/{db.data['update_channels'][0].strip()}")])
    
    row1 = []
    if db.data.get("channels") and db.data["channels"][0]:
        row1.append(InlineKeyboardButton(f"{E.CHANNEL} ᴄʜᴀɴɴᴇʟ", url=f"https://t.me/{db.data['channels'][0].strip()}"))
    if db.data.get("chat_gcs") and db.data["chat_gcs"][0]:
        row1.append(InlineKeyboardButton(f"{E.CHAT} ɢʀᴏᴜᴘ", url=f"https://t.me/{db.data['chat_gcs'][0].strip()}"))
    if row1: keyboard.append(row1)
    
    keyboard.append([InlineKeyboardButton(f"{E.UPLOAD} ᴜᴘʟᴏᴀᴅ ʙᴏᴛ", callback_data="upload_file"),
                     InlineKeyboardButton(f"{E.CHECK} ᴍʏ ʙᴏᴛs", callback_data="check_files")])
    keyboard.append([InlineKeyboardButton(f"{E.SPEED} sᴘᴇᴇᴅ ᴛᴇsᴛ", callback_data="bot_speed"),
                     InlineKeyboardButton(f"{E.STATS} sᴛᴀᴛɪsᴛɪᴄs", callback_data="statistics")])
    keyboard.append([InlineKeyboardButton(f"{E.HEADPHONE} 【 ᴄᴏɴᴛᴀᴄᴛ sᴜᴘᴘᴏʀᴛ 】 {E.HEADPHONE}", url=f"tg://user?id={contact_admin}")])
    return InlineKeyboardMarkup(keyboard)

def back_keyboard(data="main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{E.BACK} ʙᴀᴄᴋ", callback_data=data)]])

def back_main_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{E.BACK} ʙᴀᴄᴋ ᴛᴏ ʟɪsᴛ", callback_data="check_files"), 
                                  InlineKeyboardButton(f"{E.HOME} ʜᴏᴍᴇ", callback_data="main_menu")]])

def get_uptime(bot_name):
    if bot_name in running_bots:
        started = running_bots[bot_name].get("started")
        if started:
            try:
                delta = datetime.now() - datetime.fromisoformat(started)
                return format_uptime(int(delta.total_seconds()))
            except: pass
    return "N/A"

# ═══════════════════════════════════════════
# USER COMMANDS
# ═══════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if db.is_banned(user_id):
        await update.message.reply_text(f"{E.ERROR} {E.SHIELD} <b>ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ</b> {E.SHIELD}", parse_mode=ParseMode.HTML)
        return
    
    user_data = db.get_user(user_id)
    user_data["username"] = user.username or ""
    user_data["first_name"] = user.first_name or ""
    user_data["last_active"] = datetime.now().isoformat()
    await db.save()
    
    running_count = sum(1 for n in user_data["bots"] if n in running_bots and running_bots[n]["process"].poll() is None)
    stats = get_system_stats()
    
    welcome_text = (
        f"◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈\n"
        f"  {E.PREMIUM} <b>ᴘʀᴇᴍɪᴜᴍ ʙᴏᴛ ʜᴏsᴛɪɴɢ</b> {E.PREMIUM}\n"
        f"◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈\n\n"
        f"{E.CROWN} <b>ᴡᴇʟᴄᴏᴍᴇ</b> {E.SPARKLE}\n"
        f"   {escape_html(user.first_name)} [{user_id}]\n\n"
        f"{E.STATUS} <b>ʏᴏᴜʀ sᴛᴀᴛs</b>\n"
        f"   {E.FILES} ᴜᴘʟᴏᴀᴅs : <code>{user_data['uploads_count']} / {user_data['max_uploads']}</code>\n"
        f"   {E.ROBOT} ᴀᴄᴛɪᴠᴇ : <code>{running_count}</code>\n\n"
        f"{E.SERVER} <b>sᴇʀᴠᴇʀ sᴛᴀᴛᴜs</b>\n"
        f"   {E.CPU} ᴄᴘᴜ : [{stats['cpu_bar']}] <code>{stats['cpu']}%</code>\n"
        f"   {E.RAM} ʀᴀᴍ : [{stats['ram_bar']}] <code>{stats['ram']}%</code>\n"
        f"   {E.UPTIME} ᴜᴘᴛɪᴍᴇ : <code>{format_uptime(get_bot_uptime())}</code>\n\n"
        f"{E.LINE}────────────────────\n"
        f"{E.DOT} 𝟸𝟺/𝟽 ᴘʀᴇᴍɪᴜᴍ ʜᴏsᴛɪɴɢ\n"
        f"{E.DOT} ᴀɪ-ᴘᴏᴡᴇʀᴇᴅ ᴀᴜᴛᴏ ꜰɪx\n"
        f"{E.LINE}────────────────────"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard(user_id), parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════

async def upload_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if user_data["uploads_count"] >= user_data["max_uploads"]:
        await safe_edit_message(query, f"{E.ERROR} ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ! ᴍᴀx: {user_data['max_uploads']}", reply_markup=back_keyboard())
        return
    
    user_states[user_id] = "waiting_file"
    text = (f"{E.UPLOAD} <b>ᴜᴘʟᴏᴀᴅ ʏᴏᴜʀ ʙᴏᴛ ꜰɪʟᴇ</b>\n\n"
            f"{E.DOT} sᴜᴘᴘᴏʀᴛᴇᴅ: .ᴘʏ, .ᴢɪᴘ\n"
            f"{E.DOT} ᴀᴅᴅ ʙᴏᴛ ᴛᴏᴋᴇɴ ɪɴ ᴄᴀᴘᴛɪᴏɴ (ᴏᴘᴛɪᴏɴᴀʟ)\n"
            f"{E.DOT} <ins>ᴀɪ ᴡɪʟʟ ᴀᴜᴛᴏ-ɪɴsᴛᴀʟʟ ᴍɪssɪɴɢ ᴍᴏᴅᴜʟᴇs</ins>")
    await safe_edit_message(query, text, reply_markup=back_keyboard("main_menu"))

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.is_banned(user_id) or user_states.get(user_id) != "waiting_file": return
    user_states[user_id] = None
    
    file = update.message.document
    if not file: return await update.message.reply_text(f"{E.ERROR} sᴇɴᴅ ᴀ ꜰɪʟᴇ!", reply_markup=back_keyboard("main_menu"))
    
    file_name = file.file_name or f"bot_{user_id}_{int(time.time())}"
    if not (file_name.endswith('.py') or file_name.endswith('.zip')):
        return await update.message.reply_text(f"{E.ERROR} ᴏɴʟʏ .ᴘʏ ᴏʀ .ᴢɪᴘ ᴀʟʟᴏᴡᴇᴅ!", reply_markup=back_keyboard("main_menu"))
    
    bot_name = os.path.splitext(file_name)[0].replace(" ", "_")[:30]
    bot_dir = os.path.join(BOTS_DIR, str(user_id), bot_name)
    
    if os.path.exists(bot_dir): shutil.rmtree(bot_dir)
    os.makedirs(bot_dir, exist_ok=True)
    
    status_msg = await update.message.reply_text(f"{E.CLOCK} <b>ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...</b>", parse_mode=ParseMode.HTML)
    file_path = os.path.join(bot_dir, file_name)
    tg_file = await context.bot.get_file(file.file_id)
    await tg_file.download_to_drive(file_path)
    
    token = update.message.caption or ""
    
    try:
        if file_name.endswith('.zip'):
            await asyncio.to_thread(lambda: zipfile.ZipFile(file_path, 'r').extractall(bot_dir) or os.remove(file_path))
        elif file_name.endswith('.py'):
            os.rename(file_path, os.path.join(bot_dir, f"bot.py"))
        
        # Kill previous instance gracefully
        if bot_name in running_bots:
            kill_process_tree(running_bots[bot_name]["process"].pid)
            del running_bots[bot_name]
        
        result = await FastDeployEngine.deploy_fast(bot_dir, bot_name, user_id, token, status_msg, context)
        
        if result and "error" not in result:
            running_bots[bot_name] = result
            db.get_user(user_id)["bots"][bot_name] = {
                "name": bot_name, "dir": bot_dir, "main_file": result["main_file"],
                "status": "running", "uploaded": datetime.now().isoformat(),
            }
            db.get_user(user_id)["uploads_count"] += 1
            db.data["total_uploads"] += 1
            await db.save()
            
            await safe_edit_message(status_msg, f"{E.SUCCESS} <b>ʙᴏᴛ ɪs ʀᴜɴɴɪɴɢ!</b>\n\n{E.ROBOT} ɴᴀᴍᴇ: <code>{bot_name}</code>\n{E.ID} ᴘɪᴅ: <code>{result['process'].pid}</code>\n{E.CLOCK} ᴜᴘᴛɪᴍᴇ: 0s\n\n<pre>{escape_html(chr(10).join(result.get('deploy_logs', [])[-4:]))}</pre>", reply_markup=back_main_keyboard())
        else:
            await safe_edit_message(status_msg, f"{E.WARNING} <b>ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ꜰᴀɪʟᴇᴅ</b>\n\n{result.get('error')}", reply_markup=back_main_keyboard())
            
    except Exception as e:
        await safe_edit_message(status_msg, f"{E.ERROR} <b>ᴇʀʀᴏʀ:</b> {escape_html(str(e)[:200])}", reply_markup=back_keyboard("main_menu"))

async def check_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bots = db.get_user(update.effective_user.id).get("bots", {})
    
    if not bots:
        return await safe_edit_message(query, f"{E.CHECK} ɴᴏ ʙᴏᴛs ꜰᴏᴜɴᴅ.", reply_markup=back_keyboard("main_menu"))
    
    text = f"{E.CHECK} <b>ʏᴏᴜʀ ʙᴏᴛs</b>\n{E.LINE}────────────────\n\n"
    keyboard = []
    for bot_name in bots:
        is_active = bot_name in running_bots and running_bots[bot_name]["process"].poll() is None
        status = E.RUNNING if is_active else E.STOPPED
        text += f"{status} <code>{escape_html(bot_name[:20])}</code>\n"
        keyboard.append([InlineKeyboardButton(f"{status} {bot_name[:25]}", callback_data=f"botinfo_{bot_name}")])
    
    keyboard.append([InlineKeyboardButton(f"{E.HOME} ʜᴏᴍᴇ", callback_data="main_menu")])
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.replace("botinfo_", "")
    bot_data = db.get_user(update.effective_user.id)["bots"].get(bot_name)
    
    if not bot_data: return await safe_edit_message(query, "ʙᴏᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ!", reply_markup=back_keyboard("check_files"))
    
    is_active = bot_name in running_bots and running_bots[bot_name]["process"].poll() is None
    status_icon, status_text = (E.RUNNING, "ᴀᴄᴛɪᴠᴇ") if is_active else (E.STOPPED, "sᴛᴏᴘᴘᴇᴅ")
    
    text = (f"{E.ROBOT} <b>ʙᴏᴛ ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ</b>\n{E.LINE}────────────────\n\n"
            f"ɴᴀᴍᴇ: <code>{escape_html(bot_name)}</code>\n"
            f"sᴛᴀᴛᴜs: {status_icon} {status_text}\n"
            f"ᴘɪᴅ: <code>{running_bots[bot_name]['process'].pid if is_active else 'ɴ/ᴀ'}</code>\n"
            f"ᴜᴘᴛɪᴍᴇ: {get_uptime(bot_name) if is_active else 'ɴ/ᴀ'}")
    
    keyboard = [
        [InlineKeyboardButton(f"{E.STOP} sᴛᴏᴘ", callback_data=f"stopbot_{bot_name}"), InlineKeyboardButton(f"{E.RESTART} ʀᴇsᴛᴀʀᴛ", callback_data=f"restartbot_{bot_name}"), InlineKeyboardButton(f"{E.DELETE} ᴅᴇʟᴇᴛᴇ", callback_data=f"deletebot_{bot_name}")],
        [InlineKeyboardButton(f"{E.LOGS} ʟᴏɢs", callback_data=f"viewlogs_{bot_name}")],
        [InlineKeyboardButton(f"{E.BACK} ʙᴀᴄᴋ", callback_data="check_files")]
    ]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    bot_name = query.data.replace("deletebot_", "")
    user_data = db.get_user(user_id)
    
    if bot_name in running_bots:
        kill_process_tree(running_bots[bot_name]["process"].pid)
        del running_bots[bot_name]
    
    if bot_name in user_data["bots"]:
        bot_dir = user_data["bots"][bot_name].get("dir", "")
        if os.path.exists(bot_dir): shutil.rmtree(bot_dir, ignore_errors=True)
        del user_data["bots"][bot_name]
        user_data["uploads_count"] = max(0, user_data["uploads_count"] - 1)
        db.data["total_deletions"] += 1
        await db.save()
    
    await safe_edit_message(query, f"{E.SUCCESS} ʙᴏᴛ ᴅᴇʟᴇᴛᴇᴅ: <code>{escape_html(bot_name)}</code>", reply_markup=back_keyboard("check_files"))

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.replace("stopbot_", "")
    
    if bot_name in running_bots:
        kill_process_tree(running_bots[bot_name]["process"].pid)
        del running_bots[bot_name]
        await safe_edit_message(query, f"{E.SUCCESS} ʙᴏᴛ sᴛᴏᴘᴘᴇᴅ: <code>{escape_html(bot_name)}</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{E.RESTART} ʀᴇsᴛᴀʀᴛ", callback_data=f"restartbot_{bot_name}"), InlineKeyboardButton(f"{E.BACK} ʙᴀᴄᴋ", callback_data=f"botinfo_{bot_name}")]]))
    else:
        await query.answer("Bot is already stopped!")

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Restarting...", show_alert=False)
    user_id = update.effective_user.id
    bot_name = query.data.replace("restartbot_", "")
    bot_data = db.get_user(user_id)["bots"].get(bot_name)
    
    if not bot_data: return
    
    if bot_name in running_bots:
        kill_process_tree(running_bots[bot_name]["process"].pid)
        del running_bots[bot_name]
    
    bot_dir, main_file = bot_data["dir"], bot_data["main_file"]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1" # Important for Logs Fix
    
    if os.path.exists(os.path.join(bot_dir, ".env")):
        with open(os.path.join(bot_dir, ".env")) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    
    python_exe = await FastDeployEngine.find_python()
    log_f = open(os.path.join(bot_dir, "bot.log"), "w")
    process = subprocess.Popen([python_exe, os.path.basename(main_file)], stdout=log_f, stderr=subprocess.STDOUT, cwd=os.path.dirname(main_file), env=env, start_new_session=True)
    
    running_bots[bot_name] = {"process": process, "user_id": user_id, "dir": bot_dir, "main_file": main_file, "started": datetime.now().isoformat(), "python": python_exe}
    
    await safe_edit_message(query, f"{E.RESTART} ʀᴇsᴛᴀʀᴛᴇᴅ: <code>{escape_html(bot_name)}</code>\nᴘɪᴅ: {process.pid}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{E.BACK} ʙᴀᴄᴋ", callback_data=f"botinfo_{bot_name}")]]))

async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.replace("viewlogs_", "")
    bot_data = db.get_user(update.effective_user.id)["bots"].get(bot_name)
    
    if not bot_data: return
    
    log_path = os.path.join(bot_data["dir"], "bot.log")
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            logs = f.read()[-3000:] # Increased log reading size
        text = f"{E.LOGS} <b>{escape_html(bot_name)} ʟᴏɢs</b>\n\n<pre>{escape_html(logs) if logs.strip() else 'Waiting for output...'}</pre>"
    else:
        text = f"{E.ERROR} ɴᴏ ʟᴏɢs ꜰᴏᴜɴᴅ."
        
    await safe_edit_message(query, text[:4000], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{E.RESTART} ʀᴇꜰʀᴇsʜ", callback_data=f"viewlogs_{bot_name}")], [InlineKeyboardButton(f"{E.BACK} ʙᴀᴄᴋ", callback_data=f"botinfo_{bot_name}")]]))

async def bot_speed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    st = time.time()
    stats = get_system_stats()
    ping = round((time.time() - st) * 1000, 2)
    
    text = (f"{E.SPEED} <b>sʏsᴛᴇᴍ ᴍᴏɴɪᴛᴏʀ</b>\n{E.LINE}────────────────\n\n"
            f"{E.PING} ᴘɪɴɢ : <code>{ping}ᴍs</code>\n"
            f"{E.CPU} ᴄᴘᴜ  : [{stats['cpu_bar']}] <code>{stats['cpu']}%</code>\n"
            f"{E.RAM} ʀᴀᴍ  : [{stats['ram_bar']}] <code>{stats['ram']}%</code>\n"
            f"{E.UPTIME} ᴜᴘᴛɪᴍᴇ: <code>{format_uptime(get_bot_uptime())}</code>")
    await safe_edit_message(query, text, reply_markup=back_keyboard("main_menu"))

async def statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (f"{E.STATS} <b>ꜰᴜʟʟ sᴛᴀᴛɪsᴛɪᴄs</b>\n{E.LINE}────────────────\n\n"
            f"{E.TOTAL} ᴛᴏᴛᴀʟ ᴜsᴇʀs : <code>{len(db.data['users'])}</code>\n"
            f"{E.UPLOAD} ᴛᴏᴛᴀʟ ᴜᴘʟᴏᴀᴅs : <code>{db.data['total_uploads']}</code>\n"
            f"{E.ACTIVE} ᴀᴄᴛɪᴠᴇ ʙᴏᴛs : <code>{len([b for b in running_bots.values() if b['process'].poll() is None])}/{len(running_bots)}</code>")
    await safe_edit_message(query, text, reply_markup=back_keyboard("main_menu"))

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    running = sum(1 for n in user_data["bots"] if n in running_bots and running_bots[n]["process"].poll() is None)
    
    text = (f"◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈\n  {E.PREMIUM} <b>ᴘʀᴇᴍɪᴜᴍ ʙᴏᴛ ʜᴏsᴛɪɴɢ</b> {E.PREMIUM}\n◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈◈\n\n"
            f"{E.CROWN} {escape_html(update.effective_user.first_name)}\n"
            f"{E.FILES} <code>{user_data['uploads_count']} / {user_data['max_uploads']}</code>\n"
            f"{E.ROBOT} <code>{running}</code> ᴀᴄᴛɪᴠᴇ")
    await safe_edit_message(query, text, reply_markup=main_menu_keyboard(user_id))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Log errors quietly, don't break the bot
    if "Message is not modified" in str(context.error): return
    with open(LOG_FILE, 'a') as f:
        f.write(f"{datetime.now().isoformat()} - {str(context.error)}\n")

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(upload_file_callback, pattern="^upload_file$"))
    app.add_handler(CallbackQueryHandler(check_files, pattern="^check_files$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(bot_info, pattern="^botinfo_"))
    app.add_handler(CallbackQueryHandler(stop_bot, pattern="^stopbot_"))
    app.add_handler(CallbackQueryHandler(restart_bot, pattern="^restartbot_"))
    app.add_handler(CallbackQueryHandler(delete_bot, pattern="^deletebot_"))
    app.add_handler(CallbackQueryHandler(view_logs, pattern="^viewlogs_"))
    app.add_handler(CallbackQueryHandler(bot_speed, pattern="^bot_speed$"))
    app.add_handler(CallbackQueryHandler(statistics, pattern="^statistics$"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    
    app.add_error_handler(error_handler)
    
    await app.bot.set_my_commands([BotCommand("start", "🚀 Start the bot")])
    print("✅ PREMIUM BOT HOSTING - STARTED!")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    while True: await asyncio.sleep(1)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: executor.shutdown(wait=False)