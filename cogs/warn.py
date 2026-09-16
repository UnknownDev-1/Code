import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import re
from datetime import datetime, timezone, timedelta

DATA_FILE = "warnings.json"

COLOR_SUCCESS = 0x57F287
COLOR_ERROR = 0xED4245
COLOR_INFO = 0x5865F2
COLOR_WARN = 0xFEE75C

NO_PING = discord.AllowedMentions.none()

WARNS_PER_PAGE = 6
USERS_PER_PAGE = 12

WEBHOOK_NAME = "Warn Logs"


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
        "log_webhook_id": None,
        "log_webhook_token": None,
        "moderator_roles": [],
        "warnings": {},
        "banned_words": [],
        "ignored_channels": [],
        "next_id": 1
    })
    gd.setdefault("moderator_roles", [])
    gd.setdefault("log_webhook_id", None)
    gd.setdefault("log_webhook_token", None)
    gd.setdefault("banned_words", [])
    gd.setdefault("ignored_channels", [])
    if "moderator_role" in gd:
        old = gd.pop("moderator_role")
        if old and old not in gd["moderator_roles"]:
            gd["moderator_roles"].append(old)
    return gd


def simple_view(text: str, color: int = COLOR_INFO) -> discord.ui.LayoutView:
    class _V(discord.ui.LayoutView):
        container = discord.ui.Container(
            discord.ui.TextDisplay(text),
            accent_color=color
        )
    return _V()


def is_moderator(guild: discord.Guild, user: discord.Member, gd: dict) -> bool:
    if user.guild_permissions.administrator:
        return True
    role_ids = [int(r) for r in gd.get("moderator_roles", [])]
    return any(r.id in role_ids for r in user.roles)


async def get_log_webhook(bot: commands.Bot, channel: discord.TextChannel, gd: dict, guild_id: str, data: dict):
    wid = gd.get("log_webhook_id")
    wtoken = gd.get("log_webhook_token")
    if wid and wtoken:
        return discord.Webhook.partial(int(wid), wtoken, client=bot)

    try:
        existing = await channel.webhooks()
        for wh in existing:
            if wh.name == WEBHOOK_NAME and wh.user and wh.user.id == bot.user.id:
                gd["log_webhook_id"] = str(wh.id)
                gd["log_webhook_token"] = wh.token
                save_data(data)
                return discord.Webhook.partial(wh.id, wh.token, client=bot)
    except discord.Forbidden:
        return None

    try:
        avatar_bytes = await bot.user.display_avatar.read()
        new_wh = await channel.create_webhook(name=WEBHOOK_NAME, avatar=avatar_bytes, reason="Warning system logging")
        gd["log_webhook_id"] = str(new_wh.id)
        gd["log_webhook_token"] = new_wh.token
        save_data(data)
        return discord.Webhook.partial(new_wh.id, new_wh.token, client=bot)
    except discord.Forbidden:
        return None
    except discord.HTTPException:
        return None


async def post_log(bot: commands.Bot, guild: discord.Guild, gd: dict, guild_id: str, text: str, color: int):
    log_channel_id = gd.get("log_channel")
    if not log_channel_id:
        return
    channel = guild.get_channel(int(log_channel_id))
    if not channel:
        return

    data = load_data()
    fresh_gd = get_guild_data(data, guild_id)
    webhook = await get_log_webhook(bot, channel, fresh_gd, guild_id, data)

    if webhook:
        try:
            await webhook.send(view=simple_view(text, color), allowed_mentions=NO_PING)
            return
        except discord.NotFound:
            fresh_gd["log_webhook_id"] = None
            fresh_gd["log_webhook_token"] = None
            save_data(data)
        except Exception:
            pass

    try:
        await channel.send(view=simple_view(text, color), allowed_mentions=NO_PING)
    except Exception:
        pass


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


def parse_warn_ids(raw: str) -> list:
    tokens = re.split(r"[,\s]+", raw.strip())
    ids = []
    for token in tokens:
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            continue
    return ids


