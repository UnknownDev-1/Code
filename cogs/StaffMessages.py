import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import storage as main_storage
from utils import make_paginator, YELLOW

DATA_FILE = "staffmessages.json"

MIN_WORDS = 3
STREAK_WINDOW_SECONDS = 3
STREAK_TRIGGER = 3
DEDUCTION_AMOUNT = 6

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U0000FE0F"
    "\U0000200D"
    "]+"
)
CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:\w+:\d+>")
URL_PATTERN = re.compile(r"https?://\S+")


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
        "staff_roles": [],
        "blacklisted_channels": [],
        "members": {}
    })
    gd.setdefault("staff_roles", [])
    gd.setdefault("blacklisted_channels", [])
    gd.setdefault("members", {})
    return gd


def get_member_data(gd: dict, user_id: str) -> dict:
    md = gd["members"].setdefault(user_id, {
        "days": {},
        "streak_count": 0,
        "streak_last": None
    })
    md.setdefault("days", {})
    return md


def get_day_entry(md: dict, day: str) -> dict:
    entry = md["days"].setdefault(day, {"valid": 0, "deducted": 0, "manual": 0, "events": []})
    entry.setdefault("events", [])
    return entry


def get_tz(guild_id: str) -> str:
    try:
        data = main_storage.load()
        return main_storage.get_guild_timezone(data, guild_id)
    except Exception:
        return "UTC"


def now_in_tz(tz_name: str) -> datetime:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz)


def day_key(tz_name: str) -> str:
    return now_in_tz(tz_name).date().isoformat()


def month_key(tz_name: str) -> str:
    return now_in_tz(tz_name).strftime("%Y-%m")


def net(entry: dict) -> int:
    return entry["valid"] - entry["deducted"] + entry["manual"]


def month_totals(md: dict, month: str) -> dict:
    valid = deducted = manual = 0
    for day, entry in md["days"].items():
        if day.startswith(month):
            valid += entry["valid"]
            deducted += entry["deducted"]
            manual += entry["manual"]
    return {"valid": valid, "deducted": deducted, "manual": manual, "net": valid - deducted + manual}


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


def is_staff(member: discord.Member, gd: dict) -> bool:
    role_ids = [int(r) for r in gd.get("staff_roles", [])]
    return any(r.id in role_ids for r in member.roles)


def is_staff_or_admin(member: discord.Member, gd: dict) -> bool:
    return is_admin(member) or is_staff(member, gd)


def parse_roles(guild: discord.Guild, raw: str) -> list:
    if not raw:
        return []
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


def is_valid_content(message: discord.Message) -> bool:
    if message.attachments:
        return False
    if message.stickers:
        return False

    content = message.content
    content = CUSTOM_EMOJI_PATTERN.sub("", content)
    content = EMOJI_PATTERN.sub("", content)

    if not content.strip():
        return False

    without_links = URL_PATTERN.sub("", content)
    if not without_links.strip():
        return False

    words = without_links.split()
    return len(words) >= MIN_WORDS


