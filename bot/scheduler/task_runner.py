import asyncio
import random
from datetime import datetime, timedelta
from telethon.errors import MessageIdInvalidError

from ..client import client
from .storage import get_last_sent, update_last_sent, load_state, save_state
from utils.logger import logger

# Safe polling windows (to avoid frequent API hits)
LONG_POLL  = 2400  # 40 min when far from event
MID_POLL   = 900   # 15 min when 10m–1h before event
SHORT_POLL = 300   # 5  min when <10m before event
WAIT_POLL  = 900   # 15 min when waiting for Telegram to deliver a scheduled msg

# Deletion window after message appears in chat
DELETE_MIN_SEC = 90
DELETE_MAX_SEC = 200


def _now() -> datetime:
    return datetime.now()

def _fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None

def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def _seconds_until(dt: datetime) -> int:
    return max(0, int((dt - _now()).total_seconds()))

def _choose_sleep(target_dt: datetime | None) -> int:
    """Adaptive backoff based on how far the next event is."""
    if not target_dt:
        return LONG_POLL
    sec = _seconds_until(target_dt)
    if sec > 3600:
        return LONG_POLL
    elif sec > 600:
        return MID_POLL
    else:
        return SHORT_POLL

async def _delete_message_after_delay(chat_id: int, msg_id: int):
    """Delete a delivered message after a human-like random delay."""
    delay = random.randint(DELETE_MIN_SEC, DELETE_MAX_SEC)
    logger.debug(f"[{chat_id}] [AUTO_DELETE] will delete message {msg_id} in {delay}s")
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, msg_id)
        logger.info(f"[{chat_id}] [AUTO_DELETE] message {msg_id} deleted after {delay}s")
    except MessageIdInvalidError:
        # Already gone or never delivered; not fatal
        logger.warning(f"[{chat_id}] [AUTO_DELETE] message {msg_id} not found (already deleted?)")
    except Exception as e:
        logger.warning(f"[{chat_id}] [AUTO_DELETE] failed to delete message {msg_id}: {e}")

async def run_task(task_id, task_conf, state):
    """
    Robust scheduled task:
      - schedules the message via Telegram with a 60–120s random delay
      - persists scheduled_msg_id and scheduled_send_at
      - after actual delivery, updates last_sent using msg.date and schedules deletion (90–200s)
      - uses slow polling to mimic a human client and avoid bans
      - survives restarts thanks to state.json
    task_conf fields:
      - chat_id: int
      - message: str
      - interval_minutes: int
    """
    chat_id = task_conf["chat_id"]
    interval = int(task_conf["interval_minutes"])

    while True:
        # Pull fresh state each loop (handles external edits)
        full_state = load_state()
        task_state = full_state.get(task_id, {})
        last_sent = get_last_sent(task_id, full_state)

        scheduled_msg_id = task_state.get("scheduled_msg_id")
        scheduled_send_at = _dt(task_state.get("scheduled_send_at"))

        now = _now()

        # 1) If there is a scheduled message pending, manage its lifecycle
        if scheduled_msg_id and scheduled_send_at:
            if now >= scheduled_send_at:
                # Past the scheduled time: check if Telegram actually delivered it
                try:
                    msg = await client.get_messages(chat_id, ids=scheduled_msg_id)
                except Exception as e:
                    logger.warning(f"[{task_id}] ⚠️ fetch scheduled msg failed: {e}")
                    msg = None

                if msg and getattr(msg, "date", None):
                    actual = msg.date.replace(tzinfo=None)
                    # Persist last_sent from actual delivery time
                    update_last_sent(task_id, full_state, actual)
                    # Clear scheduled markers
                    task_state["scheduled_msg_id"] = None
                    task_state["scheduled_send_at"] = None
                    full_state[task_id] = task_state
                    save_state(full_state)

                    logger.info(f"[{task_id}] ✅ delivered at {actual} (id={scheduled_msg_id})")
                    # Schedule deletion (non-blocking)
                    asyncio.create_task(_delete_message_after_delay(chat_id, scheduled_msg_id))

                    # Decide next wakeup based on interval
                    sleep_time = _choose_sleep(actual + timedelta(minutes=interval))
                    await asyncio.sleep(sleep_time)
                    continue
                else:
                    # Not in history yet -> Telegram lagging. Wait calmly and retry.
                    logger.info(f"[{task_id}] ⏳ waiting for delivery of scheduled msg id={scheduled_msg_id}…")
                    await asyncio.sleep(WAIT_POLL)
                    continue
            else:
                # Not yet time — sleep adaptively until scheduled time
                sleep_time = _choose_sleep(scheduled_send_at)
                await asyncio.sleep(sleep_time)
                continue

        # 2) No pending scheduled message. Decide whether to schedule a new one.
        if last_sent is None or (now - last_sent >= timedelta(minutes=interval)):
            # Random pre-send delay (makes schedule look natural & resilient to restarts)
            schedule_delay = random.randint(60, 120)
            scheduled_time = now + timedelta(seconds=schedule_delay)

            logger.info(
                f"[{task_id}] ⏰ scheduling message in {schedule_delay}s "
                f"(at {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')})"
            )
            try:
                # Ask Telegram to deliver later; keeps working if our process restarts
                msg = await client.send_message(
                    chat_id,
                    task_conf["message"],
                    schedule=timedelta(seconds=schedule_delay)
                )
                # Persist schedule metadata
                task_state["scheduled_msg_id"] = getattr(msg, "id", None)
                task_state["scheduled_send_at"] = _fmt(scheduled_time)
                full_state[task_id] = task_state
                save_state(full_state)

                logger.debug(f"[{task_id}] 🗓 scheduled (id={task_state['scheduled_msg_id']}) "
                             f"for {task_state['scheduled_send_at']}")
            except Exception as e:
                logger.error(f"[{task_id}] ❌ failed to schedule: {e}")

            # After scheduling, we can sleep until roughly the scheduled time window
            sleep_time = _choose_sleep(scheduled_time)
        else:
            # Not yet time — report ETA and sleep sparsely
            mins_left = interval - int((now - last_sent).total_seconds() // 60)
            logger.info(f"[{task_id}] ⌛ Time left: {max(0, mins_left)} minutes")
            sleep_time = 600 if mins_left < 61 else random.randint(1800, 3600)

        await asyncio.sleep(sleep_time)
