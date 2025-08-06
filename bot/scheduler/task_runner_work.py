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
        logger.info(f"[{TASK_ID}] 🛠 State initialized: phase={task_state['phase']}, last_sent={task_state['last_sent']}")

async def run_chain_task():
    init_chain_state()

    while True:
        state = get_state()
        phase_index = state["phase"]
        phase = PHASES[phase_index]
        now = datetime.now()

        last_time = None
        if state["last_sent"]:
            try:
                last_time = datetime.strptime(state["last_sent"], "%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logger.warning(f"[{TASK_ID}] ⚠️ Error parsing last_sent: {e}")

        # random delay for the current phase
        delay = random.randint(phase["min_delay"], phase["max_delay"])
        should_send = last_time is None or (now - last_time >= timedelta(minutes=delay))
        message = phase["get_message"](state)

        if should_send:
            schedule_delay = random.randint(60, 120)
            scheduled_time = now + timedelta(seconds=schedule_delay)

            logger.info(
                f"[{TASK_ID}] ⏰ Scheduling '{message}' in {schedule_delay}s "
                f"(will send at {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')})"
            )
            try:
                await client.send_message(
                    CHAT_ID,
                    message,
                    schedule=timedelta(seconds=schedule_delay)
                )
                next_phase = (phase_index + 1) % len(PHASES)
                update_state(next_phase, scheduled_time)
                logger.info(f"[{TASK_ID}] ✅ Phase switched to: {PHASES[next_phase]['name']}")
            except Exception as e:
                logger.error(f"[{TASK_ID}] ❌ Failed to send: {e}")

            # after sending, wait for a 30-60 minutes before next check
            sleep_time = random.randint(1800, 3600)
        else:
            mins_left = delay - int((now - last_time).total_seconds() // 60) if last_time else delay
            logger.info(f"[{TASK_ID}] ⌛ {mins_left} min left to send: {phase['name']} ({message})")

            # if less than 61 minutes left, check more frequently
            if mins_left < 61:
                sleep_time = 600   # 10 minutes
            else:
                sleep_time = random.randint(1800, 3600)  # 30–60 minutes

        logger.debug(f"[{TASK_ID}] 💤 Sleeping for {sleep_time}s")
        await asyncio.sleep(sleep_time)