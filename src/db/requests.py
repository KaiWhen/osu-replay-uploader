from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.cursor import AsyncCursor


async def insert_request(db: AsyncDatabase, score_id: int, description: str, message_id: int, file_id: str = None):
    await db['requests'].insert_one({
        'score_id': score_id,
        'description': description,
        'message_id': message_id,
        'file_id': file_id,
        'resolved': False
    })


async def get_pending_request(db: AsyncDatabase, score_id: int):
    return await db['requests'].find_one({ 'score_id': score_id, 'resolved': False })


async def get_pending_requests(db: AsyncDatabase) -> AsyncCursor | None:
    return await db['requests'].find({ 'resolved': False }).to_list(length=None)


async def resolve_request(db: AsyncDatabase, req_id: ObjectId):
    await db['requests'].find_one_and_update(
        {"_id": req_id, "resolved": False},
        {"$set": {"resolved": True}},
        return_document=False
    )
