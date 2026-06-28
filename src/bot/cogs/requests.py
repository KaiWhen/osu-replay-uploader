import asyncio
import os
import discord
import math
from discord.ext import commands, tasks
from src.db.jobs import enqueue
from src.db.scores import insert_score
from src.db.requests import insert_request, get_pending_requests, resolve_request
from src.services.drive import delete_file
from src.services.score import get_score_data
from src.services.forms import get_form_resp
from src.config import DISCORD_REQUESTS_CHANNEL_ID, REPLAYS_DIR, VOTES_REQUIRED
from src.utils import get_map_country_rank, map_difficulty_to_str, sort_mods


class Requests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.form_loop.start()
        self.check_request_loop.start()


    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        self.form_loop.cancel()
        self.check_request_loop.cancel()
        return super().cog_unload()


    @tasks.loop(minutes=1)
    async def form_loop(self):
        scores = await get_form_resp()
        if not scores:
            return

        for score in scores:
            await self._handle_request(self.channel, score)
            await asyncio.sleep(2)
    

    @tasks.loop(seconds=5)
    async def check_request_loop(self):
        pending_requests = await get_pending_requests(self.bot.db)
        for req in pending_requests:
            message = await self.channel.fetch_message(req['message_id'])
            score_id = req['score_id']
            reactions = message.reactions
            for r in reactions:
                if str(r.emoji) == "✅":
                    if r.normal_count >= VOTES_REQUIRED + 1:
                        score_data = await get_score_data(score_id)
                        await insert_score(self.bot.db, score_data)
                        await enqueue(self.bot.db, "submit_render", score_id, {"score_id": score_id})
                        await resolve_request(self.bot.db, req['_id'])
                        await message.edit(content="## **Replay queued for upload ✅**")
                        break
                elif str(r.emoji) == "❌":
                    if r.normal_count >= VOTES_REQUIRED + 1:
                        if req['file_id']:
                            await delete_file(req['file_id'])
                            os.remove(REPLAYS_DIR / f"{score_id}.osr")
                        await resolve_request(self.bot.db, req['_id'])
                        await message.edit(content="## ❌ rip bozo")
                        break
            remaining_reqs = await get_pending_requests(self.bot.db)
            if len(remaining_reqs) == 0:
                self.check_request_loop.cancel()
                return


    async def _handle_request(self, channel, score_dict):
        score_id = score_dict['score_id']
        try:
            score = await self.bot.osu.score(score_id=score_id)
        except:
            score = None

        if not score_dict['valid']:
            embed = self._build_fail_embed(score_dict, score)
            return await channel.send(
                content="**Invalid replay upload request**",
                embed=embed
            )

        beatmap_scores = await self.bot.osu.beatmap_scores(
            beatmap_id=score.beatmap.id,
            mode="osu",
            type="country"
        )
        embed = await self._build_embed(score, beatmap_scores)
        username = score._user.username
        message = await channel.send(
            content=f"## **Pending replay upload request for score by {username}**",
            embed=embed
        )
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        score_description = (
            f"{username} | {score.beatmapset.artist} - {score.beatmapset.title}"
            f"[{score.beatmap.version}]"
        )
        await insert_request(self.bot.db, score_id, score_description, message.id, score_dict['file_id'])
        if not self.check_request_loop.is_running():
            self.check_request_loop.start()


    async def _build_embed(self, score, beatmap_scores) -> discord.Embed:
        acc = math.floor(score.accuracy * 10000) / 100
        mods = [mod.acronym for mod in score.mods]
        mods = sort_mods(mods)
        mods_str = f" {"+"}{"".join(mods)} " if len(mods) > 0 else " "
        status = score.beatmap.status.__str__()[11:]
        ar_str, od_str, cs_str, bpm_str, sr_string, pp = await map_difficulty_to_str(score, mods, acc)
        meh = score.statistics.meh if score.statistics.meh else 0
        ok = score.statistics.ok if score.statistics.ok else 0
        great = score.statistics.great if score.statistics.great else 0
        misses = score.statistics.miss if score.statistics.miss else 0
        hit_count_str = f"[{great}/{ok}/{meh}/{misses}]"
        country_ranking = get_map_country_rank(score, beatmap_scores)

        pp_str = f"{round(score.pp)}PP"
        if status == "LOVED":
            pp_str = f"{round(pp)}PP"

        em = discord.Embed()
        em.set_author(
            name=f"{score.beatmapset.artist} - {score.beatmapset.title} "
            f"[{score.beatmap.version}]{mods_str}[{sr_string}★]",
            icon_url=f"https://a.ppy.sh/{score.user_id}",
            url=f"https://osu.ppy.sh/b/{score.beatmap.id}"
        )
        em.add_field(
            name=f"{pp_str} ▸ {acc}% ▸ {score.max_combo}/{score.beatmap.max_combo}x "
            f"▸ {hit_count_str}",
            value=f"{bpm_str}bpm ▸ AR{ar_str} ▸ CS{cs_str} ▸ OD{od_str} ▸ {status} ▸ "
            f"🌐 #{score.rank_global} ▸ 🇮🇪 #{country_ranking}\nDate set: {str(score.ended_at)[:-6]}"
        )
        em.set_image(url=f"https://assets.ppy.sh/beatmaps/{score.beatmapset.id}/covers/card.jpg")
        em.set_footer(text=f"Requires {VOTES_REQUIRED} votes to approve or deny")

        return em


    def _build_fail_embed(self, score_dict, score) -> discord.Embed:
        em = discord.Embed()
        if score:
            mods = [mod.acronym for mod in score.mods]
            mods = sort_mods(mods)
            mods_str = "".join(mods)
            em.set_author(
                name=f"{score._user.username} | {score.beatmapset.artist} - {score.beatmapset.title} "
                f"[{score.beatmap.version}] +{mods_str}",
                icon_url=f"https://a.ppy.sh/{score.user_id}",
                url=f"https://osu.ppy.sh/scores/{score_dict['score_id']}"
            )
        else:
            em.set_author(
                name=f"SCORE NOT FOUND: {score_dict['score_id']}",
                url=f"https://osu.ppy.sh/scores/{score_dict['score_id']}"
            )

        em.add_field(
            name="Invalid reason",
            value=f"{score_dict['err']}"
        )

        if score_dict['file_id']:
            em.add_field(
                name="File",
                value=f"https://drive.google.com/file/d/{score_dict['file_id']}/view",
                inline=False
            )

        return em


    @form_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        self.channel = self.bot.get_channel(DISCORD_REQUESTS_CHANNEL_ID)


    @check_request_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Requests(bot))
