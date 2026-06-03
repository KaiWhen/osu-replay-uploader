import asyncio
import os
from datetime import datetime
from src.clients import get_youtube
from src.db.mongo import db
from src.db.jobs import recover_stale_jobs
from src.db.status import get_status, insert_status
from src.uploader.workers.render import render_worker
from src.uploader.workers.upload import upload_worker
from src.uploader.workers.score import score_worker
from src.uploader.workers.poll_render import poll_render_worker
from src.config import COUNTRY_CODE


async def main():
    check_dirs()

    status = await get_status(db, COUNTRY_CODE)
    if not status:
        now = datetime.now()
        timestamp = datetime.timestamp(now)
        await insert_status(db, {
            'country': COUNTRY_CODE,
            'last_updated': timestamp,
            'form_updated': timestamp
        })

    youtube = get_youtube()
    await recover_stale_jobs(db)
    await asyncio.gather(
        score_worker(db),
        render_worker(db),
        poll_render_worker(db),
        upload_worker(db, youtube),
    )


def check_dirs():
    if not os.path.exists("videos/"):
        os.mkdir("videos/")
    if not os.path.exists("maps/"):
        os.mkdir("maps/")
    if not os.path.exists("replays/"):
        os.mkdir("replays/")


asyncio.run(main())
