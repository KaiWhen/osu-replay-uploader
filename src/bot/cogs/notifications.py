from discord.ext import commands, tasks
from src.db.notifications import get_unsent, mark_sent
from src.config import DISCORD_NOTIFICATION_CHANNEL_ID


class Notifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.notification_loop.start()


    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        self.notification_loop.cancel()
        return super().cog_unload()


    @tasks.loop(minutes=1)
    async def notification_loop(self):
        notifications = await get_unsent(self.bot.db)
        for notif in notifications:
            await self.channel.send(f"https://youtu.be/{notif['video_id']}")
            await mark_sent(self.bot.db, notif['_id'])


    @notification_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        self.channel = self.bot.get_channel(DISCORD_NOTIFICATION_CHANNEL_ID)


async def setup(bot):
    await bot.add_cog(Notifications(bot))
