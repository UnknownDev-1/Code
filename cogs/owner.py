import discord
import os
import sys
import re
import asyncio
import subprocess
import aiohttp
from bs4 import BeautifulSoup
from discord.ext import commands
from discord import app_commands


class ReloadView(discord.ui.LayoutView):
    def __init__(self, reloaded, failed, synced_count, author):
        super().__init__(timeout=None)

        reloaded_text = "\n".join(f"- `{c}`" for c in reloaded) if reloaded else "`None`"
        failed_text = "\n".join(f"- `{c}`" for c in failed) if failed else "`None`"

        container = discord.ui.Container(
            discord.ui.TextDisplay("### <a:NX_Check:1526717230396735598> Reload Complete"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**Reloaded Cogs**\n{reloaded_text}"),
            discord.ui.TextDisplay(f"**Failed to Reload**\n{failed_text}"),
            discord.ui.TextDisplay(f"**Synced Commands:** `{synced_count}`"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"-# Requested by {author}"),
            accent_color=discord.Color.green()
        )
        self.add_item(container)


class RestartView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay("### <:restart:1517202843998748722> Restart Successful!"),
            discord.ui.TextDisplay("Bot is restarting now..."),
            accent_color=discord.Color.orange()
        )
        self.add_item(container)


class PipListView(discord.ui.LayoutView):
    def __init__(self, packages: list, author):
        super().__init__(timeout=None)

        chunks = []
        current = ""
        for pkg in packages:
            line = f"- `{pkg}`"
            if len(current) + len(line) + 1 > 3500 and current:
                chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)

        children = [discord.ui.TextDisplay(f"### <a:NX_Check:1526717230396735598> Installed Packages ({len(packages)})")]
        children.append(discord.ui.Separator())
        for chunk in chunks[:3]:
            children.append(discord.ui.TextDisplay(chunk))
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# Requested by {author}"))

        container = discord.ui.Container(*children, accent_color=discord.Color.blurple())
        self.add_item(container)


class PipActionView(discord.ui.LayoutView):
    def __init__(self, action: str, package: str, success: bool, output: str, author, req_note: str = None):
        super().__init__(timeout=None)

        verb = "Installed" if action == "install" else "Uninstalled"
        emoji = "<a:NX_Check:1526717230396735598>" if success else "<:NX_Error:1526717414522490950>"
        color = discord.Color.green() if success else discord.Color.red()

        output_trimmed = output.strip()[-1500:] if output.strip() else "No output."

        children = [
            discord.ui.TextDisplay(f"### {emoji} {verb if success else f'Failed to {action}'}: `{package}`"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"```\n{output_trimmed}\n```")
        ]

        if success and req_note:
            children.append(discord.ui.Separator())
            children.append(discord.ui.TextDisplay(f"**requirements.txt:** {req_note}"))

        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# Requested by {author}"))

        container = discord.ui.Container(*children, accent_color=color)
        self.add_item(container)


class PipSearchView(discord.ui.LayoutView):
    def __init__(self, query: str, results: list, author):
        super().__init__(timeout=None)

        if not results:
            children = [discord.ui.TextDisplay(f"### <:NX_Error:1526717414522490950> No results found for `{query}`")]
        else:
            lines = []
            for r in results[:10]:
                lines.append(f"**{r['name']}** `{r['version']}`\n{r['description']}")
            children = [discord.ui.TextDisplay(f"### <a:NX_Check:1526717230396735598> Search Results: `{query}`")]
            children.append(discord.ui.Separator())
            children.append(discord.ui.TextDisplay("\n\n".join(lines)[:3900]))

        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# Requested by {author}"))

        container = discord.ui.Container(*children, accent_color=discord.Color.blurple())
        self.add_item(container)


class PipInfoView(discord.ui.LayoutView):
    def __init__(self, found: bool, info: dict, package: str, author):
        super().__init__(timeout=None)

        if not found:
            children = [discord.ui.TextDisplay(f"### <:NX_Error:1526717414522490950> Package `{package}` not found on PyPI")]
        else:
            summary = info.get("summary") or "No description available."
            children = [
                discord.ui.TextDisplay(f"### <a:NX_Check:1526717230396735598> {info.get('name')} `{info.get('version')}`"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"**Summary**\n{summary}\n\n"
                    f"**Author:** {info.get('author') or 'Unknown'}\n"
                    f"**License:** {info.get('license') or 'Unknown'}\n"
                    f"**Homepage:** {info.get('homepage') or 'None'}"
                )
            ]

        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# Requested by {author}"))

        color = discord.Color.blurple() if found else discord.Color.red()
        container = discord.ui.Container(*children, accent_color=color)
        self.add_item(container)


