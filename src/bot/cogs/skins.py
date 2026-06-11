import discord
from discord.ext import commands
from discord import app_commands
from src.services.render import skin_exists
from src.config import ADMIN_USER_ID


class Skins(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(name="setskin", description="Set skin for player")
    async def set_skin(self, interaction: discord.Interaction, osu_name: str, skin_id: str):
        try:
            player = await self.bot.osu.user(user=osu_name)
        except:
            await interaction.response.send_message("Invalid player name. Please try again.")
            return

        if not skin_exists(skin_id):
            await interaction.response.send_message("Skin does not exist on o!rdr.")
            return

        await self.bot.db['skins'].update_one(
            {'user_id': player.id},
            {'$set': {'username': osu_name, 'user_id': player.id, 'skin_id': skin_id}},
            upsert=True
        )
        await interaction.response.send_message(f"Skin {skin_id} set for {osu_name}.")


async def setup(bot):
    await bot.add_cog(Skins(bot))
