from pymongo.asynchronous.database import AsyncDatabase
from pymongo.typings import _DocumentType


async def get_status(db: AsyncDatabase, country_code: str) -> _DocumentType | None:
    return await db['status'].find_one({"country": country_code})


async def insert_status(db: AsyncDatabase, data: dict) -> bool:
    exists = await db['status'].find_one({"country": data['country']})
    if exists:
        return False
    await db['status'].insert_one(data)
    return True


async def update_status(db: AsyncDatabase, country_code: str, data: dict) -> bool:
    res = await db['status'].update_one(
        {"country": country_code},
        {"$set": data}
    )
    return res.modified_count == 1
