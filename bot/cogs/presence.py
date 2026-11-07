"""Bot status + activity, fully controlled from .env (see PRESENCE_* / ACTIVITY_*)."""
import discord
from discord.ext import commands, tasks

from bot.utils import err, ok
from config import Config

STATUSES = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible,
}
TYPES = {
    "listening": discord.ActivityType.listening,
    "watching": discord.ActivityType.watching,
    "competing": discord.ActivityType.competing,
}


class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.index = 0

    async def cog_load(self):
        self._set_interval()
        self.loop.start()

    async def cog_unload(self):
        self.loop.cancel()

    def _set_interval(self):
        secs = Config.PRESENCE_ROTATE_SECONDS
        # Discord limits presence updates, so never go below 15s
        self.loop.change_interval(seconds=max(15, secs) if secs > 0 else 600)

    def texts(self):
        return [t.strip() for t in Config.ACTIVITY_TEXT.split(";") if t.strip()]

    async def render(self, text):
        guild = self.bot.get_guild(Config.GUILD_ID)
        stats = await self.bot.db.stats()
        return text.format_map(SafeDict(
            prefix=Config.PREFIX, tickets=stats["open"], total=stats["total"],
            members=guild.member_count if guild else 0, guild=guild.name if guild else ""))

    def activity(self, text):
        kind = Config.ACTIVITY_TYPE
        if not text or kind == "none":
            return None
        if kind == "playing":
            return discord.Game(name=text)
        if kind == "streaming":
            return discord.Streaming(name=text, url=Config.ACTIVITY_URL or "https://twitch.tv/discord")
        if kind == "custom":
            return discord.CustomActivity(name=text)
        return discord.Activity(type=TYPES.get(kind, discord.ActivityType.watching), name=text)

    async def apply(self):
        texts = self.texts()
        text = None
        if texts:
            text = await self.render(texts[self.index % len(texts)])
            if Config.PRESENCE_ROTATE_SECONDS > 0:
                self.index += 1
        await self.bot.change_presence(
            status=STATUSES.get(Config.PRESENCE_STATUS, discord.Status.online),
            activity=self.activity(text))

    @tasks.loop(seconds=30)
    async def loop(self):
        await self.apply()

    @loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def presence(self, ctx, action: str = "show"):
        """Owner only. `presence reload` re-reads the presence settings from .env."""
        if ctx.author.id not in Config.OWNER_IDS:
            return await ctx.send(embed=err("Owner only."))
        if action.lower() == "reload":
            Config.load()
            self.index = 0
            self._set_interval()
            self.loop.restart()
            return await ctx.send(embed=ok("Presence reloaded from `.env`."))
        await ctx.send(embed=ok(
            f"Status `{Config.PRESENCE_STATUS}` · type `{Config.ACTIVITY_TYPE}` · "
            f"{len(self.texts())} text(s) · rotate `{Config.PRESENCE_ROTATE_SECONDS}s`"))


async def setup(bot):
    await bot.add_cog(Presence(bot))
