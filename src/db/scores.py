from pymongo.asynchronous.database import AsyncDatabase
from pymongo.typings import _DocumentType
from pymongo.cursor import Cursor


async def insert_score(db: AsyncDatabase, score_data: dict) -> bool:
    exists = await db['scores'].find_one({"score_id": score_data['score_id']})
    if exists:
        return False
    await db['scores'].insert_one(score_data)
    return True


async def get_score(db: AsyncDatabase, query: dict) -> _DocumentType | None:
    return await db['scores'].find_one(query)


async def get_scores(db: AsyncDatabase, query: dict) -> Cursor[_DocumentType]:
    return await db['scores'].find(query).to_list(length=None)


async def update_score(db: AsyncDatabase, score_id: int, set_query: dict) -> bool:
    res = await db['scores'].update_one({
        'score_id': score_id
    },{
        '$set': set_query
    })
    return res.modified_count == 1
