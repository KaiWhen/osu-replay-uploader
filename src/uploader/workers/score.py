import asyncio
from src.services.score import get_top_scores, get_score_data
from src.db.scores import insert_score
from src.db.jobs import enqueue
from src.config import COUNTRY_CODE, WORKER_POLL_INTERVAL


async def score_worker(db):
    while True:
        score_ids = await get_top_scores(db, COUNTRY_CODE)
        for score_id in score_ids:
            score_data = await get_score_data(score_id)
            await insert_score(db, score_id, score_data)
            await enqueue(db, "render", score_id, {"score_id": score_id})
        await asyncio.sleep(WORKER_POLL_INTERVAL)
