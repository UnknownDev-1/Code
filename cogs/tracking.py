import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from config.emojis import e
from utils import make_paginator, medal, YELLOW, PaginatorView
from config import storage

invite_cache: dict[int, dict[str, discord.Invite]] = {}

async def cache_guild(guild: discord.Guild):
    try:
        invite_cache[guild.id] = {inv.code: inv for inv in await guild.invites()}
    except discord.Forbidden:
        pass

class Tracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await cache_guild(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await cache_guild(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        data = storage.load()
        gid = str(member.guild.id)
        mid = str(member.id)
        used_code = inviter_id = None

        try:
            new_inv = {inv.code: inv for inv in await member.guild.invites()}
            old_inv = invite_cache.get(member.guild.id, {})
            for code, inv in new_inv.items():
                if inv.uses > (old_inv[code].uses if code in old_inv else 0):
                    used_code = code
                    inviter_id = str(inv.inviter.id) if inv.inviter else None
                    break
            invite_cache[member.guild.id] = new_inv
        except discord.Forbidden:
            pass

        if inviter_id:
            rec = storage.get_invite_record(data, gid, inviter_id)
            is_fake = (datetime.now(timezone.utc) - member.created_at).days < 7
            is_rejoin = any(u["user_id"] == mid for u in rec["invited_users"])

            if is_fake:
                rec["fake"] += 1
            elif is_rejoin:
                rec["rejoins"] += 1
            else:
                rec["regular"] += 1

            rec["invited_users"].append({
                "user_id": mid, "username": str(member),
                "joined_at": datetime.utcnow().isoformat(), "left_at": None,
                "invite_code": used_code, "fake": is_fake, "rejoin": is_rejoin,
            })
            storage.save(data)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        data = storage.load()
        gid = str(member.guild.id)
        mid = str(member.id)
        for uid, rec in data["invites"].get(gid, {}).items():
            for entry in rec["invited_users"]:
                if entry["user_id"] == mid and entry["left_at"] is None:
                    entry["left_at"] = datetime.utcnow().isoformat()
                    if not entry.get("fake") and not entry.get("rejoin"):
                        rec["left"] += 1
                    break
        storage.save(data)

    @commands.command(name="invites", aliases=["i"])
    async def prefix_invites(self, ctx, member: discord.Member = None):
        await self._invites(ctx, member or ctx.author, slash=False)

    @app_commands.command(name="invites", description="Display the invite stats of a member")
    @app_commands.describe(member="Member to check (default: you)")
    async def slash_invites(self, interaction, member: discord.Member = None):
        await self._invites(interaction, member or interaction.user, slash=True)

    async def _invites(self, ctx, target, slash):
        data = storage.load()
        rec = storage.get_invite_record(data, str(target.guild.id), str(target.id))
        eff = storage.effective_invites(rec)
        req = ctx.author if not slash else ctx.user

        embed = discord.Embed(color=YELLOW)
        embed.set_author(name=f"{target.name}'s Invites Stats", icon_url=target.display_avatar.url)
        embed.description = (
            f"{e('dot')} **{target.mention} currently has `{eff}` invites.**\n\n"
            f"**Total:**\n"
            f"{e('arrow')} {e('dot')} Joins : **{rec['regular']}**\n"
            f"{e('arrow')} {e('dot')} Left : **{rec['left']}**\n"
            f"{e('arrow')} {e('dot')} Bonus : **{rec['bonus']}**\n\n"
            f"**Other:**\n"
            f"{e('arrow')} {e('dot')} Fake : **{rec['fake']}**\n"
            f"{e('arrow')} {e('dot')} Rejoins : **{rec.get('rejoins', 0)}**"
        )
        embed.set_footer(text=f"Requested by {req.name}")
        embed.timestamp = datetime.now(timezone.utc)
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="inviter")
    async def prefix_inviter(self, ctx, member: discord.Member = None):
        await self._inviter(ctx, member or ctx.author, slash=False)

    @app_commands.command(name="inviter", description="Displays who invited a server member")
    @app_commands.describe(member="Member to look up")
    async def slash_inviter(self, interaction, member: discord.Member = None):
        await self._inviter(interaction, member or interaction.user, slash=True)

    async def _inviter(self, ctx, target, slash):
        data = storage.load()
        gid = str(target.guild.id)
        mid = str(target.id)
        found_uid = found_entry = None
        req = ctx.author if not slash else ctx.user
        guild = ctx.guild if not slash else ctx.guild

        for uid, rec in data["invites"].get(gid, {}).items():
            for entry in rec["invited_users"]:
                if entry["user_id"] == mid:
                    found_uid = uid; found_entry = entry; break
            if found_uid: break

        embed = discord.Embed(color=YELLOW)
        embed.set_author(name="Inviter Information", icon_url=self.bot.user.display_avatar.url)

        if not found_uid:
            embed.description = (
                f"{e('arrow')} **{target.mention}** was invited by **Unknown**\n"
                f"{e('dot')} Joined : Unknown"
            )
        else:
            inv_member = guild.get_member(int(found_uid))
            inv_str = f"@{inv_member.name}" if inv_member else f"<@{found_uid}>"
            ts = found_entry["joined_at"][:16].replace("T", " ") if found_entry.get("joined_at") else "Unknown"
            embed.description = (
                f"{e('arrow')} **{target.mention}** was invited by **{inv_str}**\n"
                f"{e('dot')} Joined : {ts}"
            )

        embed.set_footer(text=f"Requested by {req.name}")
        embed.timestamp = datetime.now(timezone.utc)
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="invited")
    async def prefix_invited(self, ctx, member: discord.Member = None):
        await self._invited(ctx, member or ctx.author, slash=False)

    @app_commands.command(name="invited", description="Display the invited list of a member")
    @app_commands.describe(member="Member to check (default: you)")
    async def slash_invited(self, interaction, member: discord.Member = None):
        await self._invited(interaction, member or interaction.user, slash=True)

    async def _invited(self, ctx, target, slash):
        data = storage.load()
        rec = storage.get_invite_record(data, str(target.guild.id), str(target.id))
        invited = [u for u in rec["invited_users"] if not u.get("fake")]
        req = ctx.author if not slash else ctx.user
        guild = ctx.guild if not slash else ctx.guild
        PER = 10

        if not invited:
            embed = discord.Embed(color=YELLOW)
            embed.set_author(name=f"Invited list of {target.name}", icon_url=target.display_avatar.url)
            embed.description = f"{e('dot')} Nobody invited by **{target.name}** yet."
            embed.set_footer(text="Page 1/1")
            pages = [embed]
        else:
            chunks = [invited[i:i+PER] for i in range(0, len(invited), PER)]
            pages = []
            for idx, chunk in enumerate(chunks):
                embed = discord.Embed(color=YELLOW)
                embed.set_author(name=f"Invited list of {target.name}", icon_url=target.display_avatar.url)
                lines = []
                for j, u in enumerate(chunk, idx*PER+1):
                    m = guild.get_member(int(u["user_id"]))
                    online = m and str(m.status) != "offline"
                    status = "🟢 Online" if online else "⚫ Offline"
                    tag = " *(rejoin)*" if u.get("rejoin") else ""
                    lines.append(f"#{j} {e('dot')} **{u['username']}** • {status}{tag}")
                embed.description = "\n".join(lines)
                embed.set_footer(text=f"Page {idx+1}/{len(chunks)}")
                pages.append(embed)

        view = make_paginator(pages, req.id)
        if slash: await ctx.response.send_message(embed=pages[0], view=view)
        else: await ctx.send(embed=pages[0], view=view)

    @commands.command(name="inviteinfo")
    async def prefix_inviteinfo(self, ctx, member: discord.Member = None):
        await self._inviteinfo(ctx, member or ctx.author, slash=False)

    @app_commands.command(name="inviteinfo", description="Display active invite codes of a user")
    @app_commands.describe(member="Member to check (default: you)")
    async def slash_inviteinfo(self, interaction, member: discord.Member = None):
        await self._inviteinfo(interaction, member or interaction.user, slash=True)

    async def _inviteinfo(self, ctx, target, slash):
        guild = ctx.guild if not slash else ctx.guild
        req = ctx.author if not slash else ctx.user
        embed = discord.Embed(color=YELLOW)
        embed.set_author(name=f"{target.name}'s Active Invite Codes", icon_url=target.display_avatar.url)
        try:
            all_inv = await guild.invites()
            user_inv = [inv for inv in all_inv if inv.inviter and inv.inviter.id == target.id]
        except discord.Forbidden:
            embed.description = f"{e('error')} Missing **Manage Guild** permission."
            if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
            else: await ctx.send(embed=embed)
            return

        if not user_inv:
            embed.description = f"{e('dot')} No active invite codes for **{target.name}**."
        else:
            lines = []
            for inv in user_inv:
                mu = str(inv.max_uses) if inv.max_uses else "∞"
                exp = f"<t:{int(inv.expires_at.timestamp())}:R>" if inv.expires_at else "Never"
                lines.append(f"{e('arrow')} `{inv.code}` — **{inv.uses}**/{mu} uses · #{inv.channel.name} · expires {exp}")
            embed.description = "\n".join(lines)

        embed.set_footer(text=f"Requested by {req.name}")
        embed.timestamp = datetime.now(timezone.utc)
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="addinvites")
    @commands.has_permissions(manage_guild=True)
    async def prefix_addinvites(self, ctx, member: discord.Member, amount: int):
        await self._mod_invites(ctx, member, amount, slash=False, add=True)

    @app_commands.command(name="addinvites", description="Add bonus invites to a user")
    @app_commands.describe(member="Target member", amount="Amount to add")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_addinvites(self, interaction, member: discord.Member, amount: int):
        await self._mod_invites(interaction, member, amount, slash=True, add=True)

    @commands.command(name="removeinvites")
    @commands.has_permissions(manage_guild=True)
    async def prefix_removeinvites(self, ctx, member: discord.Member, amount: int):
        await self._mod_invites(ctx, member, amount, slash=False, add=False)

    @app_commands.command(name="removeinvites", description="Remove invites from a user")
    @app_commands.describe(member="Target member", amount="Amount to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_removeinvites(self, interaction, member: discord.Member, amount: int):
        await self._mod_invites(interaction, member, amount, slash=True, add=False)

    async def _mod_invites(self, ctx, target, amount, slash, add):
        data = storage.load()
        rec = storage.get_invite_record(data, str(target.guild.id), str(target.id))
        rec["bonus"] += amount if add else -amount
        storage.save(data)
        emoji = e("add") if add else e("remove")
        verb = "Added" if add else "Removed"
        embed = discord.Embed(color=YELLOW)
        embed.description = (
            f"{emoji} {verb} **{amount}** invite(s) {'to' if add else 'from'} {target.mention}\n"
            f"{e('dot')} New total: `{storage.effective_invites(rec)}`"
        )
        if slash: await ctx.response.send_message(embed=embed)
        else: await ctx.send(embed=embed)

    @commands.command(name="clearinvites")
    @commands.has_permissions(manage_guild=True)
    async def prefix_clearinvites(self, ctx, member: discord.Member = None):
        await self._clearinvites(ctx, member, slash=False)

    @app_commands.command(name="clearinvites", description="Clear invite data of a member or entire guild")
    @app_commands.describe(member="Member to clear (empty = entire guild)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_clearinvites(self, interaction, member: discord.Member = None):
        await self._clearinvites(interaction, member, slash=True)

    async def _clearinvites(self, ctx, target, slash):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        gid = str(guild.id)
        if target:
            data["invites"].get(gid, {}).pop(str(target.id), None)
            desc = f"{e('clear')} Cleared invite data for {target.mention}."
        else:
            data["invites"].pop(gid, None)
            desc = f"{e('clear')} Cleared **all** invite data for this server."
        storage.save(data)
        embed = discord.Embed(description=desc, color=YELLOW)
        if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
        else: await ctx.send(embed=embed)

    @commands.command(name="resetmyinvites", aliases=["rmi"])
    async def prefix_rmi(self, ctx):
        await self._rmi(ctx, slash=False)

    @app_commands.command(name="resetmyinvites", description="Clear your own invite data")
    async def slash_rmi(self, interaction):
        await self._rmi(interaction, slash=True)

    async def _rmi(self, ctx, slash):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        user = ctx.author if not slash else ctx.user
        data["invites"].get(str(guild.id), {}).pop(str(user.id), None)
        storage.save(data)
        embed = discord.Embed(description=f"{e('reset')} Your invite data in **{guild.name}** has been cleared.", color=YELLOW)
        if slash: await ctx.response.send_message(embed=embed, ephemeral=True)
        else: await ctx.send(embed=embed)

    @commands.command(name="lb")
    async def prefix_lb(self, ctx, category: str = "invites"):
        cat = category.lower()
        msg_cog = self.bot.get_cog("Messages")
        if cat in ("invites", "i", "invite"):
            await self._lb_invites(ctx, slash=False)
        elif cat in ("messages", "m", "message"):
            if msg_cog: await msg_cog._lb_messages(ctx, slash=False, daily=False)
        elif cat in ("dailymessages", "daily", "dm"):
            if msg_cog: await msg_cog._lb_messages(ctx, slash=False, daily=True)
        else:
            await ctx.send(f"{e('error')} Use: `invites`, `messages`, or `dailymessages`")

    @commands.command(name="leaderboard")
    async def prefix_leaderboard(self, ctx, category: str = "invites"):
        await self.prefix_lb(ctx, category)

    @app_commands.command(name="leaderboard", description="Show leaderboard")
    @app_commands.describe(category="invites | messages | dailymessages")
    @app_commands.choices(category=[
        app_commands.Choice(name="invites", value="invites"),
        app_commands.Choice(name="messages", value="messages"),
        app_commands.Choice(name="dailymessages", value="dailymessages"),
    ])
    async def slash_leaderboard(self, interaction, category: str = "invites"):
        msg_cog = self.bot.get_cog("Messages")
        if category == "invites": await self._lb_invites(interaction, slash=True)
        elif category == "messages":
            if msg_cog: await msg_cog._lb_messages(interaction, slash=True, daily=False)
        else:
            if msg_cog: await msg_cog._lb_messages(interaction, slash=True, daily=True)

    async def _lb_invites(self, ctx, slash: bool):
        data = storage.load()
        guild = ctx.guild if not slash else ctx.guild
        gid = str(guild.id)
        raw = data["invites"].get(gid, {})
        requester = ctx.author if not slash else ctx.user

        PER_PAGE = 10
        pages = []

        if not raw:
            embed = discord.Embed(title="Invite Leaderboard", color=YELLOW)
            embed.description = f"{e('dot')} No invite data yet."
            embed.set_footer(text="Page 1/1")
            pages = [embed]
        else:
            top = sorted(raw.items(), key=lambda x: storage.effective_invites(x[1]), reverse=True)
            chunks = [top[i:i+PER_PAGE] for i in range(0, len(top), PER_PAGE)]
            total = len(chunks)
            for page_idx, chunk in enumerate(chunks):
                embed = discord.Embed(title="Invite Leaderboard", color=YELLOW)
                lines = []
                for i, (uid, rec) in enumerate(chunk):
                    rank = page_idx * PER_PAGE + i
                    eff = storage.effective_invites(rec)
                    joins = rec["regular"]
                    left = rec["left"]
                    fakes = rec["fake"]
                    rejoins = rec.get("rejoins", 0)
                    member = guild.get_member(int(uid))
                    name = member.name if member else f"Unknown ({uid})"
                    lines.append(
                        f"{medal(rank)} | **{name}** • **{eff}** Invites "
                        f"(**{joins}** Joins, **{left}** Leaves, **{fakes}** Fakes, **{rejoins}** Rejoins)"
                    )
                embed.description = "\n\n".join(lines)
                embed.set_footer(text=f"Page {page_idx+1}/{total}")
                pages.append(embed)

        view = PaginatorView(pages, requester.id)
        if len(pages) == 1:
            for item in view.children:
                item.disabled = True

        if slash: await ctx.response.send_message(embed=pages[0], view=view)
        else: await ctx.send(embed=pages[0], view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tracking(bot))