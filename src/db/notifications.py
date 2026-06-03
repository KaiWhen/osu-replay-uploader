from datetime import datetime, timezone


async def create_notification(db, video_id: str):
    await db['notifications'].insert_one({
        "video_id": video_id,
        "sent": False,
        "created_at": datetime.now(timezone.utc),
    })


async def get_unsent(db) -> list[dict]:
    return await db['notifications'].find({"sent": False}).to_list(length=None)


async def mark_sent(db, notification_id):
    await db['notifications'].update_one(
        {"_id": notification_id},
        {"$set": {"sent": True}}
    )
