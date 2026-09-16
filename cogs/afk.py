import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import time

DATA_FILE = "afk_data.json"
NO_PING = discord.AllowedMentions.none()
MAX_PINGS_SHOWN = 25


class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = self.load_data()

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return {}

        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}

    def save_data(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.afk_users, f, indent=4)

    async def set_afk_logic(self, user: discord.User, reason: str):
        user_id = str(user.id)

        self.afk_users[user_id] = {
            "reason": reason,
            "since": int(time.time()),
            "pings": []
        }

        self.save_data()

        reason_text = reason if reason else "No Reason Provided!"

        embed = discord.Embed(
            title="<a:NX_Clock:1544867078354378803> AFK Status Set!",
            description=(
                f"**{user.mention}** you are now AFK.\n"
                f"<:NX_Arrow:1527406425469354054> **With a Reason:** {reason_text}"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )

        return embed

    @app_commands.command(name="afk", description="Set yourself as AFK")
    @app_commands.describe(reason="Reason for going AFK")
    async def afk_slash(self, interaction: discord.Interaction, reason: str = None):
        embed = await self.set_afk_logic(interaction.user, reason)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="afk")
    async def afk_prefix(self, ctx: commands.Context, *, reason: str = None):
        embed = await self.set_afk_logic(ctx.author, reason)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        ctx = await self.bot.get_context(message)
        if ctx.command:
            return

        user_id = str(message.author.id)

        if user_id in self.afk_users:
            data = self.afk_users[user_id]
            afk_since = data["since"]
            pings = data.get("pings", [])

            del self.afk_users[user_id]
            self.save_data()

            ping_count = len(pings)

            if ping_count == 0:
                description = f"You are not AFK anymore, you were AFK since <t:{afk_since}:R>."
            else:
                description = (
                    f"You are not AFK anymore, you were AFK since <t:{afk_since}:R> "
                    f"and you got {ping_count} ping{'s' if ping_count != 1 else ''}:\n"
                )
                lines = []
                for i, ping in enumerate(pings[:MAX_PINGS_SHOWN], 1):
                    lines.append(f"{i}. [Mention]({ping['message_link']}) from <@{ping['mentioner_id']}>")
                if ping_count > MAX_PINGS_SHOWN:
                    lines.append(f"...and {ping_count - MAX_PINGS_SHOWN} more.")
                description += "\n".join(lines)

            embed = discord.Embed(
                title="Welcome Back!",
                description=description,
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            await message.channel.send(embed=embed)

        for user in message.mentions:
            mentioned_id = str(user.id)

            if mentioned_id in self.afk_users:
                data = self.afk_users[mentioned_id]
                reason = data["reason"]
                reason_text = reason if reason else "No Reason Provided!"
                afk_since = data["since"]

                data.setdefault("pings", []).append({
                    "mentioner_id": str(message.author.id),
                    "message_link": message.jump_url
                })
                self.save_data()

                content = (
                    f"**{user.mention}** is currently AFK, **Since:** <t:{afk_since}:R> "
                    f"with **Reason:** {reason_text}"
                )

                await message.channel.send(content, allowed_mentions=NO_PING)


async def setup(bot):
    await bot.add_cog(AFK(bot))
