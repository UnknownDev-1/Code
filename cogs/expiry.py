import discord
from discord import app_commands
from discord.ext import commands
import re
from datetime import datetime, timezone, timedelta


class Expiry(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def parse_duration(self, raw: str):
        raw = raw.strip().lower()
        if raw.isdigit():
            return int(raw), "d"

        match = re.fullmatch(r"(\d+)\s*(d|w|mo|y)", raw)
        if not match:
            return None, None

        amount = int(match.group(1))
        unit = match.group(2)
        return amount, unit

    def calculate_days(self, amount: int, unit: str) -> int:
        if unit == "d":
            return amount
        if unit == "w":
            return amount * 7
        if unit == "mo":
            return amount * 30
        if unit == "y":
            return amount * 365
        return amount

    @commands.command(name="expiry", aliases=["expires", "exp"])
    async def prefix_expiry(self, ctx: commands.Context, *, duration: str):
        await self._expiry(ctx, duration, slash=False)

    @app_commands.command(name="expiry", description="Calculate an expiration date from a duration (e.g. 24d, 1mo, 3mo, 1y)")
    @app_commands.describe(duration="Duration like 24d, 1w, 3mo, 1y")
    async def slash_expiry(self, interaction: discord.Interaction, duration: str):
        await self._expiry(interaction, duration, slash=True)

    async def _expiry(self, ctx, duration: str, slash: bool):
        amount, unit = self.parse_duration(duration)

        if amount is None:
            embed = discord.Embed(
                description="<:NX_Error:1526717414522490950> Invalid duration. Use formats like `24d`, `1w`, `3mo`, `1y`, or just a number of days like `24`.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            if slash:
                await ctx.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx.reply(embed=embed, mention_author=False)
            return

        total_days = self.calculate_days(amount, unit)
        start = datetime.now(timezone.utc)
        expiry = start + timedelta(days=total_days)

        unit_labels = {"d": "day(s)", "w": "week(s)", "mo": "month(s)", "y": "year(s)"}
        duration_text = f"{amount} {unit_labels.get(unit, 'day(s)')}"

        embed = discord.Embed(
            title="Expiration Calculator",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Duration", value=f"{duration_text} ({total_days} days total)", inline=False)
        embed.add_field(name="Start Date", value=f"<t:{int(start.timestamp())}:F>", inline=False)
        embed.add_field(name="Expires On", value=f"<t:{int(expiry.timestamp())}:F>\n<t:{int(expiry.timestamp())}:R>", inline=False)

        if slash:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Expiry(bot))
    