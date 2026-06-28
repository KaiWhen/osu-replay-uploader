import asyncio
from datetime import datetime, timedelta, timezone
import discord
import json
import hashlib
from bson import ObjectId
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from src.db.jobs import get_ongoing_jobs
from src.config import DISCORD_JOBS_FEED_CHANNEL_ID, ADMIN_USER_ID
from src.utils import clear_score_files, sort_mods


class JobsFeed(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.jobs_feed_loop.start()


    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        self.jobs_feed_loop.cancel()
        return super().cog_unload()


    @tasks.loop(seconds=15)
    async def jobs_feed_loop(self):
        active_jobs = await get_ongoing_jobs(self.bot.db)
        for job in active_jobs:
            if job['discord_message_id'] < 0:
                embed = await self._build_job_embed(job)
                hash = self.embed_hash(embed)
                message = await self.channel.send(content=f"**Ongoing job for score {job['score_id']}**", embed=embed)
                await self.bot.db['jobs'].update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "discord_message_id": message.id,
                        "discord_message_hash": hash
                    }}
                )
            else:
                try:
                    embed = await self._build_job_embed(job)
                    hash = self.embed_hash(embed)
                    if job['discord_message_hash'] == hash:
                        continue
                    message = await self.channel.fetch_message(job['discord_message_id'])
                    await message.edit(embed=embed)
                    await self.bot.db['jobs'].update_one(
                        {"_id": job["_id"]},
                        {"$set": {
                            "discord_message_hash": hash
                        }}
                    )
                except discord.NotFound:
                    pass
            await asyncio.sleep(2)


    async def _build_job_embed(self, job):
        score_id = job['score_id']
        score = await self.bot.osu.score(score_id=score_id)
        mods = [mod.acronym for mod in score.mods]
        mods = sort_mods(mods)
        mods_str = f" {"+"}{"".join(mods)}" if len(mods) > 0 else ""

        em = discord.Embed()
        em.set_author(
            name=f"{score._user.username} | {score.beatmapset.artist} - {score.beatmapset.title} "
            f"[{score.beatmap.version}]{mods_str}",
            icon_url=f"https://a.ppy.sh/{score.user_id}",
            url=f"https://osu.ppy.sh/scores/{score_id}"
        )
        em.add_field(
            name=f"Job Status: {job['status'].upper()}",
            value=f"*Stage*: {job['type'].upper()}   ▸   *Retry Attempt*: {job['attempts']}",
            inline=False
        )
        if job['error']:
            em.add_field(
                name="Error",
                value=f"{job['error']}",
                inline=False
            )
        em.set_image(url=f"https://assets.ppy.sh/beatmaps/{score.beatmapset.id}/covers/card.jpg")
        em.set_footer(text=f"{job['_id']}")
        return em


    def embed_hash(self, embed: discord.Embed) -> str:
        return hashlib.md5(json.dumps(embed.to_dict(), sort_keys=True).encode()).hexdigest()


    @app_commands.command(name="retry", description="Retry a failed job")
    async def retry(self, interaction: Interaction, job_id: str):
        if interaction.user.id == ADMIN_USER_ID:
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
                        "attempts": 0,
                        "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=20),
                        "updated_at": datetime.now(timezone.utc),
                        "error": None
                    }}
                )
        else:
            return await interaction.response.send_message("You are not allowed to do this!")
    

    @app_commands.command(name="delete", description="Delete a job")
    async def delete(self, interaction: Interaction, job_id: str):
        if interaction.user.id == ADMIN_USER_ID:
            _id = ObjectId(job_id)
            job = await self.bot.db['jobs'].find_one({ "_id": _id })
            if not job:
                return await interaction.response.send_message(f"job id {job_id} does not exist")
            score_id = job['score_id']
            clear_score_files(score_id)
            await self.bot.db['jobs'].delete_one({ "_id": _id })
            return await interaction.response.send_message(f"Job {job_id} score ID: {score_id} has been deleted")
        else:
            return await interaction.response.send_message("You are not allowed to do this!")


    @jobs_feed_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        self.channel = self.bot.get_channel(DISCORD_JOBS_FEED_CHANNEL_ID)


async def setup(bot):
    await bot.add_cog(JobsFeed(bot))
