import asyncio
from datetime import datetime, timezone, timedelta
from pymongo.asynchronous.database import AsyncDatabase
from src.db.jobs import claim_next_job, complete_job, fail_job, enqueue
from src.services.render import poll_render
from src.services.thumbnail import create_thumbnail
from src.services.metadata import configure_metadata
from src.config import WORKER_POLL_INTERVAL


async def poll_render_worker(db: AsyncDatabase):
    while True:
        job = await claim_next_job(db, "poll_render")
        if not job:
            await asyncio.sleep(WORKER_POLL_INTERVAL)
            continue

        try:
            render_id = job["payload"]["render_id"]
            score_id = job["score_id"]
            done, video_url = await poll_render(render_id)
            if not done:
                await db.jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "status": "pending",
                        "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=30)
                    }}
                )
                continue
            await complete_job(db, job["_id"], {"video_url": video_url})
            thumb_path = await create_thumbnail(score_id)
            options = await configure_metadata(score_id)
            options['thumb_path'] = thumb_path
            await enqueue(db, "upload", score_id, {"video_url": video_url})
        except Exception as e:
            await fail_job(db, job["_id"], str(e))
