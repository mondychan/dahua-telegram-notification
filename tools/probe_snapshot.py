import asyncio
import os

from dahua_telegram_bridge.config import load_config
from dahua_telegram_bridge.dahua.client import DahuaClient


async def main() -> None:
    config = load_config(os.getenv("DAHUA_CONFIG"))
    client = DahuaClient(config.dahua)
    try:
        for channel in (0, 1):
            try:
                data = await client.snapshot(channel, 3000)
                print(f"snapshot_ok channel={channel} bytes={len(data)} content_type=image/jpeg")
            except Exception as exc:
                print(f"snapshot_error channel={channel} type={type(exc).__name__} detail={exc}")
    except Exception as exc:
        print(f"snapshot_error type={type(exc).__name__} detail={exc}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
