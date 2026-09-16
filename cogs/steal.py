import discord
from discord.ext import commands
import re
import io
import asyncio
import aiohttp
from PIL import Image
from datetime import datetime, timezone

EMOJI_PATTERN = re.compile(r"<(a?):(\w{2,32}):(\d{17,20})>")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

CREATE_DELAY = 1.5


def sanitize_emoji_name(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw).strip("_")
    if not cleaned:
        cleaned = "emoji"
    if len(cleaned) < 2:
        cleaned = (cleaned + "__")[:2]
    return cleaned[:32]


def sanitize_sticker_name(raw: str) -> str:
    cleaned = raw.strip()
    if len(cleaned) < 2:
        cleaned = (cleaned + "  ")[:2].strip() or "sticker"
    return cleaned[:30]


def extract_embed_media(message: discord.Message) -> list:
    sources = []
    seen_urls = set()

    for embed in message.embeds:
        url = None
        if embed.image and embed.image.url:
            url = embed.image.url
        elif embed.thumbnail and embed.thumbnail.url:
            url = embed.thumbnail.url

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        clean_url = url.split("?")[0]
        name = clean_url.rsplit("/", 1)[-1].rsplit(".", 1)[0] or "embed_image"
        sources.append((name, url))

    return sources


def normalize_image(data: bytes, target: str):
    img = Image.open(io.BytesIO(data))
    is_animated = getattr(img, "is_animated", False)
    max_dim = 128 if target == "emoji" else 320
    size_cap = 240 * 1024 if target == "emoji" else 480 * 1024

    if is_animated:
        return _normalize_animated(img, max_dim, size_cap), True
    return _normalize_static(img, max_dim, size_cap), False


def _normalize_static(img: Image.Image, max_dim: int, size_cap: int) -> bytes:
    for _ in range(12):
        frame = img.convert("RGBA")
        if frame.width > max_dim or frame.height > max_dim:
            frame.thumbnail((max_dim, max_dim))

        out = io.BytesIO()
        frame.save(out, format="PNG", optimize=True)
        result = out.getvalue()

        if len(result) <= size_cap or max_dim <= 16:
            return result

        max_dim = max(16, int(max_dim * 0.75))

    return result


def _normalize_animated(img: Image.Image, max_dim: int, size_cap: int) -> bytes:
    n_frames = img.n_frames
    frame_step = 1

    for _ in range(30):
        frames = []
        durations = []
        for i in range(0, n_frames, frame_step):
            img.seek(i)
            frame = img.convert("RGBA")
            if frame.width > max_dim or frame.height > max_dim:
                frame.thumbnail((max_dim, max_dim))
            frames.append(frame.quantize(colors=255))
            durations.append(img.info.get("duration", 100) * frame_step)

        if not frames:
            frame = img.convert("RGBA")
            frame.thumbnail((max_dim, max_dim))
            frames = [frame.quantize(colors=255)]
            durations = [100]

        out = io.BytesIO()
        frames[0].save(
            out, format="GIF", save_all=True, append_images=frames[1:],
            duration=durations, loop=0, disposal=2, optimize=True
        )
        result = out.getvalue()

        if len(result) <= size_cap:
            return result

        if max_dim > 32:
            max_dim = max(32, int(max_dim * 0.75))
        elif frame_step < n_frames:
            frame_step += 1
        else:
            return result

    return result


