import discord
from config.emojis import e

YELLOW = 0xFFD700

def medal(i: int) -> str:
    return [e("gold"), e("silver"), e("bronze")][i] if i < 3 else f"{i+1} {e('dot')}"

class PaginatorView(discord.ui.View):
    def __init__(self, pages: list, author_id: int):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0
        self.author_id = author_id
        self._sync()

    def _sync(self):
        n = len(self.pages)
        self.first_btn.disabled = self.current == 0
        self.prev_btn.disabled = self.current == 0
        self.stop_btn.disabled = False
        self.next_btn.disabled = self.current >= n - 1
        self.last_btn.disabled = self.current >= n - 1

    async def _auth(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _go(self, interaction: discord.Interaction, page: int):
        self.current = page
        self._sync()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="<<", style=discord.ButtonStyle.grey)
    async def first_btn(self, i, b):
        if await self._auth(i): await self._go(i, 0)

    @discord.ui.button(label="<", style=discord.ButtonStyle.grey)
    async def prev_btn(self, i, b):
        if await self._auth(i): await self._go(i, self.current - 1)

    @discord.ui.button(label="■", style=discord.ButtonStyle.red)
    async def stop_btn(self, i, b):
        if not await self._auth(i): return
        for item in self.children: item.disabled = True
        await i.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label=">", style=discord.ButtonStyle.grey)
    async def next_btn(self, i, b):
        if await self._auth(i): await self._go(i, self.current + 1)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.grey)
    async def last_btn(self, i, b):
        if await self._auth(i): await self._go(i, len(self.pages) - 1)

    async def on_timeout(self):
        for item in self.children: item.disabled = True

def make_paginator(pages: list, author_id: int) -> PaginatorView:
    view = PaginatorView(pages, author_id)
    if len(pages) == 1:
        for item in view.children: item.disabled = True
    return view