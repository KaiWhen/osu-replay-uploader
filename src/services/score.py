import asyncio
import io
import sys
from datetime import datetime
from ossapi import Score
from src.clients import osu
from src.db.status import get_status, update_status
from src.db.scores import get_scores, get_score, update_score
from src.config import COUNTRY_CODE
from src.utils import sort_mods
from pymongo.asynchronous.database import AsyncDatabase

TWO_DAYS = 172800
TWELVE_MINUTES = 720
FIVE_DAYS = 432000


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
            if not score.replay:
                continue
            if datetime.timestamp(score.ended_at) - status['last_updated'] < -TWELVE_MINUTES:
                continue
            db_score = await get_score(db, {'score_id': score.id})
            if db_score:
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
            legacy_rank_1 = await is_legacy_rank_1(score)
            if score.rank_global and (score.rank_global == 1 or legacy_rank_1):
                now = datetime.now()
                timestamp = datetime.timestamp(now)
                if (datetime.timestamp(score.ended_at) - status['last_updated'] < -TWELVE_MINUTES
                    or not score.replay
                    or score.beatmap.difficulty_rating < 4
                    or not score.passed
                    or score.id in valid_scores):
                        continue
                db_score = await get_score(db, {'score_id': score.id})
                if db_score:
                    continue
                try:
                    beatmapset = await asyncio.wait_for(
                        score.beatmap.beatmapset(),
                        timeout=30
                    )
                except Exception as e:
                    sys.stdout.write(f"Error getting beatmapset: {e}\n")
                if timestamp - datetime.timestamp(beatmapset.ranked_date) < FIVE_DAYS:
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


async def is_legacy_rank_1(score: Score):
    scores = await osu.beatmap_scores(beatmap_id=score.beatmap.id, mode="osu", limit=1, legacy_only=True)
    for s in scores.scores:
        if s.user_id == score.user_id:
            return True
    return False


async def delete_recent_overwritten_score(db: AsyncDatabase, score_id, youtube):
    score = await osu.score(score_id=score_id)
    old_scores = await get_scores(db, {"map_id": score.beatmap.id, "user_id": score.user_id, "deleted": False})
    if not old_scores:
        return
    timestamps = []
    for s in old_scores:
        if score.id == s['score_id']:
            continue
        timestamps.append(s['timestamp'])
    if len(timestamps) == 0:
        return
    recent_timestamp = max(timestamps)
    old_score = await get_score(db, {"map_id": score.beatmap.id, "user_id": score.user_id, "timestamp": recent_timestamp})
    old_mods = old_score['mods']
    mods = [mod.acronym for mod in score.mods]
    sorted_mods = sort_mods(mods)
    mods_str = "".join(sorted_mods)
    if mods_str == old_mods or ("DT" or "NC" in mods_str and old_mods):
        now = datetime.now()
        timestamp = datetime.timestamp(now)
        if timestamp - old_score['timestamp'] < TWO_DAYS:
            request = youtube.videos().update(
                part="status",
                body={
                    'id': old_score['video_id'],
                    'status': {
                        'privacyStatus': "private"
                    }
                }
            )
            request.execute()
            await update_score(db, old_score['score_id'], {'deleted': True})
