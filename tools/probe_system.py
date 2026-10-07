import asyncio

from dahua_telegram_bridge.config import load_config
from dahua_telegram_bridge.dahua.client import DahuaClient


async def main() -> None:
    config = load_config()
    client = DahuaClient(config.dahua)
    try:
        info = await client.system_info()
        for key, value in info.items():
            print(f"{key}={value}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
