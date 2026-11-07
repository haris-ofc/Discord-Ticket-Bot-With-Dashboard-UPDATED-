"""All buttons, dropdowns and modals. Persistent views use fixed custom_ids."""
import discord

from bot.utils import err, info, ok
from emojis import Emojis as E


# ═════════════ opening a ticket ═════════════
async def start_ticket(interaction: discord.Interaction, cat_id: int):
    svc = interaction.client.tickets
    cat = await svc.db.category(cat_id)
    if not cat or not cat["enabled"]:
        return await interaction.response.send_message(embed=err("That category no longer exists."), ephemeral=True)
    problem = await svc.can_open(interaction.user)
    if problem:
        return await interaction.response.send_message(embed=err(problem), ephemeral=True)
    await interaction.response.send_modal(OpenTicketModal(cat))


class OpenTicketModal(discord.ui.Modal):
    def __init__(self, category):
        super().__init__(title=f"{category['name']}"[:45])
        self.category = category
        self.subject = discord.ui.TextInput(label="Subject", max_length=100, placeholder="Short summary")
        self.details = discord.ui.TextInput(
            label="Describe your issue", style=discord.TextStyle.paragraph, max_length=1000,
            placeholder="Give us as much detail as you can")
        self.add_item(self.subject)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        thread, problem = await interaction.client.tickets.open_ticket(
            interaction, self.category, str(self.subject), str(self.details))
        if problem:
            return await interaction.followup.send(embed=err(problem), ephemeral=True)
        await interaction.followup.send(embed=ok(f"Your ticket is ready: {thread.mention}"), ephemeral=True)


class CategoryButton(discord.ui.Button):
    def __init__(self, cat):
        super().__init__(label=cat["name"][:80], emoji=cat["emoji"] or None,
                         style=discord.ButtonStyle.primary, custom_id=f"tk:open:{cat['id']}")
        self.cat_id = cat["id"]

    async def callback(self, interaction):
        await start_ticket(interaction, self.cat_id)


class CategorySelect(discord.ui.Select):
    def __init__(self, cats):
        options = [
            discord.SelectOption(label=c["name"][:100], value=str(c["id"]),
                                 description=(c["description"] or None) and c["description"][:100],
                                 emoji=c["emoji"] or None)
            for c in cats[:25]
        ]
        super().__init__(placeholder="Choose a category…", options=options, custom_id="tk:select")

    async def callback(self, interaction):
        await start_ticket(interaction, int(self.values[0]))


class PanelView(discord.ui.View):
    def __init__(self, cats, style="buttons"):
        super().__init__(timeout=None)
        if not cats:
            return
        if style == "select":
            self.add_item(CategorySelect(cats))
        else:
            for c in cats[:25]:
                self.add_item(CategoryButton(c))


# ═════════════ inside a ticket ═════════════
async def _ticket(interaction):
    svc = interaction.client.tickets
    ticket = await svc.db.ticket_by_thread(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message(embed=err("This isn't a ticket thread."), ephemeral=True)
    return svc, ticket


class CloseModal(discord.ui.Modal, title="Close ticket"):
    reason = discord.ui.TextInput(label="Reason (optional)", required=False, max_length=300,
                                  style=discord.TextStyle.paragraph)

    def __init__(self, ticket_id):
        super().__init__()
        self.ticket_id = ticket_id

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        svc = interaction.client.tickets
        ticket = await svc.db.ticket(self.ticket_id)
        await svc.close_ticket(ticket, interaction.user.id, str(self.reason) or "No reason provided")
        await interaction.followup.send(embed=ok("Ticket closed."), ephemeral=True)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", emoji=E.CLAIM, style=discord.ButtonStyle.success, custom_id="tk:claim")
    async def claim(self, interaction, button):
        svc, ticket = await _ticket(interaction)
        if not ticket:
            return
        if not svc.is_staff(interaction.user):
            return await interaction.response.send_message(embed=err("Staff only."), ephemeral=True)
        if ticket["claimed_by"]:
            return await interaction.response.send_message(
                embed=err(f"Already claimed by <@{ticket['claimed_by']}>."), ephemeral=True)
        await svc.claim(ticket, interaction.user.id)
        await interaction.response.send_message(
            embed=info(f"{E.CLAIM} {interaction.user.mention} claimed this ticket."))

    @discord.ui.button(label="Close", emoji=E.CLOSE, style=discord.ButtonStyle.danger, custom_id="tk:close")
    async def close(self, interaction, button):
        svc, ticket = await _ticket(interaction)
        if not ticket:
            return
        if ticket["status"] == "closed":
            return await interaction.response.send_message(embed=err("Already closed."), ephemeral=True)
        if not (svc.is_staff(interaction.user) or interaction.user.id == ticket["user_id"]):
            return await interaction.response.send_message(embed=err("You can't close this ticket."), ephemeral=True)
        await interaction.response.send_modal(CloseModal(ticket["id"]))

    @discord.ui.button(label="Transcript", emoji=E.TRANSCRIPT, style=discord.ButtonStyle.secondary,
                       custom_id="tk:transcript")
    async def transcript(self, interaction, button):
        svc, ticket = await _ticket(interaction)
        if not ticket:
            return
        if not svc.is_staff(interaction.user):
            return await interaction.response.send_message(embed=err("Staff only."), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        path = await svc.make_transcript(interaction.channel, ticket)
        await interaction.followup.send(file=discord.File(path, filename=f"transcript-{ticket['id']:04d}.html"),
                                        ephemeral=True)


# ═════════ rating (sent in DMs) ═════════
class RatingView(discord.ui.View):
    def __init__(self, bot, ticket_id):
        super().__init__(timeout=3 * 24 * 3600)
        self.bot, self.ticket_id = bot, ticket_id
        for n in range(1, 6):
            b = discord.ui.Button(label=str(n), emoji=E.STAR, style=discord.ButtonStyle.secondary)
            b.callback = self._make(n)
            self.add_item(b)

    def _make(self, n):
        async def callback(interaction):
            await self.bot.db.update_ticket(self.ticket_id, rating=n)
            for c in self.children:
                c.disabled = True
            await interaction.response.edit_message(
                content=f"{E.SUCCESS} Thanks! You rated your ticket **{n}/5**.", view=self)
            self.stop()
        return callback
