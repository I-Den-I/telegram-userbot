import os
import sys
import json
import psutil
from telethon import events, Button
from datetime import datetime
from .client import client
from .config import TARGET_CHAT_ID
from utils.logger import logger, LOG_FILE
from .scheduler.storage import load_state, save_state

START_TIME = datetime.now()
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

@client.on(events.NewMessage(from_users=SELF_USER))
async def handle_message(event):
    msg = (event.raw_text or "").strip()
    if not msg:
        return                   

    # Only process commands starting with "."
    # if not msg.startswith("."):
    #     return

    chat = await event.get_chat()
    chat_name = getattr(chat, "title", "Saved Messages")
    logger.info(f"[{chat_name}] Your message: {msg}")

    parts = msg.split()
    cmd = parts[0].lower()
    args = parts[1:] 

    handler = COMMAND_HANDLERS.get(cmd)
    if handler:
        await handler(event, *args)

# === 📌 Commands ===

@command(".help")
async def handle_help(event):
    help_text = """
📚 <b>Available Commands</b>:
<code>.help</code> — show this list of available commands
<code>.nextwork</code> — switch to the next job (in a cycle)
<code>.cycle_status</code> — show current work cycle status
<code>.cycle_skip</code> — skip current waiting period and start job immediately
<code>.cycle_set</code> — set custom next start time for work cycle
<code>.ping</code> — check if the bot is alive, replies with "pong 🏓"
<code>..status</code> — show status of all active tasks
<code>.logs</code> — show the latest status updates from all active tasks
<code>.exportlogs</code> — send the full userbot log file as a document
<code>.clearlogs</code> — clear the userbot log file  
<code>.state</code> — send the current state.json contents as a formatted JSON block
<code>.time</code> — show current server time  
<code>.uptime</code> — show how long the bot has been running
<code>.stop</code> — fully stop the userbot process
<code>.reload</code> — reload the userbot code without restarting
<code>.cpu</code> — show current CPU usage
<code>.mem</code> — show current memory usage
"""
    logger.info("ℹ️ Received .help — sending list of commands")
    await event.reply(help_text, parse_mode="html")

@command(".ping")
async def handle_ping(event):
    logger.info("🔁 Received .ping — replying pong 🏓")
    await event.reply("pong 🏓")

@command(".logs")
async def handle_log(event):
    """
    Show last meaningful status per task/group from the log.
    Groups:
      - WORK_CYCLE_*  -> WORK_CYCLE
      - feed_frog     -> feed_frog
      - work_cycle_*  -> work_cycle (control commands/status)
    Filters out chat titles and "Your message:" echoes.
    """
    import os, re, html, asyncio

    LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    MAX_SCAN_LINES = 8000  # scan only tail to be fast

    def _read_tail(path: str, max_lines: int):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return lines[-max_lines:] if len(lines) > max_lines else lines

    # figure out LOG_FILE from your imports
    if not os.path.exists(LOG_FILE):
        await event.reply("❌ Log file not found.")
        return

    lines = await asyncio.to_thread(_read_tail, LOG_FILE, MAX_SCAN_LINES)

    def _extract_group(line: str) -> str | None:
        """
        Decide which logical 'group' this log line belongs to.
        - Prefer ALLCAPS_WITH_UNDERSCORES tokens (e.g., WORK_CYCLE_START) -> map to WORK_CYCLE
        - Accept known lowercase task heads (feed_frog, work_cycle_*)
        - Ignore timestamps, levels, chat titles, and user echo lines.
        """
        # Drop obvious noise
        if "Your message:" in line:
            return None

        tokens = re.findall(r"\[(.*?)\]", line)
        if not tokens:
            return None

        # Remove timestamp & level-like tokens
        cand = []
        for t in tokens:
            t_clean = t.strip()
            if not t_clean:
                continue
            if t_clean.upper() in LOG_LEVELS:
                continue
            # ignore chat titles (contain spaces or emoji-like chars)
            if " " in t_clean:
                continue
            cand.append(t_clean)

        if not cand:
            return None

        # Priority 1: WORK_CYCLE_* -> WORK_CYCLE
        for t in reversed(cand):
            if re.fullmatch(r"WORK_CYCLE[A-Z0-9_]*", t):
                return "WORK_CYCLE"

        # Priority 2: lowercase control tags from your handlers
        for t in reversed(cand):
            if t.startswith("work_cycle_"):
                return "work_cycle"
            if t == "feed_frog":
                return "feed_frog"

        # Otherwise, if any ALLCAPS token exists, use the first two segments as a family
        for t in reversed(cand):
            if re.fullmatch(r"[A-Z0-9_]{3,}", t):
                parts = t.split("_")
                return "_".join(parts[:2]) if len(parts) >= 2 else t

        # Fallback: nothing meaningful
        return None

    latest: dict[str, str] = {}
    for line in reversed(lines):
        grp = _extract_group(line)
        if not grp:
            continue
        if grp not in latest:
            latest[grp] = line.rstrip("\n")

    if not latest:
        await event.reply("📭 No task updates found in logs.")
        return

    # Order: put WORK_CYCLE first, then feed_frog, then others alpha
    ordered_keys = []
    if "WORK_CYCLE" in latest: ordered_keys.append("WORK_CYCLE")
    if "feed_frog" in latest: ordered_keys.append("feed_frog")
    # include lowercase work_cycle (controls) next
    if "work_cycle" in latest: ordered_keys.append("work_cycle")
    for k in sorted(latest.keys()):
        if k not in ordered_keys:
            ordered_keys.append(k)

    payload = html.escape("\n".join(latest[k] for k in ordered_keys))
    await event.reply(f"📝 Latest task statuses:\n\n<code>{payload}</code>", parse_mode="html")

