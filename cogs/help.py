import discord
from discord import app_commands
from discord.ext import commands
import json
import os

WARNINGS_DATA_FILE = "warnings.json"

# Registry of known commands, built by reading through every cog.
# Each entry maps to the real command that exists in the bot. Permission tags
# are checked live against the invoking user, nothing here is just cosmetic.
# If a command exists in the bot but isn't listed here, it still shows up
# under "Other" with a generic description, see discover_unlisted() below.

COMMAND_REGISTRY = [
    # Invites
    {"name": "invites", "slash": "invites", "prefix": "invites", "aliases": ["i"],
     "category": "Invites", "permission": None,
     "description": "View invite stats for yourself or another member.", "args": "[member]"},
    {"name": "inviter", "slash": "inviter", "prefix": "inviter", "aliases": [],
     "category": "Invites", "permission": None,
     "description": "See who invited a specific member.", "args": "[member]"},
    {"name": "invited", "slash": "invited", "prefix": "invited", "aliases": [],
     "category": "Invites", "permission": None,
     "description": "See the list of members someone has invited.", "args": "[member]"},
    {"name": "inviteinfo", "slash": "inviteinfo", "prefix": "inviteinfo", "aliases": [],
     "category": "Invites", "permission": None,
     "description": "View a member's active invite codes.", "args": "[member]"},
    {"name": "addinvites", "slash": "addinvites", "prefix": "addinvites", "aliases": [],
     "category": "Invites", "permission": "manage_guild",
     "description": "Add bonus invites to a member.", "args": "<member> <amount>"},
    {"name": "removeinvites", "slash": "removeinvites", "prefix": "removeinvites", "aliases": [],
     "category": "Invites", "permission": "manage_guild",
     "description": "Remove invites from a member.", "args": "<member> <amount>"},
    {"name": "clearinvites", "slash": "clearinvites", "prefix": "clearinvites", "aliases": [],
     "category": "Invites", "permission": "manage_guild",
     "description": "Clear invite data for a member, or the whole server if no member is given.", "args": "[member]"},
    {"name": "resetmyinvites", "slash": "resetmyinvites", "prefix": "resetmyinvites", "aliases": ["rmi"],
     "category": "Invites", "permission": None,
     "description": "Clear your own invite data.", "args": ""},
    {"name": "leaderboard", "slash": "leaderboard", "prefix": "leaderboard", "aliases": ["lb"],
     "category": "Invites", "permission": None,
     "description": "Show the invite, message, or daily message leaderboard.", "args": "<invites|messages|dailymessages>"},

    # Messages
    {"name": "messages", "slash": "messages", "prefix": "messages", "aliases": ["m"],
     "category": "Messages", "permission": None,
     "description": "View message stats for yourself or another member.", "args": "[member]"},
    {"name": "addmessages", "slash": "addmessages", "prefix": "addmessages", "aliases": [],
     "category": "Messages", "permission": "manage_guild",
     "description": "Add to a member's message count.", "args": "<member> <amount>"},
    {"name": "removemessages", "slash": "removemessages", "prefix": "removemessages", "aliases": [],
     "category": "Messages", "permission": "manage_guild",
     "description": "Remove from a member's message count.", "args": "<member> <amount>"},
    {"name": "blacklistchannel", "slash": "blacklistchannel", "prefix": "blacklistchannel", "aliases": [],
     "category": "Messages", "permission": "manage_guild",
     "description": "Stop counting messages sent in a channel.", "args": "[channel]"},
    {"name": "unblacklistchannel", "slash": "unblacklistchannel", "prefix": "unblacklistchannel", "aliases": [],
     "category": "Messages", "permission": "manage_guild",
     "description": "Resume counting messages in a channel.", "args": "[channel]"},
    {"name": "blacklistedchannels", "slash": "blacklistedchannels", "prefix": "blacklistedchannels", "aliases": [],
     "category": "Messages", "permission": "manage_guild",
     "description": "List channels excluded from message counting.", "args": ""},
    {"name": "clearmessages", "slash": "clearmessages", "prefix": "clearmessages", "aliases": [],
     "category": "Messages", "permission": "manage_guild",
     "description": "Clear message data for a member, or the whole server if no member is given.", "args": "[member]"},
    {"name": "resetmymessages", "slash": "resetmymessages", "prefix": "resetmymessages", "aliases": ["rmm"],
     "category": "Messages", "permission": None,
     "description": "Clear your own message data.", "args": ""},
    {"name": "topmessages", "slash": "topmessages", "prefix": "topmessages", "aliases": [],
     "category": "Messages", "permission": None,
     "description": "Show the all time message leaderboard.", "args": ""},
    {"name": "topdailymessages", "slash": "topdailymessages", "prefix": "topdailymessages", "aliases": [],
     "category": "Messages", "permission": None,
     "description": "Show today's message leaderboard.", "args": ""},
    {"name": "accage", "slash": "accage", "prefix": "accage", "aliases": [],
     "category": "Messages", "permission": None,
     "description": "Show a member's account creation date and age.", "args": "[member]"},
    {"name": "settimezone", "slash": "settimezone", "prefix": "settimezone", "aliases": [],
     "category": "Messages", "permission": "administrator",
     "description": "Set the server's timezone for daily and weekly stats.", "args": "<timezone>"},
    {"name": "timezone", "slash": "timezone", "prefix": "timezone", "aliases": [],
     "category": "Messages", "permission": "administrator",
     "description": "View the server's current timezone setting.", "args": ""},

    # Moderation
    {"name": "warn", "slash": "warn", "prefix": "warn", "aliases": [],
     "category": "Moderation", "permission": "moderator",
     "description": "Warn a member.", "args": "<member> <reason>"},
    {"name": "warns view", "slash": "warns view", "prefix": "warns", "aliases": [],
     "category": "Moderation", "permission": None,
     "description": "View a member's warning history. Viewing your own is always allowed, viewing someone else needs Moderator role or Administrator.",
     "args": "[member]"},
    {"name": "warns list", "slash": "warns list", "prefix": "warns list", "aliases": [],
     "category": "Moderation", "permission": "moderator",
     "description": "Show every member with warnings and how many each has.", "args": ""},
    {"name": "warns clear", "slash": "warns clear", "prefix": "warns clear", "aliases": [],
     "category": "Moderation", "permission": "moderator",
     "description": "Clear all warnings for a member.", "args": "<member>"},
    {"name": "warns remove", "slash": "warns remove", "prefix": "warns remove", "aliases": [],
     "category": "Moderation", "permission": "moderator",
     "description": "Remove one or more warnings from a member by id.", "args": "<member> <id(s)>"},
    {"name": "warns log", "slash": "warns log", "prefix": None, "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Set the log channel and moderator roles for the warning system.", "args": "[channel] [roles]"},
    {"name": "warns words add", "slash": "warns words add", "prefix": "warns words add", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Add a word or phrase to the automod banned list.", "args": "<word>"},
    {"name": "warns words remove", "slash": "warns words remove", "prefix": "warns words remove", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Remove a word or phrase from the automod banned list.", "args": "<word>"},
    {"name": "warns words list", "slash": "warns words list", "prefix": "warns words", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "List all automod banned words.", "args": ""},
    {"name": "warns ignore add", "slash": "warns ignore add", "prefix": "warns ignore add", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Let a channel bypass automod entirely.", "args": "<channel>"},
    {"name": "warns ignore remove", "slash": "warns ignore remove", "prefix": "warns ignore remove", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Remove a channel from the automod ignore list.", "args": "<channel>"},
    {"name": "warns ignore list", "slash": "warns ignore list", "prefix": "warns ignore", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "List channels ignored by automod.", "args": ""},
    {"name": "nuke", "slash": None, "prefix": "nuke", "aliases": [],
     "category": "Moderation", "permission": "manage_channels",
     "description": "Clone and delete a channel to instantly clear it, asks for confirmation first.", "args": "[channel]"},
    {"name": "purge", "slash": None, "prefix": "purge", "aliases": [],
     "category": "Moderation", "permission": "manage_messages",
     "description": "Bulk delete a number of recent messages, max 100.", "args": "<amount>"},
    {"name": "hide", "slash": None, "prefix": "hide", "aliases": [],
     "category": "Moderation", "permission": "manage_channels",
     "description": "Hide the current channel from everyone.", "args": ""},
    {"name": "unhide", "slash": None, "prefix": "unhide", "aliases": [],
     "category": "Moderation", "permission": "manage_channels",
     "description": "Make the current channel visible to everyone again.", "args": ""},
    {"name": "lock", "slash": None, "prefix": "lock", "aliases": [],
     "category": "Moderation", "permission": "manage_channels",
     "description": "Lock the current channel so nobody can send messages.", "args": ""},
    {"name": "unlock", "slash": None, "prefix": "unlock", "aliases": [],
     "category": "Moderation", "permission": "manage_channels",
     "description": "Unlock the current channel.", "args": ""},
    {"name": "transcript", "slash": None, "prefix": "transcript", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Generate an HTML transcript of the current channel and send it to a user or channel.", "args": "[user|channel] [limit]"},
    {"name": "rename", "slash": None, "prefix": "rename", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Rename a channel, or the current one if none is given.", "args": "[channel] <name>"},
    {"name": "delete", "slash": None, "prefix": "delete", "aliases": [],
     "category": "Moderation", "permission": "administrator",
     "description": "Delete a channel, or the current one if none is given. Asks for confirmation first.", "args": "[channel]"},

    # Applications
    {"name": "application setup", "slash": "application setup", "prefix": None, "aliases": [],
     "category": "Applications", "permission": "administrator",
     "description": "Set the log channel and reviewer role for applications.", "args": "<channel> <role>"},
    {"name": "application manage", "slash": "application manage", "prefix": None, "aliases": [],
     "category": "Applications", "permission": "administrator",
     "description": "Create, edit, open, close, or delete applications.", "args": ""},
    {"name": "application panel", "slash": "application panel", "prefix": None, "aliases": [],
     "category": "Applications", "permission": "administrator",
     "description": "Send the application panel to a channel.", "args": "<channel>"},
    {"name": "application panel_edit", "slash": "application panel_edit", "prefix": None, "aliases": [],
     "category": "Applications", "permission": "administrator",
     "description": "Refresh an existing application panel.", "args": "<channel> <message_id>"},
    {"name": "apply", "slash": "apply", "prefix": None, "aliases": [],
     "category": "Applications", "permission": None,
     "description": "Apply for a specific application.", "args": "<application>"},

    # Automation
    {"name": "autoresponder add", "slash": "autoresponder add", "prefix": "autoresponder add", "aliases": [],
     "category": "Automation", "permission": "administrator",
     "description": "Add an automatic text response for a trigger word or phrase.", "args": "<trigger> <response>"},
    {"name": "autoresponder remove", "slash": "autoresponder remove", "prefix": "autoresponder remove", "aliases": [],
     "category": "Automation", "permission": "administrator",
     "description": "Remove an autoresponder.", "args": "<trigger>"},
    {"name": "autoresponder list", "slash": "autoresponder list", "prefix": "autoresponder", "aliases": [],
     "category": "Automation", "permission": "administrator",
     "description": "List all autoresponders.", "args": ""},
    {"name": "autoreact add", "slash": "autoreact add", "prefix": "autoreact add", "aliases": [],
     "category": "Automation", "permission": "administrator",
     "description": "Add an automatic emoji reaction for a trigger word or phrase.", "args": "<trigger> <emojis>"},
    {"name": "autoreact remove", "slash": "autoreact remove", "prefix": "autoreact remove", "aliases": [],
     "category": "Automation", "permission": "administrator",
     "description": "Remove an autoreact.", "args": "<trigger>"},
    {"name": "autoreact list", "slash": "autoreact list", "prefix": "autoreact", "aliases": [],
     "category": "Automation", "permission": "administrator",
     "description": "List all autoreacts.", "args": ""},

    # Utility
    {"name": "steal", "slash": None, "prefix": "steal", "aliases": [],
     "category": "Utility", "permission": "administrator",
     "description": "Steal emojis, stickers, images, or gifs from a replied message. Can convert between emoji and sticker.",
     "args": "[emoji|sticker]"},
    {"name": "translate", "slash": None, "prefix": "translate", "aliases": ["tr"],
     "category": "Utility", "permission": None,
     "description": "Translate text, or reply to a message to translate it.", "args": "<language> [text]"},
    {"name": "search", "slash": None, "prefix": "search", "aliases": ["google"],
     "category": "Utility", "permission": None,
     "description": "Search the web.", "args": "<query>"},
    {"name": "yt", "slash": None, "prefix": "yt", "aliases": ["youtube"],
     "category": "Utility", "permission": None,
     "description": "Search YouTube.", "args": "<query>"},
    {"name": "firstmessage", "slash": "firstmessage", "prefix": "firstmessage", "aliases": ["firstmsg"],
     "category": "Utility", "permission": None,
     "description": "Jump to the first message ever sent in a channel.", "args": "[channel]"},
    {"name": "expiry", "slash": "expiry", "prefix": "expiry", "aliases": ["expires", "exp"],
     "category": "Utility", "permission": None,
     "description": "Calculate an expiration date from a duration like 24d, 1mo, or 1y.", "args": "<duration>"},
    {"name": "ping", "slash": None, "prefix": "ping", "aliases": [],
     "category": "Utility", "permission": None,
     "description": "Check the bot's latency.", "args": ""},
    {"name": "timer", "slash": None, "prefix": "timer", "aliases": [],
     "category": "Utility", "permission": None,
     "description": "Set a timer, e.g. 10s, 5m, 1h.", "args": "<time> [name]"},
    {"name": "embed_create", "slash": "embed_create", "prefix": None, "aliases": [],
     "category": "Utility", "permission": "administrator",
     "description": "Create a new interactive embed.", "args": ""},
    {"name": "embed_copy", "slash": "embed_copy", "prefix": None, "aliases": [],
     "category": "Utility", "permission": "administrator",
     "description": "Copy and edit an existing embed by its message id.", "args": "<message_id>"},
    {"name": "embed_edit", "slash": "embed_edit", "prefix": None, "aliases": [],
     "category": "Utility", "permission": "administrator",
     "description": "Edit an existing embed by its message id.", "args": "<message_id>"},
    {"name": "rm", "slash": None, "prefix": "rm", "aliases": [],
     "category": "Utility", "permission": None,
     "description": "Set a reminder, minimum 30 seconds.", "args": "<time> [reason]"},
    {"name": "message", "slash": "message", "prefix": None, "aliases": [],
     "category": "Utility", "permission": "administrator",
     "description": "Send a message using the bot, optionally as a reply.", "args": "<content> [reply_to] [mention_reply]"},
    {"name": "message-edit", "slash": "message-edit", "prefix": None, "aliases": [],
     "category": "Utility", "permission": "administrator",
     "description": "Edit a message previously sent by the bot.", "args": "<message_id> <content>"},
    {"name": "afk", "slash": "afk", "prefix": "afk", "aliases": [],
     "category": "Utility", "permission": None,
     "description": "Set yourself as AFK, get notified when someone mentions you and welcomed back when you return.", "args": "[reason]"},

    # Owner only
    {"name": "reload", "slash": None, "prefix": "reload", "aliases": [],
     "category": "Owner", "permission": "owner",
     "description": "Reload all cogs and sync slash commands.", "args": ""},
    {"name": "restart", "slash": None, "prefix": "restart", "aliases": [],
     "category": "Owner", "permission": "owner",
     "description": "Restart the bot.", "args": ""},
    {"name": "pips", "slash": None, "prefix": "pips", "aliases": ["piplist"],
     "category": "Owner", "permission": "owner",
     "description": "List installed pip packages.", "args": ""},
    {"name": "pipinstall", "slash": None, "prefix": "pipinstall", "aliases": [],
     "category": "Owner", "permission": "owner",
     "description": "Install a pip package and add it to requirements.txt.", "args": "<package>"},
    {"name": "pipuninstall", "slash": None, "prefix": "pipuninstall", "aliases": [],
     "category": "Owner", "permission": "owner",
     "description": "Uninstall a pip package and remove it from requirements.txt.", "args": "<package>"},
    {"name": "pipsearch", "slash": None, "prefix": "pipsearch", "aliases": [],
     "category": "Owner", "permission": "owner",
     "description": "Search PyPI for packages matching a query.", "args": "<query>"},
    {"name": "pipinfo", "slash": None, "prefix": "pipinfo", "aliases": [],
     "category": "Owner", "permission": "owner",
     "description": "Look up details for an exact package name on PyPI.", "args": "<package>"},
]

CATEGORY_ORDER = ["Invites", "Messages", "Moderation", "Applications", "Automation", "Utility", "Owner", "Other"]

CATEGORY_EMOJIS = {
    "Invites": "<:NX_Link:1526755918048661516>",
    "Messages": "<a:NX_Messages:1531758364353105951>",
    "Moderation": "<a:HeadAdmin:1500123547035635894>",
    "Applications": "<:NX_Application:1531759145408004397>",
    "Automation": "<a:NX_Settings:1531757583193477400>",
    "Utility": "<:YellowBotDeveloper:1524481146862436403>",
    "Owner": "<a:crown_yellow:1412732684941135962>",
    "Other": "📦"
}

CATEGORY_BLURBS = {
    "Invites": "Invite tracking commands.",
    "Messages": "Message tracking and stats commands.",
    "Moderation": "Moderation and server management commands.",
    "Applications": "Application system commands.",
    "Automation": "Automated response commands.",
    "Utility": "General utility commands.",
    "Owner": "Bot owner commands.",
    "Other": "Uncategorized commands."
}

PERMISSION_LABELS = {
    "administrator": "Administrator",
    "manage_guild": "Manage Server",
    "manage_channels": "Manage Channels",
    "manage_messages": "Manage Messages",
    "moderator": "Moderator role or Administrator",
    "owner": "Bot Owner"
}


async def user_can_use(entry, bot: commands.Bot, guild: discord.Guild, member: discord.Member) -> bool:
    perm = entry.get("permission")
    if perm is None:
        return True
    if perm == "administrator":
        return member.guild_permissions.administrator
    if perm == "manage_guild":
        return member.guild_permissions.manage_guild
    if perm == "manage_channels":
        return member.guild_permissions.manage_channels
    if perm == "manage_messages":
        return member.guild_permissions.manage_messages
    if perm == "owner":
        return await bot.is_owner(member)
    if perm == "moderator":
        if member.guild_permissions.administrator:
            return True
        if not os.path.exists(WARNINGS_DATA_FILE):
            return False
        with open(WARNINGS_DATA_FILE, "r") as f:
            data = json.load(f)
        gd = data.get(str(guild.id), {})
        role_ids = [int(r) for r in gd.get("moderator_roles", [])]
        return any(r.id in role_ids for r in member.roles)
    return True


def format_entry(entry: dict) -> str:
    lines = []

    if entry["slash"] and entry["prefix"]:
        lines.append(f"<a:Yellow_Arrow:1528892113721495702> `/{entry['slash']}` / `*{entry['prefix']}`")
    elif entry["slash"]:
        lines.append(f"<a:Yellow_Arrow:1528892113721495702> `/{entry['slash']}`")
    elif entry["prefix"]:
        lines.append(f"<a:Yellow_Arrow:1528892113721495702> `*{entry['prefix']}`")

    if entry["aliases"]:
        alias_text = ", ".join(f"`{a}`" for a in entry["aliases"])
        lines.append(f"Alias: {alias_text}")

    desc = entry["description"]
    perm_label = PERMISSION_LABELS.get(entry.get("permission"))
    if perm_label:
        desc = f"{desc} (Requires {perm_label})"

    lines.append(f"-# {desc}")
    return "\n".join(lines)


def format_usage(entry: dict) -> str:
    usage_lines = []
    args = entry.get("args", "")
    if entry["slash"]:
        raw = f"/{entry['slash']} {args}".strip()
        usage_lines.append(f"`{raw}`")
    if entry["prefix"]:
        raw = f"*{entry['prefix']} {args}".strip()
        usage_lines.append(f"`{raw}`")
    return "\n".join(usage_lines)


async def get_visible_categories(bot: commands.Bot, guild: discord.Guild, member: discord.Member) -> dict:
    visible = {}
    for entry in COMMAND_REGISTRY:
        if not await user_can_use(entry, bot, guild, member):
            continue
        visible.setdefault(entry["category"], []).append(entry)
    return visible


def chunk_text(text: str, limit: int = 3800) -> list:
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""
    for block in text.split("\n\n"):
        if len(current) + len(block) + 2 > limit and current:
            chunks.append(current)
            current = block
        else:
            current = current + "\n\n" + block if current else block
    if current:
        chunks.append(current)
    return chunks


HOME_VALUE = "__home__"


class CategorySelect(discord.ui.Select):
    def __init__(self, categories: list, current: str = None):
        options = [
            discord.SelectOption(label="Home", value=HOME_VALUE, emoji="<:NX_Home:1531759626394144938>", default=(current is None))
        ]
        for cat in categories:
            options.append(
                discord.SelectOption(label=cat, value=cat, emoji=CATEGORY_EMOJIS.get(cat), default=(cat == current))
            )
        super().__init__(placeholder="Choose a category...", options=options, custom_id="help_category_select")

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        selected = self.values[0]
        if selected == HOME_VALUE:
            await view.show_home(interaction)
        else:
            await view.show_category(interaction, selected)


class HelpView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, member: discord.Member, visible_categories: dict):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.member = member
        self.visible_categories = visible_categories
        self.message = None
        self.current_category = None
        self._render_home()

    def _sorted_categories(self):
        return [c for c in CATEGORY_ORDER if c in self.visible_categories]

    def _render_home(self):
        self.clear_items()
        self.current_category = None

        avatar_url = str(self.bot.user.display_avatar.url)
        header = discord.ui.Section(
            discord.ui.TextDisplay(f"## {self.bot.user.name} Help"),
            accessory=discord.ui.Thumbnail(media=avatar_url)
        )

        intro = f"I'm {self.bot.user.name}, a Discord bot specially for this server. Browse the categories below..."

        categories = self._sorted_categories()
        category_lines = []
        total_commands = 0
        for cat in categories:
            count = len(self.visible_categories.get(cat, []))
            total_commands += count
            emoji = CATEGORY_EMOJIS.get(cat, "")
            category_lines.append(f"{emoji} **{cat}** : {count} command{'s' if count != 1 else ''}")

        totals_line = f"<a:Yellow_Dot:1531788907887198309> **Total Categories:** {len(categories)}  **Total Commands:** {total_commands}"

        outro = (
            "Pick a category from below to see the available commands. "
            "You can also do `*help <command>` or `/help command:<command>` to look up a specific command."
        )

        home_body = intro + "\n\n" + totals_line + "\n\n" + ("\n".join(category_lines) if category_lines else "No commands available to you.")

        container = discord.ui.Container(
            header,
            discord.ui.Separator(),
            discord.ui.TextDisplay(home_body),
            discord.ui.Separator(),
            discord.ui.TextDisplay(outro),
            accent_color=discord.Color.gold()
        )

        if categories:
            select_row = discord.ui.ActionRow()
            select_row.add_item(CategorySelect(categories))
            container.add_item(select_row)

        self.add_item(container)

    def _render_category(self, category: str):
        self.clear_items()
        self.current_category = category

        entries = self.visible_categories.get(category, [])
        avatar_url = str(self.bot.user.display_avatar.url)
        emoji = CATEGORY_EMOJIS.get(category, "")
        header = discord.ui.Section(
            discord.ui.TextDisplay(f"## {emoji} {category} Commands"),
            accessory=discord.ui.Thumbnail(media=avatar_url)
        )

        blurb = CATEGORY_BLURBS.get(category, "")

        body = "\n\n".join(format_entry(e) for e in entries)
        chunks = chunk_text(body)

        children = [
            header,
            discord.ui.TextDisplay(f"-# {blurb}") if blurb else None,
            discord.ui.Separator(),
        ]
        children = [c for c in children if c is not None]

        for chunk in chunks:
            children.append(discord.ui.TextDisplay(chunk))

        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# Showing {len(entries)} command{'s' if len(entries) != 1 else ''}"))

        container = discord.ui.Container(*children, accent_color=discord.Color.gold())

        categories = self._sorted_categories()
        if categories:
            select_row = discord.ui.ActionRow()
            select_row.add_item(CategorySelect(categories, current=category))
            container.add_item(select_row)

        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id:
            await interaction.response.send_message("This help menu isn't yours, run the command yourself to get your own.", ephemeral=True)
            return False
        return True

    async def show_category(self, interaction: discord.Interaction, category: str):
        self._render_category(category)
        await interaction.response.edit_message(view=self)

    async def show_home(self, interaction: discord.Interaction):
        self._render_home()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        for item in self.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


def find_command(query: str) -> dict:
    query = query.strip().lower()
    for entry in COMMAND_REGISTRY:
        names = [entry["name"].lower()]
        if entry["slash"]:
            names.append(entry["slash"].lower())
        if entry["prefix"]:
            names.append(entry["prefix"].lower())
        names.extend(a.lower() for a in entry["aliases"])

        if query in names:
            return entry
    return None


class HelpSearchView(discord.ui.LayoutView):
    def __init__(self, entry: dict):
        super().__init__(timeout=None)

        usage = format_usage(entry)
        perm_label = PERMISSION_LABELS.get(entry.get("permission"))

        lines = [f"## {entry['name']}", entry["description"]]
        if entry["aliases"]:
            lines.append(f"**Aliases:** {', '.join(f'`{a}`' for a in entry['aliases'])}")
        lines.append(f"**Usage:**\n{usage}")
        if perm_label:
            lines.append(f"**Requires:** {perm_label}")

        container = discord.ui.Container(
            discord.ui.TextDisplay("\n\n".join(lines)),
            accent_color=discord.Color.gold()
        )
        self.add_item(container)


class NotFoundView(discord.ui.LayoutView):
    def __init__(self, query: str):
        super().__init__(timeout=None)
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"No command called `{query}` was found."),
            accent_color=discord.Color.red()
        )
        self.add_item(container)


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help")
    async def prefix_help(self, ctx: commands.Context, *, query: str = None):
        if query:
            await self._search(ctx, query, slash=False)
            return

        visible = await get_visible_categories(self.bot, ctx.guild, ctx.author)
        view = HelpView(self.bot, ctx.guild, ctx.author, visible)
        view.message = await ctx.reply(view=view, mention_author=False)

    @app_commands.command(name="help", description="Show the help menu, or look up a specific command")
    @app_commands.describe(command="Command name to look up directly")
    async def slash_help(self, interaction: discord.Interaction, command: str = None):
        if command:
            await self._search(interaction, command, slash=True)
            return

        visible = await get_visible_categories(self.bot, interaction.guild, interaction.user)
        view = HelpView(self.bot, interaction.guild, interaction.user, visible)
        await interaction.response.send_message(view=view)
        view.message = await interaction.original_response()

    async def _search(self, ctx, query: str, slash: bool):
        guild = ctx.guild if not slash else ctx.guild
        member = ctx.author if not slash else ctx.user

        entry = find_command(query)
        allowed = entry is not None and await user_can_use(entry, self.bot, guild, member)

        if not allowed:
            view = NotFoundView(query)
        else:
            view = HelpSearchView(entry)

        if slash:
            await ctx.response.send_message(view=view, ephemeral=True)
        else:
            await ctx.reply(view=view, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))