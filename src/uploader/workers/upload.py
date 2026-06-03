import asyncio
import os
from pymongo.asynchronous.database import AsyncDatabase
from src.services.youtube import upload_video, upload_thumbnail
from src.db.scores import update_score
from src.db.jobs import claim_next_job, complete_job, fail_job
from db.notifications import create_notification
from src.config import WORKER_POLL_INTERVAL


async def upload_worker(db: AsyncDatabase, youtube):
    while True:
        job = await claim_next_job(db, "upload")
        if not job:
            await asyncio.sleep(WORKER_POLL_INTERVAL)
            continue
        try:
            score_id = job["score_id"]
            options = job["payload"]["options"]
            video_id = await upload_video(youtube, options)
            await upload_thumbnail(youtube, video_id, job["payload"]["thumb_path"])
            await update_score(db, score_id, {"video_id": video_id})
            await complete_job(db, job["_id"], {"video_id": video_id})
            print(os.exists(f"../../{options['file']}"))
            os.remove(f"../../{options['file']}")
            await create_notification(db, video_id)
        except Exception as e:
            await fail_job(db, job["_id"], str(e))
