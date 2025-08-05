import asyncio
import random
from datetime import datetime, timedelta
from bot.client import client
from utils.logger import logger
from .storage import load_state, save_state

TASK_ID = "work_cycle"
CHAT_ID = -1001433535272
DEFAULT_JOB = "@toadbot Поход в столовую"

PHASES = [
    {
        "name": "go_canteen",
        "message": None,  # dynamic from .setjob
        "wait_minutes": 481  # 8h 1min
    },
    {
        "name": "end_work",
        "message": "@toadbot Завершить работу",
        "wait_minutes": 121  # 2h 1min
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

async def run_chain_task():
    while True:
        state = get_state()
        phase_index = state["phase"]
        phase = PHASES[phase_index]
        now = datetime.now()

        should_send = False
        last_time = None

        if state["last_sent"] is not None:
            try:
                last_time = datetime.strptime(state["last_sent"], "%Y-%m-%d %H:%M:%S")
                delta = now - last_time
                should_send = delta >= timedelta(minutes=phase["wait_minutes"])
            except Exception as e:
                logger.warning(f"[{TASK_ID}] ⚠️ Error parsing last_sent: {e}")
                should_send = True
        else:
            should_send = True

        # Get message for the current phase
        if phase["name"] == "go_canteen":
            message = state.get("current_job", DEFAULT_JOB)
        else:
            message = phase["message"]

        if should_send:
            logger.info(f"[{TASK_ID}] ⏰ Sending: {message}")
            await client.send_message(
                CHAT_ID,
                message,
                schedule=timedelta(seconds=random.randint(30, 90))
            )

            next_phase = (phase_index + 1) % len(PHASES)
            update_state(next_phase, now)
            logger.info(f"[{TASK_ID}] ✅ Phase switched to: {PHASES[next_phase]['name']}")
        else:
            mins_left = phase["wait_minutes"] - ((now - last_time).seconds // 60)
            logger.info(f"[{TASK_ID}] ⌛ {mins_left} min left to send: {phase['name']} ({message})")

        await asyncio.sleep(random.randint(300, 600))  # 5–10 min
