import os
import re
import time
import zipfile
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ CONFIG ============
API_ID = 123456
API_HASH = "YOUR_API_HASH"
BOT_TOKEN = "YOUR_BOT_TOKEN"
OWNER_ID = 8207582785

DOWNLOAD_DIR = "downloads"
ZIP_DIR = "zips"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(ZIP_DIR, exist_ok=True)

app = Client("final_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=10)

# ============ DATA ============
admins = set()
users_batch = {}
batch_active = {}
prefix_data = {}
waiting_prefix = {}
start_image = None

processing = set()
queue = asyncio.Queue()

# ============ HELPERS ============
def extract_episode(text):
    patterns = [
        r"S(\d+)[\s._-]?E(\d+)",
        r"Season\s*(\d+)\s*Episode\s*(\d+)",
        r"E(\d+)"
    ]
    for p in patterns:
        m = re.search(p, text or "", re.IGNORECASE)
        if m:
            if len(m.groups()) == 2:
                return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}"
            else:
                return f"E{int(m.group(1)):02d}"
    return None

def glow_bar(done, total, speed, file_index):
    percent = int((done / total) * 100) if total else 0
    blocks = percent // 10
    bar = "█"*blocks + "░"*(10-blocks)
    return f"""**📦 Processing Files...

[{bar}] {percent}%

⚡ Speed: {speed:.2f} MB/s
📁 File: {done} / {total}
━━━━━━━━━━━━━━━━━━━━━━**"""

def progress_bar(percent):
    blocks = int(percent/10)
    return "█"*blocks + "░"*(10-blocks)

# ============ START ============
@app.on_message(filters.command("start"))
async def start(client, message):
    text = f"""**╔═══『 🤖 ZIP BOT 』═══╗**

**👋 Hello, {message.from_user.first_name}**

__I Can Convert Files Into Zip Easily.__

***⚡ Fast • Smart • Reliable ⚡***

> **Maintain By:** @AniWorld_Bot_Hub

**╚═══════════════════════╝**"""

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👑 Owner", url="https://t.me/AniWorld_Bot_Hub"),
            InlineKeyboardButton("📜 Commands", callback_data="cmd")
        ],
        [
            InlineKeyboardButton("📢 Update", url="https://t.me/AniWorld_Bot_Hub")
        ]
    ])

    if start_image:
        await message.reply_photo(start_image, caption=text, reply_markup=buttons)
    else:
        await message.reply_text(text, reply_markup=buttons)

@app.on_callback_query(filters.regex("cmd"))
async def cmd(client, query):
    text = """**📜 Commands**

/start 😵‍💫
/batch 😗
/prefix 🏷️
/lzip 📦
/panel 📊"""
    await query.message.edit_text(text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="back")]
        ])
    )

@app.on_callback_query(filters.regex("back"))
async def back(client, query):
    await start(client, query.message)

# ============ ADMIN ============
@app.on_message(filters.command("add_admin"))
async def add_admin(client, message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("**❌ ERROR: You're Not Authorized 😤**")
    try:
        uid = int(message.text.split()[1])
        admins.add(uid)
        await message.reply_text(f"**✅ Admin Added: {uid}**")
    except:
        await message.reply_text("**❌ ERROR: Usage: /add_admin user_id**")

@app.on_message(filters.command("panel"))
async def panel(client, message):
    if message.from_user.id != OWNER_ID:
        return
    await message.reply_text(f"**📊 Admins: {len(admins)}**")

# ============ ADD IMAGE ============
@app.on_message(filters.command("add_image"))
async def add_image(client, message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("**❌ ERROR: You're Not Authorized 😤**")

    await message.reply_text("**📸 Send Image Now**")

@app.on_message(filters.photo)
async def save_image(client, message):
    global start_image

    if message.from_user.id != OWNER_ID:
        return

    start_image = message.photo.file_id
    await message.reply_text("**✅ Image Saved Successfully**")

  
# ============ PREFIX ============
@app.on_message(filters.command("prefix"))
async def prefix(client, message):
    uid = message.from_user.id
    if uid != OWNER_ID and uid not in admins:
        return await message.reply_text("**❌ ERROR: You Are Not Authorized 😤**")

    waiting_prefix[uid] = True
    await message.reply_text("**🏷️ Give Me Your Prefix**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_prefix")]
        ])
    )

@app.on_message(filters.text & ~filters.command(["prefix","batch","lzip"]))
async def handle_prefix(client, message):
    uid = message.from_user.id
    if waiting_prefix.get(uid):
        prefix_data[uid] = message.text
        waiting_prefix.pop(uid)
        await message.reply_text("**✅ Prefix Saved**")

@app.on_callback_query(filters.regex("cancel_prefix"))
async def cancel_prefix(client, query):
    waiting_prefix.pop(query.from_user.id, None)
    await query.message.edit_text("**❌ Prefix Cancelled**")

