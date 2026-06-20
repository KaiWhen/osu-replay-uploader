import asyncio
import sys
from datetime import datetime
from pymongo.asynchronous.database import AsyncDatabase
from src.services.youtube import upload_video, upload_thumbnail
from src.db.scores import update_score
from src.db.jobs import claim_next_job, complete_job, fail_job
from src.db.notifications import create_notification
from src.config import WORKER_POLL_INTERVAL
from src.utils import clear_score_files


async def upload_worker(db: AsyncDatabase, youtube):
    while True:
        sys.stdout.write(f"[{datetime.now()}] upload_worker POLLING\n")
        sys.stdout.flush()
        job = await claim_next_job(db, "upload")
        if not job:
            await asyncio.sleep(WORKER_POLL_INTERVAL)
            continue
        try:
            score_id = job["score_id"]
            options = job["payload"]["options"]
            video_id = await upload_video(db, youtube, score_id, options)
            await upload_thumbnail(youtube, video_id, job["payload"]["options"]["thumb_path"])
            await update_score(db, score_id, {"video_id": video_id})
            await complete_job(db, job["_id"], {"video_id": video_id})
            clear_score_files(score_id)
            await create_notification(db, video_id)
        except Exception as e:
            await fail_job(db, job["_id"], str(e))
