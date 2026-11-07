import logging

import discord
from discord.ext import commands

from bot.core import TicketService
from bot.views import TicketControlView
from config import Config
from database import Database

log = logging.getLogger("ticketbot")

EXTENSIONS = ("bot.cogs.tickets", "bot.cogs.events", "bot.cogs.presence")


def get_prefix(bot, message):
    return commands.when_mentioned_or(Config.PREFIX)(bot, message)


class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True   # needed for prefix commands
        intents.members = True           # needed for staff role checks
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None, case_insensitive=True)
        self.db = Database(Config.DATABASE_PATH)
        self.tickets = TicketService(self)

    async def setup_hook(self):
        self.add_view(TicketControlView())
        await self.tickets.register_panel_view()
        for ext in EXTENSIONS:
            await self.load_extension(ext)

    async def on_ready(self):
        log.info("Logged in as %s (prefix %s)", self.user, Config.PREFIX)
        for g in self.guilds:
            if g.id != Config.GUILD_ID and g.id not in Config.EXTRA_GUILD_IDS:
                log.warning("Leaving unauthorised guild %s", g.name)
                await g.leave()