# ============ BATCH ============
@app.on_message(filters.command("batch"))
async def batch_start(client, message):
    uid = message.from_user.id
    if uid != OWNER_ID and uid not in admins:
        return await message.reply_text("**❌ ERROR: You Are Not Authorized 😤**")

    users_batch[uid] = []
    batch_active[uid] = True

    await message.reply_text("**📂 Send Your Files One By One 😗**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_batch")]
        ])
    )

@app.on_message(filters.video | filters.document | filters.audio)
async def collect(client, message):
    uid = message.from_user.id
    if not batch_active.get(uid):
        return

    users_batch[uid].append(message)
    total = len(users_batch[uid])
    size = sum((m.video.file_size if m.video else m.document.file_size) for m in users_batch[uid] if (m.video or m.document))
    size_mb = round(size / 1024 / 1024, 2)

    await message.reply_text(
        f"""**🎬 File Added ✅**

📦 Total Files: {total}
💾 Total Size: {size_mb} MB

Send /lzip when done 😗""",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_batch")]
        ])
    )

@app.on_callback_query(filters.regex("cancel_batch"))
async def cancel_batch(client, query):
    uid = query.from_user.id
    users_batch.pop(uid, None)
    batch_active.pop(uid, None)
    await query.message.edit_text("**❌ Batch Cancelled**")

# ============ LZIP ============
@app.on_message(filters.command("lzip"))
async def lzip(client, message):
    uid = message.from_user.id

    if uid != OWNER_ID and uid not in admins:
        return await message.reply_text("**❌ ERROR: You Are Not Authorized 😤**")

    if uid in processing:
        return await message.reply_text("⏳ Already Processing")

    files = users_batch.get(uid)
    if not files:
        return await message.reply_text("**❌ ERROR: No Files Found**")

    processing.add(uid)
    await queue.put((uid, message))
    await message.reply_text("**✅ Added to Queue**")

# ============ WORKER ============
async def worker():
    while True:
        uid, message = await queue.get()
        try:
            await process_zip(uid, message)
        except Exception as e:
            await message.reply_text("**❌ ERROR OCCURRED\n⚠️ Please Try Again**")
            print(e)
        queue.task_done()

async def process_zip(uid, message):
    files = users_batch.get(uid)
    match = re.findall(r"\[(.*?)\]", message.text or "")
    name = match[0] if len(match)>0 else "Series"
    quality = match[-1] if len(match)>1 else ""
    prefix = prefix_data.get(uid, "")

    try:
        msg = await message.reply_text("**🚀 Initializing Process...**")
        await asyncio.sleep(1)

        await msg.edit_text("**📥 Downloading Files...**")

        start_time = time.time()

        # ✅ FIXED DOWNLOAD WITH PROGRESS
        paths = []
        for i, m in enumerate(files):
            path = await m.download(file_name=f"{DOWNLOAD_DIR}/{uid}_{i}")
            paths.append(path)

            speed = (i+1)/(time.time()-start_time+1)

            await msg.edit_text(
                glow_bar(i+1, len(files), speed, i+1),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
                ])
            )

        await msg.edit_text("**⚙️ Compressing Data...**")

        zip_path = f"{ZIP_DIR}/{uid}.zip"
        z = zipfile.ZipFile(zip_path, "w")

        for i, path in enumerate(paths):
            m = files[i]
            ep = extract_episode(m.caption or "") or f"E{i+1:02d}"
            new_name = f"{prefix} {name} {ep} {quality}.mkv"
            new_path = f"{DOWNLOAD_DIR}/{new_name}"

            os.rename(path, new_path)
            z.write(new_path, new_name)
            os.remove(new_path)

        z.close()

        # ✅ UPLOAD WITH PROGRESS
        async def upload_progress(current, total):
            percent = current * 100 / total

            await msg.edit_text(f"""**📤 Uploading Final Zip...

[{progress_bar(percent)}] {int(percent)}%

💾 {round(current/1024/1024,2)} MB / {round(total/1024/1024,2)} MB
━━━━━━━━━━━━━━━━━━━━━━**""")

        await message.reply_document(zip_path, progress=upload_progress)

        await message.reply_text(f"""**✅ TASK COMPLETED

📦 Files Processed: {len(files)}
⚡ Status: SUCCESS

━━━━━━━━━━━━━━━━━━━━━━
🚀 Delivered Successfully
━━━━━━━━━━━━━━━━━━━━━━**""")

    except Exception as e:
        await message.reply_text("**❌ ERROR OCCURRED\n⚠️ Please Try Again**")
        print(e)

    finally:
        for f in os.listdir(DOWNLOAD_DIR):
            os.remove(os.path.join(DOWNLOAD_DIR, f))
        os.remove(zip_path)
        users_batch[uid] = []
        batch_active.pop(uid, None)
        processing.discard(uid)

@app.on_callback_query(filters.regex("refresh"))
async def refresh(client, query):
    await query.answer("✅ Refreshed")

asyncio.get_event_loop().create_task(worker())

print("Bot Running...")
app.run()
