import discord
from discord.ext import commands
import io
import chat_exporter
from datetime import datetime, timezone

MAX_FILE_SIZE = 24 * 1024 * 1024


async def resolve_target(ctx, raw: str):
    if not raw:
        return None, None

    try:
        member = await commands.MemberConverter().convert(ctx, raw)
        return "member", member
    except commands.BadArgument:
        pass

    try:
        channel = await commands.TextChannelConverter().convert(ctx, raw)
        return "channel", channel
    except commands.BadArgument:
        pass

    return None, None


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, author_id: int, channel: discord.TextChannel):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.channel = channel
        self.message = None
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This confirmation isn't yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            await self.channel.delete(reason=f"Deleted by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(description="I don't have permission to delete that channel.", color=discord.Color.red()),
                ephemeral=True
            )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(description="Deletion cancelled.", color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = discord.Embed(description="Confirmation timed out, channel was not deleted.", color=discord.Color.blurple())
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


class ChannelTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="transcript")
    @commands.has_permissions(administrator=True)
    async def transcript(self, ctx: commands.Context, target: str = None, limit: int = None):
        kind, resolved = await resolve_target(ctx, target)

        if target and kind is None:
            embed = discord.Embed(description=f"Couldn't find a user or channel matching `{target}`.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        status_embed = discord.Embed(description="Generating transcript, this may take a moment...", color=discord.Color.blurple())
        status_msg = await ctx.reply(embed=status_embed, mention_author=False)

        try:
            transcript_html = await chat_exporter.export(
                ctx.channel,
                limit=limit,
                bot=self.bot,
                tz_info="UTC",
                military_time=True
            )
        except Exception as e:
            embed = discord.Embed(description=f"Failed to generate transcript.\n`{e}`", color=discord.Color.red())
            await status_msg.edit(embed=embed)
            return

        if transcript_html is None:
            embed = discord.Embed(description="Failed to generate transcript.", color=discord.Color.red())
            await status_msg.edit(embed=embed)
            return

        encoded = transcript_html.encode()
        if len(encoded) > MAX_FILE_SIZE:
            embed = discord.Embed(
                description=(
                    f"The transcript is too large to send ({len(encoded) / 1024 / 1024:.1f} MB). "
                    f"Try again with a lower `limit` argument, e.g. `*transcript {target or ''} 2000`."
                ),
                color=discord.Color.red()
            )
            await status_msg.edit(embed=embed)
            return

        file = discord.File(io.BytesIO(encoded), filename=f"transcript-{ctx.channel.name}.html")

        result_embed = discord.Embed(
            description=f"Transcript of {ctx.channel.mention} generated.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )

        if kind == "member":
            try:
                await resolved.send(embed=result_embed, file=file)
            except discord.Forbidden:
                fail_embed = discord.Embed(description=f"Couldn't DM {resolved.mention}, their DMs may be closed.", color=discord.Color.red())
                await status_msg.edit(embed=fail_embed)
                return
        elif kind == "channel":
            await resolved.send(embed=result_embed, file=file)
        else:
            try:
                await ctx.author.send(embed=result_embed, file=file)
            except discord.Forbidden:
                fail_embed = discord.Embed(description="Couldn't DM you, your DMs may be closed.", color=discord.Color.red())
                await status_msg.edit(embed=fail_embed)
                return

        done_embed = discord.Embed(description="Transcript sent.", color=discord.Color.green())
        await status_msg.edit(embed=done_embed)

    @commands.command(name="rename")
    @commands.has_permissions(administrator=True)
    async def rename(self, ctx: commands.Context, channel: discord.TextChannel = None, *, name: str = None):
        if name is None and channel is not None:
            name = channel.name
            channel = None

        if not name:
            embed = discord.Embed(description="Provide a new name, e.g. `*rename new-name` or `*rename #channel new-name`.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        target = channel or ctx.channel
        old_name = target.name

        try:
            await target.edit(name=name, reason=f"Renamed by {ctx.author}")
        except discord.Forbidden:
            embed = discord.Embed(description="I don't have permission to rename that channel.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return
        except discord.HTTPException as e:
            embed = discord.Embed(description=f"Failed to rename channel.\n`{e}`", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        embed = discord.Embed(description=f"Renamed **#{old_name}** to {target.mention}.", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def delete(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel

        embed = discord.Embed(
            description=f"Are you sure you want to delete {target.mention}? This cannot be undone. This confirmation expires in 60 seconds.",
            color=discord.Color.orange()
        )
        view = ConfirmDeleteView(ctx.author.id, target)
        view.message = await ctx.reply(embed=embed, view=view, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelTools(bot))
    