@command(".exportlogs")
async def handle_export_log(event):
    if os.path.exists(LOG_FILE):
        await client.send_file(event.chat_id, LOG_FILE, caption="📦 Full log file:")
        logger.info("📤 Sent log file via .exportlog")
    else:
        await event.reply("❌ Log file not found.")

@command(".clearlogs")
async def handle_clearlog(event):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.truncate(0)
        logger.info("🧹 Log file cleared via .clearlog")
        await event.reply("🧹 Log file has been cleared.")
    except Exception as e:
        logger.error(f"❌ Failed to clear log: {e}")
        await event.reply("❌ Failed to clear log file.")

@command(".state")
async def handle_export_state(event, *args):
    """
    Send the current contents of state.json as a formatted JSON text block.
    """
    # Path to state.json in the project root
    path = os.path.join(os.getcwd(), "state.json")
    
    if os.path.exists(path):
        # Load the state dictionary
        state = load_state()
        # Pretty-print with 2-space indent
        pretty = json.dumps(state, indent=2, ensure_ascii=False)
        # Reply with the JSON in a code block
        await event.reply(
            "📊 Current state (state.json):\n```json\n" + pretty + "\n```"
        )
        logger.info("[work_cycle_state] 📤 Sent state.json content via .exportstate")
    else:
        await event.reply("❌ state.json not found.")
        logger.warning("[work_cycle_warning] state.json file is missing")

@command(".uptime")
async def handle_uptime(event):
    uptime = datetime.now() - START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)

    logger.info("ℹ️ Received .uptime — replying with bot uptime")
    await event.reply(f"⏳ Uptime: {hours}h {minutes}m")
    
@command(".nextwork")
async def handle_nextwork(event):
    state = load_state()
    task_state = state.get("work_cycle", {})
    current_work = task_state.get("current_job", AVAILABLE_JOBS[0])

    try:
        idx = AVAILABLE_JOBS.index(current_work)
    except ValueError:
        idx = 0

    next_work = AVAILABLE_JOBS[(idx + 1) % len(AVAILABLE_JOBS)]
    task_state["current_job"] = next_work
    state["work_cycle"] = task_state
    save_state(state)

    logger.info(f"[work_cycle_switch] 🔄 Work switched to: {next_work}")
    await event.reply(f"✅ Switched to job:\n<code>{next_work}</code>", parse_mode="html")

@command(".time")
async def handle_time(event):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🕒 Received .time — replying with {now}")
    await event.reply(f"🕒 Current time:\n<code>{now}</code>", parse_mode="html")

@command(".stop")
async def handle_stop(event):
    logger.info("🛑 Received .stop — force quitting userbot...")
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

@command(".cpu")
async def handle_cpu(event):
    cpu_pct = psutil.cpu_percent(interval=1)
    logger.info(f"🖥️ Received .cpu — replying with CPU {cpu_pct}%")
    await event.reply(
        f"🖥️ CPU usage:\n<code>{cpu_pct}%</code>",
        parse_mode="html"
    )

@command(".mem")
async def handle_mem(event):
    vm = psutil.virtual_memory()
    used_gb = vm.used / (1024 ** 3)
    total_gb = vm.total / (1024 ** 3)
    pct = vm.percent
    logger.info(f"💾 Received .mem — replying with Memory {pct}% ({used_gb:.2f}/{total_gb:.2f} GB)")
    await event.reply(
        f"💾 Memory usage:\n<code>{used_gb:.2f} GB / {total_gb:.2f} GB ({pct}%)</code>",
        parse_mode="html"
    )

