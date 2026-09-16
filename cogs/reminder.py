import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import time

DATA_FILE = "reminders.json"

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminders = self.load_data()
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return []

        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return []

    def save_data(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.reminders, f, indent=4)

    def parse_time(self, time_str: str):
        units = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400
        }

        try:
            unit = time_str[-1]
            amount = int(time_str[:-1])
            return amount * units[unit]
        except:
            return None

    @commands.command()
    async def rm(self, ctx, time_input: str, *, reason: str = None):
        seconds = self.parse_time(time_input)

        if not seconds:
            msg = await ctx.reply("❌ Invalid time format. Use s, m, h, or d.")
            await msg.delete(delay=5)
            return

        if seconds < 30:
            msg = await ctx.reply("❌ Minimum reminder time is 30 seconds.")
            await msg.delete(delay=5)
            return

        now = int(time.time())
        remind_at = now + seconds

        reminder_data = {
            "user_id": ctx.author.id,
            "reason": reason,
            "created_at": now,
            "remind_at": remind_at,
            "message_link": ctx.message.jump_url
        }

        self.reminders.append(reminder_data)
        self.save_data()

        msg = await ctx.reply(f"<a:NX_Check:1526717230396735598> **OK! I will Remind You in <t:{remind_at}:R>!**")
        await asyncio.sleep(5)

        try:
            await msg.delete()
        except:
            pass

        await ctx.message.add_reaction("<a:NX_Check:1526717230396735598>")

    @tasks.loop(seconds=5)
    async def check_reminders(self):
        now = int(time.time())
        to_remove = []

        for reminder in self.reminders:
            if now >= reminder["remind_at"]:
                user = self.bot.get_user(reminder["user_id"])
                if not user:
                    try:
                        user = await self.bot.fetch_user(reminder["user_id"])
                    except:
                        continue

                embed = discord.Embed(
                    description=f"{user.mention} your reminder is here!",
                    color=discord.Color.blurple()
                )

                if reminder["reason"]:
                    embed.add_field(
                        name="Reason",
                        value=reminder["reason"],
                        inline=False
                    )

                embed.add_field(
                    name="Created",
                    value=f"<t:{reminder['created_at']}:R>",
                    inline=False
                )

                embed.add_field(
                    name="Original Message",
                    value=reminder["message_link"] or "Unknown",
                    inline=False
                )

                try:
                    await user.send(embed=embed)
                except:
                    pass

                to_remove.append(reminder)

        if to_remove:
            for r in to_remove:
                self.reminders.remove(r)

            self.save_data()

    @check_reminders.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Reminder(bot))