async def issue_warning(bot: commands.Bot, guild: discord.Guild, moderator, member: discord.Member, reason: str, source: str = "manual"):
    data = load_data()
    gd = get_guild_data(data, str(guild.id))

    warn_id = gd["next_id"]
    gd["next_id"] += 1
    entry = {
        "id": warn_id,
        "reason": reason,
        "moderator_id": str(moderator.id) if moderator else "automod",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source
    }
    gd["warnings"].setdefault(str(member.id), []).append(entry)
    save_data(data)

    total = len(gd["warnings"][str(member.id)])

    try:
        dm = await member.create_dm()
        await dm.send(view=simple_view(
            f"## You Have Been Warned\n"
            f"**Server:** {guild.name}\n"
            f"**Reason:** {reason}\n"
            f"**Warn ID:** {warn_id}",
            COLOR_WARN
        ))
    except Exception:
        pass

    moderator_line = moderator.mention if moderator else "Automod System"

    await post_log(
        bot, guild, gd, str(guild.id),
        f"## New Warning\n"
        f"**Member:** {member.mention} (`{member.id}`)\n"
        f"**Moderator:** {moderator_line}\n"
        f"**Reason:** {reason}\n"
        f"**Warn ID:** {warn_id}\n"
        f"**Total Warnings:** {total}",
        COLOR_WARN
    )

    return warn_id, total


def remove_warnings(gd: dict, member_id: str, warn_ids: list) -> tuple:
    warns = gd["warnings"].get(member_id, [])
    removed = []
    not_found = []
    for wid in warn_ids:
        match = next((w for w in warns if w["id"] == wid), None)
        if match:
            warns.remove(match)
            removed.append(wid)
        else:
            not_found.append(wid)
    return removed, not_found


def chunk_list(items: list, size: int) -> list:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_warn_pages(guild: discord.Guild, target: discord.Member, warns: list) -> list:
    groups = chunk_list(warns, WARNS_PER_PAGE)
    pages = []
    for group in groups:
        lines = [f"## Warnings for {target.name}\n**Total:** {len(warns)}\n"]
        for w in group:
            if w["moderator_id"] == "automod":
                mod_name = "Automod System"
            else:
                mod = guild.get_member(int(w["moderator_id"]))
                mod_name = mod.mention if mod else f"<@{w['moderator_id']}>"
            ts = f"<t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:R>"
            lines.append(f"**#{w['id']}** {w['reason']}\nBy {mod_name}, {ts}")
        pages.append("\n\n".join(lines))
    return pages


def build_users_list_pages(guild: discord.Guild, entries: list) -> list:
    groups = chunk_list(entries, USERS_PER_PAGE)
    pages = []
    for group in groups:
        lines = ["## Members With Warnings\n"]
        for uid, count in group:
            member = guild.get_member(int(uid))
            name = member.mention if member else f"<@{uid}>"
            lines.append(f"{name} : **{count}** warning(s)")
        pages.append("\n".join(lines))
    return pages


