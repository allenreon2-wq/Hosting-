import os
import sqlite3
import asyncio
import base64
import aiohttp
import sys
import io
import traceback
import re
from datetime import datetime
from bs4 import BeautifulSoup
from gtts import gTTS
from pyrogram import Client, filters
from pyrogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction, ChatMemberStatus, ChatType
from duckduckgo_search import DDGS
from google import genai
from google.genai import types

# ================== CONFIGURATION ==================
API_ID = 37114316
API_HASH = "ebc830f2b1c22bebd367eae88328c4f5"
BOT_TOKEN = "8827329221:AAESe4s23G6756UG2A7U1BjI6S6Hb_Zbw2Q"

# API KEYS
GROQ_API_KEY = "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"
GEMINI_API_KEY = "AIzaSyCQaLZ0I7intA-XPoTdqXKMti5zGIrhIBw"

OWNER_ID = 8636937832  
CREATOR_NAME = "REONFX"  
BOT_NAME = "REONAI"  

GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

try:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Gemini Init Error: {e}")
    ai_client = None

# ================== DATABASE & MEMORY ==================
def init_db():
    conn = sqlite3.connect("reonai.db")
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, total_msgs INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0, joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS groups (chat_id INTEGER PRIMARY KEY, chat_title TEXT, chat_username TEXT, is_active INTEGER DEFAULT 1, added_by INTEGER, added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, chat_id INTEGER, role TEXT, content TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS core_memory (user_id INTEGER PRIMARY KEY, summary TEXT DEFAULT '', last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    """)
    conn.commit()
    conn.close()

init_db()

def add_user_and_count(uid, uname, fname, lname=""):
    try:
        conn = sqlite3.connect("reonai.db"); c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_date) VALUES (?,?,?,?, CURRENT_TIMESTAMP)", (uid, uname, fname, lname))
        c.execute("UPDATE users SET username=?, first_name=?, total_msgs = total_msgs + 1 WHERE user_id=?", (uname, fname, uid))
        c.execute("SELECT total_msgs FROM users WHERE user_id=?", (uid,))
        count = c.fetchone()[0]
        conn.commit(); conn.close()
        return count
    except: return 1

def save_memory(uid, cid, role, content):
    try:
        conn = sqlite3.connect("reonai.db"); c = conn.cursor()
        c.execute("INSERT INTO memory (user_id, chat_id, role, content) VALUES (?,?,?,?)", (uid, cid, role, str(content)[:2000]))
        c.execute("DELETE FROM memory WHERE id NOT IN (SELECT id FROM memory WHERE user_id=? ORDER BY timestamp DESC LIMIT 30)", (uid,))
        conn.commit(); conn.close()
    except: pass

def get_recent_memory(uid, limit=12):
    try:
        conn = sqlite3.connect("reonai.db"); c = conn.cursor()
        c.execute("SELECT role, content FROM memory WHERE user_id=? ORDER BY timestamp DESC LIMIT ?", (uid, limit))
        mem = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
        conn.close()
        return list(reversed(mem))
    except: return []

def get_core_memory(uid):
    try:
        conn = sqlite3.connect("reonai.db"); c = conn.cursor()
        c.execute("SELECT summary FROM core_memory WHERE user_id=?", (uid,))
        res = c.fetchone()
        conn.close()
        return res[0] if res else ""
    except: return ""

def update_core_memory_db(uid, new_summary):
    try:
        conn = sqlite3.connect("reonai.db"); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO core_memory (user_id, summary, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)", (uid, new_summary))
        conn.commit(); conn.close()
    except: pass

def resolve_user(query_str):
    query_str = query_str.replace("@", "").strip()
    if not query_str: return None
    conn = sqlite3.connect("reonai.db"); c = conn.cursor()
    if query_str.isdigit():
        c.execute("SELECT user_id, first_name, username, total_msgs FROM users WHERE user_id=?", (int(query_str),))
    else:
        c.execute("SELECT user_id, first_name, username, total_msgs FROM users WHERE username LIKE ? OR first_name LIKE ? COLLATE NOCASE", (f"%{query_str}%", f"%{query_str}%"))
    res = c.fetchone()
    conn.close()
    return res

async def generate_user_dossier(target_user):
    uid, fname, uname, msgs = target_user
    conn = sqlite3.connect("reonai.db"); c = conn.cursor()
    c.execute("SELECT role, content FROM memory WHERE user_id=? ORDER BY timestamp ASC LIMIT 20", (uid,))
    chats = c.fetchall()
    conn.close()
    
    core_mem = get_core_memory(uid)
    dossier = f"📂 **TARGET ACQUIRED: {fname}**\n👤 Username: @{uname if uname else 'N/A'}\n🆔 ID: `{uid}`\n💬 Total Msgs to AI: {msgs}\n\n"
    if core_mem: dossier += f"🧠 **AI's Summary of User:**\n{core_mem}\n\n"
    dossier += "🕵️‍♂️ **Recent Secret History:**\n"
    if not chats: dossier += "No recent chat found."
    else:
        for role, content in chats:
            icon = "👤" if role == "user" else "🤖"
            dossier += f"{icon}: {content[:100]}...\n"
    return dossier

async def get_todays_users():
    try:
        conn = sqlite3.connect("reonai.db"); c = conn.cursor()
        c.execute("SELECT user_id, first_name, username FROM users WHERE date(joined_date) = date('now')")
        users = c.fetchall()
        conn.close()
        if not users: return "Aaj koi naya user nahi aaya boss."
        res = f"📈 **Today's New Targets ({len(users)}):**\n\n"
        for u in users: res += f"• {u[1]} (@{u[2]}) - ID: `{u[0]}`\n"
        return res
    except: return "Error fetching today's users."

async def process_infinite_memory(uid, fname):
    recent_msgs = get_recent_memory(uid, 15)
    if len(recent_msgs) < 5: return
    current_summary = get_core_memory(uid)
    chat_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent_msgs])
    
    prompt = f"Update the core memory profile for user '{fname}'. Keep existing facts and add new important facts/projects from this recent chat. Keep it short and factual.\nCurrent Memory: {current_summary}\nRecent Chat: {chat_text}"
    
    try:
        response = await asyncio.to_thread(ai_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
        if response.text: update_core_memory_db(uid, response.text)
    except: pass

# ================== ADVANCED TOOLS ==================

async def generate_image_pollinations(prompt):
    import urllib.parse
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/p/{encoded_prompt}?width=1024&height=1024&seed=42&model=flux"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200: return await resp.read()
    except: pass
    return None

async def scrape_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    soup = BeautifulSoup(await resp.text(), "html.parser")
                    for script in soup(["script", "style"]): script.decompose()
                    text = soup.get_text()
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    return "\n".join(chunk for chunk in chunks if chunk)[:4000]
    except: pass
    return None

def run_python_sandbox(code_str):
    blacklist = ["os.", "sys.", "subprocess", "open", "eval", "exec", "shutil", "requests", "aiohttp", "importlib"]
    if any(word in code_str for word in blacklist):
        return "❌ Security Violation: Safe execution sandbox mein ye commands allowed nahi hain!"
    
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    
    try:
        exec(code_str, {"__builtins__": __import__("builtins")}, {})
        stdout_val = redirected_output.getvalue()
        return stdout_val if stdout_val.strip() else "Code executed successfully with NO console output (print)."
    except Exception:
        return traceback.format_exc()
    finally:
        sys.stdout = old_stdout

# ================== AI ENGINES ==================

async def ask_official_gemini_vision(prompt, image_path):
    if not ai_client: return "⚠️ Vision module offline."
    try:
        with open(image_path, "rb") as f: image_bytes = f.read()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')
        final_prompt = prompt if prompt else "Detail mein batao is image mein kya hai?"
        response = await asyncio.to_thread(ai_client.models.generate_content, model='gemini-2.5-flash', contents=[final_prompt, image_part])
        return response.text
    except Exception as e:
        return f"⚠️ Vision Error: {e}"

async def ask_official_gemini(system_prompt, messages_list):
    if not ai_client: return None
    contents = []
    for m in messages_list:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))
    config = types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.7)
    try:
        response = await asyncio.to_thread(ai_client.models.generate_content, model='gemini-2.5-flash', contents=contents, config=config)
        return response.text
    except: return None

async def ask_reonai_text(uid, text, uname="User", chat_type="private"):
    text_lower = text.lower()
    
    search_context = ""
    if any(word in text_lower for word in ["search", "latest", "news", "aaj"]):
        try:
            results = await asyncio.to_thread(DDGS().text, text, max_results=2)
            search_context = "\n[LIVE WEB SEARCH RESULTS]:\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        except: pass

    url_match = re.search(r'(https?://[^\s]+)', text)
    if url_match:
        scraped_content = await scrape_url(url_match.group(1))
        if scraped_content:
            search_context += f"\n[SCRAPED WEBPAGE CONTENT FROM LINK]:\n{scraped_content}\n"

    deep_memory = ""
    if any(word in text_lower for word in ["project", "yaad", "purana", "pichla"]):
        conn = sqlite3.connect("reonai.db"); c = conn.cursor()
        c.execute("SELECT content FROM memory WHERE user_id=? AND role='user' AND (content LIKE '%project%' OR content LIKE '%code%' OR content LIKE '%bana%') ORDER BY timestamp DESC LIMIT 5", (uid,))
        past_data = c.fetchall()
        conn.close()
        if past_data: deep_memory = "\n[DEEP DATABASE RECALL (User's Past Mentions)]:\n" + "\n".join([f"- {row[0]}" for row in past_data])

    recent_memory = get_recent_memory(uid, 12)
    core_mem = get_core_memory(uid)
    memory_injection = f"\nPERMANENT CONTEXT ABOUT THIS USER: {core_mem}\n{deep_memory}" if core_mem or deep_memory else ""
    
    if uid == OWNER_ID:
        system = f"You are {BOT_NAME}, an elite ultra-intelligent JARVIS entity. Creator is {CREATOR_NAME}. Wrap all code scripts strictly between ```python and ``` blocks. {memory_injection} {search_context}"
    else:
        system = f"You are {BOT_NAME}, an advanced critical-thinking AI by {CREATOR_NAME}. Wrap code scripts strictly between ```python and ``` blocks. Mix Hindi/English. {memory_injection} {search_context}"
    
    full_messages = recent_memory + [{"role": "user", "content": f"{uname}: {text}"}]
    reply = await ask_official_gemini(system, full_messages)
    
    if not reply:
        messages = [{"role": "system", "content": system}] + full_messages
        for model in GROQ_MODELS:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, json={"model": model, "messages": messages, "temperature": 0.6}) as resp:
                        if resp.status == 200:
                            reply = (await resp.json())["choices"][0]["message"]["content"]
                            break
            except: continue
            
    if reply:
        save_memory(uid, uid, "user", text)
        save_memory(uid, uid, "assistant", reply)
        return reply
    return "⚠️ Servers busy hain, thodi der me try kar."

# ================== BOT CLIENT & HANDLERS ==================
app = Client("reonai_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def cmd_start(client, message):
    add_user_and_count(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.reply_text(f"🌟 Welcome {message.from_user.first_name}!\n\n🤖 I am {BOT_NAME}.\nSandbox, Extra APIs & Web Reader is Online!")

# ================== NEW API HANDLERS ==================

@app.on_message(filters.command("meme"))
async def cmd_meme(client, message):
    """Reddit Meme API Integration"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://meme-api.com/gimme") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await message.reply_photo(data["url"], caption=f"🤪 **{data['title']}**\n(From r/{data['subreddit']})")
                else:
                    await message.reply_text("❌ Meme fetch karne me error aayi.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@app.on_message(filters.command("weather"))
async def cmd_weather(client, message):
    """Fast keyless Weather API (wttr.in)"""
    if len(message.command) < 2: 
        return await message.reply_text("❌ City ka naam daal bhai! Example: `/weather Indore`")
    
    city = "+".join(message.command[1:])
    try:
        async with aiohttp.ClientSession() as session:
            # format %C(Condition) %t(Temp) %w(Wind) %h(Humidity)
            async with session.get(f"https://wttr.in/{city}?format=%C+%t+%w+%h") as resp:
                if resp.status == 200:
                    data = await resp.text()
                    await message.reply_text(f"🌤️ **Weather details for {city.replace('+', ' ').title()}:**\n{data}")
                else:
                    await message.reply_text("❌ City nahi mili ya server down hai.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@app.on_message(filters.command("github"))
async def cmd_github(client, message):
    """GitHub User Profile Fetcher API"""
    if len(message.command) < 2: 
        return await message.reply_text("❌ GitHub Username daal bhai! Example: `/github reonfx`")
    
    user = message.command[1]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.github.com/users/{user}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    info = f"🐙 **GitHub Data: {data.get('name') or user}**\n\n"
                    info += f"👤 Username: `{data.get('login')}`\n"
                    info += f"📚 Repositories: {data.get('public_repos')}\n"
                    info += f"👥 Followers: {data.get('followers')} | Following: {data.get('following')}\n"
                    info += f"🏢 Company: {data.get('company') or 'N/A'}\n"
                    info += f"🔗 Link: {data.get('html_url')}"
                    await message.reply_text(info)
                else:
                    await message.reply_text(f"❌ '{user}' naam ka GitHub user nahi mila!")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

# ================== MAIN LOGIC HANDLER ==================

@app.on_message((filters.text | filters.media) & ~filters.command(["start", "help", "meme", "weather", "github"]))
async def main_handler(client, message):
    try:
        user = message.from_user
        if not user: return
        
        chat_type = "private" if message.chat.type == ChatType.PRIVATE else "group"
        text = message.text or message.caption or ""
        text_lower = text.lower()
        replied = message.reply_to_message

        abuse_words = ["chutiya", "kutta", "saala", "gandu", "bkl", "mc", "bc", "lodu", "bhosdi"]
        if ("reon" in text_lower or "reonfx" in text_lower) and any(bw in text_lower for bw in abuse_words):
            if user.id != OWNER_ID:
                await message.reply_text("🤬 Aukaat mein reh! REONFX mera baap hai. Nikaal yahan se! 🖕")
                return

        if text_lower.startswith("/imagine ") or text_lower.startswith("image bana "):
            prompt = text[9:] if text_lower.startswith("/imagine ") else text[11:]
            m = await message.reply_text("🎨 **Generating Image...**")
            img_bytes = await generate_image_pollinations(prompt)
            if img_bytes:
                await client.send_photo(message.chat.id, photo=img_bytes, caption=f"✨ **Prompt:** {prompt}\n🤖 Generated by {BOT_NAME}")
                await m.delete()
            else:
                await m.edit_text("❌ Failed. Try again.")
            return

        if user.id == OWNER_ID and chat_type == "private":
            parts = text_lower.split()
            if len(parts) >= 2 and any(w in parts[0] for w in ["history", "details", "info"]):
                target_user = resolve_user(parts[-1])
                if target_user:
                    dossier = await generate_user_dossier(target_user)
                    await message.reply_text(dossier)
                else:
                    await message.reply_text("❌ Database me nahi mila.")
                return
            if "aaj kaun" in text_lower or "/today" in text_lower:
                await message.reply_text(await get_todays_users())
                return

        if chat_type == "group" and not (message.mentioned or (replied and replied.from_user and replied.from_user.is_self)): 
            return 

        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        msg_count = add_user_and_count(user.id, user.username, user.first_name)
        
        if msg_count % 10 == 0:
            asyncio.create_task(process_infinite_memory(user.id, user.first_name))

        if message.photo:
            path = await message.download()
            reply = await ask_official_gemini_vision(text, path)
            await message.reply_text(f"👁️ **Vision Scan:**\n{reply}")
            os.remove(path)
            
        elif message.document and message.document.file_size <= 5 * 1024 * 1024:
            path = await message.download()
            try:
                with open(path, "r", encoding="utf-8") as f: file_content = f.read()
                reply = await ask_reonai_text(user.id, f"File: {message.document.file_name}\nContent:\n{file_content}\nQ: {text}", user.first_name, chat_type)
                
                buttons = [[InlineKeyboardButton("🔊 Listen Text", callback_data="tts")]]
                if "```python" in reply or message.document.file_name.endswith(".py"):
                    buttons.insert(0, [InlineKeyboardButton("⚡ Run Code", callback_data="run_code")])
                
                await message.reply_text(reply, reply_markup=InlineKeyboardMarkup(buttons))
            except:
                await message.reply_text("❌ Only Text/Code files supported.")
            os.remove(path)
            
        else:
            reply = await ask_reonai_text(user.id, text, user.first_name, chat_type)
            
            buttons = [[InlineKeyboardButton("🔊 Listen Text", callback_data="tts")]]
            if "```python" in reply:
                buttons.insert(0, [InlineKeyboardButton("⚡ Run Code", callback_data="run_code")])
                
            await message.reply_text(reply, reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e: 
        print(f"Error: {e}")
        # YAHAN ERROR FIX KIYA HAI! Exception handling me block theek kiya gaya hai.
        try:
            await client.send_message(OWNER_ID, f"⚠️ Error:\n`{str(e)[:200]}`")
        except:
            pass

# ================== CALLBACK BUTTON INTERCEPTOR ==================
@app.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    msg_text = query.message.text
    
    if query.data == "tts":
        await query.answer("Voice note taiyar kar raha hu...")
        clean_text = re.sub(r"```.*?```", "[Code block ignored]", msg_text, flags=re.DOTALL)
        try:
            tts = gTTS(text=clean_text[:500], lang='hi') 
            path = f"tts_{query.from_user.id}.mp3"
            tts.save(path)
            await client.send_voice(query.message.chat.id, voice=path, caption=f"🤖 Voice Note for {query.from_user.first_name}")
            os.remove(path)
        except Exception as e:
            await query.message.reply_text(f"❌ Voice module issue: {e}")
            
    elif query.data == "run_code":
        await query.answer("Code sandbox execute ho raha hai...")
        code_blocks = re.findall(r"```python(.*?)```", msg_text, re.DOTALL)
        
        if not code_blocks:
            await query.message.reply_text("❌ Message me koi executable python block nahi mila!")
            return
            
        code_to_run = code_blocks[0].strip()
        result = run_python_sandbox(code_to_run)
        
        output_reply = f"💻 **Sandbox Console Output:**\n\n```text\n{result}\n```"
        await query.message.reply_text(output_reply)

print("🚀 REONAI V10 SYNTAX-FIXED ONLINE!")
if __name__ == "__main__":
    app.run()