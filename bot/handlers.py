import os
import sys
from telethon import events, Button
from datetime import datetime
from .client import client
from .config import TARGET_CHAT_ID
from utils.logger import logger, LOG_FILE
from .scheduler.storage import load_state, save_state

START_TIME = datetime.now()
LISTEN_CHATS = [TARGET_CHAT_ID, 'me']
SELF_USER = 'me'

AVAILABLE_JOBS = [
    "@toadbot Поход в столовую",
    "@toadbot Работа крупье",
    "@toadbot Работа грабитель"
]

COMMAND_HANDLERS = {}

def command(name):
    def wrapper(func):
        COMMAND_HANDLERS[name] = func
        return func
    return wrapper

@client.on(events.NewMessage(chats=LISTEN_CHATS, from_users=SELF_USER))
async def handle_message(event):
    msg = event.raw_text.strip()
    chat = await event.get_chat()
    chat_name = getattr(chat, 'title', 'Saved Messages')

    logger.info(f"[{chat_name}] Your message: {msg}")

    cmd = msg.split()[0].lower()
    if cmd in COMMAND_HANDLERS:
        await COMMAND_HANDLERS[cmd](event)

# === 📌 Commands ===

@command(".help")
async def handle_help(event):
    help_text = """
📚 <b>Available Commands</b>:
<code>.help</code> — show this list of available commands
<code>.ping</code> — check if the bot is alive, replies with "pong 🏓"
<code>.log</code> — show the latest status updates from all active tasks
<code>.exportlog</code> — send the full userbot log file as a document
<code>.clearlog</code> — clear the userbot log file  
<code>.time</code> — show current server time  
<code>.uptime</code> — show how long the bot has been running
<code>.shutdown</code> — fully stop the userbot process
<code>.reload</code> — reload the userbot code without restarting
<code>.nextwork</code> — switch to the next job (in a cycle)
<code>.getwork</code> — display the currently selected job
"""
    logger.info("ℹ️ Received .help — sending list of commands")
    await event.reply(help_text, parse_mode="html")

@command(".ping")
async def handle_ping(event):
    logger.info("🔁 Received .ping — replying pong 🏓")
    await event.reply("pong 🏓")

@command(".log")
async def handle_log(event):
    if not os.path.exists(LOG_FILE):
        await event.reply("❌ Log file not found.")
        return

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    last_entries = {}
    for line in reversed(lines):
        if "] [" not in line: continue
        try:
            task_id = line.split("] [")[2].split("]")[0]
            if task_id not in last_entries:
                last_entries[task_id] = line.strip()
        except IndexError:
            continue

    if not last_entries:
        await event.reply("📭 No task updates found in logs.")
    else:
        log_output = "\n".join(last_entries[task] for task in sorted(last_entries))
        await event.reply(f"📝 Latest task statuses:\n\n<code>{log_output}</code>", parse_mode='html')

@command(".uptime")
async def handle_uptime(event):
    uptime = datetime.now() - START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)

    logger.info("ℹ️ Received .uptime — replying with bot uptime")
    await event.reply(f"⏳ Uptime: {hours}h {minutes}m")
    
@command(".nextwork")
async def handle_nextjob(event):
    state = load_state()
    task_state = state.get("work_cycle", {})
    current_job = task_state.get("current_job", AVAILABLE_JOBS[0])

    try:
        idx = AVAILABLE_JOBS.index(current_job)
    except ValueError:
        idx = 0

    next_job = AVAILABLE_JOBS[(idx + 1) % len(AVAILABLE_JOBS)]
    task_state["current_job"] = next_job
    state["work_cycle"] = task_state
    save_state(state)

    logger.info(f"[work_cycle] 🔄 Job switched to: {next_job}")
    await event.reply(f"✅ Switched to job:\n<code>{next_job}</code>", parse_mode="html")

@command(".getwork")
async def handle_getjob(event):

    state = load_state()
    job = state.get("work_cycle", {}).get("current_job", "@toadbot Поход в столовую")

    logger.info(f"[work_cycle] 📄 Current job is: {job}")
    await event.reply(f"👔 Current job:\n<code>{job}</code>", parse_mode="html")

@command(".exportlog")
async def handle_export_log(event):
    if os.path.exists(LOG_FILE):
        await client.send_file(event.chat_id, LOG_FILE, caption="📦 Full log file:")
        logger.info("📤 Sent log file via .exportlog")
    else:
        await event.reply("❌ Log file not found.")

@command(".clearlog")
async def handle_clearlog(event):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.truncate(0)
        logger.info("🧹 Log file cleared via .clearlog")
        await event.reply("🧹 Log file has been cleared.")
    except Exception as e:
        logger.error(f"❌ Failed to clear log: {e}")
        await event.reply("❌ Failed to clear log file.")

@command(".time")
async def handle_time(event):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🕒 Received .time — replying with {now}")
    await event.reply(f"🕒 Current time:\n<code>{now}</code>", parse_mode="html")

@command(".shutdown")
async def handle_shutdown(event):
    logger.info("🛑 Received .shutdown — force quitting userbot...")
    await event.reply("🔌 Userbot is shutting down now.")
    await client.disconnect()
    os._exit(0)

@command(".reload")
async def handle_reload(event):
    import sys
    import os

    logger.info("🔄 Received .reload — restarting userbot code...")
    await event.reply("♻️ Reloading...")

    os.execv(sys.executable, [sys.executable, "-m", "bot.main"])