class Pager(discord.ui.LayoutView):
    def __init__(self, pages: list, author_id: int, color: int = COLOR_INFO):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0
        self.author_id = author_id
        self.color = color
        self.message = None
        self._render()

    def _render(self):
        self.clear_items()
        children = [discord.ui.TextDisplay(self.pages[self.current])]

        if len(self.pages) > 1:
            prev_btn = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=self.current == 0)
            prev_btn.callback = self.on_prev
            next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, disabled=self.current >= len(self.pages) - 1)
            next_btn.callback = self.on_next

            nav = discord.ui.ActionRow()
            nav.add_item(prev_btn)
            nav.add_item(next_btn)

            children.append(discord.ui.Separator(visible=True))
            children.append(discord.ui.TextDisplay(f"-# Page {self.current + 1}/{len(self.pages)}"))
            children.append(nav)

        container = discord.ui.Container(*children, accent_color=self.color)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                view=simple_view("This isn't your menu.", COLOR_ERROR),
                ephemeral=True,
                allowed_mentions=NO_PING
            )
            return False
        return True

    async def on_prev(self, interaction: discord.Interaction):
        self.current -= 1
        self._render()
        await interaction.response.edit_message(view=self)

    async def on_next(self, interaction: discord.Interaction):
        self.current += 1
        self._render()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        for child in self.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class ConfirmClearView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild_id: str, member_id: str, member_name: str, author_id: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.member_id = member_id
        self.author_id = author_id
        self.message = None

        confirm_btn = discord.ui.Button(label="Confirm Clear", style=discord.ButtonStyle.danger)
        confirm_btn.callback = self.confirm
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = self.cancel

        btn_row = discord.ui.ActionRow()
        btn_row.add_item(confirm_btn)
        btn_row.add_item(cancel_btn)

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"Are you sure you want to clear all warnings for **{member_name}**? This cannot be undone."),
            discord.ui.Separator(visible=True),
            btn_row,
            accent_color=COLOR_WARN
        )
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                view=simple_view("This isn't your menu.", COLOR_ERROR),
                ephemeral=True,
                allowed_mentions=NO_PING
            )
            return False
        return True

    async def confirm(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild_data(data, self.guild_id)
        count = len(gd["warnings"].get(self.member_id, []))
        gd["warnings"][self.member_id] = []
        save_data(data)
        for child in self.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            view=simple_view(f"Cleared {count} warning(s).", COLOR_SUCCESS),
            ephemeral=True,
            allowed_mentions=NO_PING
        )
        await post_log(self.bot, interaction.guild, gd, self.guild_id, f"All warnings cleared for <@{self.member_id}> by {interaction.user.mention} ({count} removed)", COLOR_WARN)

    async def cancel(self, interaction: discord.Interaction):
        for child in self.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        for child in self.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


def find_banned_word(content: str, banned_words: list):
    for word in banned_words:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])"
        if re.search(pattern, content, re.IGNORECASE):
            return word
    return None


def automod_detect_view(member: discord.Member, banned_word: str) -> discord.ui.LayoutView:
    class _V(discord.ui.LayoutView):
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"## <:NX_Error:1526717414522490950> Banned Word Detected\n"
                f"{member.mention}, your message was removed for containing a banned word: `{banned_word}`.\n"
                f"Using it again within **1 hour** will result in a **1 hour timeout**."
            ),
            accent_color=COLOR_ERROR
        )
    return _V()


def automod_timeout_channel_view(member: discord.Member, banned_word: str) -> discord.ui.LayoutView:
    class _V(discord.ui.LayoutView):
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"## <:NX_Error:1526717414522490950> Member Timed Out\n"
                f"{member.mention}, you used the banned word `{banned_word}` again within **1 hour** "
                f"and have been timed out for **1 hour**."
            ),
            accent_color=COLOR_ERROR
        )
    return _V()


async def safe_send_channel(channel, view: discord.ui.LayoutView):
    try:
        allowed = discord.AllowedMentions(users=True, roles=False, everyone=False)
        await channel.send(view=view, allowed_mentions=allowed)
    except Exception:
        pass


async def safe_send_dm(member: discord.Member, view: discord.ui.LayoutView):
    try:
        dm = await member.create_dm()
        await dm.send(view=view)
    except Exception:
        pass


