import asyncio
import io
import sys
from datetime import datetime
from src.clients import osu
from src.db.status import get_status, update_status
from src.config import COUNTRY_CODE
from src.utils import sort_mods
from pymongo.asynchronous.database import AsyncDatabase


async def get_top100() -> list[int]:
    cursor_pg2 = { "page": 2 }
    top50 = await osu.ranking(mode="osu", country=COUNTRY_CODE, type="performance")
    top100 = await osu.ranking(mode="osu", country=COUNTRY_CODE, type="performance", cursor=cursor_pg2)
    top100_users = []
    for player in top50.ranking + top100.ranking:
        top100_users.append(player.user.id)
    return top100_users


async def get_top_scores(db: AsyncDatabase) -> list[int]:
    status = await get_status(db, COUNTRY_CODE)
    top100 = await get_top100()
    valid_scores = []
    for player in top100:
        # get player's top 10
        try:
            scores_top10 = await asyncio.wait_for(
                osu.user_scores(user_id=player, type="best", limit=10, mode="osu"),
                timeout=30
            )
        except Exception as e:
            sys.stdout.write(f"Error getting player {player} top 10: {e}\n")
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

        # get player's recent 20
        try:
            scores_recent20 = await asyncio.wait_for(
                osu.user_scores(user_id=player, type="recent", limit=20, mode="osu"),
                timeout=30
            )
        except Exception as e:
            sys.stdout.write(f"Error getting player {player} recent 20: {e}\n")
            continue

        # add #1 global scores
        for score in scores_recent20:
            if score.rank_global and score.rank_global == 1:
                now = datetime.now()
                timestamp = datetime.timestamp(now)
                if (not score
                    or datetime.timestamp(score.ended_at) - status['last_updated'] < 0
                    or not score.replay
                    or score.beatmap.difficulty_rating < 4
                    or not score.passed
                    or score.id in valid_scores):
                        continue
                try:
                    beatmapset = await asyncio.wait_for(
                        score.beatmap.beatmapset(),
                        timeout=30
                    )
                except Exception as e:
                    sys.stdout.write(f"Error getting beatmapset: {e}\n")
                if timestamp - datetime.timestamp(beatmapset.ranked_date) < 432000:
                    continue
                valid_scores.append(score.id)

    now = datetime.now()
    timestamp = datetime.timestamp(now)
    await update_status(db, COUNTRY_CODE, {
       "last_updated": timestamp
    })
    sys.stdout.write(f"[{datetime.now()}] score_worker UPDATED\n")
    sys.stdout.flush()

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
        raw = await osu.download_score(score_id=score_id, raw=True)
        return io.BytesIO(raw)
    except Exception as e:
        sys.stdout.write(f"Replay download failed for {score_id}: {e}\n")
        return None
