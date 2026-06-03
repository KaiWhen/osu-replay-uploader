from discord.ext import commands, tasks
from src.db.jobs import enqueue
from src.db.scores import insert_score
from src.services.score import get_score_data
from src.services.forms import get_form_resp
from src.config import DISCORD_APPROVAL_CHANNEL_ID
import discord, asyncio, math

from src.utils import get_map_country_rank, map_difficulty_to_str, sort_mods

VOTES_REQUIRED = 3


class Approvals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.form_loop.start()


    def cog_unload(self) -> tasks.Coroutine[tasks.Any, tasks.Any, None]:
        self.form_loop.cancel()
        return super().cog_unload()


    @tasks.loop(minutes=1)
    async def form_loop(self):
        channel = self.bot.get_channel(DISCORD_APPROVAL_CHANNEL_ID)
        score_ids = await get_form_resp(self.bot.db)
        if not score_ids:
            return

        for score_id in score_ids:
            await self._handle_request(channel, score_id)


    async def _handle_request(self, channel, score_id):
        score = await self.bot.osu.score(score_id=score_id)
        beatmap_scores = await self.bot.osu.beatmap_scores(
            beatmap_id=score.beatmap.id,
            mode="osu",
            type="country"
        )
        embed = self._build_embed(score, beatmap_scores)
        message = await channel.send(
            content=f"**Replay upload request for score by {score._user.username}**",
            embed=embed
        )
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        yes_count = no_count = 0
        reacted_users = []

        def check(reaction, user):
            return (
                reaction.message.id == message.id
                and str(reaction.emoji) in ["✅", "❌"]
                and user.id not in reacted_users
            )

        while yes_count < VOTES_REQUIRED and no_count < VOTES_REQUIRED:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=86400, check=check)
                reacted_users.append(user.id)
                if str(reaction.emoji) == "✅":
                    yes_count += 1
                else:
                    no_count += 1
            except asyncio.TimeoutError:
                await channel.send(f"Request for score {score_id} timed out.")
                return

        if yes_count == VOTES_REQUIRED:
            score_data = await get_score_data(score_id)
            await insert_score(self.bot.db, score_data)
            await enqueue(self.bot.db, "render", score_id, {"score_id": score_id})
            await channel.send("**Replay queued for upload ✅**")
        else:
            await channel.send("rip bozo")


    def _build_embed(self, score, beatmap_scores) -> discord.Embed:
        acc = math.floor(score.accuracy * 10000) / 100
        mods = [mod.acronym for mod in score.mods]
        mods = sort_mods(mods)
        mods_str = "".join(mods)
        status = score.beatmap.status.__str__()[11:]
        ar_str, od_str, cs_str, bpm_str, sr_string = map_difficulty_to_str(score, mods, acc)
        country_ranking = get_map_country_rank(score, beatmap_scores)

        em = discord.Embed()
        em.set_author(
            name=f"{score.beatmapset.artist} - {score.beatmapset.title} "
            f"[{score.beatmap.version}] +{mods_str} [{sr_string}★]",
            icon_url=f"https://a.ppy.sh/{score.user_id}",
            url=f"https://osu.ppy.sh/b/{score.beatmap.id}"
        )
        em.add_field(
            name=f"{round(score.pp)}pp ▸ {acc}% ▸ {score.max_combo}x/{score.beatmap.max_combo}x "
            f"▸ {score.statistics.count_miss}❌",
            value=f"{bpm_str}bpm ▸ AR{ar_str} ▸ CS{cs_str} ▸ OD{od_str} ▸ {status} ▸ "
            f"🌐 #{score.rank_global} ▸ 🇮🇪 #{country_ranking}\nDate set: {str(score.created_at)[:-6]}"
        )
        em.set_image(url=f"https://assets.ppy.sh/beatmaps/{score.beatmapset.id}/covers/card.jpg")
        em.set_footer(text=f"Requires {VOTES_REQUIRED} votes to approve or deny")

        return em


    @form_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Approvals(bot))
