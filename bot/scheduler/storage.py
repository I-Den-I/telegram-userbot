import json
import os
from datetime import datetime

STATE_FILE = "state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_last_sent(task_id, state):
    ts = state.get(task_id, {}).get("last_sent")
    if ts:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    return None

def update_last_sent(task_id, state, when: datetime=None):
    if task_id not in state:
        state[task_id] = {}

    if when is None:
        when = datetime.now()

    state[task_id]["last_sent"] = when.strftime("%Y-%m-%d %H:%M:%S")
    save_state(state)