class Steal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="steal")
    @commands.has_permissions(administrator=True)
    async def steal(self, ctx: commands.Context, target: str = None):
        if target is not None and target.lower() not in ("emoji", "sticker"):
            embed = discord.Embed(
                description="<:NX_Error:1526717414522490950> Target must be `emoji` or `sticker` if provided.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        target_override = target.lower() if target else None

        if not ctx.message.reference:
            embed = discord.Embed(
                description="<:NX_Error:1526717414522490950> Reply to a message containing sticker(s), emoji(s), or image/gif attachment(s) or link(s) to steal them.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        try:
            ref_msg = ctx.message.reference.resolved
            if ref_msg is None or isinstance(ref_msg, discord.DeletedReferencedMessage):
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except Exception:
            embed = discord.Embed(
                description="<:NX_Error:1526717414522490950> Couldn't find the message you replied to.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        emoji_matches = []
        seen_ids = set()
        for animated, name, eid in EMOJI_PATTERN.findall(ref_msg.content):
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            emoji_matches.append((bool(animated), name, int(eid)))

        stickers = ref_msg.stickers

        image_sources = [
            (a.filename.rsplit(".", 1)[0], a.url)
            for a in ref_msg.attachments
            if (a.content_type and a.content_type.startswith("image/"))
            or a.filename.lower().endswith(IMAGE_EXTENSIONS)
        ]
        image_sources.extend(extract_embed_media(ref_msg))

        if not emoji_matches and not stickers and not image_sources:
            embed = discord.Embed(
                description="<:NX_Error:1526717414522490950> That message doesn't contain any stickers, custom emojis, or image/gif attachments or links.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        status_embed = discord.Embed(
            description="Stealing... this may take a moment.",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        status_msg = await ctx.reply(embed=status_embed, mention_author=False)

        results = []

        async with aiohttp.ClientSession() as session:
            for sticker_item in stickers:
                effective = target_override or "sticker"
                results.append(await self._steal_sticker(ctx.guild, session, sticker_item, effective))
                await asyncio.sleep(CREATE_DELAY)

            for animated, name, eid in emoji_matches:
                effective = target_override or "emoji"
                results.append(await self._steal_emoji(ctx.guild, session, animated, name, eid, effective))
                await asyncio.sleep(CREATE_DELAY)

            for name, url in image_sources:
                effective = target_override or "emoji"
                results.append(await self._steal_image(ctx.guild, session, name, url, effective))
                await asyncio.sleep(CREATE_DELAY)

        lines = [f"{status} **{name}**{f' : {detail}' if detail else ''}" for status, name, detail in results]

        summary = discord.Embed(
            title="Steal Results",
            description="\n".join(lines)[:4000],
            color=discord.Color.green() if all(r[0] == "<a:NX_Check:1526717230396735598>" for r in results) else discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        await status_msg.edit(embed=summary)

    async def _download(self, session: aiohttp.ClientSession, url: str) -> bytes | None:
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception:
            return None

    async def _create_emoji(self, guild: discord.Guild, name: str, data: bytes):
        clean_name = sanitize_emoji_name(name)
        for attempt in range(3):
            try:
                await guild.create_custom_emoji(name=clean_name, image=data, reason=f"Stolen emoji: {clean_name}")
                return ("<a:NX_Check:1526717230396735598>", clean_name, None)
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 2)
                    await asyncio.sleep(retry_after)
                    continue
                return ("<:NX_Error:1526717414522490950>", clean_name, str(e.text if hasattr(e, "text") else e))
            except discord.Forbidden:
                return ("<:NX_Error:1526717414522490950>", clean_name, "missing permissions")

        return ("<:NX_Error:1526717414522490950>", clean_name, "rate limited, gave up after retries")

    async def _create_sticker(self, guild: discord.Guild, name: str, description: str, emoji_tag: str, data: bytes, animated: bool):
        clean_name = sanitize_sticker_name(name)
        ext = "gif" if animated else "png"

        for attempt in range(3):
            try:
                file = discord.File(io.BytesIO(data), filename=f"{clean_name}.{ext}")
                await guild.create_sticker(
                    name=clean_name,
                    description=description or "Stolen sticker",
                    emoji=emoji_tag,
                    file=file,
                    reason=f"Stolen sticker: {clean_name}"
                )
                return ("<a:NX_Check:1526717230396735598>", clean_name, None)
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 2)
                    await asyncio.sleep(retry_after)
                    continue
                return ("<:NX_Error:1526717414522490950>", clean_name, str(e.text if hasattr(e, "text") else e))
            except discord.Forbidden:
                return ("<:NX_Error:1526717414522490950>", clean_name, "missing permissions")

        return ("<:NX_Error:1526717414522490950>", clean_name, "rate limited, gave up after retries")

    async def _steal_emoji(self, guild: discord.Guild, session: aiohttp.ClientSession, animated_guess: bool, name: str, eid: int, target: str):
        partial = discord.PartialEmoji(name=name, animated=animated_guess, id=eid)
        data = await self._download(session, str(partial.url))
        if data is None:
            return ("<:NX_Error:1526717414522490950>", name, "failed to download")

        try:
            normalized, is_animated = await asyncio.to_thread(normalize_image, data, target)
        except Exception:
            return ("<:NX_Error:1526717414522490950>", name, "failed to process image")

        if target == "sticker":
            return await self._create_sticker(guild, name, f"Converted from emoji :{name}:", "⭐", normalized, is_animated)
        return await self._create_emoji(guild, name, normalized)

    async def _steal_sticker(self, guild: discord.Guild, session: aiohttp.ClientSession, sticker_item: discord.StickerItem, target: str):
        try:
            full = await sticker_item.fetch()
        except discord.HTTPException:
            return ("<:NX_Error:1526717414522490950>", sticker_item.name, "couldn't fetch sticker details")

        if full.format is discord.StickerFormatType.lottie:
            return ("<:NX_Error:1526717414522490950>", full.name, "lottie stickers can't be copied")

        data = await self._download(session, full.url)
        if data is None:
            return ("<:NX_Error:1526717414522490950>", full.name, "failed to download")

        try:
            normalized, is_animated = await asyncio.to_thread(normalize_image, data, target)
        except Exception:
            return ("<:NX_Error:1526717414522490950>", full.name, "failed to process image")

        if target == "emoji":
            return await self._create_emoji(guild, full.name, normalized)

        description = getattr(full, "description", "") or ""
        if isinstance(full, discord.GuildSticker):
            emoji_tag = full.emoji
        else:
            tags = getattr(full, "tags", [])
            emoji_tag = tags[0] if tags else "⭐"

        return await self._create_sticker(guild, full.name, description, emoji_tag, normalized, is_animated)

    async def _steal_image(self, guild: discord.Guild, session: aiohttp.ClientSession, name: str, url: str, target: str):
        data = await self._download(session, url)
        if data is None:
            return ("<:NX_Error:1526717414522490950>", name, "failed to download")

        try:
            normalized, is_animated = await asyncio.to_thread(normalize_image, data, target)
        except Exception:
            return ("<:NX_Error:1526717414522490950>", name, "failed to process image")

        if target == "sticker":
            return await self._create_sticker(guild, name, "Stolen image", "⭐", normalized, is_animated)
        return await self._create_emoji(guild, name, normalized)


async def setup(bot: commands.Bot):
    await bot.add_cog(Steal(bot))
