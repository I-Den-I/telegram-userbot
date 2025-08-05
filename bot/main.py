import asyncio
from .scheduler import manager
from .client import client
from . import handlers
from utils.logger import logger  

async def main():
    await client.start()
    logger.info("✅ Userbot is running...")

    await asyncio.gather(
        client.run_until_disconnected(),
        manager.start_all_tasks()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("❌ Userbot stopped manually by keyboard interrupt.")