@command(".cycle_status")
async def handle_cycle_status(event):
    """
    Show current work_cycle status with human-readable remaining time.
    """
    import html
    from datetime import datetime

    state = load_state()
    wc = state.get("work_cycle", {})

    def _get(k, default=None):
        return wc.get(k, default)

    def _fmt_dt(s):
        return s if isinstance(s, str) else s  # load_state already stores strings
    def _parse_dt(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None
        except Exception:
            return None

    now = datetime.now()

    current_job      = _get("current_job", "@toadbot Поход в столовую")
    next_start_at_s  = _get("next_start_at")
    scheduled_end_at_s = _get("scheduled_end_at")
    scheduled_end_id = _get("scheduled_end_id")
    last_end_at_s    = _get("last_end_at")

    next_start_at    = _parse_dt(next_start_at_s)
    scheduled_end_at = _parse_dt(scheduled_end_at_s)
    last_end_at      = _parse_dt(last_end_at_s)

    # Figure out the next upcoming event and time remaining
    upcoming_label = "—"
    eta_str = "—"
    if scheduled_end_at:
        upcoming_label = "End work (scheduled)"
        delta = (scheduled_end_at - now).total_seconds()
        if delta >= 0:
            m, s = divmod(int(delta), 60)
            h, m = divmod(m, 60)
            eta_str = f"{h}h {m}m"
        else:
            eta_str = "any minute (waiting to be delivered)"
    elif next_start_at:
        upcoming_label = "Start work"
        delta = (next_start_at - now).total_seconds()
        if delta >= 0:
            m, s = divmod(int(delta), 60)
            h, m = divmod(m, 60)
            eta_str = f"{h}h {m}m"
        else:
            eta_str = "due now"

    # Build nice HTML reply
    lines = [
        "🧭 <b>Work Cycle Status</b>",
        f"👔 <b>Current job:</b> <code>{html.escape(current_job)}</code>",
        f"🕑 <b>Next start at:</b> <code>{html.escape(next_start_at_s or '—')}</code>",
        f"⏳ <b>Scheduled end at:</b> <code>{html.escape(scheduled_end_at_s or '—')}</code>",
        f"🧾 <b>Scheduled end msg_id:</b> <code>{html.escape(str(scheduled_end_id) if scheduled_end_id else '—')}</code>",
        f"✅ <b>Last end at:</b> <code>{html.escape(last_end_at_s or '—')}</code>",
        "",
        f"📌 <b>Upcoming:</b> <code>{html.escape(upcoming_label)}</code>",
        f"⏱️ <b>Time remaining:</b> <code>{html.escape(eta_str)}</code>",
    ]

    await event.reply("\n".join(lines), parse_mode="html")
    logger.info("[work_cycle_status] 📤 Sent .cycle_status")

@command(".cycle_skip")
async def handle_cycle_skip(event):
    """
    Skip current waiting period and start job immediately.
    """
    from datetime import datetime
    state = load_state()
    wc = state.get("work_cycle", {})

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    wc["next_start_at"] = now_str
    wc["scheduled_end_at"] = None
    wc["scheduled_end_id"] = None
    state["work_cycle"] = wc
    save_state(state)

    logger.info("[work_cycle_skip] ⏩ Current cycle skipped — starting now")
    await event.reply("⏩ Skipped current cycle.\n▶️ Next job will start immediately.")

@command(".cycle_set")
async def handle_cycle_set(event, *args):
    """
    Set custom next_start_at for work_cycle.
    Usage:
      .cycle_set 2025-08-09 20:15:00   -> absolute time
      .cycle_set +30                   -> relative in minutes
    """
    from datetime import datetime, timedelta

    if not args:
        await event.reply("❌ Usage:\n<code>.cycle_set YYYY-MM-DD HH:MM:SS</code>\n<code>.cycle_set +30</code> (minutes)", parse_mode="html")
        return

    arg = " ".join(args).strip()
    now = datetime.now()

    # Relative format
    if arg.startswith("+"):
        try:
            minutes = int(arg[1:])
            new_time = now + timedelta(minutes=minutes)
        except ValueError:
            await event.reply("❌ Invalid minutes format.")
            return
    else:
        try:
            new_time = datetime.strptime(arg, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            await event.reply("❌ Invalid time format. Use: YYYY-MM-DD HH:MM:SS")
            return

    state = load_state()
    wc = state.get("work_cycle", {})
    wc["next_start_at"] = new_time.strftime("%Y-%m-%d %H:%M:%S")
    wc["scheduled_end_at"] = None
    wc["scheduled_end_id"] = None
    state["work_cycle"] = wc
    save_state(state)

    logger.info(f"[work_cycle_set] ⏳ Next start manually set to {new_time}")
    await event.reply(f"⏳ Next job start manually set to:\n<code>{new_time}</code>", parse_mode="html")

@command(".status")
async def handle_status(event):
    """
    Show the status of all active tasks from state.json
    """
    state = load_state()
    if not state:
        await event.reply("📭 No state data found.")
        return

    lines = ["📊 <b>Task Status Overview</b>"]

    for task_id, task_state in state.items():
        if not isinstance(task_state, dict):
            continue

        last_sent = task_state.get("last_sent") or task_state.get("last_end_at") or "—"
        next_start = task_state.get("next_start_at") or "—"
        scheduled_end = task_state.get("scheduled_end_at") or "—"
        scheduled_id = task_state.get("scheduled_end_id") or "—"

        lines.append(
            f"\n<b>{task_id}</b>"
            f"\n  • Last sent: <code>{last_sent}</code>"
            f"\n  • Next start: <code>{next_start}</code>"
            f"\n  • Scheduled end: <code>{scheduled_end}</code>"
            f"\n  • End msg ID: <code>{scheduled_id}</code>"
        )

    msg = "\n".join(lines)
    await event.reply(msg, parse_mode="html")
    logger.info("[work_cycle_status] 📤 Sent .status")
