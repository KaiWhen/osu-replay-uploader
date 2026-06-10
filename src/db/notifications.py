from datetime import datetime, timezone
from pymongo.asynchronous.database import AsyncDatabase
from bson import ObjectId


async def create_notification(db: AsyncDatabase, video_id: str):
    await db['notifications'].insert_one({
        "video_id": video_id,
        "sent": False,
        "created_at": datetime.now(timezone.utc),
    })


async def get_unsent(db: AsyncDatabase) -> list[dict]:
    return await db['notifications'].find({"sent": False}).to_list(length=None)


async def mark_sent(db: AsyncDatabase, notification_id: ObjectId):
    await db['notifications'].update_one(
        {"_id": notification_id},
        {"$set": {"sent": True}}
    )
