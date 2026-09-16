import discord
from discord.ext import commands
import asyncio
import time
from datetime import datetime, timezone
from deep_translator import GoogleTranslator
from ddgs import DDGS
import yt_dlp

DDG_BACKENDS = ["html", "lite", "api"]


class Search(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="translate", aliases=["tr"])
    async def translate(self, ctx: commands.Context, target_lang: str, *, text: str = None):
        if not text:
            if ctx.message.reference:
                try:
                    ref_msg = ctx.message.reference.resolved
                    if ref_msg is None or isinstance(ref_msg, discord.DeletedReferencedMessage):
                        ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                    text = ref_msg.content
                except Exception:
                    text = None

            if not text:
                embed = discord.Embed(
                    description=f"<:NX_Error:1526717414522490950> Provide text to translate, or reply to a message containing text.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                await ctx.reply(embed=embed, mention_author=False)
                return

        try:
            result = await asyncio.to_thread(
                GoogleTranslator(source="auto", target=target_lang).translate, text
            )
        except Exception:
            embed = discord.Embed(
                description=f"<:NX_Error:1526717414522490950> Couldn't translate that. Make sure `{target_lang}` is a valid language code or name (e.g. `es`, `french`, `ja`).",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        embed = discord.Embed(
            title="🌐 Translation",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Original", value=text[:1000], inline=False)
        embed.add_field(name=f"Translated ({target_lang})", value=result[:1000], inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="search", aliases=["google"])
    async def search(self, ctx: commands.Context, *, query: str):
        async with ctx.typing():
            results, error = await asyncio.to_thread(self._ddg_search, query)

        if not results:
            desc = f"<:NX_Error:1526717414522490950> DuckDuckGo is rate limiting right now, please try again in a few seconds." if error == "ratelimit" else f"<:NX_Error:1526717414522490950> No results found."
            embed = discord.Embed(description=desc, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            await ctx.reply(embed=embed, mention_author=False)
            return

        embed = discord.Embed(
            title=f"🔎 Search Results: {query}",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        for r in results[:5]:
            title = r.get("title", "No title")[:256]
            link = r.get("href", "")
            snippet = r.get("body", "")[:200]
            embed.add_field(name=title, value=f"{snippet}\n{link}", inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    def _ddg_search(self, query: str):
        last_error = None
        for backend in DDG_BACKENDS:
            for attempt in range(2):
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(query, max_results=5, backend=backend))
                    if results:
                        return results, None
                except Exception as e:
                    last_error = e
                    if "ratelimit" in str(e).lower() or "202" in str(e):
                        last_error = "ratelimit"
                        time.sleep(1.5)
                        continue
                    break
        return [], ("ratelimit" if last_error == "ratelimit" else None)

    @commands.command(name="yt", aliases=["youtube"])
    async def yt(self, ctx: commands.Context, *, query: str):
        async with ctx.typing():
            try:
                results = await asyncio.to_thread(self._yt_search, query)
            except Exception:
                results = []

        if not results:
            embed = discord.Embed(description=f"<:NX_Error:1526717414522490950> No results found.", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            await ctx.reply(embed=embed, mention_author=False)
            return

        embed = discord.Embed(
            title=f"▶️ YouTube Results: {query}",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        for entry in results[:5]:
            title = entry.get("title", "Unknown title")[:256]
            url = entry.get("webpage_url") or entry.get("url") or f"https://youtu.be/{entry.get('id', '')}"
            uploader = entry.get("uploader", "Unknown channel")
            duration = entry.get("duration")
            dur_str = self._format_duration(duration) if duration else "Live/Unknown"
            embed.add_field(name=title, value=f"{uploader} • {dur_str}\n{url}", inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    def _yt_search(self, query: str):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "default_search": "ytsearch5",
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            return info.get("entries", []) if info else []

    def _format_duration(self, seconds: int) -> str:
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


async def setup(bot: commands.Bot):
    await bot.add_cog(Search(bot))
    