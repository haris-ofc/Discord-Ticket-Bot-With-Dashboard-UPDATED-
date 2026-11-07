import os
from dotenv import load_dotenv


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


class Config:
    """Everything comes from .env. Call Config.load() to re-read it."""

    @classmethod
    def load(cls):
        load_dotenv(override=True)
        g = os.getenv
        cls.TOKEN = g("DISCORD_TOKEN", "")
        cls.GUILD_ID = _int(g("GUILD_ID"))
        cls.OWNER_IDS = {_int(x) for x in g("OWNER_IDS", "").split(",") if x.strip()}
        cls.PREFIX = g("PREFIX", "!")
        cls.EXTRA_GUILD_IDS = {_int(x) for x in g("EXTRA_GUILD_IDS", "").split(",") if x.strip()}

        cls.DASHBOARD_HOST = g("DASHBOARD_HOST", "127.0.0.1")
        cls.DASHBOARD_PORT = _int(g("DASHBOARD_PORT"), 8000)
        cls.DASHBOARD_PASSWORD = g("DASHBOARD_PASSWORD", "change-me")
        cls.SECRET_KEY = g("SECRET_KEY", "change-me-too")
        cls.DATABASE_PATH = g("DATABASE_PATH", "data/tickets.db")
        cls.TRANSCRIPT_DIR = os.path.join(os.path.dirname(cls.DATABASE_PATH) or ".", "transcripts")

        # presence
        cls.PRESENCE_STATUS = g("PRESENCE_STATUS", "online").strip().lower()
        cls.ACTIVITY_TYPE = g("ACTIVITY_TYPE", "watching").strip().lower()
        cls.ACTIVITY_TEXT = g("ACTIVITY_TEXT", "{tickets} open tickets;{prefix}help")
        cls.ACTIVITY_URL = g("ACTIVITY_URL", "https://twitch.tv/discord")
        cls.PRESENCE_ROTATE_SECONDS = _int(g("PRESENCE_ROTATE_SECONDS"), 30)


Config.load()
