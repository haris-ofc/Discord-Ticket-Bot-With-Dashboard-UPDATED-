import re

import discord

from emojis import Emojis as E


def _embed(text, color):
    return discord.Embed(description=text, color=color)


def ok(text):
    return _embed(f"{E.SUCCESS} {text}", discord.Color.green())


def err(text):
    return _embed(f"{E.ERROR} {text}", discord.Color.red())


def info(text):
    return _embed(f"{E.INFO} {text}", discord.Color.blurple())


def slug(text, limit=20):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s or "x")[:limit]


def hex_color(value):
    try:
        return discord.Color(int(str(value).strip().lstrip("#"), 16))
    except ValueError:
        return discord.Color.blurple()
