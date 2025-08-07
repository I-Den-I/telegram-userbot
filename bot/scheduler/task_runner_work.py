import asyncio
import random
from datetime import datetime, timedelta
from bot.client import client
from utils.logger import logger
from .storage import load_state, save_state
from ..config import TARGET_CHAT_ID

TASK_ID = "work_cycle"
CHAT_ID = TARGET_CHAT_ID
DEFAULT_JOB = "@toadbot Поход в столовую"

PHASES = [
    {
        "name": "go_canteen",
        "get_message": lambda state: state.get("current_job", DEFAULT_JOB),
        "min_delay": 361,
        "max_delay": 365
    },
    {
        "name": "end_work",
        "get_message": lambda state: "@toadbot Завершить работу",
        "min_delay": 121,
        "max_delay": 125
    }
]

def get_state():
    full_state = load_state()
    task_state = full_state.get(TASK_ID, {})
    return {
        "phase": task_state.get("phase", 0),
        "last_sent": task_state.get("last_sent", None),
        "current_job": task_state.get("current_job", DEFAULT_JOB)
    }

def update_state(phase, last_sent, current_job=None):
    state = load_state()
    task_state = state.get(TASK_ID, {})
    task_state["phase"] = phase
    task_state["last_sent"] = last_sent.strftime("%Y-%m-%d %H:%M:%S")
    if current_job is not None:
        task_state["current_job"] = current_job
    state[TASK_ID] = task_state
    save_state(state)

def init_chain_state():
    state = load_state()
    task_state = state.get(TASK_ID, {})

    changed = False
    if "phase" not in task_state:
        task_state["phase"] = 0
        changed = True
        
    if "last_sent" not in task_state:
        task_state["last_sent"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        changed = True

    if changed:
        state[TASK_ID] = task_state
        save_state(state)
        logger.info(f"[{TASK_ID}_init] 🛠 State initialized: phase={task_state['phase']}, last_sent={task_state['last_sent']}")

def get_adaptive_sleep(mins_left: float, min_sleep: int = 2, max_sleep: int = 60) -> int:
    """
    Compute a sleep interval that shrinks as time remaining decreases.
    - If mins_left > max_sleep: sleep max_sleep minutes.
    - Else start at mins_left, then halve until pause*2 <= mins_left or pause <= min_sleep.
    - Never sleep less than min_sleep minutes.
    Returns seconds.
    """
    # Choose starting pause in minutes
    if mins_left > max_sleep:
        pause = max_sleep
    else:
        pause = mins_left
        # Halve until pause*2 <= mins_left or pause <= min_sleep
        while pause > min_sleep and pause * 2 > mins_left:
            pause /= 2
    # Ensure pause is at least the minimum
    pause = max(pause, min_sleep)
    # Log the chosen adaptive sleep
    try:
        seconds = int(pause * 60)
        logger.debug(f"[{TASK_ID}_debug] 💤 Adaptive sleep chosen: {pause:.2f} minutes ({seconds}s)")
    except Exception as e:
        logger.warning(f"[{TASK_ID}_warning] ⚠️ Error logging adaptive sleep: {e}")
        seconds = int(pause * 60)
    return seconds

async def run_chain_task():
    init_chain_state()

    while True:
        state = get_state()
        phase_index = state.get("phase", 0)
        phase = PHASES[phase_index]
        now = datetime.now()

        # Parse last_sent timestamp
        last_time = None
        ts = state.get("last_sent")
        if ts:
            try:
                last_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logger.warning(f"[{TASK_ID}_warning] ⚠️ Error parsing last_sent: {e}")

        # Determine if we should send now
        delay_needed = random.randint(phase["min_delay"], phase["max_delay"])
        should_send = last_time is None or (now - last_time >= timedelta(minutes=delay_needed))
        message = phase["get_message"](state)

        if should_send:
            # Schedule the phase message
            schedule_delay = random.randint(60, 120)
            scheduled_time = now + timedelta(seconds=schedule_delay)
            logger.info(
                f"[{TASK_ID}_schedule] ⏰ Scheduling '{message}' in {schedule_delay}s "
                f"(will send at {scheduled_time:%Y-%m-%d %H:%M:%S})"
            )
            try:
                await client.send_message(
                    CHAT_ID,
                    message,
                    schedule=timedelta(seconds=schedule_delay)
                )
                # Switch to next phase
                next_phase = (phase_index + 1) % len(PHASES)
                update_state(next_phase, scheduled_time)
                logger.info(f"[{TASK_ID}_switch] ✅ Phase switched to: {PHASES[next_phase]['name']}")
            except Exception as e:
                logger.error(f"[{TASK_ID}_error] ❌ Failed to send: {e}")
            # After sending, wait a fixed short interval before next check
            sleep_time = random.randint(1800, 3600)
        else:
            # Calculate minutes left until we reach delay_needed
            elapsed = (now - last_time).total_seconds() if last_time else 0
            mins_left = max((delay_needed*60 - elapsed) / 60, 0)
            logger.info(f"[{TASK_ID}_time] ⌛ {mins_left:.1f} min left to send: {phase['name']} ({message})")
            # Adaptive sleep: shrinks as mins_left decreases
            sleep_time = get_adaptive_sleep(mins_left)

        logger.debug(f"[{TASK_ID}_debug] 💤 Sleeping for {sleep_time}s")
        await asyncio.sleep(sleep_time)