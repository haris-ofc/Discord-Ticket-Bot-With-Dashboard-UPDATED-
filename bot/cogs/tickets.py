"""Prefix commands. Default prefix is `!` (change PREFIX in .env)."""
import discord
from discord.ext import commands

from bot.core import PRIORITIES
from bot.utils import err, info, ok
from config import Config
from emojis import Emojis as E, PRIORITY_EMOJI


def staff_only():
    async def pred(ctx):
        if ctx.bot.tickets.is_staff(ctx.author):
            return True
        raise commands.CheckFailure("Staff only.")
    return commands.check(pred)


def admin_only():
    async def pred(ctx):
        if ctx.bot.tickets.is_admin(ctx.author):
            return True
        raise commands.CheckFailure("You need **Manage Server** for that.")
    return commands.check(pred)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def svc(self):
        return self.bot.tickets

    async def cog_check(self, ctx):
        return ctx.guild is not None and ctx.guild.id == Config.GUILD_ID

    async def current(self, ctx):
        t = await self.bot.db.ticket_by_thread(ctx.channel.id)
        if not t:
            await ctx.send(embed=err("Use this inside a ticket thread."))
        return t

    # ───────── help ─────────
    @commands.command()
    async def help(self, ctx):
        p = Config.PREFIX
        e = discord.Embed(title=f"{E.TICKET} Ticket commands", color=discord.Color.blurple())
        e.add_field(name="Inside a ticket (staff)", inline=False, value=(
            f"`{p}claim` · `{p}unclaim` · `{p}close [reason]` · `{p}reopen [id]`\n"
            f"`{p}add @user` · `{p}remove @user` · `{p}rename <name>`\n"
            f"`{p}priority <low|medium|high|urgent>` · `{p}waiting` · `{p}transcript`"))
        e.add_field(name="Anyone in their own ticket", inline=False, value=f"`{p}close [reason]`")
        e.add_field(name="Staff", inline=False, value=f"`{p}tickets` · `{p}stats` · `{p}blacklist @user [reason]` · `{p}unblacklist @user`")
        e.add_field(name="Admin", inline=False, value=f"`{p}panel [#channel]` · `{p}updatepanel` · `{p}setup #log @staffrole`")
        e.add_field(name="Owner", inline=False, value=f"`{p}presence [reload]`")
        await ctx.send(embed=e)

    # ───────── admin ─────────
    @commands.command()
    @admin_only()
    async def panel(self, ctx, channel: discord.TextChannel = None):
        """Send the ticket panel."""
        channel = channel or ctx.channel
        await self.svc.send_panel(channel)
        await ctx.send(embed=ok(f"Panel sent in {channel.mention}."))

    @commands.command()
    @admin_only()
    async def updatepanel(self, ctx):
        """Refresh the existing panel after changing categories/settings."""
        try:
            await self.svc.update_panel()
        except RuntimeError as ex:
            return await ctx.send(embed=err(str(ex)))
        await ctx.send(embed=ok("Panel updated."))

    @commands.command()
    @admin_only()
    async def setup(self, ctx, log_channel: discord.TextChannel, staff_role: discord.Role):
        await self.bot.db.set("log_channel_id", log_channel.id)
        await self.bot.db.set("staff_role_id", staff_role.id)
        await ctx.send(embed=ok(f"Logs → {log_channel.mention}, staff role → {staff_role.mention}.\n"
                                f"Now run `{Config.PREFIX}panel` where you want the ticket panel."))

    # ───────── inside a ticket ─────────
    @commands.command()
    @staff_only()
    async def claim(self, ctx):
        t = await self.current(ctx)
        if not t:
            return
        if t["claimed_by"]:
            return await ctx.send(embed=err(f"Already claimed by <@{t['claimed_by']}>."))
        await self.svc.claim(t, ctx.author.id)
        await ctx.send(embed=info(f"{E.CLAIM} {ctx.author.mention} claimed this ticket."))

    @commands.command()
    @staff_only()
    async def unclaim(self, ctx):
        t = await self.current(ctx)
        if not t:
            return
        await self.svc.unclaim(t)
        await ctx.send(embed=ok("Ticket unclaimed."))

    @commands.command()
    async def close(self, ctx, *, reason: str = "No reason provided"):
        t = await self.current(ctx)
        if not t:
            return
        if not (self.svc.is_staff(ctx.author) or ctx.author.id == t["user_id"]):
            return await ctx.send(embed=err("You can't close this ticket."))
        if t["status"] == "closed":
            return await ctx.send(embed=err("Already closed."))
        await self.svc.close_ticket(t, ctx.author.id, reason)

    @commands.command()
    @staff_only()
    async def reopen(self, ctx, ticket_id: int = None):
        t = await (self.bot.db.ticket(ticket_id) if ticket_id else self.bot.db.ticket_by_thread(ctx.channel.id))
        if not t:
            return await ctx.send(embed=err("Ticket not found. Use `reopen <id>`."))
        if not await self.svc.reopen_ticket(t, ctx.author.id):
            return await ctx.send(embed=err("That ticket isn't closed."))
        await ctx.send(embed=ok(f"Ticket #{t['id']:04d} reopened."))

    @commands.command()
    @staff_only()
    async def add(self, ctx, member: discord.Member):
        if not await self.current(ctx):
            return
        await ctx.channel.add_user(member)
        await ctx.send(embed=ok(f"{E.ADD} Added {member.mention}."))

    @commands.command()
    @staff_only()
    async def remove(self, ctx, member: discord.Member):
        t = await self.current(ctx)
        if not t:
            return
        if member.id == t["user_id"]:
            return await ctx.send(embed=err("You can't remove the ticket owner."))
        await ctx.channel.remove_user(member)
        await ctx.send(embed=ok(f"{E.REMOVE} Removed {member.mention}."))

    @commands.command()
    @staff_only()
    async def rename(self, ctx, *, name: str):
        """Sets the thread name. Status changes may overwrite it later."""
        if not await self.current(ctx):
            return
        await ctx.channel.edit(name=name[:100])
        await ctx.send(embed=ok("Renamed."))

    @commands.command()
    @staff_only()
    async def priority(self, ctx, level: str):
        t = await self.current(ctx)
        if not t:
            return
        level = level.lower()
        if level not in PRIORITIES:
            return await ctx.send(embed=err("Choose: " + ", ".join(PRIORITIES)))
        await self.svc.set_priority(t, level)
        await ctx.send(embed=ok(f"Priority set to {PRIORITY_EMOJI[level]} **{level}**."))

    @commands.command()
    @staff_only()
    async def waiting(self, ctx):
        """Toggle 'waiting for user' status."""
        t = await self.current(ctx)
        if not t:
            return
        new = await self.svc.toggle_waiting(t)
        await ctx.send(embed=info("Waiting for the user's reply." if new == "waiting" else "Back to open."))

    @commands.command()
    @staff_only()
    async def transcript(self, ctx):
        t = await self.current(ctx)
        if not t:
            return
        path = await self.svc.make_transcript(ctx.channel, t)
        await ctx.send(file=discord.File(path, filename=f"transcript-{t['id']:04d}.html"))

    # ───────── overview ─────────
    @commands.command()
    @staff_only()
    async def tickets(self, ctx):
        rows = await self.bot.db.list_tickets("open", 20)
        if not rows:
            return await ctx.send(embed=info("No open tickets. 🎉"))
        lines = [f"`#{t['id']:04d}` <#{t['thread_id']}> · {PRIORITY_EMOJI[t['priority']]} · "
                 f"{t['category_name']} · <@{t['user_id']}>" for t in rows if t["thread_id"]]
        await ctx.send(embed=discord.Embed(title=f"{E.TICKET} Open tickets", description="\n".join(lines),
                                           color=discord.Color.blurple()))

    @commands.command()
    @staff_only()
    async def stats(self, ctx):
        s = await self.bot.db.stats()
        e = discord.Embed(title=f"{E.STATS} Ticket stats", color=discord.Color.blurple())
        e.add_field(name="Open", value=s["open"])
        e.add_field(name="Closed", value=s["closed"])
        e.add_field(name="Total", value=s["total"])
        e.add_field(name=f"{E.STAR} Avg rating", value=f"{s['avg_rating']}/5" if s["avg_rating"] else "—")
        if s["top_staff"]:
            e.add_field(name=f"{E.STAFF} Top staff", inline=False, value="\n".join(
                f"<@{r['claimed_by']}> — {r['c']} claimed" for r in s["top_staff"]))
        await ctx.send(embed=e)

    # ───────── blacklist ─────────
    @commands.command()
    @staff_only()
    async def blacklist(self, ctx, member: discord.Member, *, reason: str = "No reason"):
        await self.bot.db.add_blacklist(member.id, reason, ctx.author.id)
        await ctx.send(embed=ok(f"{E.BLACKLIST} {member.mention} can no longer open tickets."))

    @commands.command()
    @staff_only()
    async def unblacklist(self, ctx, member: discord.Member):
        await self.bot.db.remove_blacklist(member.id)
        await ctx.send(embed=ok(f"{member.mention} can open tickets again."))


async def setup(bot):
    await bot.add_cog(Tickets(bot))
