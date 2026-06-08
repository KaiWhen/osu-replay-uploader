import discord
import json
import hashlib
from bson import ObjectId
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from src.db.jobs import get_ongoing_jobs
from src.config import DISCORD_APPROVAL_CHANNEL_ID
from src.utils import sort_mods


class JobsFeed(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.jobs_feed_loop.start()


    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        self.jobs_feed_loop.cancel()
        return super().cog_unload()


    @tasks.loop(seconds=15)
    async def jobs_feed_loop(self):
        #channel = self.bot.get_channel(DISCORD_APPROVAL_CHANNEL_ID)
        channel = self.bot.get_channel(1106553041836052501)
        active_jobs = await get_ongoing_jobs(self.bot.db)
        for job in active_jobs:
            if job['discord_message_id'] < 0:
                embed = await self._build_job_embed(job)
                hash = self.embed_hash(embed)
                message = await channel.send(content=f"**Ongoing job for score {job['score_id']}**", embed=embed)
                await self.bot.db['jobs'].update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "discord_message_id": message.id,
                        "discord_message_hash": hash
                    }}
                )
            else:
                try:
                    message = await channel.fetch_message(job['discord_message_id'])
                    embed = await self._build_job_embed(job)
                    hash = self.embed_hash(embed)
                    if job['discord_message_hash'] == hash:
                        continue
                    await message.edit(content="**New score found**", embed=embed)
                    await self.bot.db['jobs'].update_one(
                        {"_id": job["_id"]},
                        {"$set": {
                            "discord_message_hash": hash
                        }}
                    )
                except discord.NotFound:
                    pass


    async def _build_job_embed(self, job):
        score_id = job['score_id']
        score = await self.bot.osu.score(score_id=score_id)
        mods = [mod.acronym for mod in score.mods]
        mods = sort_mods(mods)
        mods_str = "".join(mods)

        em = discord.Embed()
        em.set_author(
            name=f"Job Status: {job['status'].upper()}",
            icon_url=f"https://a.ppy.sh/{score.user_id}",
            url=f"https://osu.ppy.sh/score/{score_id}"
        )
        em.add_field(
            name=f"{score._user.username} | {score.beatmapset.artist} - {score.beatmapset.title} "
            f"[{score.beatmap.version}] +{mods_str}",
            value=f"*Stage*: {job['type'].upper()} ▸ *Attempt*: {job['attempts']}"
        )
        # em.add_field(
        #    name=f"Stage",
        #    value=f"{job['type']}"
        #)
        #em.add_field(
        #    name=f"Attempt",
        #    value=f"{job['attempts']}",
        #    inline=True
        #)
        em.set_image(url=f"https://assets.ppy.sh/beatmaps/{score.beatmapset.id}/covers/card.jpg")
        em.set_footer(text=f"{job['_id']}")
        return em


    def embed_hash(self, embed: discord.Embed) -> str:
        return hashlib.md5(json.dumps(embed.to_dict(), sort_keys=True).encode()).hexdigest()


    @app_commands.command(name="retry", description="Retry a failed job")
    async def retry(self, interaction: Interaction, job_id: str):
        _id = ObjectId(job_id)
        job = await self.bot.db['jobs'].find_one({ "_id": _id })
        if not job:
            return await interaction.response.send_message(f"job id {job_id} does not exist")
        if job['status'] != "failed":
            await interaction.response.send_message("This job has not failed.")
        else:
            await interaction.response.send_message(f"Retrying job id: {job_id}")
            await self.bot.db['jobs'].update_one(
                { "_id": job_id },
                { "$set": {
                    "status": "pending",
                    "attempts": 0
                }}
            )


    @jobs_feed_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


    @app_commands.command(name="testjobembed", description="test")
    async def jobembed(self, interaction: Interaction):
        channel = self.bot.get_channel(1106553041836052501)
        active_jobs = await get_ongoing_jobs(self.bot.db)
        for job in active_jobs:
            if job['discord_message_id'] < 0:
                embed = await self._build_job_embed(job)
                message = await channel.send(content="**New score found**", embed=embed)
                await self.bot.db['jobs'].update_one(
                    {"_id": job["_id"]},
                    {"$set": {"discord_message_id": message.id}}
                )
            else:
                try:
                    message = await channel.fetch_message(job['discord_message_id'])
                    embed = await self._build_job_embed(job)
                    await message.edit(content="**New score found**", embed=embed)
                except discord.NotFound:
                    pass


async def setup(bot):
    await bot.add_cog(JobsFeed(bot))
