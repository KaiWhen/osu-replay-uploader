import asyncio
from datetime import timedelta, timezone
import math
import os
import shutil
import discord
from discord.ext import commands, tasks
from ossapi import Beatmap, Beatmapset, Score
from src.config import MAPS_DIR
from src.utils import (
    calc_lazer_accuracy,
    calc_legacy_grade,
    calc_pp_many,
    calc_stable_accuracy,
    get_map_country_rank,
    map_difficulty_to_str,
    map_difficulty_to_str_nopp,
    parse_map_args,
    seconds_to_minutes,
    sort_mods
)


class Osu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        return super().cog_unload()
    

    @commands.command(name = "rs")
    async def rs(self, ctx: commands.Context, *, username=None):
        async with ctx.typing():
            username = username if username else ctx.author._user.name
            osu_user = await self.bot.osu.user(user=username)
            if not osu_user:
                return await ctx.reply(content="**User not found. Link your osu user using .link <username>**")
            else:
                recent_score = await asyncio.wait_for(
                    self.bot.osu.user_scores(user_id=osu_user.id, type="recent", limit=1, mode="osu", include_fails=True),
                    timeout=30
                )
                if not recent_score:
                    return await ctx.reply(content="**No recent score found**", mention_author=False)
                score = await self.bot.osu.score(recent_score[0].id)
                embed = await self._build_embed(score)
                await ctx.reply(
                    content=f"**Recent osu! Standard Play for {osu_user.username}**",
                    embed=embed,
                    mention_author=False
                )
                map_path = MAPS_DIR / f"{score.beatmapset.id}"
                if os.path.exists(map_path):
                    shutil.rmtree(map_path)
                return
    

    @commands.command(name = "map", aliases=["m"])
    async def map_info(self, ctx: commands.Context, *, args=None):
        replied_message = None
        if ctx.message.reference:
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        async with ctx.typing():
            mods = []
            map_id = None
            if args:
                map_id, mods = parse_map_args(args)
                if not map_id and len(mods) == 0:
                    return await ctx.reply(
                        content="**Please provide either a map id or link, mods, or both**",
                        mention_author=False
                    )
            if not map_id:
                if replied_message:
                    valid = False
                    if replied_message.embeds:
                        embed = replied_message.embeds[0]
                        if embed.author:
                            if "https://osu.ppy.sh/b/" in embed.author.url:
                                map_id = embed.author.url[21:]
                                valid = True
                            elif "https://osu.ppy.sh/beatmaps/" in embed.author.url:
                                map_id = embed.author.url[28:]
                                valid = True
                    if not valid:
                        return await ctx.reply(content="**No map found from that message.**", mention_author=False)
                else:
                    channel = ctx.channel
                    async for message in channel.history(limit=100):
                        if message.embeds:
                            embed = message.embeds[0]
                            if embed.author:
                                if "https://osu.ppy.sh/b/" in embed.author.url:
                                    map_id = embed.author.url[21:]
                                    break
                                elif "https://osu.ppy.sh/beatmaps/" in embed.author.url:
                                    map_id = embed.author.url[28:]
                                    break
                    if not map_id:
                        return await ctx.reply(content="**No map found in this channel.**", mention_author=False)

            beatmap_obj = await self.bot.osu.beatmap(beatmap_id=map_id)
            if not beatmap_obj:
                return await ctx.reply(content=f"**Map {map_id} not found.", mention_author=False)

            embed = await self._build_map_embed(beatmap_obj, mods)
            beatmapset: Beatmapset = beatmap_obj.beatmapset()
            map_path = MAPS_DIR / f"{beatmapset.id}"
            if os.path.exists(map_path):
                shutil.rmtree(map_path)
            return await ctx.reply(embed=embed, mention_author=False)
    

    async def _build_embed(self, score: Score) -> discord.Embed:
        acc = math.floor(score.accuracy * 10000) / 100
        mods = [mod.acronym for mod in score.mods]
        mods = sort_mods(mods)
        mods_str = f" {"+"}{"".join(mods)} " if len(mods) > 0 else " "
        status = score.beatmap.status.__str__()[11:]
        get_fc_pp = True
        if score.max_combo == score.beatmap.max_combo:
            get_fc_pp = False
        ar_str, od_str, cs_str, bpm_str, sr_string, pp, if_fc = await map_difficulty_to_str(
            score,
            mods,
            acc,
            get_fc_pp
        )
        meh = score.statistics.meh if score.statistics.meh else 0
        ok = score.statistics.ok if score.statistics.ok else 0
        great = score.statistics.great if score.statistics.great else 0
        misses = score.statistics.miss if score.statistics.miss else 0
        hit_count_str = f"[{great}/{ok}/{meh}/{misses}]"
        rank = score.rank.__str__()[6:]
        if score.passed and 'CL' in mods:
            rank = calc_legacy_grade(score, mods)
        
        map_completion = None
        if not score.passed:
            hit_count = meh+ok+great+misses
            map_object_count = score.beatmap.count_circles + score.beatmap.count_sliders + score.beatmap.count_spinners
            map_completion = round((hit_count / map_object_count)*100, 1)
        rank_str = f"F ({map_completion}%)" if map_completion else rank
        
        beatmap_scores = await self.bot.osu.beatmap_scores(
            beatmap_id=score.beatmap.id,
            mode="osu",
            type="country"
        )
        country_ranking = get_map_country_rank(score, beatmap_scores)

        pp_str = "0PP"
        if score.passed:
            pp_str = f"{round(score.pp, 2)}PP"
        if status == "LOVED" or not score.passed:
            pp_str = f"{round(pp, 2)}PP"
        if get_fc_pp:
            stats = if_fc['stats']
            if_fc_acc = calc_stable_accuracy(stats) if 'CL' in mods else calc_lazer_accuracy(stats, score.maximum_statistics)
            pp_str = f"{pp_str} ({round(if_fc['if_fc_pp'], 2)}PP for {if_fc_acc}% FC)"

        em = discord.Embed()
        em.set_author(
            name=f"{score.beatmapset.artist} - {score.beatmapset.title} "
            f"[{score.beatmap.version}]{mods_str}[{sr_string}★]",
            icon_url=f"https://a.ppy.sh/{score.user_id}",
            url=f"https://osu.ppy.sh/b/{score.beatmap.id}"
        )
        em.add_field(
            name=f"{rank_str} • {pp_str} • {acc}% • {score.max_combo}/{score.beatmap.max_combo}x "
            f"• {hit_count_str}",
            value=f"`{bpm_str}bpm` • `AR {ar_str} CS {cs_str} OD {od_str}`\n"
            f"🌐 #{score.rank_global} • 🇮🇪 #{country_ranking}"
        )
        em.set_thumbnail(url=f"https://b.ppy.sh/thumb/{score.beatmapset.id}l.jpg?format=webp")
        em.set_footer(
            text=f"{status} • Date set: {str(score.ended_at.astimezone(timezone(timedelta(hours=1))))[:-6]} IST"
        )

        return em


    async def _build_map_embed(self, beatmap: Beatmap, beatmapset: Beatmapset, mods: list[str]) -> discord.Embed:
        mods_str = None
        if len(mods) > 0:
            mods = sort_mods(mods)
            mods_str = "".join(mods)
        ar_str, od_str, cs_str, bpm_str = await map_difficulty_to_str_nopp(beatmap, mods)
        pp_results = await calc_pp_many(beatmap, beatmapset, mods)
        sr = math.floor(pp_results[0].stars*100) / 100.0
        pp_95 = round(pp_results[0].pp, 2)
        pp_98 = round(pp_results[1].pp, 2)
        pp_99 = round(pp_results[2].pp, 2)
        pp_100 = round(pp_results[3].pp, 2)
        status = beatmap.status.__str__()[11:]

        em = discord.Embed()
        mapper = await self.bot.osu.user(beatmapset.creator)
        map_owner = mapper.id if not beatmap.owners else beatmap.owners[0].id
        
        em.set_author(
            name=f"{beatmapset.artist} - {beatmapset.title}",
            icon_url=f"https://a.ppy.sh/{map_owner}",
            url=f"https://osu.ppy.sh/b/{beatmap.id}"
        )
        em.add_field(
            name=f"[{beatmap.version}]{f" +{mods_str}" if mods_str else ""}",
            value=f"**SR:** `{sr}` • **Length:** `{seconds_to_minutes(beatmap.total_length)}`"
            f"• **BPM:** `{bpm_str}` • **Combo:** `{beatmap.max_combo}`\n"
            f"**AR** {ar_str} **CS** {cs_str} **HP** {beatmap.drain} **OD** {od_str}\n"
            f"**PP:** **95**%-{pp_95} **98**%-{pp_98} **99**%-{pp_99} **100**%-{pp_100}"
        )
        em.set_thumbnail(url=f"https://b.ppy.sh/thumb/{beatmapset.id}l.jpg?format=webp")
        em.set_footer(
            text=f"{status}"
        )

        return em


async def setup(bot):
    await bot.add_cog(Osu(bot))
