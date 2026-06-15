import discord
from discord.ext import commands, tasks
from discord import app_commands
from src.services.render import skin_exists


class Skins(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        return super().cog_unload()


    @app_commands.command(name="setskin", description="Set skin for player")
    async def set_skin(self, interaction: discord.Interaction, osu_name: str, skin_id: str):
        try:
            player = await self.bot.osu.user(user=osu_name)
        except:
            await interaction.response.send_message("Invalid player name. Please try again.")
            return

        skin_exist = await skin_exists(skin_id)
        if not skin_exist:
            await interaction.response.send_message(
                f"Skin {skin_id} does not exist on o!rdr. "
                "Please upload your skin to https://ordr.issou.best/skins/upload"
                " or provide the correct skin ID."
            )
            return

        await self.bot.db['skins'].update_one(
            {'user_id': player.id},
            {'$set': {'username': osu_name, 'user_id': player.id, 'skin_id': skin_id}},
            upsert=True
        )
        await interaction.response.send_message(f"Skin {skin_id} set for {osu_name}.")


async def setup(bot):
    await bot.add_cog(Skins(bot))
