import os
import time

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, description TEXT DEFAULT '', emoji TEXT DEFAULT '',
    role_id INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1, position INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER UNIQUE, user_id INTEGER, category_id INTEGER, category_name TEXT,
    subject TEXT, status TEXT DEFAULT 'open', priority TEXT DEFAULT 'medium',
    claimed_by INTEGER DEFAULT 0, created_at REAL, last_activity REAL,
    closed_at REAL DEFAULT 0, closed_by INTEGER DEFAULT 0, close_reason TEXT DEFAULT '',
    rating INTEGER DEFAULT 0, panel_channel_id INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS blacklist (
    user_id INTEGER PRIMARY KEY, reason TEXT, added_by INTEGER, created_at REAL
);
"""

DEFAULTS = {
    "staff_role_id": "0",
    "log_channel_id": "0",
    "panel_channel_id": "0",
    "panel_message_id": "0",
    "panel_title": "Support Tickets",
    "panel_description": "Need help? Pick a category below and a private thread will be opened for you.",
    "panel_color": "#5865F2",
    "panel_style": "buttons",          # buttons | select
    "max_open": "2",
    "cooldown": "60",
    "auto_close_hours": "48",          # 0 = off
    "private_threads": "1",
    "archive_minutes": "1440",
    "name_template": "{status}┃{category}-{number}-{user}",
    "welcome_message": "Thanks for opening a ticket, {user}! {staff} will be with you shortly.",
    "transcript_dm": "1",
    "maintenance": "0",
    "maintenance_message": "Tickets are temporarily disabled. Please try again later.",
}

TICKET_FIELDS = {
    "thread_id", "status", "priority", "claimed_by", "last_activity", "closed_at",
    "closed_by", "close_reason", "rating",
}


class Database:
    def __init__(self, path):
        self.path = path
        self.conn = None
        self.settings = dict(DEFAULTS)

    # ───────── low level ─────────
    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        for r in await self.fetchall("SELECT key, value FROM settings"):
            self.settings[r["key"]] = r["value"]
        if not await self.fetchone("SELECT id FROM categories LIMIT 1"):
            from emojis import CATEGORY_DEFAULTS
            for i, (n, d, e) in enumerate(CATEGORY_DEFAULTS):
                await self.add_category(n, d, e, 0, i)

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def fetchall(self, q, args=()):
        cur = await self.conn.execute(q, args)
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def fetchone(self, q, args=()):
        rows = await self.fetchall(q, args)
        return rows[0] if rows else None

    async def execute(self, q, args=()):
        cur = await self.conn.execute(q, args)
        await self.conn.commit()
        last = cur.lastrowid
        await cur.close()
        return last

    # ───────── settings ─────────
    def get(self, key, default=""):
        return self.settings.get(key, default)

    def get_int(self, key, default=0):
        try:
            return int(self.settings.get(key, default))
        except (ValueError, TypeError):
            return default

    async def set(self, key, value):
        value = str(value)
        self.settings[key] = value
        await self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ───────── categories ─────────
    async def categories(self, enabled_only=False):
        q = "SELECT * FROM categories" + (" WHERE enabled = 1" if enabled_only else "")
        return await self.fetchall(q + " ORDER BY position, id")

    async def category(self, cid):
        return await self.fetchone("SELECT * FROM categories WHERE id = ?", (cid,))

    async def add_category(self, name, description="", emoji="", role_id=0, position=0):
        return await self.execute(
            "INSERT INTO categories(name, description, emoji, role_id, position) VALUES(?,?,?,?,?)",
            (name, description, emoji, role_id, position))

    async def update_category(self, cid, name, description, emoji, role_id, enabled, position):
        await self.execute(
            "UPDATE categories SET name=?, description=?, emoji=?, role_id=?, enabled=?, position=? WHERE id=?",
            (name, description, emoji, role_id, enabled, position, cid))

    async def delete_category(self, cid):
        await self.execute("DELETE FROM categories WHERE id = ?", (cid,))

    # ───────── tickets ─────────
    async def create_ticket(self, user_id, category_id, category_name, subject, panel_channel_id):
        now = time.time()
        return await self.execute(
            "INSERT INTO tickets(user_id, category_id, category_name, subject, created_at, last_activity, panel_channel_id) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, category_id, category_name, subject, now, now, panel_channel_id))

    async def delete_ticket(self, tid):
        await self.execute("DELETE FROM tickets WHERE id = ?", (tid,))

    async def ticket(self, tid):
        return await self.fetchone("SELECT * FROM tickets WHERE id = ?", (tid,))

    async def ticket_by_thread(self, thread_id):
        return await self.fetchone("SELECT * FROM tickets WHERE thread_id = ?", (thread_id,))

    async def update_ticket(self, tid, **fields):
        fields = {k: v for k, v in fields.items() if k in TICKET_FIELDS}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        await self.execute(f"UPDATE tickets SET {sets} WHERE id = ?", (*fields.values(), tid))

    async def touch(self, thread_id):
        await self.execute(
            "UPDATE tickets SET last_activity = ? WHERE thread_id = ? AND status != 'closed'",
            (time.time(), thread_id))

    async def open_tickets_by_user(self, uid):
        return await self.fetchall("SELECT * FROM tickets WHERE user_id = ? AND status != 'closed'", (uid,))

    async def list_tickets(self, status=None, limit=100):
        q, args = "SELECT * FROM tickets", ()
        if status == "open":
            q += " WHERE status != 'closed'"
        elif status == "closed":
            q += " WHERE status = 'closed'"
        return await self.fetchall(q + " ORDER BY id DESC LIMIT ?", (limit,))

    async def stale_tickets(self, cutoff):
        return await self.fetchall(
            "SELECT * FROM tickets WHERE status != 'closed' AND thread_id IS NOT NULL AND last_activity < ?",
            (cutoff,))

    async def count_open(self):
        r = await self.fetchone("SELECT COUNT(*) c FROM tickets WHERE status != 'closed'")
        return r["c"]

    async def stats(self):
        r = await self.fetchone(
            "SELECT COUNT(*) total, SUM(status != 'closed') open, SUM(status = 'closed') closed, "
            "AVG(NULLIF(rating, 0)) avg_rating FROM tickets")
        top = await self.fetchall(
            "SELECT claimed_by, COUNT(*) c FROM tickets WHERE claimed_by != 0 "
            "GROUP BY claimed_by ORDER BY c DESC LIMIT 5")
        return {
            "total": r["total"] or 0, "open": r["open"] or 0, "closed": r["closed"] or 0,
            "avg_rating": round(r["avg_rating"], 2) if r["avg_rating"] else None, "top_staff": top,
        }

    # ───────── blacklist ─────────
    async def is_blacklisted(self, uid):
        return await self.fetchone("SELECT * FROM blacklist WHERE user_id = ?", (uid,)) is not None

    async def add_blacklist(self, uid, reason, by):
        await self.execute(
            "INSERT OR REPLACE INTO blacklist(user_id, reason, added_by, created_at) VALUES(?,?,?,?)",
            (uid, reason, by, time.time()))

    async def remove_blacklist(self, uid):
        await self.execute("DELETE FROM blacklist WHERE user_id = ?", (uid,))

    async def blacklist(self):
        return await self.fetchall("SELECT * FROM blacklist ORDER BY created_at DESC")
