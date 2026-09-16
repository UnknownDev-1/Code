import discord
from discord.ext import commands
import json
import os
import re
from datetime import datetime, timezone, timedelta

DATA_FILE = "strikes.json"
STAFFMSG_DATA_FILE = "staffmessages.json"

NO_PING = discord.AllowedMentions.none()
WEEKLY_THRESHOLD = 3
WEEKLY_WINDOW_DAYS = 7
MONTHLY_THRESHOLD = 6


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_guild_data(data: dict, guild_id: str) -> dict:
    gd = data.setdefault(guild_id, {
        "log_channel": None,
        "strike_roles": [],
        "hierarchy": [],
        "members": {},
        "next_id": 1
    })
    gd.setdefault("strike_roles", [])
    gd.setdefault("hierarchy", [])
    gd.setdefault("members", {})
    gd.setdefault("next_id", 1)
    return gd


def get_member_data(gd: dict, user_id: str) -> dict:
    return gd["members"].setdefault(user_id, {"strikes": [], "counted_since": None})


def is_authorized(member: discord.Member, gd: dict) -> bool:
    if member.guild_permissions.administrator:
        return True
    role_ids = [int(r) for r in gd.get("strike_roles", [])]
    return any(r.id in role_ids for r in member.roles)


def is_eligible_staff(member: discord.Member, guild_id: str) -> bool:
    if not os.path.exists(STAFFMSG_DATA_FILE):
        return False
    with open(STAFFMSG_DATA_FILE, "r") as f:
        data = json.load(f)
    gd = data.get(str(guild_id), {})
    role_ids = [int(r) for r in gd.get("staff_roles", [])]
    return any(r.id in role_ids for r in member.roles)


def parse_ordered_roles(guild: discord.Guild, raw: str) -> list:
    tokens = re.split(r"[,\s]+", raw.strip())
    found = []
    for token in tokens:
        if not token:
            continue
        match = re.match(r"<@&(\d+)>", token) or re.match(r"^(\d+)$", token)
        role = None
        if match:
            role = guild.get_role(int(match.group(1)))
        else:
            role = discord.utils.find(lambda r: r.name.lower() == token.lower(), guild.roles)
        if role:
            found.append(role)
    return found


def parse_roles(guild: discord.Guild, raw: str) -> list:
    tokens = re.split(r"[,\s]+", raw.strip())
    found = []
    for token in tokens:
        if not token:
            continue
        match = re.match(r"<@&(\d+)>", token) or re.match(r"^(\d+)$", token)
        role = None
        if match:
            role = guild.get_role(int(match.group(1)))
        else:
            role = discord.utils.find(lambda r: r.name.lower() == token.lower(), guild.roles)
        if role and role not in found:
            found.append(role)
    return found


def active_strikes(member_data: dict) -> list:
    since = member_data.get("counted_since")
    if not since:
        return member_data["strikes"]
    since_dt = datetime.fromisoformat(since)
    return [s for s in member_data["strikes"] if datetime.fromisoformat(s["timestamp"]) >= since_dt]


def count_weekly(strikes: list) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WEEKLY_WINDOW_DAYS)
    return sum(1 for s in strikes if datetime.fromisoformat(s["timestamp"]) >= cutoff)


def count_monthly(strikes: list) -> int:
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    return sum(1 for s in strikes if s["timestamp"].startswith(current_month))


async def post_log(guild: discord.Guild, gd: dict, content: str, embed: discord.Embed):
    channel_id = gd.get("log_channel")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if not channel:
        return
    try:
        await channel.send(content=content, embed=embed, allowed_mentions=NO_PING if content is None else None)
    except discord.Forbidden:
        pass


