import asyncio
import os
import re

import discord
from dotenv import load_dotenv

from src.logger import get_logger
from src.agent import Agent

load_dotenv()

log = get_logger("main")

intents = discord.Intents.all()

bot = discord.Client(intents=intents)
agent = Agent()

_mention_re: re.Pattern | None = None

# One lock per user — back-to-back messages queue instead of firing in parallel
_user_locks: dict[int, asyncio.Lock] = {}

# Per-user conversation history for multi-turn flows (e.g. pizza ordering)
# Capped at 40 messages to avoid context overflow
_user_histories: dict[int, list[dict]] = {}
_MAX_HISTORY = 40


@bot.event
async def on_error(event: str, *_args, **_kwargs):
    log.exception("Unhandled exception in event: %s", event)


@bot.event
async def on_ready():
    global _mention_re
    _mention_re = re.compile(rf"<@!?{bot.user.id}>")
    log.info("=== Bot online: %s (id: %s) ===", bot.user, bot.user.id)
    log.info("Mention pattern: %s", _mention_re.pattern)


@bot.event
async def on_message(message: discord.Message):
    # Log every single message so we can see if events fire at all
    log.debug(
        "RAW MESSAGE | author=%s bot=%s | guild=%s | channel=%s | content=%r",
        message.author,
        message.author.bot,
        getattr(message.guild, "name", "DM"),
        message.channel,
        message.content,
    )

    # Simple ping — no mention needed, confirms the bot receives messages
    if message.content.strip() == "!ping":
        log.info("!ping received from %s", message.author)
        await message.reply("pong")
        return

    if message.author.bot:
        log.debug("Ignoring bot message from %s", message.author)
        return

    # Check direct user mention OR a role mention that belongs to the bot
    direct_mention = _mention_re is not None and _mention_re.search(message.content)

    role_mention = False
    if message.guild and not direct_mention:
        bot_member = message.guild.get_member(bot.user.id)
        if bot_member:
            bot_role_ids = {r.id for r in bot_member.roles}
            role_mention = any(r.id in bot_role_ids for r in message.role_mentions)

    if not direct_mention and not role_mention:
        log.debug("Not mentioned — skipping (content=%r)", message.content)
        return

    # Strip both the user mention and any bot-role mentions from content
    content = message.content
    if _mention_re:
        content = _mention_re.sub("", content)
    if role_mention and message.guild:
        bot_member = message.guild.get_member(bot.user.id)
        if bot_member:
            bot_role_ids = {r.id for r in bot_member.roles}
            for role in message.role_mentions:
                if role.id in bot_role_ids:
                    content = content.replace(f"<@&{role.id}>", "")
    content = content.strip()
    log.info(
        "Mention received | from=%s | guild=%s | channel=%s | content=%r",
        message.author,
        getattr(message.guild, "name", "DM"),
        message.channel,
        content,
    )

    if not content:
        await message.reply("Hey! Ask me anything.")
        return

    uid = message.author.id
    lock = _user_locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        log.info("Queuing message from %s — previous request still running", message.author)

    async with lock, message.channel.typing():
        history = _user_histories.get(uid, [])
        try:
            response, updated_history = await agent.run(user_message=content, history=history)
            _user_histories[uid] = updated_history[-_MAX_HISTORY:]
        except Exception:
            log.exception("Agent crashed on message: %r", content)
            response = "Something went wrong — check the logs."

    log.info("Reply to %s | length=%d", message.author, len(response))

    if len(response) <= 2000:
        await message.reply(response)
    else:
        chunks = [response[i : i + 2000] for i in range(0, len(response), 2000)]
        for chunk in chunks:
            await message.channel.send(chunk)


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in .env")
    log.info("Starting bot...")
    bot.run(token)
