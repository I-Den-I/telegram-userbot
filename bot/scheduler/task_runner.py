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

        if last_sent is None or (now - last_sent >= timedelta(minutes=interval)):
            # random delay before sending
            schedule_delay = random.randint(60, 120)
            scheduled_time = now + timedelta(seconds=schedule_delay)

            logger.info(
                f"[{task_id}] ⏰ Scheduling send in {schedule_delay}s "
                f"(will send at {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')})"
            )
            try:
                await client.send_message(
                    task_conf["chat_id"],
                    task_conf["message"],
                    schedule=timedelta(seconds=schedule_delay)
                )
                update_last_sent(task_id, state, scheduled_time)
                logger.debug(f"[{task_id}] ✅ Updated last_sent to {scheduled_time}")
            except Exception as e:
                logger.error(f"[{task_id}] ❌ Error while sending message: {e}")

            # after sending, wait for a 30-60 minutes before next check
            sleep_time = random.randint(1800, 3600)
        else:
            mins_left = interval - (now - last_sent).seconds // 60
            logger.info(f"[{task_id}] ⌛ Time left: {mins_left} minutes")

            # if less than 61 minutes left, check more frequently
            if mins_left < 61:
                sleep_time = 600  # 10 minutes
            else:
                sleep_time = random.randint(1800, 3600) # 30–60 minutes

        await asyncio.sleep(sleep_time)