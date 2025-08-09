import asyncio
import random
from datetime import datetime, timedelta

from bot.client import client
from utils.logger import logger
from .storage import load_state, save_state
from ..config import TARGET_CHAT_ID

# ====== CONFIGURATION ======
TASK_ID = "work_cycle"
CHAT_ID = TARGET_CHAT_ID
DEFAULT_JOB = "@toadbot Поход в столовую"
END_TEXT = "@toadbot Завершить работу"

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Durations
WORK_LEN = timedelta(hours=2)   # work session length
REST_LEN = timedelta(hours=6)   # rest period after work ends

# Polling intervals to avoid account bans
LONG_POLL = 2400  # 40 min (far from event)
MID_POLL  = 900   # 15 min (1h–10m before event)
SHORT_POLL = 300  # 5 min  (<10m before event)
WAIT_END_POLL = 900  # 15 min when waiting for actual "end work" message

# Delete delay (random to look human-like)
DELETE_MIN_SEC = 90
DELETE_MAX_SEC = 200


# ====== TIME HELPERS ======
def _now() -> datetime:
    return datetime.now()

def _dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, TIME_FMT)
    except Exception:
        return None

def _fmt(dt: datetime | None):
    return dt.strftime(TIME_FMT) if dt else None

def _seconds_until(dt: datetime):
    return max(0, int((dt - _now()).total_seconds()))

def _choose_sleep_time(target_dt: datetime):
    """Adaptive polling delay based on how far event is."""
    if not target_dt:
        return LONG_POLL
    sec_left = _seconds_until(target_dt)
    if sec_left > 3600:
        return LONG_POLL
    elif sec_left > 600:
        return MID_POLL
    else:
        return SHORT_POLL


# ====== STATE MANAGEMENT ======
def _migrate_state_if_needed(st: dict) -> dict:
    """Migrate from legacy keys (phase, last_sent) to new schema."""
    wc = st.get(TASK_ID, {})
    if "phase" in wc or "last_sent" in wc:
        logger.info(f"[WORK_CYCLE_MIGRATE] Migrating legacy state to new keys")
        last_sent = _dt(wc.get("last_sent"))
        st[TASK_ID] = {
            "current_job": wc.get("current_job", DEFAULT_JOB),
            "next_start_at": _fmt(_now()) if last_sent is None else _fmt(last_sent),
            "scheduled_end_at": None,
            "scheduled_end_id": None,
            "last_end_at": None,
        }
        save_state(st)
    return st

def _self_check_state(st: dict) -> dict:
    """Ensure state is consistent, fixing if needed."""
    wc = st.get(TASK_ID, {})
    if not wc.get("next_start_at") and not wc.get("scheduled_end_at"):
        wc["next_start_at"] = _fmt(_now())
        logger.warning(f"[WORK_CYCLE_SELF_FIX] No planned events found. Setting next_start_at=now")
    st[TASK_ID] = wc
    save_state(st)
    return st

def _get_state():
    st = _self_check_state(_migrate_state_if_needed(load_state()))
    wc = st.get(TASK_ID, {})
    return {
        "current_job": wc.get("current_job", DEFAULT_JOB),
        "next_start_at": _dt(wc.get("next_start_at")),
        "scheduled_end_at": _dt(wc.get("scheduled_end_at")),
        "scheduled_end_id": wc.get("scheduled_end_id"),
        "last_end_at": _dt(wc.get("last_end_at")),
    }

def _save_state(**kw):
    st = load_state()
    wc = st.get(TASK_ID, {})
    for k, v in kw.items():
        wc[k] = _fmt(v) if isinstance(v, datetime) else v
    st[TASK_ID] = wc
    save_state(st)
    logger.debug(f"[WORK_CYCLE_STATE] {wc}")


# ====== MESSAGE ACTIONS ======
async def _delete_message_after_seen(msg_id: int):
    """Delete a message after 90–200s from when it's in chat."""
    delay = random.randint(DELETE_MIN_SEC, DELETE_MAX_SEC)
    logger.debug(f"[WORK_CYCLE_DELETE] Will delete message {msg_id} in {delay}s")
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(CHAT_ID, msg_id)
        logger.info(f"[WORK_CYCLE_DELETE] Message {msg_id} deleted after {delay}s")
    except Exception as e:
        logger.warning(f"[WORK_CYCLE_DELETE] Failed to delete message {msg_id}: {e}")

async def _send_start_and_schedule_end(current_job: str):
    """Send 'start work' now and schedule 'end work' in WORK_LEN."""
    msg_start = await client.send_message(CHAT_ID, current_job)
    asyncio.create_task(_delete_message_after_seen(msg_start.id))

    scheduled_end_at = _now() + WORK_LEN
    msg_end = await client.send_message(CHAT_ID, END_TEXT, schedule=WORK_LEN)
    _save_state(scheduled_end_at=scheduled_end_at, scheduled_end_id=msg_end.id, next_start_at=None)

    logger.info(f"[WORK_CYCLE_START] Sent start '{current_job}' | "
                f"[WORK_CYCLE_SCHEDULE] End scheduled at {scheduled_end_at.strftime(TIME_FMT)} "
                f"(msg_id={msg_end.id})")


# ====== MAIN LOOP ======
async def run_chain_task():
    logger.info(f"[WORK_CYCLE_LOOP] Started")
    st = _get_state()

    # Initialize if empty
    if st["next_start_at"] is None and st["scheduled_end_at"] is None:
        _save_state(next_start_at=_now(), current_job=st["current_job"])
        logger.info(f"[WORK_CYCLE_INIT] Set next_start_at=now")

    while True:
        st = _get_state()
        now = _now()

        # If end is scheduled
        if st["scheduled_end_at"] and st["scheduled_end_id"]:
            if now >= st["scheduled_end_at"]:
                # Delete the "end work" message once it's actually sent
                asyncio.create_task(_delete_message_after_seen(st["scheduled_end_id"]))
                next_start = now + REST_LEN
                _save_state(last_end_at=now, scheduled_end_at=None,
                            scheduled_end_id=None, next_start_at=next_start)
                logger.info(f"[WORK_CYCLE_END] Ended at {now.strftime(TIME_FMT)} | "
                            f"[WORK_CYCLE_NEXT] Next start at {next_start.strftime(TIME_FMT)}")
                await asyncio.sleep(SHORT_POLL)
            else:
                await asyncio.sleep(_choose_sleep_time(st["scheduled_end_at"]))
            continue

        # If waiting for next start
        if st["next_start_at"]:
            if now >= st["next_start_at"]:
                await _send_start_and_schedule_end(st["current_job"])
                await asyncio.sleep(SHORT_POLL)
            else:
                await asyncio.sleep(_choose_sleep_time(st["next_start_at"]))
            continue

        # Safety fallback
        logger.debug("[WORK_CYCLE_IDLE] No events planned. Sleeping long.")
        await asyncio.sleep(LONG_POLL)
