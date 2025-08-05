import asyncio
import json
from .task_runner import run_task
from .storage import load_state
from .task_runner_work import run_chain_task



async def start_all_tasks():
    with open("tasks.json", "r") as f:
        tasks_config = json.load(f)

    state = load_state()

    tasks = []
    for task_id, task_conf in tasks_config.items():
        tasks.append(run_task(task_id, task_conf, state))
    
    tasks.append(run_chain_task())

    await asyncio.gather(*tasks)