import asyncio
import sys
from datetime import datetime
from pymongo.asynchronous.database import AsyncDatabase
from src.db.jobs import claim_next_job, fail_job, advance_job
from src.services.metadata import configure_metadata
from src.services.render import wait_for_render
from src.config import GET_RENDER_WORKER_POLL_INTERVAL
from src.services.thumbnail import create_thumbnail
from src.services.video import download_video


async def get_render_worker(db: AsyncDatabase):
    while True:
        sys.stdout.write(f"[{datetime.now()}] get_render_worker POLLING\n")
        sys.stdout.flush()
        job = await claim_next_job(db, "get_render")
        if not job:
            await asyncio.sleep(GET_RENDER_WORKER_POLL_INTERVAL)
            continue
        try:
            score_id = job["score_id"]
            render_id = job["payload"]["render_id"]
            await wait_for_render(render_id)
            video_path = await download_video(render_id, score_id)
            thumb_path = await create_thumbnail(score_id)
            options = await configure_metadata(db, score_id, video_path)
            options['thumb_path'] = thumb_path
            await advance_job(db, job["_id"], "upload", {"options": options})
        except Exception as e:
            await fail_job(db, job["_id"], str(e))
