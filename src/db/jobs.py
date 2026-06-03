from datetime import datetime, timezone, timedelta
from bson import ObjectId
from src.config import JOB_MAX_ATTEMPTS, JOB_RETRY_DELAY, STALE_JOB_THRESHOLD


async def enqueue(db, job_type: str, score_id: str, payload: dict):
    await db["jobs"].insert_one({
        "type": job_type,
        "status": "pending",
        "score_id": score_id,
        "payload": payload,
        "attempts": 0,
        "next_retry_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "error": None,
    })


async def claim_next_job(db, job_type: str):
    return await db["jobs"].find_one_and_update(
        {
            "type": job_type,
            "status": "pending",
            "next_retry_at": {"$lte": datetime.now(timezone.utc)},
        },
        {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
        return_document=True,
    )


async def complete_job(db, job_id: ObjectId, result_payload: dict = None):
    await db["jobs"].update_one(
        {"_id": job_id},
        {"$set": {
            "status": "done",
            "payload": result_payload or {},
            "updated_at": datetime.now(timezone.utc),
        }},
    )


async def fail_job(db, job_id: ObjectId, error: str):
    job = await db["jobs"].find_one({"_id": job_id})
    attempts = job["attempts"] + 1
    new_status = "pending" if attempts < JOB_MAX_ATTEMPTS else "failed"
    await db.jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status": new_status,
            "attempts": attempts,
            "error": error,
            "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=JOB_RETRY_DELAY),
            "updated_at": datetime.now(timezone.utc),
        }},
    )


async def recover_stale_jobs(db):
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_JOB_THRESHOLD)
    await db["jobs"].update_many(
        {"status": "processing", "updated_at": {"$lte": cutoff}},
        {"$set": {
            "status": "pending",
            "next_retry_at": datetime.now(timezone.utc),
        }},
    )
