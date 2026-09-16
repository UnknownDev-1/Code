import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import re

DATA_FILE = "autoresponses.json"


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_guild_data(data: dict, guild_id: str) -> dict:
    gd = data.setdefault(guild_id, {"responders": [], "reactors": []})
    gd.setdefault("responders", [])
    gd.setdefault("reactors", [])
    return gd


def matches_trigger(content: str, trigger: str, exact: bool) -> bool:
    if exact:
        return content.strip().lower() == trigger.strip().lower()
    pattern = r"(?<![A-Za-z0-9])" + re.escape(trigger) + r"(?![A-Za-z0-9])"
    return re.search(pattern, content, re.IGNORECASE) is not None


def parse_emojis(raw: str) -> list:
    tokens = re.split(r"[,\s]+", raw.strip())
    return [t for t in tokens if t]


class AutoResponse(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    responder_group = app_commands.Group(name="autoresponder", description="Manage automatic text responses")
    reactor_group = app_commands.Group(name="autoreact", description="Manage automatic emoji reactions")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        data = load_data()
        gd = get_guild_data(data, str(message.guild.id))

        for entry in gd["responders"]:
            if matches_trigger(message.content, entry["trigger"], entry.get("exact", False)):
                if re.search(r"<@!?\d+>", entry["trigger"]) and message.author.guild_permissions.administrator:
                    continue

                response = (
                    entry["response"]
                    .replace("{user}", message.author.mention)
                    .replace("{username}", message.author.name)
                    .replace("{server}", message.guild.name)
                )
                try:
                    await message.reply(response, mention_author=False)
                except Exception:
                    pass

                if entry.get("delete_trigger"):
                    try:
                        await message.delete()
                    except Exception:
                        pass
                break

        for entry in gd["reactors"]:
            if matches_trigger(message.content, entry["trigger"], entry.get("exact", False)):
                for emoji in entry["emojis"]:
                    try:
                        await message.add_reaction(emoji)
                    except Exception:
                        pass

    @responder_group.command(name="add", description="Add an automatic text response for a trigger word or phrase.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        trigger="Word or phrase that triggers the response",
        response="Text to reply with. Use {user}, {username}, {server} as placeholders",
        exact="Only trigger if the message is exactly this (default: contains anywhere)",
        delete_trigger="Delete the user's message after replying (default: off)"
    )
    async def slash_responder_add(self, interaction: discord.Interaction, trigger: str, response: str, exact: bool = False, delete_trigger: bool = False):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        gd["responders"].append({"trigger": trigger, "response": response, "exact": exact, "delete_trigger": delete_trigger})
        save_data(data)

        note = " Trigger messages will be deleted." if delete_trigger else ""
        embed = discord.Embed(
            description=f"Added autoresponder for `{trigger}`.{note}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @responder_group.command(name="remove", description="Remove an autoresponder by trigger.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(trigger="Trigger to remove")
    async def slash_responder_remove(self, interaction: discord.Interaction, trigger: str):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        match = next((e for e in gd["responders"] if e["trigger"].lower() == trigger.lower()), None)
        if not match:
            embed = discord.Embed(description=f"No autoresponder found for `{trigger}`.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        gd["responders"].remove(match)
        save_data(data)

        embed = discord.Embed(description=f"Removed autoresponder for `{trigger}`.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @responder_group.command(name="list", description="List all autoresponders.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_responder_list(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not gd["responders"]:
            embed = discord.Embed(description="No autoresponders set.", color=discord.Color.blurple())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        lines = []
        for e in gd["responders"]:
            mode = "exact" if e.get("exact") else "contains"
            delete_note = ", deletes trigger" if e.get("delete_trigger") else ""
            lines.append(f"`{e['trigger']}` ({mode}{delete_note}) -> {e['response'][:80]}")

        embed = discord.Embed(title="Autoresponders", description="\n".join(lines)[:4000], color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reactor_group.command(name="add", description="Add an automatic emoji reaction for a trigger word or phrase.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        trigger="Word or phrase that triggers the reaction",
        emojis="Emoji(s) to react with, space or comma separated",
        exact="Only trigger if the message is exactly this (default: contains anywhere)"
    )
    async def slash_reactor_add(self, interaction: discord.Interaction, trigger: str, emojis: str, exact: bool = False):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        emoji_list = parse_emojis(emojis)
        if not emoji_list:
            embed = discord.Embed(description="Provide at least one emoji.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        gd["reactors"].append({"trigger": trigger, "emojis": emoji_list, "exact": exact})
        save_data(data)

        embed = discord.Embed(
            description=f"Added autoreact for `{trigger}` with {' '.join(emoji_list)}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reactor_group.command(name="remove", description="Remove an autoreact by trigger.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(trigger="Trigger to remove")
    async def slash_reactor_remove(self, interaction: discord.Interaction, trigger: str):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        match = next((e for e in gd["reactors"] if e["trigger"].lower() == trigger.lower()), None)
        if not match:
            embed = discord.Embed(description=f"No autoreact found for `{trigger}`.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        gd["reactors"].remove(match)
        save_data(data)

        embed = discord.Embed(description=f"Removed autoreact for `{trigger}`.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reactor_group.command(name="list", description="List all autoreacts.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_reactor_list(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not gd["reactors"]:
            embed = discord.Embed(description="No autoreacts set.", color=discord.Color.blurple())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        lines = []
        for e in gd["reactors"]:
            mode = "exact" if e.get("exact") else "contains"
            lines.append(f"`{e['trigger']}` ({mode}) -> {' '.join(e['emojis'])}")

        embed = discord.Embed(title="Autoreacts", description="\n".join(lines)[:4000], color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.group(name="autoresponder", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_responder(self, ctx: commands.Context):
        if not ctx.author.guild_permissions.administrator:
            embed = discord.Embed(description="You need Administrator permission to use this.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not gd["responders"]:
            embed = discord.Embed(description="No autoresponders set.", color=discord.Color.blurple())
            await ctx.reply(embed=embed, mention_author=False)
            return

        lines = []
        for e in gd["responders"]:
            mode = "exact" if e.get("exact") else "contains"
            delete_note = ", deletes trigger" if e.get("delete_trigger") else ""
            lines.append(f"`{e['trigger']}` ({mode}{delete_note}) -> {e['response'][:80]}")

        embed = discord.Embed(title="Autoresponders", description="\n".join(lines)[:4000], color=discord.Color.blurple())
        await ctx.reply(embed=embed, mention_author=False)

    @prefix_responder.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def prefix_responder_add(self, ctx: commands.Context, trigger: str, *, response: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        delete_trigger = False
        cleaned = response.strip()
        if cleaned.lower().endswith("--delete"):
            delete_trigger = True
            cleaned = cleaned[:-len("--delete")].strip()

        if not cleaned:
            embed = discord.Embed(description="Provide a response, not just a flag.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        gd["responders"].append({"trigger": trigger, "response": cleaned, "exact": False, "delete_trigger": delete_trigger})
        save_data(data)

        note = " Trigger messages will be deleted." if delete_trigger else ""
        embed = discord.Embed(description=f"Added autoresponder for `{trigger}`.{note}", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)

    @prefix_responder.command(name="remove")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def prefix_responder_remove(self, ctx: commands.Context, *, trigger: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        match = next((e for e in gd["responders"] if e["trigger"].lower() == trigger.lower()), None)
        if not match:
            embed = discord.Embed(description=f"No autoresponder found for `{trigger}`.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        gd["responders"].remove(match)
        save_data(data)

        embed = discord.Embed(description=f"Removed autoresponder for `{trigger}`.", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)

    @commands.group(name="autoreact", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_reactor(self, ctx: commands.Context):
        if not ctx.author.guild_permissions.administrator:
            embed = discord.Embed(description="You need Administrator permission to use this.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not gd["reactors"]:
            embed = discord.Embed(description="No autoreacts set.", color=discord.Color.blurple())
            await ctx.reply(embed=embed, mention_author=False)
            return

        lines = []
        for e in gd["reactors"]:
            mode = "exact" if e.get("exact") else "contains"
            lines.append(f"`{e['trigger']}` ({mode}) -> {' '.join(e['emojis'])}")

        embed = discord.Embed(title="Autoreacts", description="\n".join(lines)[:4000], color=discord.Color.blurple())
        await ctx.reply(embed=embed, mention_author=False)

    @prefix_reactor.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def prefix_reactor_add(self, ctx: commands.Context, trigger: str, *, emojis: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        emoji_list = parse_emojis(emojis)
        if not emoji_list:
            embed = discord.Embed(description="Provide at least one emoji.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        gd["reactors"].append({"trigger": trigger, "emojis": emoji_list, "exact": False})
        save_data(data)

        embed = discord.Embed(description=f"Added autoreact for `{trigger}` with {' '.join(emoji_list)}.", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)

    @prefix_reactor.command(name="remove")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def prefix_reactor_remove(self, ctx: commands.Context, *, trigger: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        match = next((e for e in gd["reactors"] if e["trigger"].lower() == trigger.lower()), None)
        if not match:
            embed = discord.Embed(description=f"No autoreact found for `{trigger}`.", color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        gd["reactors"].remove(match)
        save_data(data)

        embed = discord.Embed(description=f"Removed autoreact for `{trigger}`.", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoResponse(bot))