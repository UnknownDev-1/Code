import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

def _chunk_lines(lines: list[str], max_chars: int = 4096) -> list[str]:
    chunks: list[str] = []
    cur = []
    cur_len = 0
    for line in lines:
        l = line if line.endswith("\n") else line + "\n"
        if cur_len + len(l) > max_chars:
            chunks.append("".join(cur).rstrip("\n"))
            cur = [l]
            cur_len = len(l)
        else:
            cur.append(l)
            cur_len += len(l)
    if cur:
        chunks.append("".join(cur).rstrip("\n"))
    return chunks

class ListUtilities(commands.Cog):
    """Listing utilities for roles, emojis, bans, members, and bots."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    class ListGroup(app_commands.Group):
        def __init__(self):
            super().__init__(name="list", description="Listing utilities")
            self.guild_only = True

        @app_commands.command(name="roles", description="List all roles in the server.")
        @app_commands.guild_only()
        async def roles(self, interaction: discord.Interaction):
            if not interaction.guild:
                return  # Just skip sending error, keep the check

            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Missing Permission",
                    description="You need Administrator permission to use this command.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            roles = [r for r in interaction.guild.roles if r.id != interaction.guild.id]
            if not roles:
                embed = discord.Embed(
                    title=f"Server Roles (0)",
                    description="No roles found.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                return await interaction.response.send_message(embed=embed)

            lines = [r.mention for r in sorted(roles, key=lambda r: r.position, reverse=True)]
            chunks = _chunk_lines(lines)
            total = len(roles)

            for idx, chunk in enumerate(chunks, start=1):
                title = f"Server Roles ({total})"
                embed = discord.Embed(
                    title=title,
                    description=chunk,
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                if idx == 1:
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)

        @app_commands.command(name="emojis", description="List all emojis in the server.")
        @app_commands.guild_only()
        async def emojis(self, interaction: discord.Interaction):
            if not interaction.guild:
                return

            emojis = interaction.guild.emojis
            if not emojis:
                embed = discord.Embed(
                    title="Server Emojis (0)",
                    description="No emojis found.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                return await interaction.response.send_message(embed=embed)

            lines = [str(e) for e in emojis]
            chunks = _chunk_lines(lines)
            total = len(emojis)

            for idx, chunk in enumerate(chunks, start=1):
                title = f"Server Emojis ({total})"
                embed = discord.Embed(
                    title=title,
                    description=chunk,
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                if idx == 1:
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)

        @app_commands.command(name="bans", description="List all banned members in the server.")
        @app_commands.guild_only()
        async def bans(self, interaction: discord.Interaction):
            if not interaction.guild:
                return

            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Missing Permission",
                    description="You need Administrator permission to use this command.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            bans = [ban async for ban in interaction.guild.bans()]
            if not bans:
                embed = discord.Embed(
                    title="Banned Members (0)",
                    description="No banned members found.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                return await interaction.response.send_message(embed=embed)

            lines = []
            seen = {}
            for entry in bans:
                user = entry.user
                tag = f"{user.name}#{user.discriminator}"
                if tag in seen:
                    lines.append(f"{tag} ({user.id})")
                else:
                    lines.append(tag)
                    seen[tag] = True

            chunks = _chunk_lines(lines)
            total = len(bans)

            for idx, chunk in enumerate(chunks, start=1):
                title = f"Banned Members ({total})"
                embed = discord.Embed(
                    title=title,
                    description=chunk,
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                if idx == 1:
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)

        @app_commands.command(name="inrole", description="List all members in a specific role.")
        @app_commands.guild_only()
        @app_commands.describe(role="Select a role")
        async def inrole(self, interaction: discord.Interaction, role: discord.Role):
            if not interaction.guild:
                return

            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Missing Permission",
                    description="You need Administrator permission to use this command.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            members = role.members
            if not members:
                embed = discord.Embed(
                    title=f"Members in Role: {role.name} (0)",
                    description="No members with that role.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                return await interaction.response.send_message(embed=embed)

            lines = [m.mention for m in members]
            chunks = _chunk_lines(lines)
            total = len(members)

            for idx, chunk in enumerate(chunks, start=1):
                title = f"Members in Role: {role.name} ({total})"
                embed = discord.Embed(
                    title=title,
                    description=chunk,
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                if idx == 1:
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)

        @app_commands.command(name="bots", description="List all bots in the server.")
        @app_commands.guild_only()
        async def bots(self, interaction: discord.Interaction):
            if not interaction.guild:
                return

            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Missing Permission",
                    description="You need Administrator permission to use this command.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            bots = [m for m in interaction.guild.members if m.bot]
            if not bots:
                embed = discord.Embed(
                    title="Server Bots (0)",
                    description="No bots found.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                return await interaction.response.send_message(embed=embed)

            lines = [b.mention for b in bots]
            chunks = _chunk_lines(lines)
            total = len(bots)

            for idx, chunk in enumerate(chunks, start=1):
                title = f"Server Bots ({total})"
                embed = discord.Embed(
                    title=title,
                    description=chunk,
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                if idx == 1:
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)

    async def cog_load(self):
        self.bot.tree.add_command(self.ListGroup())

async def setup(bot: commands.Bot):
    await bot.add_cog(ListUtilities(bot))