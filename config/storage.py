import json, os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATA_FILE = "data.json"

_SCHEMA = {
    "invites": {},
    "messages": {},
    "blacklisted_channels": {},
    "guild_settings": {},
}

def load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        for k, v in _SCHEMA.items():
            data.setdefault(k, v)
        return data
    return {k: {} for k in _SCHEMA}

def save(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_guild_timezone(data: dict, guild_id: str) -> str:
    return data.get("guild_settings", {}).get(guild_id, {}).get("timezone", "UTC")

def set_guild_timezone(data: dict, guild_id: str, tz_name: str):
    data.setdefault("guild_settings", {}).setdefault(guild_id, {})["timezone"] = tz_name

def is_valid_timezone(tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False

def _now_in(tz_name: str) -> datetime:
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz)

def today(tz_name: str = "UTC") -> str:
    return _now_in(tz_name).date().isoformat()

def get_invite_record(data: dict, guild_id: str, user_id: str) -> dict:
    data["invites"].setdefault(guild_id, {})
    data["invites"][guild_id].setdefault(user_id, {
        "regular": 0,
        "left": 0,
        "fake": 0,
        "bonus": 0,
        "rejoins": 0,
        "invited_users": [],
    })
    rec = data["invites"][guild_id][user_id]
    rec.setdefault("rejoins", 0)
    return rec

def effective_invites(rec: dict) -> int:
    return rec["regular"] - rec["left"] - rec["fake"] + rec["bonus"]

def get_msg_record(data: dict, guild_id: str, user_id: str) -> dict:
    data["messages"].setdefault(guild_id, {})
    data["messages"][guild_id].setdefault(user_id, {
        "username": "",
        "count": 0,
        "daily": {},
        "weekly": {},
    })
    rec = data["messages"][guild_id][user_id]
    rec.setdefault("weekly", {})
    return rec

def week_key(tz_name: str = "UTC") -> str:
    d = _now_in(tz_name).date()
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"

def is_blacklisted(data: dict, guild_id: str, channel_id: str) -> bool:
    return channel_id in data.get("blacklisted_channels", {}).get(guild_id, [])
