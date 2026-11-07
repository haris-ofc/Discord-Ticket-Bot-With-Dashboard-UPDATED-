"""Local admin dashboard (FastAPI). Runs in the same process as the bot."""
import os
import secrets
from datetime import datetime

import discord
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import Config
from emojis import Emojis, PRIORITY_EMOJI, THREAD_STATUS

BASE = os.path.dirname(__file__)

TEXT_KEYS = [
    "staff_role_id", "log_channel_id", "panel_title", "panel_description", "panel_color", "panel_style",
    "max_open", "cooldown", "auto_close_hours", "archive_minutes", "name_template", "welcome_message",
    "maintenance_message",
]
INT_KEYS = {"staff_role_id", "log_channel_id", "max_open", "cooldown", "auto_close_hours", "archive_minutes"}
CHECK_KEYS = ["private_threads", "transcript_dm", "maintenance"]


def create_app(bot):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=Config.SECRET_KEY, same_site="strict", max_age=60 * 60 * 12)
    app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

    templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))
    env = templates.env
    env.globals.update(E=Emojis, PRIORITY_EMOJI=PRIORITY_EMOJI, THREAD_STATUS=THREAD_STATUS, prefix=lambda: Config.PREFIX)
    env.filters["dt"] = lambda ts: datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M") if ts else "—"

    def uname(uid):
        u = bot.get_user(uid)
        return f"{u.name}" if u else str(uid)

    env.globals["uname"] = uname
    env.globals["jump"] = lambda tid: f"https://discord.com/channels/{Config.GUILD_ID}/{tid}"

    db = lambda: bot.db  # noqa: E731

    # ───────── helpers ─────────
    async def auth(request: Request):
        if not request.session.get("ok"):
            raise HTTPException(status_code=303, headers={"Location": "/login"})

    async def csrf(request: Request):
        form = await request.form()
        if not secrets.compare_digest(str(form.get("csrf", "")), request.session.get("csrf", "")):
            raise HTTPException(status_code=403, detail="Bad CSRF token. Reload the page.")

    def flash(request, msg, bad=False):
        request.session["flash"] = {"msg": msg, "bad": bad}

    def render(request, name, **ctx):
        g = bot.get_guild(Config.GUILD_ID)
        ctx.update(
            flash=request.session.pop("flash", None), csrf=request.session.get("csrf", ""),
            path=request.url.path, guild=g, ready=bot.is_ready())
        return templates.TemplateResponse(request, name, ctx)

    def back(request, url):
        return RedirectResponse(url, status_code=303)

    def guild_lists():
        g = bot.get_guild(Config.GUILD_ID)
        if not g:
            return [], []
        return ([{"id": c.id, "name": c.name} for c in g.text_channels],
                [{"id": r.id, "name": r.name} for r in reversed(g.roles) if not r.is_default()])

    # ───────── login ─────────
    @app.get("/login")
    async def login_page(request: Request):
        return render(request, "login.html")

    @app.post("/login")
    async def login(request: Request):
        form = await request.form()
        if secrets.compare_digest(str(form.get("password", "")), Config.DASHBOARD_PASSWORD):
            request.session.clear()
            request.session.update(ok=True, csrf=secrets.token_urlsafe(24))
            return back(request, "/")
        flash(request, "Wrong password.", True)
        return back(request, "/login")

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return back(request, "/login")

    # ───────── overview ─────────
    @app.get("/", dependencies=[Depends(auth)])
    async def overview(request: Request):
        return render(request, "overview.html", stats=await db().stats(),
                      recent=await db().list_tickets(None, 8),
                      latency=round(bot.latency * 1000) if bot.is_ready() else None)

    # ───────── settings + panel ─────────
    @app.get("/settings", dependencies=[Depends(auth)])
    async def settings_page(request: Request):
        channels, roles = guild_lists()
        return render(request, "settings.html", s=db().settings, channels=channels, roles=roles)

    @app.post("/settings", dependencies=[Depends(auth), Depends(csrf)])
    async def settings_save(request: Request):
        form = await request.form()
        for k in TEXT_KEYS:
            if k in form:
                v = str(form[k]).strip()
                if k in INT_KEYS and not v.isdigit():
                    continue
                await db().set(k, v)
        for k in CHECK_KEYS:
            await db().set(k, "1" if form.get(k) else "0")
        flash(request, "Settings saved.")
        return back(request, "/settings")

    @app.post("/panel/send", dependencies=[Depends(auth), Depends(csrf)])
    async def panel_send(request: Request):
        form = await request.form()
        g = bot.get_guild(Config.GUILD_ID)
        ch = g.get_channel(int(form.get("channel_id") or 0)) if g else None
        if not isinstance(ch, discord.TextChannel):
            flash(request, "Pick a text channel first.", True)
        else:
            try:
                await bot.tickets.send_panel(ch)
                flash(request, f"Panel sent to #{ch.name}.")
            except discord.HTTPException as ex:
                flash(request, f"Discord refused: {ex.text}", True)
        return back(request, "/settings")

    @app.post("/panel/update", dependencies=[Depends(auth), Depends(csrf)])
    async def panel_update(request: Request):
        try:
            await bot.tickets.update_panel()
            flash(request, "Panel updated in Discord.")
        except (RuntimeError, discord.HTTPException) as ex:
            flash(request, str(ex), True)
        return back(request, "/settings")

    # ───────── categories ─────────
    @app.get("/categories", dependencies=[Depends(auth)])
    async def categories(request: Request):
        _, roles = guild_lists()
        return render(request, "categories.html", cats=await db().categories(), roles=roles)

    @app.post("/categories/add", dependencies=[Depends(auth), Depends(csrf)])
    async def cat_add(request: Request):
        f = await request.form()
        name = str(f.get("name", "")).strip()
        if name:
            await db().add_category(name[:80], str(f.get("description", ""))[:100], str(f.get("emoji", "")).strip(),
                                    int(f.get("role_id") or 0), int(f.get("position") or 0))
            flash(request, f"Added “{name}”. Use Update panel to show it in Discord.")
        return back(request, "/categories")

    @app.post("/categories/{cid}/save", dependencies=[Depends(auth), Depends(csrf)])
    async def cat_save(request: Request, cid: int):
        f = await request.form()
        await db().update_category(
            cid, str(f.get("name", "")).strip()[:80] or "Untitled", str(f.get("description", ""))[:100],
            str(f.get("emoji", "")).strip(), int(f.get("role_id") or 0), 1 if f.get("enabled") else 0,
            int(f.get("position") or 0))
        flash(request, "Category saved. Use Update panel to refresh Discord.")
        return back(request, "/categories")

    @app.post("/categories/{cid}/delete", dependencies=[Depends(auth), Depends(csrf)])
    async def cat_delete(request: Request, cid: int):
        await db().delete_category(cid)
        flash(request, "Category deleted.")
        return back(request, "/categories")

    # ───────── tickets ─────────
    @app.get("/tickets", dependencies=[Depends(auth)])
    async def tickets(request: Request, status: str = "open"):
        return render(request, "tickets.html", rows=await db().list_tickets(status, 200), status=status)

    @app.post("/tickets/{tid}/close", dependencies=[Depends(auth), Depends(csrf)])
    async def ticket_close(request: Request, tid: int):
        t = await db().ticket(tid)
        if t and await bot.tickets.close_ticket(t, 0, "Closed from the dashboard"):
            flash(request, f"Ticket #{tid:04d} closed.")
        return back(request, "/tickets?status=open")

    @app.post("/tickets/{tid}/reopen", dependencies=[Depends(auth), Depends(csrf)])
    async def ticket_reopen(request: Request, tid: int):
        t = await db().ticket(tid)
        if t and await bot.tickets.reopen_ticket(t, 0):
            flash(request, f"Ticket #{tid:04d} reopened.")
        return back(request, "/tickets?status=closed")

    @app.get("/transcripts/{tid}", dependencies=[Depends(auth)])
    async def transcript(tid: int):
        path = os.path.join(Config.TRANSCRIPT_DIR, f"{tid}.html")
        if not os.path.exists(path):
            raise HTTPException(404, "No transcript saved for this ticket yet.")
        return FileResponse(path, media_type="text/html")

    # ───────── blacklist ─────────
    @app.get("/blacklist", dependencies=[Depends(auth)])
    async def blacklist(request: Request):
        return render(request, "blacklist.html", rows=await db().blacklist())

    @app.post("/blacklist/add", dependencies=[Depends(auth), Depends(csrf)])
    async def bl_add(request: Request):
        f = await request.form()
        uid = str(f.get("user_id", "")).strip()
        if uid.isdigit():
            await db().add_blacklist(int(uid), str(f.get("reason", "")) or "No reason", 0)
            flash(request, "User blacklisted.")
        else:
            flash(request, "Enter a numeric Discord user ID.", True)
        return back(request, "/blacklist")

    @app.post("/blacklist/{uid}/remove", dependencies=[Depends(auth), Depends(csrf)])
    async def bl_remove(request: Request, uid: int):
        await db().remove_blacklist(uid)
        return back(request, "/blacklist")

    return app