class Strikes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _deny(self, ctx: commands.Context, text: str = "You don't have permission to use this."):
        embed = discord.Embed(description=text, color=discord.Color.red())
        await ctx.reply(embed=embed, mention_author=False)

    async def _demote(self, guild: discord.Guild, member: discord.Member, gd: dict, reason: str):
        hierarchy_ids = gd.get("hierarchy", [])
        hierarchy_roles = [guild.get_role(int(r)) for r in hierarchy_ids]
        hierarchy_roles = [r for r in hierarchy_roles if r is not None]

        current_index = None
        for i, role in enumerate(hierarchy_roles):
            if role in member.roles:
                current_index = i
                break

        result_text = None
        if current_index is None:
            result_text = "No configured hierarchy role found on this member, no role change made."
        elif current_index == len(hierarchy_roles) - 1:
            try:
                await member.remove_roles(*hierarchy_roles, reason=reason)
                result_text = f"Removed all staff hierarchy roles from {member.mention} (was already at the lowest tier)."
            except discord.Forbidden:
                result_text = "Missing permission to remove hierarchy roles."
        else:
            old_role = hierarchy_roles[current_index]
            new_role = hierarchy_roles[current_index + 1]
            try:
                await member.remove_roles(old_role, reason=reason)
                await member.add_roles(new_role, reason=reason)
                result_text = f"Demoted {member.mention} from {old_role.mention} to {new_role.mention}."
            except discord.Forbidden:
                result_text = "Missing permission to change hierarchy roles."

        embed = discord.Embed(
            title="Auto Demotion",
            description=f"{result_text}\n\n**Reason:** {reason}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        await post_log(guild, gd, None, embed)

    @commands.command(name="strike")
    @commands.guild_only()
    async def strike(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not is_authorized(ctx.author, gd):
            await self._deny(ctx)
            return

        if not is_eligible_staff(member, ctx.guild.id):
            await self._deny(ctx, f"{member.mention} isn't a configured staff member.")
            return

        strike_id = gd["next_id"]
        gd["next_id"] += 1

        md = get_member_data(gd, str(member.id))
        md["strikes"].append({
            "id": strike_id,
            "reason": reason,
            "moderator_id": str(ctx.author.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        save_data(data)

        active = active_strikes(md)
        active_count = len(active)

        embed = discord.Embed(
            title="Strike Given",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Staff Member", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="Given By", value=ctx.author.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Strike ID", value=str(strike_id), inline=True)
        embed.add_field(name="Active Strikes", value=str(active_count), inline=True)

        await post_log(ctx.guild, gd, member.mention, embed)

        confirm_embed = discord.Embed(
            description=f"<a:NX_Check:1526717230396735598> Strike #{strike_id} given to {member.mention}. Active strikes: {active_count}.",
            color=discord.Color.green()
        )
        await ctx.reply(embed=confirm_embed, mention_author=False)

        weekly_count = count_weekly(active)
        monthly_count = count_monthly(active)

        if weekly_count >= WEEKLY_THRESHOLD:
            md["counted_since"] = datetime.now(timezone.utc).isoformat()
            save_data(data)
            await self._demote(ctx.guild, member, gd, f"Reached {weekly_count} strikes within {WEEKLY_WINDOW_DAYS} days")
        elif monthly_count >= MONTHLY_THRESHOLD:
            md["counted_since"] = datetime.now(timezone.utc).isoformat()
            save_data(data)
            await self._demote(ctx.guild, member, gd, f"Reached {monthly_count} strikes this month")

    @commands.group(name="strikes", invoke_without_command=True)
    @commands.guild_only()
    async def strikes(self, ctx: commands.Context, member: discord.Member = None):
        await self._view(ctx, member)

    @strikes.command(name="view")
    @commands.guild_only()
    async def strikes_view(self, ctx: commands.Context, member: discord.Member = None):
        await self._view(ctx, member)

    async def _view(self, ctx: commands.Context, member: discord.Member):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not is_authorized(ctx.author, gd):
            await self._deny(ctx)
            return

        if member is None:
            entries = [(uid, len(active_strikes(md))) for uid, md in gd["members"].items() if active_strikes(md)]
            if not entries:
                embed = discord.Embed(description="No members have active strikes.", color=discord.Color.blurple())
                await ctx.reply(embed=embed, mention_author=False)
                return

            entries.sort(key=lambda x: x[1], reverse=True)
            lines = []
            for uid, count in entries:
                m = ctx.guild.get_member(int(uid))
                name = m.mention if m else f"<@{uid}>"
                lines.append(f"{name} : {count} active strike{'s' if count != 1 else ''}")

            embed = discord.Embed(title="Active Strikes", description="\n".join(lines)[:4000], color=discord.Color.blurple())
            await ctx.reply(embed=embed, mention_author=False)
            return

        md = get_member_data(gd, str(member.id))
        active = active_strikes(md)

        if not active:
            embed = discord.Embed(description=f"{member.mention} has no active strikes.", color=discord.Color.blurple())
            await ctx.reply(embed=embed, mention_author=False)
            return

        lines = []
        for s in active:
            mod = ctx.guild.get_member(int(s["moderator_id"]))
            mod_text = mod.mention if mod else f"<@{s['moderator_id']}>"
            ts = int(datetime.fromisoformat(s["timestamp"]).timestamp())
            lines.append(f"**#{s['id']}** {s['reason']}\nBy {mod_text}, <t:{ts}:R>")

        embed = discord.Embed(
            title=f"Active Strikes: {member.display_name}",
            description="\n\n".join(lines)[:4000],
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.reply(embed=embed, mention_author=False)

    @strikes.command(name="history")
    @commands.guild_only()
    async def strikes_history(self, ctx: commands.Context, member: discord.Member, month: str = None):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not is_authorized(ctx.author, gd):
            await self._deny(ctx)
            return

        md = get_member_data(gd, str(member.id))
        all_strikes = md["strikes"]

        if month:
            all_strikes = [s for s in all_strikes if s["timestamp"].startswith(month)]

        if not all_strikes:
            embed = discord.Embed(description=f"No strike history found for {member.mention}{f' in {month}' if month else ''}.", color=discord.Color.blurple())
            await ctx.reply(embed=embed, mention_author=False)
            return

        lines = []
        for s in all_strikes:
            mod = ctx.guild.get_member(int(s["moderator_id"]))
            mod_text = mod.mention if mod else f"<@{s['moderator_id']}>"
            ts = int(datetime.fromisoformat(s["timestamp"]).timestamp())
            lines.append(f"**#{s['id']}** {s['reason']}\nBy {mod_text}, <t:{ts}:F>")

        title = f"Strike History: {member.display_name}"
        if month:
            title += f" ({month})"

        embed = discord.Embed(title=title, description="\n\n".join(lines)[:4000], color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
        embed.set_footer(text=f"Total: {len(all_strikes)} strike(s)")
        await ctx.reply(embed=embed, mention_author=False)

    @strikes.command(name="log")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def strikes_log(self, ctx: commands.Context, channel: discord.TextChannel):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))
        gd["log_channel"] = str(channel.id)
        save_data(data)

        embed = discord.Embed(description=f"Strike logs will now be sent to {channel.mention}.", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)

    @strikes.command(name="roles")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def strikes_roles(self, ctx: commands.Context, *, roles: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        found_roles = parse_roles(ctx.guild, roles)
        if not found_roles:
            await self._deny(ctx, "Couldn't find any of those roles.")
            return

        added = []
        already = []
        for role in found_roles:
            if str(role.id) in gd["strike_roles"]:
                already.append(role)
            else:
                gd["strike_roles"].append(str(role.id))
                added.append(role)

        save_data(data)

        lines = []
        if added:
            lines.append(f"Added: {', '.join(r.mention for r in added)}")
        if already:
            lines.append(f"Already added: {', '.join(r.mention for r in already)}")

        embed = discord.Embed(description="\n".join(lines), color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)

    @strikes.command(name="hierarchy")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def strikes_hierarchy(self, ctx: commands.Context, *, roles: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        ordered_roles = parse_ordered_roles(ctx.guild, roles)
        if not ordered_roles:
            await self._deny(ctx, "Couldn't find any of those roles.")
            return

        gd["hierarchy"] = [str(r.id) for r in ordered_roles]
        save_data(data)

        listed = " -> ".join(r.mention for r in ordered_roles)
        embed = discord.Embed(description=f"Demotion hierarchy set, highest to lowest:\n{listed}", color=discord.Color.green())
        await ctx.reply(embed=embed, mention_author=False)

    @strikes.command(name="config")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def strikes_config(self, ctx: commands.Context):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        log_text = f"<#{gd['log_channel']}>" if gd.get("log_channel") else "Not set"
        roles_text = ", ".join(f"<@&{r}>" for r in gd["strike_roles"]) or "None"
        hierarchy_roles = [ctx.guild.get_role(int(r)) for r in gd.get("hierarchy", [])]
        hierarchy_text = " -> ".join(r.mention for r in hierarchy_roles if r) or "Not set"

        embed = discord.Embed(title="Strike System Config", color=discord.Color.gold(), timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Log Channel", value=log_text, inline=False)
        embed.add_field(name="Strike Roles", value=roles_text, inline=False)
        embed.add_field(name="Demotion Hierarchy", value=hierarchy_text, inline=False)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Strikes(bot))
