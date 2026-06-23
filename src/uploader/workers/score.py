import asyncio
import sys
from datetime import datetime
from pymongo.asynchronous.database import AsyncDatabase
from src.services.score import get_top_scores, get_score_data
from src.db.scores import insert_score
from src.db.jobs import enqueue
from src.config import SCORE_WORKER_POLL_INTERVAL


async def score_worker(db: AsyncDatabase):
    while True:
        try:
            sys.stdout.write(f"[{datetime.now()}] score_worker POLLING\n")
            sys.stdout.flush()
            score_ids = await get_top_scores(db)
            for score_id in score_ids:
                score_data = await get_score_data(score_id)
                await insert_score(db, score_data)
                await enqueue(db, "submit_render", score_id, {"score_id": score_id})
        except Exception as e:
            sys.stdout.write(f"Fatal error in score worker: {e}\n")
            sys.stdout.flush()
            await asyncio.sleep(SCORE_WORKER_POLL_INTERVAL * 2)
            continue
        await asyncio.sleep(SCORE_WORKER_POLL_INTERVAL)
