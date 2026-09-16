import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timezone

DATA_FILE = "blacklist.json"

# Fill these in with your actual role IDs before use
TICKET_BLACKLIST_ROLE_ID = 1534969103339487292
CHAT_BLACKLIST_ROLE_ID = 1534968948485918841

# Roles allowed to use tbl/cbl/tunbl/cunbl, in addition to administrators
ALLOWED_ROLE_IDS = [1469259811186278597, 1485114830313754694, 1485114835543789701]


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_guild_data(data: dict, guild_id: str) -> dict:
    return data.setdefault(guild_id, {"log_channel": None})


def is_allowed(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.id in ALLOWED_ROLE_IDS for r in member.roles)


class Blacklist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _toggle_blacklist(self, ctx: commands.Context, member: discord.Member, reason: str, role_id: int, label: str, add: bool):
        if not is_allowed(ctx.author):
            embed = discord.Embed(description="You don't have permission to use this.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        role = ctx.guild.get_role(role_id)
        if role is None:
            embed = discord.Embed(description=f"The {label} blacklist role isn't configured correctly. Check the role ID in the cog.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        has_role = role in member.roles
        if add and has_role:
            embed = discord.Embed(description=f"{member.mention} is already {label} blacklisted.", color=discord.Color.blurple())
            await ctx.reply(embed=embed, mention_author=False)
            return
        if not add and not has_role:
            embed = discord.Embed(description=f"{member.mention} isn't {label} blacklisted.", color=discord.Color.blurple())
            await ctx.reply(embed=embed, mention_author=False)
            return

        try:
            if add:
                await member.add_roles(role, reason=f"{label.capitalize()} blacklisted by {ctx.author}")
            else:
                await member.remove_roles(role, reason=f"{label.capitalize()} unblacklisted by {ctx.author}")
        except discord.Forbidden:
            embed = discord.Embed(description="I don't have permission to manage that role, check role hierarchy.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        verb = "blacklisted" if add else "unblacklisted"
        confirm_embed = discord.Embed(
            description=f"{member.mention} has been {label} {verb}.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        if reason:
            confirm_embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.reply(embed=confirm_embed, mention_author=False)

        await self._log(ctx.guild, member, ctx.author, label, reason, add)

    async def _log(self, guild: discord.Guild, member: discord.Member, moderator: discord.Member, label: str, reason: str, add: bool):
        data = load_data()
        gd = get_guild_data(data, str(guild.id))
        channel_id = gd.get("log_channel")
        if not channel_id:
            return

        channel = guild.get_channel(int(channel_id))
        if channel is None:
            return

        action = "Added" if add else "Removed"
        embed = discord.Embed(
            title=f"{label.capitalize()} Blacklist {action}",
            color=discord.Color.orange() if add else discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="User ID", value=str(member.id), inline=False)
        embed.add_field(name="Blacklist Type", value=label.capitalize(), inline=False)
        embed.add_field(name="Moderator", value=moderator.mention, inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.command(name="tbl")
    @commands.guild_only()
    async def tbl(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        await self._toggle_blacklist(ctx, member, reason, TICKET_BLACKLIST_ROLE_ID, "ticket", add=True)

    @commands.command(name="tunbl")
    @commands.guild_only()
    async def tunbl(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        await self._toggle_blacklist(ctx, member, reason, TICKET_BLACKLIST_ROLE_ID, "ticket", add=False)

    @commands.command(name="cbl")
    @commands.guild_only()
    async def cbl(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        await self._toggle_blacklist(ctx, member, reason, CHAT_BLACKLIST_ROLE_ID, "chat", add=True)

    @commands.command(name="cunbl")
    @commands.guild_only()
    async def cunbl(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        await self._toggle_blacklist(ctx, member, reason, CHAT_BLACKLIST_ROLE_ID, "chat", add=False)

    @commands.command(name="blsetlog")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def blsetlog(self, ctx: commands.Context, channel: discord.TextChannel):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))
        gd["log_channel"] = str(channel.id)
        save_data(data)

        embed = discord.Embed(description=f"Blacklist logs will now be sent to {channel.mention}.", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Blacklist(bot))
    