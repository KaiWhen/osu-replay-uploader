import asyncio
import sys
from datetime import datetime
from src.clients import osu
from src.db.status import get_status, update_status
from src.config import COUNTRY_CODE
from src.db.mongo import db
from src.utils import sort_mods


async def get_top100() -> list[int]:
    cursor_pg2 = { "page": 2 }
    top50 = await osu.ranking(mode="osu", country=COUNTRY_CODE, type="performance")
    top100 = await osu.ranking(mode="osu", country=COUNTRY_CODE, type="performance", cursor=cursor_pg2)
    top100_users = []
    for player in top50.ranking + top100.ranking:
        top100_users.append(player.user.id)
    return top100_users


async def get_top_scores() -> list[int]:
    status = await get_status(db, COUNTRY_CODE)
    top100 = await get_top100()
    valid_scores = []
    for player in top100:
        # get player's top 10
        try:
            scores_top10 = await osu.user_scores(user_id=player, type="best", limit=10, mode="osu")
        except Exception as e:
            sys.stdout.write(e)
            continue

        # add recent top score
        for score in scores_top10:
            if not score:
                continue
            if datetime.timestamp(score.ended_at) - status['last_updated'] < 0:
                continue
            if not score.replay:
                continue
            valid_scores.append(score.id)
        
        # await asyncio.sleep(1)

        # get player's recent 50
        try:
            scores_recent50 = await osu.user_scores(user_id=player, type="recent", limit=50, mode="osu")
        except Exception as e:
            sys.stdout.write(e)
            continue

        # add #1 global scores
        for score in scores_recent50:
            now = datetime.now()
            timestamp = datetime.timestamp(now)
            if (not score
                or datetime.timestamp(score.ended_at) - status['last_updated'] < 0
                or not score.replay
                or score.beatmap.difficulty_rating < 4
                or not score.passed
                or score.id in valid_scores):
                    continue
            beatmapset = await score.beatmap.beatmapset()
            if timestamp - datetime.timestamp(beatmapset.ranked_date) < 432000:
                continue
            score_obj = await osu.score(score_id=score.id)
            if score_obj.rank_global == 1:
                valid_scores.append(score.id)
        
        # await asyncio.sleep(1)

    now = datetime.now()
    timestamp = datetime.timestamp(now)
    #await update_status(db, COUNTRY_CODE, {
    #    "last_updated": timestamp
    #})

    return valid_scores


async def get_score_data(score_id: int) -> dict:
    score = await osu.score(score_id=score_id)
    if not score:
        return None
    now = datetime.now()
    mods = [mod.acronym for mod in score.mods]
    sorted_mods = sort_mods(mods)
    return {
        "score_id": score_id,
        "user_id": score.user_id,
        "map_id": score.beatmap.id,
        "pp": score.pp,
        "mods": "".join(sorted_mods),
        "video_id": "",
        "description": f"{score._user.username} - {score.beatmapset.title}",
        "timestamp": datetime.timestamp(now),
        "deleted": False,
    }


async def get_replay_data(score_id: int):
    try:
        return await osu.download_score(score_id=score_id, raw=True)
    except Exception as e:
        sys.stdout.write(f"Replay download failed for {score_id}: {e}")
        return None


async def test():
    score_ids = await get_top_scores()
    print(score_ids)

# asyncio.run(test())
