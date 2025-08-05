import asyncio
import random
from datetime import datetime, timedelta
from ..client import client
from .storage import get_last_sent, update_last_sent
from utils.logger import logger  

async def run_task(task_id, task_conf, state):
    while True:
        last_sent = get_last_sent(task_id, state)
        interval = task_conf["interval_minutes"]
        now = datetime.now()
        should_send = False

        if last_sent is None or (now - last_sent >= timedelta(minutes=interval)):
            should_send = True

        if should_send:
            logger.info(f"[{task_id}] ⏰ Sending message: {task_conf['message']}")
            try:
                await client.send_message(task_conf["chat_id"], task_conf["message"], schedule=timedelta(seconds=random.randint(60, 120)))
                update_last_sent(task_id, state)
                logger.debug(f"[{task_id}] ✅ Updated last_sent")
            except Exception as e:
                logger.error(f"[{task_id}] ❌ Error while sending message: {e}")
        else:
            mins_left = interval - (now - last_sent).seconds // 60
            logger.info(f"[{task_id}] ⌛ Time left: {mins_left} minutes")

        await asyncio.sleep(random.randint(300, 600))  # 5 - 10 minutes