import json
import os
from datetime import datetime

STATE_FILE = "state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_last_sent(task_id, state):
    if task_id in state and "last_sent" in state[task_id]:
        return datetime.strptime(state[task_id]["last_sent"], "%Y-%m-%d %H:%M:%S")
    return None

def update_last_sent(task_id, state):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if task_id not in state:
        state[task_id] = {}
    state[task_id]["last_sent"] = now_str
    save_state(state)