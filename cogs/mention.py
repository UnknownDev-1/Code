import discord
from discord.ext import commands


class MentionResponder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        stripped = message.content.strip()
        bot_mentions = (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>")

        if stripped not in bot_mentions:
            return

        text = (
            f"👋 **Hey.** I am **{self.bot.user.mention}!**\n"
            f"- My prefix is `*`.\n"
            f"  - Do `*help` or `/help` for more info."
        )

        await message.reply(text, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(MentionResponder(bot))
    