import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from config.emojis import e
from config import storage
from utils import make_paginator, medal, YELLOW
import asyncio
import json
import os
import uuid


MESSAGE_ADDITIONS_FILE = "message_additions.json"


class Messages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.add_message_tasks = {}

    def _load_addition_logs(self):
        if not os.path.exists(MESSAGE_ADDITIONS_FILE):
            return {"entries": []}
        try:
            with open(MESSAGE_ADDITIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"entries": []}

    def _save_addition_logs(self, data):
        with open(MESSAGE_ADDITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _log_message_addition(self, guild_id, added_by, member_id, amount):
        data = self._load_addition_logs()
        entry_id = uuid.uuid4().hex
        entry = {
            "id": entry_id,
            "guild_id": str(guild_id),
            "added_by": str(added_by),
            "member": str(member_id),
            "amount": amount,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "removed_at": None,
            "removed": False
        }
        data.setdefault("entries", []).append(entry)
        self._save_addition_logs(data)
        return entry_id

    def _mark_message_addition_removed(self, entry_id):
        data = self._load_addition_logs()
        for entry in data.get("entries", []):
            if entry.get("id") == entry_id:
                entry["removed"] = True
                entry["removed_at"] = datetime.now(timezone.utc).isoformat()
                break
        self._save_addition_logs(data)

    async def _remove_added_messages(self, entry_id, guild_id, member_id, amount):
        try:
            await asyncio.sleep(60)

            data = storage.load()
            rec = storage.get_msg_record(data, str(guild_id), str(member_id))

            rec["count"] = max(0, rec["count"] - amount)

            storage.save(data)
            self._mark_message_addition_removed(entry_id)

        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            self.add_message_tasks.pop(entry_id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        data = storage.load()
        gid = str(message.guild.id)
        cid = str(message.channel.id)
        if storage.is_blacklisted(data, gid, cid):
            return
        uid = str(message.author.id)
        rec = storage.get_msg_record(data, gid, uid)
        rec["username"] = str(message.author)
        rec["count"] += 1
        tz_name = storage.get_guild_timezone(data, gid)
        today = storage.today(tz_name)
        week = storage.week_key(tz_name)
        rec["daily"][today] = rec["daily"].get(today, 0) + 1
        rec.setdefault("weekly", {})[week] = rec["weekly"].get(week, 0) + 1
        storage.save(data)

    @commands.command(name="messages", aliases=["m"])
    async def prefix_messages(self, ctx, member: discord.Member = None):
        await self._messages(ctx, member or ctx.author, slash=False)

    @app_commands.command(name="messages", description="Display message count of a member")
    @app_commands.describe(member="Member to check (default: you)")
    async def slash_messages(self, interaction, member: discord.Member = None):
        await self._messages(interaction, member or interaction.user, slash=True)

    async def _messages(self, ctx, target, slash):
        data = storage.load()
        rec = storage.get_msg_record(data, str(target.guild.id), str(target.id))
        tz_name = storage.get_guild_timezone(data, str(target.guild.id))
        today = storage.today(tz_name)
        week = storage.week_key(tz_name)
        req = ctx.author if not slash else ctx.user

        embed = discord.Embed(color=YELLOW)
        embed.set_author(name=f"{target.name}'s Messages", icon_url=target.display_avatar.url)
        embed.description = (
            f"**All time** {e('dot')} **{rec['count']}** messages in this server\n"
            f"**Weekly** {e('dot')} **{rec.get('weekly', {}).get(week, 0)}** messages in this server\n"
            f"**Today** {e('dot')} **{rec['daily'].get(today, 0)}** message in this server\n\n"
            f"*Messages are being updated in real-time*"
        )
        embed.set_footer(text=f"Requested by {req.name}")
        embed.timestamp = datetime.now(timezone.utc)
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="addmessages")
    @commands.has_permissions(manage_guild=True)
    async def prefix_addmessages(self, ctx, member: discord.Member, amount: int):
        await self._mod_messages(ctx, member, amount, slash=False, add=True)

    @app_commands.command(name="addmessages", description="Add messages to a user's count")
    @app_commands.describe(member="Target member", amount="Amount to add")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_addmessages(self, interaction, member: discord.Member, amount: int):
        await self._mod_messages(interaction, member, amount, slash=True, add=True)

    @commands.command(name="removemessages")
    @commands.has_permissions(manage_guild=True)
    async def prefix_removemessages(self, ctx, member: discord.Member, amount: int):
        await self._mod_messages(ctx, member, amount, slash=False, add=False)

    @app_commands.command(name="removemessages", description="Remove messages from a user's count")
    @app_commands.describe(member="Target member", amount="Amount to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_removemessages(self, interaction, member: discord.Member, amount: int):
        await self._mod_messages(interaction, member, amount, slash=True, add=False)

    async def _mod_messages(self, ctx, target, amount, slash, add):
        data = storage.load()
        rec = storage.get_msg_record(data, str(target.guild.id), str(target.id))
        if add:
            rec["count"] += amount
            tz_name = storage.get_guild_timezone(data, str(target.guild.id))
            today = storage.today(tz_name)
            rec["daily"][today] = rec["daily"].get(today, 0) + amount

            entry_id = self._log_message_addition(
                target.guild.id,
                ctx.author.id if not slash else ctx.user.id,
                target.id,
                amount
            )

            self.add_message_tasks[entry_id] = asyncio.create_task(
                self._remove_added_messages(
                    entry_id,
                    target.guild.id,
                    target.id,
                    amount
                )
            )
        else:
            rec["count"] = max(0, rec["count"] - amount)
        storage.save(data)
        emoji = e("add") if add else e("remove")
        verb = "Added" if add else "Removed"
        embed = discord.Embed(color=YELLOW)
        embed.description = (
            f"{emoji} {verb} **{amount}** message(s) {'to' if add else 'from'} {target.mention}\n"
            f"{e('dot')} New total: `{rec['count']}`"
        )
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="blacklistchannel")
    @commands.has_permissions(manage_guild=True)
    async def prefix_blacklistchannel(self, ctx, channel: discord.TextChannel = None):
        await self._blacklist(ctx, channel or ctx.channel, slash=False, add=True)

    @app_commands.command(name="blacklistchannel", description="Stop counting messages in a channel")
    @app_commands.describe(channel="Channel to blacklist (default: current)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_blacklistchannel(self, interaction, channel: discord.TextChannel = None):
        await self._blacklist(interaction, channel or interaction.channel, slash=True, add=True)

    @commands.command(name="unblacklistchannel")
    @commands.has_permissions(manage_guild=True)
    async def prefix_unblacklist(self, ctx, channel: discord.TextChannel = None):
        await self._blacklist(ctx, channel or ctx.channel, slash=False, add=False)

    @app_commands.command(name="unblacklistchannel", description="Re-enable message counting in a channel")
    @app_commands.describe(channel="Channel to unblacklist (default: current)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_unblacklist(self, interaction, channel: discord.TextChannel = None):
        await self._blacklist(interaction, channel or interaction.channel, slash=True, add=False)

    async def _blacklist(self, ctx, channel, slash, add):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        gid = str(guild.id)
        cid = str(channel.id)
        data.setdefault("blacklisted_channels", {}).setdefault(gid, [])
        bl = data["blacklisted_channels"][gid]

        if add:
            if cid in bl:
                desc = f"{e('warning')} {channel.mention} is already blacklisted."
            else:
                bl.append(cid)
                storage.save(data)
                desc = f"{e('blacklist')} {channel.mention} blacklisted. Messages there won't be counted."
        else:
            if cid not in bl:
                desc = f"{e('warning')} {channel.mention} isn't blacklisted."
            else:
                bl.remove(cid)
                storage.save(data)
                desc = f"{e('success')} {channel.mention} removed from blacklist."

        embed = discord.Embed(description=desc, color=YELLOW)
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="blacklistedchannels")
    @commands.has_permissions(manage_guild=True)
    async def prefix_blacklistedchannels(self, ctx):
        await self._blacklistedchannels(ctx, slash=False)

    @app_commands.command(name="blacklistedchannels", description="List all blacklisted channels")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_blacklistedchannels(self, interaction):
        await self._blacklistedchannels(interaction, slash=True)

    async def _blacklistedchannels(self, ctx, slash):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        bl = data.get("blacklisted_channels", {}).get(str(guild.id), [])
        embed = discord.Embed(title="Blacklisted Channels", color=YELLOW)
        embed.description = "\n".join(f"{e('arrow')} <#{cid}>" for cid in bl) if bl else f"{e('dot')} No channels blacklisted."
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="clearmessages")
    @commands.has_permissions(manage_guild=True)
    async def prefix_clearmessages(self, ctx, member: discord.Member = None):
        await self._clearmessages(ctx, member, slash=False)

    @app_commands.command(name="clearmessages", description="Clear message data of a member or entire guild")
    @app_commands.describe(member="Member to clear (empty = whole guild)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_clearmessages(self, interaction, member: discord.Member = None):
        await self._clearmessages(interaction, member, slash=True)

    async def _clearmessages(self, ctx, target, slash):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        gid = str(guild.id)
        if target:
            data["messages"].get(gid, {}).pop(str(target.id), None)
            desc = f"{e('clear')} Cleared message data for {target.mention}."
        else:
            data["messages"].pop(gid, None)
            desc = f"{e('clear')} Cleared **all** message data for this server."
        storage.save(data)
        embed = discord.Embed(description=desc, color=YELLOW)
        if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
        else: await ctx.send(embed=embed)

    @commands.command(name="resetmymessages", aliases=["rmm"])
    async def prefix_rmm(self, ctx):
        await self._rmm(ctx, slash=False)

    @app_commands.command(name="resetmymessages", description="Clear your own message data")
    async def slash_rmm(self, interaction):
        await self._rmm(interaction, slash=True)

    async def _rmm(self, ctx, slash):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        user = ctx.author if not slash else ctx.user
        data["messages"].get(str(guild.id), {}).pop(str(user.id), None)
        storage.save(data)
        embed = discord.Embed(description=f"{e('reset')} Your message data in **{guild.name}** has been cleared.", color=YELLOW)
        if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
        else: await ctx.send(embed=embed)

    @commands.command(name="topmessages")
    async def prefix_topmessages(self, ctx):
        await self._lb_messages(ctx, slash=False, daily=False)

    @commands.command(name="topdailymessages")
    async def prefix_topdailymessages(self, ctx):
        await self._lb_messages(ctx, slash=False, daily=True)

    @app_commands.command(name="topmessages", description="Top 10 all-time message senders")
    async def slash_topmessages(self, interaction):
        await self._lb_messages(interaction, slash=True, daily=False)

    @app_commands.command(name="topdailymessages", description="Top 10 daily message senders")
    async def slash_topdailymessages(self, interaction):
        await self._lb_messages(interaction, slash=True, daily=True)

    async def _lb_messages(self, ctx, slash, daily=False):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        gid = str(guild.id)
        raw = data["messages"].get(gid, {})
        tz_name = storage.get_guild_timezone(data, gid)
        today = storage.today(tz_name)
        req = ctx.author if not slash else ctx.user
        PER = 10

        title = "Messages Leaderboard"
        pages = []

        if not raw:
            embed = discord.Embed(title=title, color=YELLOW)
            embed.description = f"{e('dot')} No message data yet."
            embed.set_footer(text="Page 1/1")
            pages = [embed]
        else:
            if daily:
                top = sorted(raw.items(), key=lambda x: x[1]["daily"].get(today, 0), reverse=True)
                top = [(uid, rec) for uid, rec in top if rec["daily"].get(today, 0) > 0]
            else:
                top = sorted(raw.items(), key=lambda x: x[1]["count"], reverse=True)

            if not top:
                embed = discord.Embed(title=title, color=YELLOW)
                embed.description = f"{e('dot')} No data for today yet."
                embed.set_footer(text="Page 1/1")
                pages = [embed]
            else:
                chunks = [top[i:i+PER] for i in range(0, len(top), PER)]
                for pidx, chunk in enumerate(chunks):
                    embed = discord.Embed(title=title, color=YELLOW)
                    embed.description = "*The messages are being updated in real-time!*\n\n"
                    lines = []
                    for i, (uid, rec) in enumerate(chunk):
                        rank = pidx * PER + i
                        count = rec["daily"].get(today, 0) if daily else rec["count"]
                        m = guild.get_member(int(uid))
                        name = m.name if m else "Unknown"
                        lines.append(f"{medal(rank)} | **{name}** • **{count}** messages")
                    embed.description += "\n".join(lines)
                    embed.set_footer(text=f"Page {pidx+1}/{len(chunks)}")
                    pages.append(embed)

        view = make_paginator(pages, req.id)
        if slash: await ctx.response.send_message(embed=pages[0], view=view)
        else: await ctx.send(embed=pages[0], view=view)

    @commands.command(name="accage")
    async def prefix_accage(self, ctx, member: discord.Member = None):
        await self._accage(ctx, member or ctx.author, slash=False)

    @app_commands.command(name="accage", description="Show account age and creation date of a member")
    @app_commands.describe(member="Member to check (default: you)")
    async def slash_accage(self, interaction, member: discord.Member = None):
        await self._accage(interaction, member or interaction.user, slash=True)

    async def _accage(self, ctx, target, slash):
        req = ctx.author if not slash else ctx.user
        now = datetime.now(timezone.utc)
        created = target.created_at

        delta = now - created
        years, rem = divmod(delta.days, 365)
        months, days = divmod(rem, 30)
        hours, rem2 = divmod(delta.seconds, 3600)
        minutes = rem2 // 60

        created_str = created.strftime("%A, %B %d, %Y %I:%M %p")

        parts = []
        if years: parts.append(f"**{years}** year{'s' if years != 1 else ''}")
        if months: parts.append(f"**{months}** month{'s' if months != 1 else ''}")
        if days: parts.append(f"**{days}** day{'s' if days != 1 else ''}")
        if hours: parts.append(f"**{hours}** hour{'s' if hours != 1 else ''}")
        if minutes: parts.append(f"**{minutes}** minute{'s' if minutes != 1 else ''}")
        age_str = ", ".join(parts) if parts else "Just created"

        embed = discord.Embed(color=YELLOW)
        embed.set_author(name=f"Account Age : {target.name}", icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.description = (
            f"{e('dot')} **Created At**\n{created_str}\n\n"
            f"{e('dot')} **Account Age**\n{age_str}\n\n"
            f"{e('dot')} **User ID**\n{target.id}"
        )
        embed.set_footer(text=f"Requested by {req.name}")
        embed.timestamp = datetime.now(timezone.utc)

        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="settimezone")
    @commands.has_permissions(administrator=True)
    async def prefix_settimezone(self, ctx, tz_name: str):
        await self._settimezone(ctx, tz_name, slash=False)

    @app_commands.command(name="settimezone", description="Set the server's timezone for daily/weekly stats")
    @app_commands.describe(tz_name="IANA timezone name, e.g. Asia/Karachi, Asia/Dhaka, America/New_York")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_settimezone(self, interaction, tz_name: str):
        await self._settimezone(interaction, tz_name, slash=True)

    async def _settimezone(self, ctx, tz_name, slash):
        if not storage.is_valid_timezone(tz_name):
            embed = discord.Embed(
                description=(
                    f"{e('error')} `{tz_name}` isn't a valid timezone.\n"
                    f"Use an IANA timezone name, e.g. `Asia/Karachi`, `Asia/Dhaka`, `Europe/London`, `America/New_York`."
                ),
                color=YELLOW
            )
            if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
            else: await ctx.send(embed=embed)
            return

        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        storage.set_guild_timezone(data, str(guild.id), tz_name)
        storage.save(data)

        embed = discord.Embed(
            description=f"{e('success')} Server timezone set to `{tz_name}`. Daily and weekly stats now reset based on this timezone.",
            color=YELLOW
        )
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="timezone")
    @commands.has_permissions(administrator=True)
    async def prefix_timezone(self, ctx):
        await self._timezone(ctx, slash=False)

    @app_commands.command(name="timezone", description="View the server's current timezone setting")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_timezone(self, interaction):
        await self._timezone(interaction, slash=True)

    async def _timezone(self, ctx, slash):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        tz_name = storage.get_guild_timezone(data, str(guild.id))
        embed = discord.Embed(
            description=f"{e('dot')} This server's timezone is set to `{tz_name}`.",
            color=YELLOW
        )
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Messages(bot))