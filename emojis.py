"""
╔══════════════════════════════════════════════════════════════╗
║  EVERY emoji the bot uses lives here. Edit freely.           ║
╚══════════════════════════════════════════════════════════════╝

Unicode emoji : "🎫"
Custom emoji  : "<:name:123456789012345678>"
Animated      : "<a:name:123456789012345678>"
(Type \\:youremoji: in Discord and copy what it prints.)

The bot must share a server with custom emojis (or you can upload them as
Application Emojis in the Developer Portal) or Discord will reject them.

!! THREAD_STATUS is used in THREAD NAMES, which only support Unicode. !!
"""


class Emojis:
    # ── general ──
    TICKET = "<:ticket:1568195391193874453>"
    SUCCESS = "<:Tick:1568132116896555099>"
    ERROR = "<:CROSS_ZS:1568132224220405770>"
    WARNING = "<a:cautiondude:1568133404099088488>"
    INFO = "<:info:1568195901061734410>"
    SETTINGS = "<a:settings:1555821272980652082>"

    # ── buttons ──
    CLAIM = "<a:Green_dot1:1567917158212833300>"
    CLOSE = "<a:mm_close:1568196335813922877>"
    TRANSCRIPT = "<a:42985spellbook:1568196636671479880>"
    REOPEN = "<a:lock:1568196227022192730>"

    # ── embed field icons ──
    CATEGORY = "<:CodeXFolder:1568196733450719243>"
    PRIORITY = "<:King:1568196783530709054>"
    USER = "<:Members:1568196852732399656>"
    STAFF = "<a:staffteamss:1568197258279653386>"
    NOTE = "<a:42985spellbook:1568196636671479880>"
    CLOCK = "<a:time:1568134203449544734>"
    STATS = "<a:stats:1567917023990648842>"
    BLACKLIST = "<:ban:1568197594361106582>"
    ADD = "<:5575members:1568132816557052047>."
    REMOVE = "<:CROSS_ZS:1568132224220405770>"
    REASON = "<a:staffteamss:1568197258279653386>"

    # ── ratings ──
    STAR = "<a:019_star_pink2:1568197923949510756>"


# Seeded into the database the first time the bot starts: (name, description, emoji)
CATEGORY_DEFAULTS = [
    ("Support", "General help and questions", "<a:staffteamss:1568197258279653386>"),
    ("Billing", "Payments and purchases", "<a:money_wings:1568198051531718687>"),
    ("Bug Report", "Something isn't working", "<a:cautiondude:1568133404099088488>"),
    ("Report a User", "Report rule breakers", "<a:cautiondude:1568133404099088488>"),
    ("Other", "Anything else", "<a:DC_exclamation:1568198296927993927>"),
]

# Shown at the start of the thread name. Keep these UNICODE.
THREAD_STATUS = {
    "open": "🟢",
    "waiting": "🟡",
    "claimed": "🔵",
    "urgent": "🔴",
    "closed": "🔒",
}

PRIORITY_EMOJI = {
    "low": "⚪",
    "medium": "🟡",
    "high": "🟠",
    "urgent": "🔴",
}
