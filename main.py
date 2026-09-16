import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="*", intents=intents, help_command=None)

TOKEN = os.getenv("TOKEN")

async def load_cogs():
    cog_folder = "./cogs"

    for filename in os.listdir(cog_folder):
        if filename.endswith(".py"):
            module_path = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(module_path)
                print(f"Loaded: {module_path}")
            except Exception as e:
                print(f"Failed to load {module_path}: {e}")

@bot.event
async def on_ready():
    activity = discord.Activity(
        type=discord.ActivityType.playing,
        name="NexterCloud"
    )
    await bot.change_presence(activity=activity)
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("Bot is ready.")

@bot.event
async def setup_hook():
    await load_cogs()
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} slash commands.")

if __name__ == "__main__":
    bot.run(TOKEN)