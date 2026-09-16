EMOJIS = {
    "success": "<a:success:REPLACE_ID>",
    "error": "<:error:REPLACE_ID>",
    "warning": "<:warning:REPLACE_ID>",
    "info": "<:info:REPLACE_ID>",
    "loading": "<a:loading:REPLACE_ID>",
    "arrow": "<:arrow:REPLACE_ID>",

    "invite": "<:invite:REPLACE_ID>",
    "inviter": "<:inviter:REPLACE_ID>",
    "invited": "<:invited:REPLACE_ID>",
    "join": "<:join:REPLACE_ID>",
    "leave": "<:leave:REPLACE_ID>",
    "fake": "<:fake:REPLACE_ID>",
    "bonus": "<:bonus:REPLACE_ID>",

    "dot": "<:dot:REPLACE_ID>",
    "message": "<:message:REPLACE_ID>",
    "chart": "<:chart:REPLACE_ID>",
    "channel": "<:channel:REPLACE_ID>",
    "blacklist": "<:blacklist:REPLACE_ID>",
    "daily": "<:daily:REPLACE_ID>",

    "gold": "<:gold:REPLACE_ID>",
    "silver": "<:silver:REPLACE_ID>",
    "bronze": "<:bronze:REPLACE_ID>",
    "crown": "<:crown:REPLACE_ID>",

    "ping": "<:ping:REPLACE_ID>",
    "bot": "<:bot:REPLACE_ID>",
    "stats": "<:stats:REPLACE_ID>",
    "clock": "<:clock:REPLACE_ID>",
    "server": "<:server:REPLACE_ID>",
    "memory": "<:memory:REPLACE_ID>",
    "cpu": "<:cpu:REPLACE_ID>",
    "add": "<:add:REPLACE_ID>",
    "remove": "<:remove:REPLACE_ID>",
    "clear": "<:clear:REPLACE_ID>",
    "reset": "<:reset:REPLACE_ID>",

    "help": "<:help:REPLACE_ID>",
    "home": "<:home:REPLACE_ID>",
    "tracking_cat": "<:tracking_cat:REPLACE_ID>",
    "utility_cat": "<:utility_cat:REPLACE_ID>",
    "msg_cat": "<:msg_cat:REPLACE_ID>",
}

_FALLBACKS = {
    "dot": "•",
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️",
    "loading": "⏳", "arrow": "➜", "invite": "🔗", "inviter": "👤",
    "invited": "📋", "join": "📥", "leave": "📤", "fake": "🚫",
    "bonus": "⭐", "message": "💬", "chart": "📊", "channel": "#️⃣",
    "blacklist": "🔇", "daily": "📅", "gold": "🥇", "silver": "🥈",
    "bronze": "🥉", "crown": "👑", "ping": "📡", "bot": "🤖",
    "stats": "📈", "clock": "🕐", "server": "🖥️", "memory": "🧠",
    "cpu": "⚙️", "add": "➕", "remove": "➖", "clear": "🗑️",
    "reset": "🔄", "help": "❓", "home": "🏠", "tracking_cat": "🔍",
    "utility_cat": "🔧", "msg_cat": "💬",
}

def e(name: str) -> str:
    val = EMOJIS.get(name, "")
    if "REPLACE_ID" in val:
        return _FALLBACKS.get(name, "•")
    return val
    