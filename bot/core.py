"""TicketService: all ticket logic, shared by buttons, prefix commands and the dashboard."""
import asyncio
import html
import os
import time

import discord

from bot.utils import hex_color, slug
from bot.views import PanelView, RatingView, TicketControlView
from config import Config
from emojis import Emojis as E, PRIORITY_EMOJI, THREAD_STATUS

ESC = html.escape
PRIORITIES = ("low", "medium", "high", "urgent")

TRANSCRIPT_CSS = """body{font-family:system-ui,sans-serif;background:#1e1f22;color:#dbdee1;max-width:860px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.2rem}.msg{display:flex;gap:.7rem;margin:.9rem 0}.msg img{width:38px;height:38px;border-radius:50%}
.msg span{color:#80848e;font-size:.75rem;margin-left:.4rem}.embed{border-left:4px solid #5865f2;background:#2b2d31;padding:.4rem .7rem;margin-top:.3rem}
a{color:#00a8fc}"""


def display_status(t):
    if t["status"] == "closed":
        return "closed"
    if t["priority"] == "urgent":
        return "urgent"
    if t["claimed_by"]:
        return "claimed"
    if t["status"] == "waiting":
        return "waiting"
    return "open"


class TicketService:
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}

    @property
    def db(self):
        return self.bot.db

    @property
    def guild(self):
        return self.bot.get_guild(Config.GUILD_ID)

    # ───────── permissions ─────────
    def is_admin(self, member):
        return isinstance(member, discord.Member) and (
            member.guild_permissions.manage_guild or member.id in Config.OWNER_IDS)

    def is_staff(self, member):
        if not isinstance(member, discord.Member):
            return False
        if self.is_admin(member):
            return True
        rid = self.db.get_int("staff_role_id")
        return bool(rid) and any(r.id == rid for r in member.roles)

    # ───────── helpers ─────────
    async def get_thread(self, thread_id):
        ch = self.bot.get_channel(thread_id)
        if ch:
            return ch
        try:
            return await self.bot.fetch_channel(thread_id)
        except (discord.NotFound, discord.Forbidden):
            return None

    def name_for(self, t, username=None):
        if username is None:
            m = self.guild.get_member(t["user_id"]) if self.guild else None
            username = m.name if m else str(t["user_id"])
        name = self.db.get("name_template") or "{status}┃{category}-{number}-{user}"
        values = {
            "status": THREAD_STATUS.get(display_status(t), E.TICKET),
            "category": slug(t["category_name"], 15),
            "number": f"{t['id']:04d}",
            "user": slug(username, 20),
        }
        for k, v in values.items():
            name = name.replace("{" + k + "}", v)
        return name[:100]

    def ticket_embed(self, t, user_mention, details=None, welcome=None):
        e = discord.Embed(title=f"{E.TICKET} Ticket #{t['id']:04d}", description=welcome,
                          color=hex_color(self.db.get("panel_color")))
        e.add_field(name=f"{E.CATEGORY} Category", value=t["category_name"])
        e.add_field(name=f"{E.PRIORITY} Priority", value=f"{PRIORITY_EMOJI[t['priority']]} {t['priority'].title()}")
        e.add_field(name=f"{E.USER} Opened by", value=user_mention)
        e.add_field(name=f"{E.NOTE} Subject", value=t["subject"][:1024], inline=False)
        if details:
            e.add_field(name=f"{E.REASON} Details", value=details[:1024], inline=False)
        return e

    async def log(self, embed, path=None):
        ch = self.guild.get_channel(self.db.get_int("log_channel_id")) if self.guild else None
        if not ch:
            return
        try:
            kwargs = {"file": discord.File(path, filename=os.path.basename(path))} if path else {}
            await ch.send(embed=embed, **kwargs)
        except discord.HTTPException:
            pass

    async def _rename(self, thread, ticket):
        try:
            await thread.edit(name=self.name_for(ticket))
        except discord.HTTPException:
            pass

    async def refresh(self, ticket_id):
        """Reload ticket and rename its thread in the background (Discord rate-limits renames)."""
        t = await self.db.ticket(ticket_id)
        thread = await self.get_thread(t["thread_id"]) if t and t["thread_id"] else None
        if thread:
            asyncio.create_task(self._rename(thread, t))
        return t

    # ───────── panel ─────────
    async def build_panel(self):
        s = self.db
        cats = await s.categories(enabled_only=True)
        embed = discord.Embed(title=f"{E.TICKET} {s.get('panel_title')}", description=s.get("panel_description"),
                              color=hex_color(s.get("panel_color")))
        if cats:
            embed.add_field(name="Categories", inline=False, value="\n".join(
                f"{c['emoji']} **{c['name']}**" + (f" — {c['description']}" if c["description"] else "")
                for c in cats))
        return embed, PanelView(cats, s.get("panel_style"))

    async def register_panel_view(self):
        mid = self.db.get_int("panel_message_id")
        if mid:
            _, view = await self.build_panel()
            self.bot.add_view(view, message_id=mid)

    async def send_panel(self, channel):
        embed, view = await self.build_panel()
        msg = await channel.send(embed=embed, view=view)
        await self.db.set("panel_channel_id", channel.id)
        await self.db.set("panel_message_id", msg.id)
        self.bot.add_view(view, message_id=msg.id)
        return msg

    async def update_panel(self):
        channel = self.guild.get_channel(self.db.get_int("panel_channel_id")) if self.guild else None
        if not channel:
            raise RuntimeError("No panel has been sent yet.")
        embed, view = await self.build_panel()
        try:
            msg = await channel.fetch_message(self.db.get_int("panel_message_id"))
            await msg.edit(embed=embed, view=view)
        except discord.NotFound:
            msg = await channel.send(embed=embed, view=view)
            await self.db.set("panel_message_id", msg.id)
        self.bot.add_view(view, message_id=msg.id)

    # ───────── opening ─────────
    async def can_open(self, user):
        db = self.db
        if await db.is_blacklisted(user.id):
            return "You are blacklisted from opening tickets."
        if db.get("maintenance") == "1":
            return db.get("maintenance_message") or "Tickets are temporarily disabled."
        limit = db.get_int("max_open", 2)
        if limit and len(await db.open_tickets_by_user(user.id)) >= limit:
            return f"You already have {limit} open ticket(s). Close one first."
        cd = db.get_int("cooldown", 0)
        left = self.cooldowns.get(user.id, 0) + cd - time.time()
        if cd and left > 0:
            return f"Please wait {int(left) + 1}s before opening another ticket."
        return None

    async def open_ticket(self, interaction, category, subject, details):
        user, db = interaction.user, self.db
        problem = await self.can_open(user)
        if problem:
            return None, problem
        channel = interaction.channel
        if isinstance(channel, discord.Thread):
            channel = channel.parent

        tid = await db.create_ticket(user.id, category["id"], category["name"], subject, channel.id)
        ticket = await db.ticket(tid)
        private = db.get("private_threads") == "1"
        minutes = db.get_int("archive_minutes", 1440)
        kwargs = {"invitable": False} if private else {}
        try:
            thread = await channel.create_thread(
                name=self.name_for(ticket, user.name),
                type=discord.ChannelType.private_thread if private else discord.ChannelType.public_thread,
                auto_archive_duration=minutes if minutes in (60, 1440, 4320, 10080) else 1440, **kwargs)
            await thread.add_user(user)
        except discord.HTTPException as ex:
            await db.delete_ticket(tid)
            return None, f"Couldn't create the thread (check the bot's permissions): {ex.text}"
        await db.update_ticket(tid, thread_id=thread.id)
        self.cooldowns[user.id] = time.time()

        roles = [db.get_int("staff_role_id"), category["role_id"]]
        staff = " ".join(dict.fromkeys(f"<@&{r}>" for r in roles if r))
        welcome = (db.get("welcome_message").replace("{user}", user.mention)
                   .replace("{staff}", staff or "Our team").replace("{category}", category["name"])
                   .replace("{ticket_id}", f"{tid:04d}"))
        await thread.send(content=f"{user.mention} {staff}".strip(),
                          embed=self.ticket_embed(ticket, user.mention, details, welcome),
                          view=TicketControlView(),
                          allowed_mentions=discord.AllowedMentions(users=True, roles=True))
        log = discord.Embed(title=f"{E.TICKET} Ticket opened", color=discord.Color.green(),
                            description=f"{thread.mention} by {user.mention}\n**{category['name']}** — {subject}")
        await self.log(log)
        return thread, None

    # ───────── actions ─────────
    async def claim(self, ticket, staff_id):
        await self.db.update_ticket(ticket["id"], claimed_by=staff_id, status="open")
        await self.refresh(ticket["id"])

    async def unclaim(self, ticket):
        await self.db.update_ticket(ticket["id"], claimed_by=0)
        await self.refresh(ticket["id"])

    async def set_priority(self, ticket, level):
        await self.db.update_ticket(ticket["id"], priority=level)
        return await self.refresh(ticket["id"])

    async def toggle_waiting(self, ticket):
        new = "open" if ticket["status"] == "waiting" else "waiting"
        await self.db.update_ticket(ticket["id"], status=new)
        await self.refresh(ticket["id"])
        return new

    async def make_transcript(self, thread, ticket):
        rows = []
        async for m in thread.history(limit=None, oldest_first=True):
            body = ESC(m.content).replace("\n", "<br>")
            for a in m.attachments:
                body += f'<div><a href="{ESC(a.url)}">{ESC(a.filename)}</a></div>'
            for em in m.embeds:
                if em.title or em.description:
                    body += f'<div class="embed"><b>{ESC(em.title or "")}</b><br>{ESC(em.description or "")}</div>'
            rows.append(
                f'<div class="msg"><img src="{ESC(m.author.display_avatar.url)}"><div>'
                f'<b>{ESC(m.author.display_name)}</b><span>{m.created_at:%Y-%m-%d %H:%M UTC}</span>'
                f'<div>{body}</div></div></div>')
        doc = (f"<!doctype html><meta charset='utf-8'><title>Ticket #{ticket['id']:04d}</title>"
               f"<style>{TRANSCRIPT_CSS}</style><h1>Ticket #{ticket['id']:04d} — {ESC(ticket['category_name'])}"
               f" — {ESC(ticket['subject'])}</h1>" + "".join(rows))
        os.makedirs(Config.TRANSCRIPT_DIR, exist_ok=True)
        path = os.path.join(Config.TRANSCRIPT_DIR, f"{ticket['id']}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc)
        return path

    async def close_ticket(self, ticket, closer_id=0, reason="No reason provided"):
        if ticket["status"] == "closed":
            return False
        await self.db.update_ticket(ticket["id"], status="closed", closed_at=time.time(),
                                    closed_by=closer_id, close_reason=reason)
        ticket = await self.db.ticket(ticket["id"])
        by = f"<@{closer_id}>" if closer_id else "the dashboard"
        thread = await self.get_thread(ticket["thread_id"])
        path = None
        if thread:
            try:
                path = await self.make_transcript(thread, ticket)
                await thread.send(embed=discord.Embed(
                    title=f"{E.CLOSE} Ticket closed", color=discord.Color.red(),
                    description=f"Closed by {by}\n{E.REASON} {reason}"))
            except discord.HTTPException:
                pass

        log = discord.Embed(title=f"{E.CLOSE} Ticket closed", color=discord.Color.red(),
                            description=f"**#{ticket['id']:04d}** {ticket['category_name']} — {ticket['subject']}\n"
                                        f"Opened by <@{ticket['user_id']}> · closed by {by}\n{E.REASON} {reason}")
        await self.log(log, path)

        if self.db.get("transcript_dm") == "1":
            try:
                user = self.bot.get_user(ticket["user_id"]) or await self.bot.fetch_user(ticket["user_id"])
                dm = discord.Embed(title=f"{E.TICKET} Your ticket #{ticket['id']:04d} was closed",
                                   color=discord.Color.red(), description=f"{E.REASON} {reason}\n\nHow did we do?")
                kwargs = {"file": discord.File(path, filename=f"transcript-{ticket['id']:04d}.html")} if path else {}
                await user.send(embed=dm, view=RatingView(self.bot, ticket["id"]), **kwargs)
            except (discord.Forbidden, discord.HTTPException):
                pass

        if thread:
            try:
                await thread.edit(name=self.name_for(ticket), locked=True, archived=True)
            except discord.HTTPException:
                pass
        return True

    async def reopen_ticket(self, ticket, by_id=0):
        if ticket["status"] != "closed":
            return False
        await self.db.update_ticket(ticket["id"], status="open", closed_at=0, close_reason="",
                                    last_activity=time.time())
        ticket = await self.db.ticket(ticket["id"])
        thread = await self.get_thread(ticket["thread_id"])
        if thread:
            try:
                await thread.edit(archived=False, locked=False, name=self.name_for(ticket))
                by = f"<@{by_id}>" if by_id else "the dashboard"
                await thread.send(embed=discord.Embed(
                    title=f"{E.REOPEN} Ticket reopened", description=f"Reopened by {by}",
                    color=discord.Color.green()))
            except discord.HTTPException:
                pass
        return True