class StaffMessages(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    smessages_group = app_commands.Group(name="smessages", description="Manage the staff message tracking system")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        data = load_data()
        gd = get_guild_data(data, str(message.guild.id))

        if not gd["staff_roles"]:
            return

        if not is_staff(message.author, gd):
            return

        if str(message.channel.id) in gd["blacklisted_channels"]:
            return

        md = get_member_data(gd, str(message.author.id))
        now = datetime.now(timezone.utc)

        last = md.get("streak_last")
        gap = None
        if last:
            try:
                gap = (now - datetime.fromisoformat(last)).total_seconds()
            except Exception:
                gap = None

        if gap is not None and gap <= STREAK_WINDOW_SECONDS:
            md["streak_count"] += 1
        else:
            md["streak_count"] = 1
        md["streak_last"] = now.isoformat()

        tz = get_tz(str(message.guild.id))
        dkey = day_key(tz)
        day_entry = get_day_entry(md, dkey)

        if is_valid_content(message):
            day_entry["valid"] += 1

        if md["streak_count"] % STREAK_TRIGGER == 0:
            day_entry["deducted"] += DEDUCTION_AMOUNT
            day_entry["events"].append({
                "type": "deduction",
                "amount": DEDUCTION_AMOUNT,
                "reason": f"{STREAK_TRIGGER} messages in a row within {STREAK_WINDOW_SECONDS}s",
                "channel_id": str(message.channel.id),
                "timestamp": now.isoformat()
            })

        save_data(data)

    async def _deny(self, ctx, slash: bool):
        if slash:
            embed = discord.Embed(description="You don't have permission to use this.", color=discord.Color.red())
            await ctx.response.send_message(embed=embed, ephemeral=True)
        # prefix stays silent on purpose, no response for non staff members

    @commands.group(name="sm", aliases=["smsg", "smessage"], invoke_without_command=True)
    @commands.guild_only()
    async def prefix_sm(self, ctx: commands.Context, member: discord.Member = None):
        await self._smessage(ctx, member, slash=False)

    @app_commands.command(name="smessage", description="Check your or another staff member's message stats")
    @app_commands.guild_only()
    @app_commands.describe(member="Member to check (default: you)")
    async def slash_smessage(self, interaction: discord.Interaction, member: discord.Member = None):
        await self._smessage(interaction, member, slash=True)

    async def _smessage(self, ctx, member, slash: bool):
        guild = ctx.guild
        data = load_data()
        gd = get_guild_data(data, str(guild.id))

        author = ctx.user if slash else ctx.author
        if not is_staff_or_admin(author, gd):
            await self._deny(ctx, slash)
            return

        target = member or author
        tz = get_tz(str(guild.id))
        dkey = day_key(tz)
        mkey = month_key(tz)

        md = gd["members"].get(str(target.id), {"days": {}})
        day_entry = md.get("days", {}).get(dkey, {"valid": 0, "deducted": 0, "manual": 0})
        daily_net = day_entry["valid"] - day_entry["deducted"] + day_entry["manual"]
        month_data = month_totals(md if "days" in md else {"days": {}}, mkey)

        embed = discord.Embed(
            title=f"{target.display_name}'s Staff Message Stats",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Today", value=str(daily_net), inline=True)
        embed.add_field(name="This Month", value=str(month_data["net"]), inline=True)

        if slash:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.reply(embed=embed, mention_author=False)

    @prefix_sm.command(name="logs")
    @commands.guild_only()
    async def prefix_sm_logs(self, ctx: commands.Context, member: discord.Member, month: str = None):
        await self._logs(ctx, member, month, slash=False)

    @smessages_group.command(name="logs", description="View a staff member's valid, deducted, and manual message log for a month")
    @app_commands.guild_only()
    @app_commands.describe(member="Member to check", month="Month in YYYY-MM format, default is current month")
    async def slash_sm_logs(self, interaction: discord.Interaction, member: discord.Member, month: str = None):
        await self._logs(interaction, member, month, slash=True)

    async def _logs(self, ctx, member: discord.Member, month: str, slash: bool):
        guild = ctx.guild
        author = ctx.user if slash else ctx.author

        if not is_admin(author):
            await self._deny(ctx, slash)
            return

        data = load_data()
        gd = get_guild_data(data, str(guild.id))
        tz = get_tz(str(guild.id))
        target_month = month or month_key(tz)

        md = gd["members"].get(str(member.id), {"days": {}})
        totals = month_totals(md, target_month)

        day_lines = []
        events = []
        for day, entry in sorted(md.get("days", {}).items()):
            if not day.startswith(target_month):
                continue
            day_net = net(entry)
            day_lines.append(f"{day}: valid {entry['valid']}, deducted {entry['deducted']}, manual {entry['manual']}, net {day_net}")
            for ev in entry.get("events", []):
                events.append((day, ev))

        summary = discord.Embed(
            title=f"{member.display_name}'s Log ({target_month})",
            description=(
                f"**Valid:** {totals['valid']}\n"
                f"**Deducted:** {totals['deducted']}\n"
                f"**Manual:** {totals['manual']}\n"
                f"**Net:** {totals['net']}\n\n"
                + ("\n".join(day_lines) if day_lines else "No activity recorded this month.")
            ),
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        pages = [summary]

        if events:
            chunk_size = 8
            for i in range(0, len(events), chunk_size):
                chunk = events[i:i + chunk_size]
                lines = []
                for day, ev in chunk:
                    if ev["type"] == "deduction":
                        lines.append(f"{day} : deducted {ev['amount']} in <#{ev['channel_id']}>, {ev['reason']}")
                    else:
                        mod = guild.get_member(int(ev.get("moderator_id", 0))) if ev.get("moderator_id") else None
                        mod_text = mod.mention if mod else "unknown moderator"
                        reason_text = ev.get("reason") or "no reason given"
                        verb = "added" if ev["type"] == "manual_add" else "removed"
                        lines.append(f"{day} : {verb} {ev['amount']} by {mod_text}, {reason_text}")

                page = discord.Embed(
                    title=f"{member.display_name}'s Event Log ({target_month})",
                    description="\n".join(lines),
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                pages.append(page)

        view = make_paginator(pages, author.id)
        if slash:
            await ctx.response.send_message(embed=pages[0], view=view)
        else:
            await ctx.reply(embed=pages[0], view=view, mention_author=False)

    @prefix_sm.command(name="add")
    @commands.guild_only()
    async def prefix_sm_add(self, ctx: commands.Context, member: discord.Member, amount: int, *, reason: str = None):
        await self._adjust(ctx, member, amount, reason, add=True, slash=False)

    @smessages_group.command(name="add", description="Add to a staff member's message count for today")
    @app_commands.guild_only()
    @app_commands.describe(member="Member to adjust", amount="Amount to add", reason="Optional reason")
    async def slash_sm_add(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: str = None):
        await self._adjust(interaction, member, amount, reason, add=True, slash=True)

    @prefix_sm.command(name="remove")
    @commands.guild_only()
    async def prefix_sm_remove(self, ctx: commands.Context, member: discord.Member, amount: int, *, reason: str = None):
        await self._adjust(ctx, member, amount, reason, add=False, slash=False)

    @smessages_group.command(name="remove", description="Remove from a staff member's message count for today")
    @app_commands.guild_only()
    @app_commands.describe(member="Member to adjust", amount="Amount to remove", reason="Optional reason")
    async def slash_sm_remove(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: str = None):
        await self._adjust(interaction, member, amount, reason, add=False, slash=True)

    async def _adjust(self, ctx, member: discord.Member, amount: int, reason: str, add: bool, slash: bool):
        guild = ctx.guild
        author = ctx.user if slash else ctx.author

        if not is_admin(author):
            await self._deny(ctx, slash)
            return

        data = load_data()
        gd = get_guild_data(data, str(guild.id))
        md = get_member_data(gd, str(member.id))
        tz = get_tz(str(guild.id))
        dkey = day_key(tz)
        day_entry = get_day_entry(md, dkey)

        day_entry["manual"] += amount if add else -amount
        day_entry["events"].append({
            "type": "manual_add" if add else "manual_remove",
            "amount": amount,
            "reason": reason,
            "moderator_id": str(author.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        save_data(data)

        verb = "Added" if add else "Removed"
        prep = "to" if add else "from"
        embed = discord.Embed(
            description=f"{verb} **{amount}** {prep} {member.mention}'s message count today.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        if slash:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="slb", aliases=["sleaderboard"])
    @commands.guild_only()
    async def prefix_slb(self, ctx: commands.Context, mode: str = "monthly", month: str = None):
        await self._leaderboard(ctx, mode, month, slash=False)

    @app_commands.command(name="sleaderboard", description="Show the staff message leaderboard")
    @app_commands.guild_only()
    @app_commands.describe(mode="daily or monthly", month="Month in YYYY-MM format, admin only for past months")
    @app_commands.choices(mode=[
        app_commands.Choice(name="daily", value="daily"),
        app_commands.Choice(name="monthly", value="monthly")
    ])
    async def slash_slb(self, interaction: discord.Interaction, mode: str = "monthly", month: str = None):
        await self._leaderboard(interaction, mode, month, slash=True)

    async def _leaderboard(self, ctx, mode: str, month: str, slash: bool):
        guild = ctx.guild
        author = ctx.user if slash else ctx.author

        data = load_data()
        gd = get_guild_data(data, str(guild.id))

        if not is_staff_or_admin(author, gd):
            await self._deny(ctx, slash)
            return

        tz = get_tz(str(guild.id))
        mode = mode.lower()

        if mode == "daily":
            dkey = day_key(tz)
            rows = []
            for uid, md in gd["members"].items():
                entry = md.get("days", {}).get(dkey)
                if entry:
                    rows.append((uid, net(entry)))
            title = "Daily Staff Leaderboard"
        else:
            current_month = month_key(tz)
            target_month = month or current_month
            if target_month != current_month and not is_admin(author):
                await self._deny(ctx, slash)
                return

            rows = []
            for uid, md in gd["members"].items():
                totals = month_totals(md, target_month)
                if totals["valid"] or totals["deducted"] or totals["manual"]:
                    rows.append((uid, totals["net"]))
            title = f"Monthly Staff Leaderboard ({target_month})"

        rows.sort(key=lambda x: x[1], reverse=True)

        if not rows:
            embed = discord.Embed(description="No activity recorded for this period.", color=discord.Color.blurple())
            if slash:
                await ctx.response.send_message(embed=embed)
            else:
                await ctx.reply(embed=embed, mention_author=False)
            return

        per_page = 10
        pages = []
        for i in range(0, len(rows), per_page):
            chunk = rows[i:i + per_page]
            lines = []
            for rank, (uid, value) in enumerate(chunk, start=i + 1):
                member = guild.get_member(int(uid))
                name = member.mention if member else f"<@{uid}>"
                lines.append(f"**#{rank}** {name} : {value}")
            page = discord.Embed(
                title=title,
                description="\n".join(lines),
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            pages.append(page)

        view = make_paginator(pages, author.id)
        if slash:
            await ctx.response.send_message(embed=pages[0], view=view)
        else:
            await ctx.reply(embed=pages[0], view=view, mention_author=False)

    @commands.command(name="sroles")
    @commands.guild_only()
    async def prefix_sroles(self, ctx: commands.Context, *, roles: str):
        await self._sroles(ctx, roles, slash=False)

    @app_commands.command(name="sroles", description="Add roles to the staff list for message tracking")
    @app_commands.guild_only()
    @app_commands.describe(roles="Roles to add, space or comma separated")
    async def slash_sroles(self, interaction: discord.Interaction, roles: str):
        await self._sroles(interaction, roles, slash=True)

    async def _sroles(self, ctx, roles: str, slash: bool):
        guild = ctx.guild
        author = ctx.user if slash else ctx.author

        if not is_admin(author):
            await self._deny(ctx, slash)
            return

        data = load_data()
        gd = get_guild_data(data, str(guild.id))

        found_roles = parse_roles(guild, roles)
        if not found_roles:
            embed = discord.Embed(description="Couldn't find any of those roles.", color=discord.Color.red())
            if slash:
                await ctx.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx.reply(embed=embed, mention_author=False)
            return

        added = []
        already = []
        for role in found_roles:
            if str(role.id) in gd["staff_roles"]:
                already.append(role)
            else:
                gd["staff_roles"].append(str(role.id))
                added.append(role)

        save_data(data)

        lines = []
        if added:
            lines.append(f"Added: {', '.join(r.mention for r in added)}")
        if already:
            lines.append(f"Already added: {', '.join(r.mention for r in already)}")

        embed = discord.Embed(description="\n".join(lines), color=discord.Color.green())
        if slash:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="sblacklist")
    @commands.guild_only()
    async def prefix_sblacklist(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._blacklist(ctx, channel, add=True, slash=False)

    @app_commands.command(name="sblacklist", description="Exclude a channel from staff message tracking")
    @app_commands.guild_only()
    @app_commands.describe(channel="Channel to exclude")
    async def slash_sblacklist(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._blacklist(interaction, channel, add=True, slash=True)

    @commands.command(name="sunblacklist")
    @commands.guild_only()
    async def prefix_sunblacklist(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._blacklist(ctx, channel, add=False, slash=False)

    @app_commands.command(name="sunblacklist", description="Re-include a channel in staff message tracking")
    @app_commands.guild_only()
    @app_commands.describe(channel="Channel to re-include")
    async def slash_sunblacklist(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._blacklist(interaction, channel, add=False, slash=True)

    async def _blacklist(self, ctx, channel: discord.TextChannel, add: bool, slash: bool):
        guild = ctx.guild
        author = ctx.user if slash else ctx.author

        if not is_admin(author):
            await self._deny(ctx, slash)
            return

        data = load_data()
        gd = get_guild_data(data, str(guild.id))
        cid = str(channel.id)

        if add:
            if cid in gd["blacklisted_channels"]:
                desc = f"{channel.mention} is already blacklisted."
            else:
                gd["blacklisted_channels"].append(cid)
                save_data(data)
                desc = f"{channel.mention} is now excluded from staff message tracking."
        else:
            if cid not in gd["blacklisted_channels"]:
                desc = f"{channel.mention} isn't blacklisted."
            else:
                gd["blacklisted_channels"].remove(cid)
                save_data(data)
                desc = f"{channel.mention} will be tracked again."

        embed = discord.Embed(description=desc, color=discord.Color.green())
        if slash:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.reply(embed=embed, mention_author=False)

    @commands.group(name="sconfig", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_sconfig(self, ctx: commands.Context):
        pass

    @prefix_sconfig.command(name="view")
    @commands.guild_only()
    async def prefix_sconfig_view(self, ctx: commands.Context):
        await self._config_view(ctx, slash=False)

    sconfig_group = app_commands.Group(name="sconfig", description="View staff message tracking configuration")

    @sconfig_group.command(name="view", description="View staff roles and blacklisted channels")
    @app_commands.guild_only()
    async def slash_sconfig_view(self, interaction: discord.Interaction):
        await self._config_view(interaction, slash=True)

    async def _config_view(self, ctx, slash: bool):
        guild = ctx.guild
        author = ctx.user if slash else ctx.author

        if not is_admin(author):
            await self._deny(ctx, slash)
            return

        data = load_data()
        gd = get_guild_data(data, str(guild.id))

        roles_text = ", ".join(f"<@&{r}>" for r in gd["staff_roles"]) or "None set"
        channels_text = ", ".join(f"<#{c}>" for c in gd["blacklisted_channels"]) or "None"

        embed = discord.Embed(
            title="Staff Message Tracking Config",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Staff Roles", value=roles_text, inline=False)
        embed.add_field(name="Blacklisted Channels", value=channels_text, inline=False)

        if slash:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="shelp")
    @commands.guild_only()
    async def prefix_shelp(self, ctx: commands.Context):
        await self._shelp(ctx, slash=False)

    @app_commands.command(name="shelp", description="Show staff message tracking commands")
    @app_commands.guild_only()
    async def slash_shelp(self, interaction: discord.Interaction):
        await self._shelp(interaction, slash=True)

    async def _shelp(self, ctx, slash: bool):
        guild = ctx.guild
        author = ctx.user if slash else ctx.author
        data = load_data()
        gd = get_guild_data(data, str(guild.id))

        admin = is_admin(author)
        staff = is_staff(author, gd)

        if not admin and not staff:
            if slash:
                container = discord.ui.Container(
                    discord.ui.TextDisplay("You don't have permission to use this."),
                    accent_color=discord.Color.red()
                )

                class _Deny(discord.ui.LayoutView):
                    pass

                view = _Deny(timeout=None)
                view.add_item(container)
                await ctx.response.send_message(view=view, ephemeral=True)
            return

        staff_lines = [
            "`/smessage` / `*sm`\nAlias: `smsg`, `smessage`\n-# Check your or another staff member's message stats",
            "`/sleaderboard` / `*slb`\nAlias: `sleaderboard`\n-# Show the daily or monthly staff leaderboard"
        ]

        admin_lines = [
            "`/smessages logs` / `*sm logs`\n-# View a staff member's valid, deducted, and manual message log",
            "`/smessages add` / `*sm add`\n-# Add to a staff member's message count for today",
            "`/smessages remove` / `*sm remove`\n-# Remove from a staff member's message count for today",
            "`/sroles` / `*sroles`\n-# Add roles to the staff list",
            "`/sblacklist` / `*sblacklist`\n-# Exclude a channel from tracking",
            "`/sunblacklist` / `*sunblacklist`\n-# Re-include a channel in tracking",
            "`/sconfig view` / `*sconfig view`\n-# View staff roles and blacklisted channels"
        ]

        children = [discord.ui.TextDisplay("## Staff Message Tracking Help")]
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay("\n\n".join(staff_lines)))

        if admin:
            children.append(discord.ui.Separator())
            children.append(discord.ui.TextDisplay("\n\n".join(admin_lines)))

        container = discord.ui.Container(*children, accent_color=discord.Color.gold())

        class _HelpView(discord.ui.LayoutView):
            pass

        view = _HelpView(timeout=180)
        view.add_item(container)

        if slash:
            await ctx.response.send_message(view=view, ephemeral=True)
        else:
            await ctx.reply(view=view, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffMessages(bot))