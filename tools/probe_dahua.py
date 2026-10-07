import asyncio
import logging
import os

from dahua_telegram_bridge.config import load_config
from dahua_telegram_bridge.dahua.client import DahuaClient
from dahua_telegram_bridge.dahua.parser import parse_event


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config(os.getenv("DAHUA_CONFIG"))
    client = DahuaClient(config.dahua)
    try:
        print("Listening for Dahua events; press Ctrl-C to stop")
        async for raw in client.events():
            print("RAW:", raw.decode("utf-8", "replace"))
            print("PARSED:", parse_event(raw))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
