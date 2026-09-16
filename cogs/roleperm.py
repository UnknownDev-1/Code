import discord
from discord.ext import commands
from datetime import datetime, timezone
from utils import make_paginator

CHANNELS_PER_PAGE = 5


def format_perm_name(name: str) -> str:
    return name.replace("_", " ").title()


class RolePerms(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="roleperm")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def roleperm(self, ctx: commands.Context, *, role: discord.Role):
        overall = [format_perm_name(name) for name, value in role.permissions if value]
        overall_text = ", ".join(overall) if overall else "None"

        channel_entries = []
        for channel in ctx.guild.channels:
            if role not in channel.overwrites:
                continue
            overwrite = channel.overwrites[role]
            allow, deny = overwrite.pair()
            allowed = [format_perm_name(n) for n, v in allow if v]
            denied = [format_perm_name(n) for n, v in deny if v]
            if allowed or denied:
                channel_entries.append((channel, allowed, denied))

        color = role.color if role.color.value != 0 else discord.Color.blurple()

        first_embed = discord.Embed(
            title=f"Role Permissions: {role.name}",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        first_embed.add_field(name="Role ID", value=str(role.id), inline=True)
        first_embed.add_field(name="Members With Role", value=str(len(role.members)), inline=True)
        first_embed.add_field(name="Overall Permissions (any channel)", value=overall_text[:1024], inline=False)

        pages = [first_embed]

        if not channel_entries:
            first_embed.add_field(name="Channel Specific Overwrites", value="None", inline=False)
        else:
            for i in range(0, len(channel_entries), CHANNELS_PER_PAGE):
                chunk = channel_entries[i:i + CHANNELS_PER_PAGE]
                embed = discord.Embed(
                    title=f"Role Permissions: {role.name} (Channel Overwrites)",
                    color=color,
                    timestamp=datetime.now(timezone.utc)
                )
                for channel, allowed, denied in chunk:
                    value_lines = []
                    if allowed:
                        value_lines.append(f"<a:NX_Check:1526717230396735598> Allowed: {', '.join(allowed)}")
                    if denied:
                        value_lines.append(f"<:NX_Error:1526717414522490950> Denied: {', '.join(denied)}")
                    embed.add_field(name=f"#{channel.name}", value="\n".join(value_lines)[:1024], inline=False)
                pages.append(embed)

        view = make_paginator(pages, ctx.author.id)
        await ctx.reply(embed=pages[0], view=view, mention_author=False)

    @roleperm.error
    async def roleperm_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.RoleNotFound):
            embed = discord.Embed(description=f"Couldn't find a role matching `{error.argument}`.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(description="You need Administrator permission to use this.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(RolePerms(bot))
    