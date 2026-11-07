# Ticket Bot (prefix commands · threads · custom emojis · local dashboard)

Single-server Discord ticket system in Python. Tickets are **private threads**, commands use a
**prefix** (default `!`), every emoji lives in **`emojis.py`**, and the bot's **presence is set in `.env`**.
A dashboard runs on `http://127.0.0.1:8000` in the same process.

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`, `GUILD_ID`, `OWNER_IDS`, `DASHBOARD_PASSWORD`, `SECRET_KEY`.
3. Developer Portal → your bot → enable **Message Content Intent** and **Server Members Intent**.
4. Invite the bot with these permissions: View Channels, Send Messages, Send Messages in Threads,
   Create Private Threads, Manage Threads, Embed Links, Attach Files, Read Message History, Add Reactions.
5. `python main.py`, then in Discord: `!setup #ticket-logs @Staff` and `!panel`.

## Presence (.env)
| Key | Values |
|---|---|
| `PRESENCE_STATUS` | `online` `idle` `dnd` `invisible` |
| `ACTIVITY_TYPE` | `playing` `watching` `listening` `streaming` `competing` `custom` `none` |
| `ACTIVITY_TEXT` | texts separated by `;` (they rotate). Placeholders: `{prefix}` `{tickets}` `{total}` `{members}` `{guild}` |
| `ACTIVITY_URL` | stream URL (only for `streaming`) |
| `PRESENCE_ROTATE_SECONDS` | `15`+ to rotate, `0` = no rotation |

Edit `.env`, then run `!presence reload` (owner only), no restart needed.

## Prefix commands
- **Inside a ticket (staff):** `claim` `unclaim` `close [reason]` `reopen [id]` `add @u` `remove @u` `rename <name>` `priority <low|medium|high|urgent>` `waiting` `transcript`
- **Ticket owner:** `close [reason]`
- **Staff:** `tickets` `stats` `blacklist @u [reason]` `unblacklist @u`
- **Admin (Manage Server):** `panel [#channel]` `updatepanel` `setup #log @staffrole`
- **Owner:** `presence [reload]`

Buttons and modals (open ticket, claim, close, transcript) are Discord components, not slash commands.

## Emojis
Open `emojis.py`. Use `"🎫"` or a custom emoji string like `"<:ticket:123456789012345678>"`.
The bot has to be in a server that has the emoji (or use Application Emojis).
`THREAD_STATUS` is used in thread names, which only support Unicode, so keep that dict as Unicode.
Category emojis are edited in the dashboard (Categories page).

## Dashboard
Overview, tickets (close/reopen/transcripts), categories, panel + all settings, blacklist.
Bound to `127.0.0.1` by default. For remote access use an SSH tunnel or Tailscale, don't expose the port.

## Notes
- The bot only works in `GUILD_ID` and leaves any other server.
- Discord limits thread renames to about 2 per 10 minutes, so rapid status changes may lag in the thread name.
- Transcripts are saved to `data/transcripts/` and posted to the log channel and the user's DMs.