class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return (
            await self.bot.is_owner(ctx.author)
        )

    @commands.command(name="reload")
    async def reload(self, ctx):
        """Reload all cogs and sync slash commands."""
        reloaded_cogs = []
        failed_cogs = []

        for ext in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(ext)
                reloaded_cogs.append(ext)
            except Exception as e:
                failed_cogs.append(f"{ext} — {type(e).__name__}: {e}")

        try:
            synced = await self.bot.tree.sync()
            synced_count = len(synced)
        except Exception:
            synced_count = 0

        view = ReloadView(reloaded_cogs, failed_cogs, synced_count, ctx.author)
        await ctx.reply(view=view, mention_author=False)

    @commands.command(name="restart")
    async def restart(self, ctx):
        """Restart the bot"""

        view = RestartView()
        await ctx.reply(view=view, mention_author=False)
        await asyncio.sleep(1)
        sys.stdout.flush()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.command(name="pips", aliases=["piplist"])
    async def pip_list(self, ctx):
        """List all installed pip packages"""
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pip", "list", "--format=freeze"],
            capture_output=True, text=True
        )

        packages = [line for line in result.stdout.strip().splitlines() if line]
        if not packages:
            packages = ["No packages found."]

        view = PipListView(packages, ctx.author)
        await ctx.reply(view=view, mention_author=False)

    def _req_base_name(self, line: str) -> str:
        match = re.match(r"^[A-Za-z0-9_.\-]+", line.strip())
        return match.group(0).lower() if match else line.strip().lower()

    def _add_to_requirements(self, package: str) -> str:
        req_path = "requirements.txt"
        lines = []
        if os.path.exists(req_path):
            with open(req_path, "r") as f:
                lines = [l.rstrip("\n") for l in f if l.strip()]

        base = self._req_base_name(package)
        for line in lines:
            if self._req_base_name(line) == base:
                return f"`{package}` is already listed, left unchanged."

        lines.append(package)
        with open(req_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return f"Added `{package}`."

    def _remove_from_requirements(self, package: str) -> str:
        req_path = "requirements.txt"
        if not os.path.exists(req_path):
            return "No requirements.txt found, nothing to update."

        with open(req_path, "r") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]

        base = self._req_base_name(package)
        new_lines = [l for l in lines if self._req_base_name(l) != base]

        if len(new_lines) == len(lines):
            return f"`{package}` wasn't listed, nothing changed."

        with open(req_path, "w") as f:
            f.write("\n".join(new_lines) + ("\n" if new_lines else ""))
        return f"Removed `{package}`."

    @commands.command(name="pipinstall")
    async def pip_install(self, ctx, package: str):
        """Install a pip package and add it to requirements.txt"""
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pip", "install", "--break-system-packages", package],
            capture_output=True, text=True
        )

        success = result.returncode == 0
        output = result.stdout if success else result.stderr
        req_note = self._add_to_requirements(package) if success else None
        view = PipActionView("install", package, success, output, ctx.author, req_note)
        await ctx.reply(view=view, mention_author=False)

    @commands.command(name="pipuninstall")
    async def pip_uninstall(self, ctx, package: str):
        """Uninstall a pip package and remove it from requirements.txt"""
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pip", "uninstall", "-y", package],
            capture_output=True, text=True
        )

        success = result.returncode == 0
        output = result.stdout if success else result.stderr
        req_note = self._remove_from_requirements(package) if success else None
        view = PipActionView("uninstall", package, success, output, ctx.author, req_note)
        await ctx.reply(view=view, mention_author=False)

    @commands.command(name="pipsearch")
    async def pip_search(self, ctx, *, query: str):
        """Search PyPI for packages matching a query"""
        results = await self._search_pypi(query)
        view = PipSearchView(query, results, ctx.author)
        await ctx.reply(view=view, mention_author=False)

    async def _search_pypi(self, query: str) -> list:
        headers = {
            "User-Agent": "NexterCloudBot/1.0",
            "Accept": "application/json"
        }

        package = query.strip()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                url = f"https://pypi.org/pypi/{package}/json"

                async with session.get(url) as resp:
                    if resp.status != 200:
                        return []

                    data = await resp.json()

            info = data.get("info", {})

            return [{
                "name": info.get("name", package),
                "version": info.get("version", "unknown"),
                "description": info.get("summary") or "No description."
            }]

        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        results = []
        for snippet in soup.select("a.package-snippet"):
            name_tag = snippet.select_one(".package-snippet__name")
            version_tag = snippet.select_one(".package-snippet__version")
            desc_tag = snippet.select_one(".package-snippet__description")
            if not name_tag:
                continue
            results.append({
                "name": name_tag.get_text(strip=True),
                "version": version_tag.get_text(strip=True) if version_tag else "unknown",
                "description": desc_tag.get_text(strip=True) if desc_tag else "No description."
            })
        return results

    @commands.command(name="pipinfo")
    async def pip_info(self, ctx, package: str):
        """Look up detailed info for an exact package name on PyPI"""
        found, info = await self._fetch_pypi_info(package)
        view = PipInfoView(found, info, package, ctx.author)
        await ctx.reply(view=view, mention_author=False)

    async def _fetch_pypi_info(self, package: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://pypi.org/pypi/{package}/json") as resp:
                    if resp.status != 200:
                        return False, {}
                    data = await resp.json()
        except Exception:
            return False, {}

        info = data.get("info", {})
        return True, {
            "name": info.get("name"),
            "version": info.get("version"),
            "summary": info.get("summary"),
            "author": info.get("author"),
            "license": info.get("license"),
            "homepage": info.get("home_page") or info.get("project_url")
        }


async def setup(bot):
    await bot.add_cog(Owner(bot))