class Warnings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    warns_group = app_commands.Group(name="warns", description="View and manage warning history")
    words_group = app_commands.Group(name="words", description="Manage automod banned words", parent=warns_group)
    ignore_group = app_commands.Group(name="ignore", description="Manage automod-ignored channels", parent=warns_group)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        data = load_data()
        gd = get_guild_data(data, str(message.guild.id))

        banned_words = gd.get("banned_words", [])
        if not banned_words:
            return

        if is_moderator(message.guild, message.author, gd):
            return

        if str(message.channel.id) in gd.get("ignored_channels", []):
            return

        matched_word = find_banned_word(message.content, banned_words)
        if not matched_word:
            return

        try:
            await message.delete()
        except Exception:
            pass

        now = datetime.now(timezone.utc)
        existing = gd["warnings"].get(str(message.author.id), [])
        recent_automod = [
            w for w in existing
            if w.get("source") == "automod"
            and (now - datetime.fromisoformat(w["timestamp"])) < timedelta(hours=1)
        ]
        should_timeout = len(recent_automod) > 0

        channel_mention = message.channel.mention
        warn_reason = f"Used a banned word/phrase (`{matched_word}`) in {channel_mention}."
        if should_timeout:
            warn_reason += " Repeat offense within 1 hour."

        await issue_warning(self.bot, message.guild, None, message.author, warn_reason, source="automod")

        if should_timeout:
            await safe_send_channel(message.channel, automod_timeout_channel_view(message.author, matched_word))

            try:
                await message.author.timeout(timedelta(hours=1), reason="Automod: repeated banned word usage within 1 hour")
                timeout_applied = True
            except Exception:
                timeout_applied = False

            await safe_send_dm(message.author, simple_view(
                f"## You Have Been Timed Out\n"
                f"**Server:** {message.guild.name}\n"
                f"**Duration:** 1 hour\n"
                f"**Reason:** Used the banned word `{matched_word}` again within 1 hour.",
                COLOR_ERROR
            ))

            await post_log(
                self.bot, message.guild, gd, str(message.guild.id),
                f"## Member Timed Out\n"
                f"**Member:** {message.author.mention} (`{message.author.id}`)\n"
                f"**Duration:** 1 hour\n"
                f"**Applied:** {'Yes' if timeout_applied else 'Failed (missing permissions)'}\n"
                f"**Reason:** Repeated banned word usage within 1 hour",
                COLOR_ERROR
            )
        else:
            await safe_send_channel(message.channel, automod_detect_view(message.author, matched_word))

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.guild_only()
    @app_commands.describe(user="Member to warn", reason="Reason for the warning")
    async def slash_warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not is_moderator(interaction.guild, interaction.user, gd):
            await interaction.response.send_message(
                view=simple_view("You don't have permission to warn members.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        warn_id, total = await issue_warning(self.bot, interaction.guild, interaction.user, user, reason)

        await interaction.response.send_message(
            view=simple_view(
                f"## Member Warned\n"
                f"**Member:** {user.mention}\n"
                f"**Reason:** {reason}\n"
                f"**Warn ID:** {warn_id}\n"
                f"**Total Warnings:** {total}",
                COLOR_SUCCESS
            ),
            ephemeral=True, allowed_mentions=NO_PING
        )

    @warns_group.command(name="clear", description="Clear all warnings for a member.")
    @app_commands.guild_only()
    @app_commands.describe(user="Member to clear warnings for")
    async def slash_warns_clear(self, interaction: discord.Interaction, user: discord.Member):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not is_moderator(interaction.guild, interaction.user, gd):
            await interaction.response.send_message(
                view=simple_view("You don't have permission to clear warnings.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        warns = gd["warnings"].get(str(user.id), [])
        if not warns:
            await interaction.response.send_message(
                view=simple_view(f"{user.name} has no warnings to clear.", COLOR_INFO),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        view = ConfirmClearView(self.bot, str(interaction.guild_id), str(user.id), user.name, interaction.user.id)
        await interaction.response.send_message(view=view, ephemeral=True, allowed_mentions=NO_PING)
        view.message = await interaction.original_response()

    @warns_group.command(name="remove", description="Remove one or more warnings from a member.")
    @app_commands.guild_only()
    @app_commands.describe(user="Member the warning(s) belong to", id="Warn ID(s) to remove, space or comma separated (e.g. 1,3,5)")
    async def slash_warns_remove(self, interaction: discord.Interaction, user: discord.Member, id: str):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not is_moderator(interaction.guild, interaction.user, gd):
            await interaction.response.send_message(
                view=simple_view("You don't have permission to remove warnings.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        warn_ids = parse_warn_ids(id)
        if not warn_ids:
            await interaction.response.send_message(
                view=simple_view("Provide at least one valid warn ID (e.g. `3` or `1,2,3`).", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        removed, not_found = remove_warnings(gd, str(user.id), warn_ids)
        save_data(data)

        lines = []
        if removed:
            lines.append(f"Removed warning(s) {', '.join(f'#{i}' for i in removed)} from {user.mention}.")
        if not_found:
            lines.append(f"Not found: {', '.join(f'#{i}' for i in not_found)}")

        await interaction.response.send_message(
            view=simple_view("\n".join(lines), COLOR_SUCCESS if removed else COLOR_ERROR),
            ephemeral=True, allowed_mentions=NO_PING
        )

        if removed:
            await post_log(
                self.bot, interaction.guild, gd, str(interaction.guild_id),
                f"Warning(s) {', '.join(f'#{i}' for i in removed)} removed from {user.mention} by {interaction.user.mention}",
                COLOR_INFO
            )

    @warns_group.command(name="view", description="View a member's warning history.")
    @app_commands.guild_only()
    @app_commands.describe(user="Member to check")
    async def slash_warns_view(self, interaction: discord.Interaction, user: discord.Member):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if user.id != interaction.user.id and not is_moderator(interaction.guild, interaction.user, gd):
            await interaction.response.send_message(
                view=simple_view("You don't have permission to view other members' warnings.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        warns = gd["warnings"].get(str(user.id), [])
        if not warns:
            await interaction.response.send_message(
                view=simple_view(f"**{user.name}** has no warnings.", COLOR_INFO),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        pages = build_warn_pages(interaction.guild, user, warns)
        view = Pager(pages, interaction.user.id, COLOR_INFO)
        await interaction.response.send_message(view=view, ephemeral=True, allowed_mentions=NO_PING)
        view.message = await interaction.original_response()

    @warns_group.command(name="list", description="Show all members with warnings and how many each has.")
    @app_commands.guild_only()
    async def slash_warns_list(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not is_moderator(interaction.guild, interaction.user, gd):
            await interaction.response.send_message(
                view=simple_view("You don't have permission to use this.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        entries = [(uid, len(w)) for uid, w in gd["warnings"].items() if w]
        if not entries:
            await interaction.response.send_message(
                view=simple_view("No members have warnings in this server.", COLOR_INFO),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        entries.sort(key=lambda x: x[1], reverse=True)
        pages = build_users_list_pages(interaction.guild, entries)
        view = Pager(pages, interaction.user.id, COLOR_INFO)
        await interaction.response.send_message(view=view, ephemeral=True, allowed_mentions=NO_PING)
        view.message = await interaction.original_response()

    @warns_group.command(name="log", description="Set the log channel and/or moderator roles for warnings.")
    @app_commands.guild_only()
    @app_commands.describe(
        log_channel="Channel where warning actions will be logged (a Warn Logs webhook will be created here)",
        roles="Roles that can manage warnings, space or comma separated (mentions, IDs, or names)"
    )
    async def slash_warns_log(self, interaction: discord.Interaction, log_channel: discord.TextChannel = None, roles: str = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=simple_view("You need Administrator permission to use this.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if log_channel is None and roles is None:
            current_roles = [f"<@&{r}>" for r in gd.get("moderator_roles", [])]
            channel_line = f"<#{gd['log_channel']}>" if gd.get("log_channel") else "Not set"
            lines = [
                f"**Log Channel:** {channel_line}",
                f"**Moderator Roles:** {', '.join(current_roles) if current_roles else 'None'}"
            ]
            await interaction.response.send_message(view=simple_view("\n".join(lines), COLOR_INFO), ephemeral=True, allowed_mentions=NO_PING)
            return

        lines = ["Configuration updated."]
        if log_channel:
            if str(log_channel.id) != gd.get("log_channel"):
                gd["log_webhook_id"] = None
                gd["log_webhook_token"] = None
            gd["log_channel"] = str(log_channel.id)
            lines.append(f"Log Channel: {log_channel.mention}")
        if roles:
            found_roles = parse_roles(interaction.guild, roles)
            if not found_roles:
                await interaction.response.send_message(
                    view=simple_view("Couldn't find any of those roles.", COLOR_ERROR),
                    ephemeral=True, allowed_mentions=NO_PING
                )
                return
            gd["moderator_roles"] = [str(r.id) for r in found_roles]
            lines.append(f"Moderator Roles: {', '.join(r.mention for r in found_roles)}")

        save_data(data)
        await interaction.response.send_message(view=simple_view("\n".join(lines), COLOR_SUCCESS), ephemeral=True, allowed_mentions=NO_PING)

    @words_group.command(name="add", description="Add a word or phrase to the automod banned list.")
    @app_commands.guild_only()
    @app_commands.describe(word="Word or phrase to ban")
    async def slash_words_add(self, interaction: discord.Interaction, word: str):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=simple_view("You need Administrator permission to manage banned words.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        if word.lower() in [w.lower() for w in gd["banned_words"]]:
            await interaction.response.send_message(
                view=simple_view(f"`{word}` is already banned.", COLOR_INFO),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        gd["banned_words"].append(word)
        save_data(data)
        await interaction.response.send_message(
            view=simple_view(f"Added `{word}` to the banned word list.", COLOR_SUCCESS),
            ephemeral=True, allowed_mentions=NO_PING
        )

    @words_group.command(name="remove", description="Remove a word or phrase from the automod banned list.")
    @app_commands.guild_only()
    @app_commands.describe(word="Word or phrase to unban")
    async def slash_words_remove(self, interaction: discord.Interaction, word: str):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=simple_view("You need Administrator permission to manage banned words.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        match = next((w for w in gd["banned_words"] if w.lower() == word.lower()), None)
        if not match:
            await interaction.response.send_message(
                view=simple_view(f"`{word}` isn't in the banned word list.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        gd["banned_words"].remove(match)
        save_data(data)
        await interaction.response.send_message(
            view=simple_view(f"Removed `{match}` from the banned word list.", COLOR_SUCCESS),
            ephemeral=True, allowed_mentions=NO_PING
        )

    @words_group.command(name="list", description="Show all automod banned words.")
    @app_commands.guild_only()
    async def slash_words_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=simple_view("You need Administrator permission to use this.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not gd["banned_words"]:
            await interaction.response.send_message(
                view=simple_view("No banned words set.", COLOR_INFO),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        listed = "\n".join(f"- `{w}`" for w in gd["banned_words"])
        await interaction.response.send_message(
            view=simple_view(f"**Banned Words**\n{listed}", COLOR_INFO),
            ephemeral=True, allowed_mentions=NO_PING
        )

    @ignore_group.command(name="add", description="Let a channel bypass automod entirely, no deletion, warning, or timeout.")
    @app_commands.guild_only()
    @app_commands.describe(channel="Channel to ignore")
    async def slash_ignore_add(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=simple_view("You need Administrator permission to manage ignored channels.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        if str(channel.id) in gd["ignored_channels"]:
            await interaction.response.send_message(
                view=simple_view(f"{channel.mention} is already ignored.", COLOR_INFO),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        gd["ignored_channels"].append(str(channel.id))
        save_data(data)
        await interaction.response.send_message(
            view=simple_view(f"{channel.mention} will no longer be checked by automod.", COLOR_SUCCESS),
            ephemeral=True, allowed_mentions=NO_PING
        )

    @ignore_group.command(name="remove", description="Remove a channel from the automod ignore list.")
    @app_commands.guild_only()
    @app_commands.describe(channel="Channel to stop ignoring")
    async def slash_ignore_remove(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=simple_view("You need Administrator permission to manage ignored channels.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        if str(channel.id) not in gd["ignored_channels"]:
            await interaction.response.send_message(
                view=simple_view(f"{channel.mention} isn't on the ignore list.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        gd["ignored_channels"].remove(str(channel.id))
        save_data(data)
        await interaction.response.send_message(
            view=simple_view(f"{channel.mention} will be checked by automod again.", COLOR_SUCCESS),
            ephemeral=True, allowed_mentions=NO_PING
        )

    @ignore_group.command(name="list", description="Show all channels ignored by automod.")
    @app_commands.guild_only()
    async def slash_ignore_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=simple_view("You need Administrator permission to use this.", COLOR_ERROR),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        data = load_data()
        gd = get_guild_data(data, str(interaction.guild_id))

        if not gd["ignored_channels"]:
            await interaction.response.send_message(
                view=simple_view("No channels are ignored.", COLOR_INFO),
                ephemeral=True, allowed_mentions=NO_PING
            )
            return

        listed = "\n".join(f"- <#{cid}>" for cid in gd["ignored_channels"])
        await interaction.response.send_message(
            view=simple_view(f"**Ignored Channels**\n{listed}", COLOR_INFO),
            ephemeral=True, allowed_mentions=NO_PING
        )

    @commands.command(name="warn")
    @commands.guild_only()
    async def prefix_warn(self, ctx: commands.Context, user: discord.Member, *, reason: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not is_moderator(ctx.guild, ctx.author, gd):
            await ctx.reply(view=simple_view("You don't have permission to warn members.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        warn_id, total = await issue_warning(self.bot, ctx.guild, ctx.author, user, reason)

        await ctx.reply(
            view=simple_view(
                f"## Member Warned\n"
                f"**Member:** {user.mention}\n"
                f"**Reason:** {reason}\n"
                f"**Warn ID:** {warn_id}\n"
                f"**Total Warnings:** {total}",
                COLOR_SUCCESS
            ),
            mention_author=False, allowed_mentions=NO_PING
        )

    @commands.group(name="warns", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_warns(self, ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if target.id != ctx.author.id and not is_moderator(ctx.guild, ctx.author, gd):
            await ctx.reply(view=simple_view("You don't have permission to view other members' warnings.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        warns = gd["warnings"].get(str(target.id), [])
        if not warns:
            await ctx.reply(view=simple_view(f"**{target.name}** has no warnings.", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)
            return

        pages = build_warn_pages(ctx.guild, target, warns)
        view = Pager(pages, ctx.author.id, COLOR_INFO)
        view.message = await ctx.reply(view=view, mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns.command(name="list")
    @commands.guild_only()
    async def prefix_warns_list(self, ctx: commands.Context):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not is_moderator(ctx.guild, ctx.author, gd):
            await ctx.reply(view=simple_view("You don't have permission to use this.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        entries = [(uid, len(w)) for uid, w in gd["warnings"].items() if w]
        if not entries:
            await ctx.reply(view=simple_view("No members have warnings in this server.", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)
            return

        entries.sort(key=lambda x: x[1], reverse=True)
        pages = build_users_list_pages(ctx.guild, entries)
        view = Pager(pages, ctx.author.id, COLOR_INFO)
        view.message = await ctx.reply(view=view, mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns.command(name="clear")
    @commands.guild_only()
    async def prefix_warns_clear(self, ctx: commands.Context, user: discord.Member):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not is_moderator(ctx.guild, ctx.author, gd):
            await ctx.reply(view=simple_view("You don't have permission to clear warnings.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        warns = gd["warnings"].get(str(user.id), [])
        if not warns:
            await ctx.reply(view=simple_view(f"{user.name} has no warnings to clear.", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)
            return

        view = ConfirmClearView(self.bot, str(ctx.guild.id), str(user.id), user.name, ctx.author.id)
        view.message = await ctx.reply(view=view, mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns.command(name="remove")
    @commands.guild_only()
    async def prefix_warns_remove(self, ctx: commands.Context, user: discord.Member, *, ids: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not is_moderator(ctx.guild, ctx.author, gd):
            await ctx.reply(view=simple_view("You don't have permission to remove warnings.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        warn_ids = parse_warn_ids(ids)
        if not warn_ids:
            await ctx.reply(view=simple_view("Provide at least one valid warn ID (e.g. `3` or `1,2,3`).", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        removed, not_found = remove_warnings(gd, str(user.id), warn_ids)
        save_data(data)

        lines = []
        if removed:
            lines.append(f"Removed warning(s) {', '.join(f'#{i}' for i in removed)} from {user.mention}.")
        if not_found:
            lines.append(f"Not found: {', '.join(f'#{i}' for i in not_found)}")

        await ctx.reply(
            view=simple_view("\n".join(lines), COLOR_SUCCESS if removed else COLOR_ERROR),
            mention_author=False, allowed_mentions=NO_PING
        )

        if removed:
            await post_log(self.bot, ctx.guild, gd, str(ctx.guild.id), f"Warning(s) {', '.join(f'#{i}' for i in removed)} removed from {user.mention} by {ctx.author.mention}", COLOR_INFO)

    @prefix_warns.group(name="words", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_warns_words(self, ctx: commands.Context):
        if not ctx.author.guild_permissions.administrator:
            await ctx.reply(view=simple_view("You need Administrator permission to use this.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not gd["banned_words"]:
            await ctx.reply(view=simple_view("No banned words set.", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)
            return

        listed = "\n".join(f"- `{w}`" for w in gd["banned_words"])
        await ctx.reply(view=simple_view(f"**Banned Words**\n{listed}", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns_words.command(name="add")
    @commands.guild_only()
    async def prefix_warns_words_add(self, ctx: commands.Context, *, word: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not ctx.author.guild_permissions.administrator:
            await ctx.reply(view=simple_view("You need Administrator permission to manage banned words.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        if word.lower() in [w.lower() for w in gd["banned_words"]]:
            await ctx.reply(view=simple_view(f"`{word}` is already banned.", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)
            return

        gd["banned_words"].append(word)
        save_data(data)
        await ctx.reply(view=simple_view(f"Added `{word}` to the banned word list.", COLOR_SUCCESS), mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns_words.command(name="remove")
    @commands.guild_only()
    async def prefix_warns_words_remove(self, ctx: commands.Context, *, word: str):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not ctx.author.guild_permissions.administrator:
            await ctx.reply(view=simple_view("You need Administrator permission to manage banned words.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        match = next((w for w in gd["banned_words"] if w.lower() == word.lower()), None)
        if not match:
            await ctx.reply(view=simple_view(f"`{word}` isn't in the banned word list.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        gd["banned_words"].remove(match)
        save_data(data)
        await ctx.reply(view=simple_view(f"Removed `{match}` from the banned word list.", COLOR_SUCCESS), mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns.group(name="ignore", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_warns_ignore(self, ctx: commands.Context):
        if not ctx.author.guild_permissions.administrator:
            await ctx.reply(view=simple_view("You need Administrator permission to use this.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not gd["ignored_channels"]:
            await ctx.reply(view=simple_view("No channels are ignored.", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)
            return

        listed = "\n".join(f"- <#{cid}>" for cid in gd["ignored_channels"])
        await ctx.reply(view=simple_view(f"**Ignored Channels**\n{listed}", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns_ignore.command(name="add")
    @commands.guild_only()
    async def prefix_warns_ignore_add(self, ctx: commands.Context, channel: discord.TextChannel):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not ctx.author.guild_permissions.administrator:
            await ctx.reply(view=simple_view("You need Administrator permission to manage ignored channels.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        if str(channel.id) in gd["ignored_channels"]:
            await ctx.reply(view=simple_view(f"{channel.mention} is already ignored.", COLOR_INFO), mention_author=False, allowed_mentions=NO_PING)
            return

        gd["ignored_channels"].append(str(channel.id))
        save_data(data)
        await ctx.reply(view=simple_view(f"{channel.mention} will no longer be checked by automod.", COLOR_SUCCESS), mention_author=False, allowed_mentions=NO_PING)

    @prefix_warns_ignore.command(name="remove")
    @commands.guild_only()
    async def prefix_warns_ignore_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        data = load_data()
        gd = get_guild_data(data, str(ctx.guild.id))

        if not ctx.author.guild_permissions.administrator:
            await ctx.reply(view=simple_view("You need Administrator permission to manage ignored channels.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        if str(channel.id) not in gd["ignored_channels"]:
            await ctx.reply(view=simple_view(f"{channel.mention} isn't on the ignore list.", COLOR_ERROR), mention_author=False, allowed_mentions=NO_PING)
            return

        gd["ignored_channels"].remove(str(channel.id))
        save_data(data)
        await ctx.reply(view=simple_view(f"{channel.mention} will be checked by automod again.", COLOR_SUCCESS), mention_author=False, allowed_mentions=NO_PING)


async def setup(bot: commands.Bot):
    await bot.add_cog(Warnings(bot))