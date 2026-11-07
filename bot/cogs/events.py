import logging
import time

import discord
from discord.ext import commands, tasks

from bot.utils import err
from config import Config

log = logging.getLogger("ticketbot")


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.auto_close.start()

    async def cog_unload(self):
        self.auto_close.cancel()

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
       if guild.id != Config.GUILD_ID and guild.id not in Config.EXTRA_GUILD_IDS:
            await guild.leave()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, discord.Thread):
            return
        ticket = await self.bot.db.ticket_by_thread(message.channel.id)
        if not ticket or ticket["status"] == "closed":
            return
        await self.bot.db.touch(message.channel.id)
        # the user answered while we were waiting on them -> back to open
        if ticket["status"] == "waiting" and message.author.id == ticket["user_id"]:
            await self.bot.db.update_ticket(ticket["id"], status="open")
            await self.bot.tickets.refresh(ticket["id"])

    @tasks.loop(minutes=10)
    async def auto_close(self):
        hours = self.bot.db.get_int("auto_close_hours", 0)
        if not hours:
            return
        for t in await self.bot.db.stale_tickets(time.time() - hours * 3600):
            try:
                await self.bot.tickets.close_ticket(t, self.bot.user.id, f"Auto-closed after {hours}h of inactivity")
            except Exception:
                log.exception("auto-close failed for ticket %s", t["id"])

    @auto_close.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CheckFailure):
            return await ctx.send(embed=err(str(error) or "You can't use that command."))
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            usage = f"{Config.PREFIX}{ctx.command.qualified_name} {ctx.command.signature}".strip()
            return await ctx.send(embed=err(f"Wrong usage. Try: `{usage}`"))
        log.exception("Command error", exc_info=error)
        await ctx.send(embed=err("Something went wrong. Check the bot console."))


async def setup(bot):
    await bot.add_cog(Events(bot))
