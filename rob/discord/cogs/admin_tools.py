from __future__ import annotations

import re
from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from rob.discord.client import RobBot

_MENTION_RE = re.compile(r"<@!?(\d+)>")


def _parse_user_id(target: str) -> int | None:
    raw = target.strip()
    mention = _MENTION_RE.fullmatch(raw)
    if mention:
        raw = mention.group(1)
    if not raw.isdigit():
        return None
    return int(raw)


class AdminToolsCog(commands.Cog):
    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    def _can_manage(self, ctx: commands.Context) -> bool:
        author = ctx.author
        if not hasattr(author, "guild_permissions"):
            return False
        return bool(author.guild_permissions.manage_guild)

    @commands.command(name="rob-blacklist")
    async def rob_blacklist(self, ctx: commands.Context, target: str, *, reason: str = "manual") -> None:
        if ctx.guild is None or not self._can_manage(ctx):
            await ctx.reply("You do not have permission to use this command.")
            return
        discord_user_id = _parse_user_id(target)
        if discord_user_id is None:
            await ctx.reply("Usage: `!rob-blacklist <discord_user_id_or_mention> [reason]`")
            return
        await self.bot.blacklist_repo.add(
            discord_user_id=discord_user_id,
            reason=reason.strip() or "manual",
            created_by=ctx.author.id,
        )
        await ctx.reply(f"`{discord_user_id}` has been added to Rob's blacklist.")

    @commands.command(name="rob-unblacklist")
    async def rob_unblacklist(self, ctx: commands.Context, target: str) -> None:
        if ctx.guild is None or not self._can_manage(ctx):
            await ctx.reply("You do not have permission to use this command.")
            return
        discord_user_id = _parse_user_id(target)
        if discord_user_id is None:
            await ctx.reply("Usage: `!rob-unblacklist <discord_user_id_or_mention>`")
            return
        await self.bot.blacklist_repo.remove(discord_user_id=discord_user_id)
        await ctx.reply(f"`{discord_user_id}` has been removed from Rob's blacklist.")

    @commands.command(name="throne-blacklist")
    async def throne_blacklist(self, ctx: commands.Context, target: str) -> None:
        if ctx.guild is None or not self._can_manage(ctx):
            await ctx.reply("You do not have permission to use this command.")
            return
        discord_user_id = _parse_user_id(target)
        if discord_user_id is None:
            await ctx.reply("Usage: `!throne-blacklist <discord_user_id_or_mention>`")
            return

        removed_creator = await self.bot.throne_creators_repo.remove_by_user_id(ctx.guild.id, discord_user_id)
        await self.bot.dommes_repo.remove_by_user_id(ctx.guild.id, discord_user_id)
        await self.bot.blacklist_repo.add(
            discord_user_id=discord_user_id,
            reason="throne blacklist",
            created_by=ctx.author.id,
        )
        if removed_creator is None:
            await ctx.reply(
                f"No Throne registration found for `{discord_user_id}`. Added to global blacklist."
            )
            return
        await ctx.reply(
            f"Removed Throne creator `{removed_creator.throne_creator_id}` for `{discord_user_id}` and added to global blacklist."
        )
