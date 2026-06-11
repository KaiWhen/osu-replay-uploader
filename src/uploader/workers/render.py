import asyncio
import os
from pymongo.asynchronous.database import AsyncDatabase
from src.db.jobs import claim_next_job, fail_job, complete_job, enqueue
from src.services.metadata import configure_metadata
from src.services.score import get_replay_data
from src.services.render import submit_render, wait_for_render
from src.config import WORKER_POLL_INTERVAL, REPLAYS_DIR
from src.services.thumbnail import create_thumbnail
from src.services.video import download_video


async def render_worker(db: AsyncDatabase):
    while True:
        job = await claim_next_job(db, "render")
        if not job:
            await asyncio.sleep(WORKER_POLL_INTERVAL)
            continue

        try:
            score_id = job["payload"]["score_id"]
            replay_data = None
            replay_file_path = REPLAYS_DIR / f"{score_id}.osr"
            if os.path.exists(replay_file_path):
                replay_data = open(replay_file_path, 'rb')
            else:
                replay_data = await get_replay_data(score_id)
            if not replay_data:
                await fail_job(db, job["_id"], "Failed to get replay data")
                continue
            render_id = await submit_render(db, score_id, replay_data)
            if not render_id:
                await fail_job(db, job["_id"], "Render submit failed")
                continue
            await wait_for_render(render_id)
            video_path = await download_video(render_id, score_id)
            thumb_path = await create_thumbnail(score_id)
            options = await configure_metadata(score_id, video_path)
            options['thumb_path'] = thumb_path
            await complete_job(db, job["_id"])
            await enqueue(db, "upload", score_id, {"options": options})
        except Exception as e:
            await fail_job(db, job["_id"], str(e))
