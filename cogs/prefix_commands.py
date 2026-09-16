import discord
from discord.ext import commands
import asyncio
import re
from datetime import datetime, timezone


class PrefixCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def parse_time(self, t: str):
        m = re.fullmatch(r"(\d+)(s|m|h)", t.lower())
        if not m:
            return None
        n = int(m.group(1))
        u = m.group(2)
        if u == "s":
            return n
        if u == "m":
            return n * 60
        if u == "h":
            return n * 3600

    @commands.command(name="ping")
    @commands.guild_only()
    async def ping(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: `{round(self.bot.latency * 1000)}ms`",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.send(embed=embed)

    @commands.command(name="timer")
    @commands.guild_only()
    async def timer(self, ctx: commands.Context, time: str, *, name: str = None):
        seconds = self.parse_time(time)
        if seconds is None:
            embed = discord.Embed(
                title="❌ Invalid Format",
                description="Use format like `10s`, `5m`, `1h`.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            return await ctx.send(embed=embed)

        timer_name = name if name else "Timer"
        end_ts = int(datetime.now(timezone.utc).timestamp() + seconds)

        embed = discord.Embed(
            title=f"⏳ {timer_name}",
            description=f"Ending <t:{end_ts}:R>",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_author(
            name=ctx.guild.name,
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )

        msg = await ctx.send(embed=embed)

        await asyncio.sleep(seconds)

        end_embed = discord.Embed(
            title=f"⏰ {timer_name}",
            description=f"Timer ended <t:{end_ts}:R>",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )

        end_embed.set_author(
            name=ctx.guild.name,
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )

        try:
            await msg.edit(embed=end_embed)
        except:
            try:
                await msg.channel.send(embed=end_embed)
            except:
                pass

    @commands.command(name="nuke")
    @commands.guild_only()
    async def nuke(self, ctx: commands.Context, channel: discord.TextChannel = None):

        target = channel or ctx.channel

        if not isinstance(target, discord.TextChannel):
            embed = discord.Embed(
                title="❌ Error",
                description="Target must be a text channel.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            return await ctx.send(embed=embed)

        if not ctx.author.guild_permissions.manage_channels:
            embed = discord.Embed(
                title="❌ Missing Permission",
                description="You need the Manage Channels permission to nuke channels.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            return await ctx.send(embed=embed)

        if not ctx.guild.me.guild_permissions.manage_channels:
            embed = discord.Embed(
                title="❌ Error",
                description="I need the Manage Channels permission to nuke channels.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            return await ctx.send(embed=embed)

        class ConfirmView(discord.ui.View):
            def __init__(self, author_id: int, target_channel: discord.TextChannel):
                super().__init__(timeout=60)
                self.author_id = author_id
                self.target_channel = target_channel

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != self.author_id:
                    embed_block = discord.Embed(
                        title="❌ Error",
                        description="Only the command executor can use these buttons.",
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    await interaction.response.send_message(embed=embed_block, ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="Confirm Nuke", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                try:
                    old = self.target_channel
                    pos = old.position
                    cat = old.category

                    new = await old.clone(name=old.name)

                    if cat:
                        await new.edit(category=cat, position=pos)
                    else:
                        await new.edit(position=pos)

                    embed_done = discord.Embed(
                        title="✅ Channel Nuked",
                        description=f"Nuked and recreated {new.mention}",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )

                    await interaction.response.edit_message(embed=embed_done, view=None)

                    await old.delete()

                    embed_notify = discord.Embed(
                        title="💥 Channel Nuked",
                        description=f"This channel was nuked by {interaction.user.mention}",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )

                    await new.send(embed=embed_notify)

                except Exception as e:
                    embed_fail = discord.Embed(
                        title="❌ Error",
                        description=f"Nuke failed.\n{e}",
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    await interaction.response.edit_message(embed=embed_fail, view=None)

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                embed_cancel = discord.Embed(
                    title="❌ Error",
                    description="Nuke cancelled.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                await interaction.response.edit_message(embed=embed_cancel, view=None)

        embed_confirm = discord.Embed(
            title="⚠️ Confirm Nuke",
            description=f"Are you sure you want to nuke {target.mention}? This will permanently delete all messages.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        view = ConfirmView(ctx.author.id, target)
        await ctx.send(embed=embed_confirm, view=view)

    @commands.command(name="purge")
    @commands.guild_only()
    async def purge(self, ctx: commands.Context, amount: int):
        if not ctx.author.guild_permissions.manage_messages:
            return

        if not ctx.guild.me.guild_permissions.manage_messages:
            return

        if amount <= 0 or amount > 100:
            return

        deleted = await ctx.channel.purge(limit=amount + 1)

        msg = await ctx.send(f"Deleted {len(deleted) - 1} messages.")
        await asyncio.sleep(3)
        await msg.delete()

    @commands.command(name="hide")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def hide(self, ctx):
        channel = ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.view_channel is False:
            embed = discord.Embed(description=f"Channel is already hidden")
            return await ctx.send(embed=embed)

        overwrite.view_channel = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(description=f"Channel has been hidden from @everyone")

        await ctx.send(embed=embed)

    @commands.command(name="unhide")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unhide(self, ctx):
        channel = ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.view_channel is True:
            embed = discord.Embed(description=f"Channel is already visible")
            return await ctx.send(embed=embed)

        overwrite.view_channel = True
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

        embed = discord.Embed(description=f"Channel is now visible to @everyone")

        await ctx.send(embed=embed)

    @commands.command(name="lock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        channel = ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.send_messages is False:
            embed = discord.Embed(description=f"Channel is already locked")
            return await ctx.send(embed=embed)

        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(description=f"Channel has been locked")
        await ctx.send(embed=embed)

    @commands.command(name="unlock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        channel = ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.send_messages is True:
            embed = discord.Embed(description=f"Chanel is already unlocked")
            return await ctx.send(embed=embed)

        overwrite.send_messages = True
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(description=f"Channel has been unlocked")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PrefixCommands(bot))