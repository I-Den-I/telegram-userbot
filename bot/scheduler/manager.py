import asyncio
import json
import logging
from pathlib import Path

from .task_runner import run_task
from .task_runner_work import run_chain_task
from .storage import load_state

logger = logging.getLogger("userbot")

BASE_DIR = Path(__file__).parent.parent.parent

async def start_all_tasks():
    logger.info("🛠 Starting all scheduled tasks…")

    tasks_config_path = BASE_DIR / "tasks.json"
    try:
        with tasks_config_path.open("r", encoding="utf-8") as f:
            tasks_config = json.load(f)
    except FileNotFoundError:
        logger.error(f"❌ Cannot find tasks.json at {tasks_config_path}")
        return

    state = load_state()

    tasks = [
        run_task(task_id, task_conf, state)
        for task_id, task_conf in tasks_config.items()
    ]

    # work_cycle
    tasks.append(run_chain_task())

    await asyncio.gather(*tasks)