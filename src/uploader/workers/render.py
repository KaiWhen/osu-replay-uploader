import asyncio
from pymongo.asynchronous.database import AsyncDatabase
from src.db.jobs import claim_next_job, fail_job, complete_job, enqueue
from src.services.score import get_replay_data
from src.services.render import submit_render
from src.config import WORKER_POLL_INTERVAL


async def render_worker(db: AsyncDatabase):
    while True:
        job = await claim_next_job(db, "render")
        if not job:
            await asyncio.sleep(WORKER_POLL_INTERVAL)
            continue

        try:
            score_id = job["payload"]["score_id"]
            replay_data = await get_replay_data(score_id)
            if not replay_data:
                await fail_job(db, job["_id"], "Replay download failed")
                continue
            render_id = await submit_render(db, score_id, replay_data)
            if not render_id:
                await fail_job(db, job["_id"], "Render submit failed")
                continue
            await complete_job(db, job["_id"], {"render_id": render_id})
            await enqueue(db, "poll_render", score_id, {"render_id": render_id})
        except Exception as e:
            await fail_job(db, job["_id"], str(e))
