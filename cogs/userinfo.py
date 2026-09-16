import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timezone

DATA_FILE = "last_seen.json"

KEY_PERMISSIONS_MAP = {
    "manage_guild": "Manage Server",
    "manage_roles": "Manage Roles",
    "manage_channels": "Manage Channels",
    "manage_messages": "Manage Messages",
    "manage_webhooks": "Manage Webhooks",
    "manage_nicknames": "Manage Nicknames",
    "manage_emojis_and_stickers": "Manage Emojis and Stickers",
    "kick_members": "Kick Members",
    "ban_members": "Ban Members",
    "mention_everyone": "Mention Everyone",
    "moderate_members": "Timeout Members"
}


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


class UserInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        data = load_data()
        gd = data.setdefault(str(message.guild.id), {})
        gd[str(message.author.id)] = datetime.now(timezone.utc).isoformat()
        save_data(data)

    async def resolve_target(self, ctx: commands.Context, raw: str):
        try:
            return await commands.MemberConverter().convert(ctx, raw)
        except commands.BadArgument:
            pass

        cleaned = raw.strip("<@!>")
        if cleaned.isdigit():
            try:
                return await self.bot.fetch_user(int(cleaned))
            except discord.NotFound:
                pass

        try:
            return await commands.UserConverter().convert(ctx, raw)
        except commands.BadArgument:
            pass

        return None

    def format_permissions(self, member: discord.Member) -> str:
        if member.guild_permissions.administrator:
            return "Administrator\n    [All Permissions]"

        granted = [label for perm, label in KEY_PERMISSIONS_MAP.items() if getattr(member.guild_permissions, perm, False)]
        if not granted:
            return "No Key Permissions"
        return "\n".join(f"- {p}" for p in granted)

    @commands.command(name="userinfo", aliases=["ui", "whois"])
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, *, target: str = None):
        if target is None:
            target_obj = ctx.author
        else:
            target_obj = await self.resolve_target(ctx, target)

        if target_obj is None:
            embed = discord.Embed(description=f"Couldn't find a user matching `{target}`.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        is_member = isinstance(target_obj, discord.Member)

        embed = discord.Embed(
            title=f"@{target_obj.name}'s User Information",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=target_obj.display_avatar.url)

        general_lines = [
            f"- ID: `{target_obj.id}`",
            f"- Username: `@{target_obj.name}`",
            f"- Display Name: `{target_obj.display_name}`"
        ]
        if is_member and target_obj.nick:
            general_lines.append(f"  - Nick Name: `{target_obj.nick}`")
        general_lines.append(f"- Mention: {target_obj.mention}")
        embed.add_field(name="**__General:__**", value="\n".join(general_lines), inline=False)

        created_ts = int(target_obj.created_at.timestamp())
        embed.add_field(
            name="**__Created At:__**",
            value=f"- Date: <t:{created_ts}:D>\n- Relative: <t:{created_ts}:R>",
            inline=False
        )

        if is_member:
            joined_ts = int(target_obj.joined_at.timestamp())
            embed.add_field(
                name="**__Joined At:__**",
                value=f"- Date: <t:{joined_ts}:D>\n- Relative: <t:{joined_ts}:R>",
                inline=False
            )

            roles = sorted((r for r in target_obj.roles if r.name != "@everyone"), key=lambda r: r.position, reverse=True)
            roles_text = "\n".join(f"- {r.mention}" for r in roles) if roles else "No roles"
            embed.add_field(name=f"**__Roles [{len(roles)}]:__**", value=roles_text[:1024], inline=False)

            data = load_data()
            last_seen = data.get(str(ctx.guild.id), {}).get(str(target_obj.id))
            if last_seen:
                last_ts = int(datetime.fromisoformat(last_seen).timestamp())
                activity_value = f"- Last Seen: <t:{last_ts}:R>\n- Last Message: <t:{last_ts}:R>"
            else:
                activity_value = "- Last Seen: No data yet\n- Last Message: No data yet"
            embed.add_field(name="**__Latest Activity:__**", value=activity_value, inline=False)

            embed.add_field(name="**__Key Permissions:__**", value=self.format_permissions(target_obj), inline=False)

        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)

        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserInfo(bot))