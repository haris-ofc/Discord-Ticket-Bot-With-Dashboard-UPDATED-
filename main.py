import asyncio
import contextlib
import logging

import uvicorn

from bot.client import TicketBot
from config import Config
from dashboard.app import create_app


class QuietServer(uvicorn.Server):
    """Uvicorn without its own signal handling, so Ctrl+C stops everything."""

    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def capture_signals(self):
        yield


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not Config.TOKEN or not Config.GUILD_ID:
        raise SystemExit("Set DISCORD_TOKEN and GUILD_ID in your .env first (see .env.example).")

    bot = TicketBot()
    await bot.db.connect()

    server = QuietServer(uvicorn.Config(
        create_app(bot), host=Config.DASHBOARD_HOST, port=Config.DASHBOARD_PORT, log_level="warning"))
    dashboard = asyncio.create_task(server.serve())
    print(f"Dashboard: http://{Config.DASHBOARD_HOST}:{Config.DASHBOARD_PORT}")

    try:
        async with bot:
            await bot.start(Config.TOKEN)
    finally:
        server.should_exit = True
        await dashboard
        await bot.db.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
