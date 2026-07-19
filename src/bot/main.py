import discord
import sys
from discord.ext import commands
from src.config import DISCORD_TOKEN
from src.db.mongo import db
from src.clients import osu


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=".", intents=intents)


    async def setup_hook(self):
        self.db = db
        self.osu = osu
        await self.load_extension("src.bot.cogs.general")
        await self.load_extension("src.bot.cogs.requests")
        await self.load_extension("src.bot.cogs.skins")
        await self.load_extension("src.bot.cogs.notifications")
        await self.load_extension("src.bot.cogs.jobs_feed")
        await self.load_extension("src.bot.cogs.osu")
        
        await self.tree.sync()


    async def on_ready(self):
        sys.stdout.write(f"Logged in as {self.user}\n")


Bot().run(DISCORD_TOKEN)
