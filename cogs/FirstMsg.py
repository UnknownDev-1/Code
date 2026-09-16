import discord
from discord import app_commands
from discord.ext import commands

COLOR = 0xFFD700
COLOR_ERROR = 0xED4245


class FirstMessage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="firstmessage", aliases=["firstmsg"])
    async def prefix_firstmessage(self, ctx: commands.Context, channel: discord.TextChannel = None):
        await self._firstmessage(ctx, channel or ctx.channel, slash=False)

    @app_commands.command(name="firstmessage", description="Jump to the first message ever sent in a channel")
    @app_commands.describe(channel="Channel to check (default: this channel)")
    async def slash_firstmessage(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        await self._firstmessage(interaction, channel or interaction.channel, slash=True)

    async def _firstmessage(self, ctx, target_channel: discord.TextChannel, slash: bool):
        try:
            history = [msg async for msg in target_channel.history(
                after=discord.Object(id=target_channel.id), limit=1, oldest_first=True
            )]
        except discord.Forbidden:
            embed = discord.Embed(description=f"I don't have permission to read {target_channel.mention}.", color=COLOR_ERROR)
            if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
            else: await ctx.reply(embed=embed, mention_author=False)
            return
        except discord.HTTPException:
            embed = discord.Embed(description="Something went wrong fetching that channel's history.", color=COLOR_ERROR)
            if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
            else: await ctx.reply(embed=embed, mention_author=False)
            return

        if not history:
            embed = discord.Embed(description=f"{target_channel.mention} has no messages.", color=COLOR_ERROR)
            if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
            else: await ctx.reply(embed=embed, mention_author=False)
            return

        first = history[0]
        content = first.content if first.content else "*No text content (embed, attachment, or system message)*"
        if len(content) > 500:
            content = content[:500] + "..."

        embed = discord.Embed(
            title=f"First Message in #{target_channel.name}",
            description=content,
            color=COLOR
        )
        embed.set_author(name=str(first.author), icon_url=first.author.display_avatar.url)
        embed.add_field(name="Jump To Message", value=f"[Click here]({first.jump_url})", inline=False)
        embed.timestamp = first.created_at

        req = ctx.author if not slash else ctx.user
        embed.set_footer(text=f"Requested by {req.name}")

        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(FirstMessage(bot))
    