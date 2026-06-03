import discord
from discord.ext import commands, tasks
from discord import app_commands
from src.config import ADMIN_USER_ID


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        return super().cog_unload()


    @app_commands.command(name = "shutdown", description = "Shutdown the bot")
    async def shutdown(self, interaction: discord.Interaction):
        if interaction.user.id == ADMIN_USER_ID:
            await interaction.response.send_message("Shutting down...", ephemeral=True)
            await self.bot.close()


async def setup(bot):
    await bot.add_cog(General(bot))
