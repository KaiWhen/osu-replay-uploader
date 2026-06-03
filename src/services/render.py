import aiohttp
import sys
from pymongo.asynchronous.database import AsyncDatabase
from src.db.scores import get_score
from src.config import ORDR_API_URL, ORDR_KEY, DEFAULT_SKIN, SKIN_URL


async def submit_render(db: AsyncDatabase, score_id: int, replay_data: str) -> str | None:
    score = await get_score(db, score_id)
    skin = await db['skins'].find_one({'user_id': score['user_id']})
    skin_id = skin['skin_id'] if skin else DEFAULT_SKIN

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            ORDR_API_URL,
            data={
                'username': "o!IEBot",
                'resolution': "1280x720",
                'skin': str(skin_id),
                'customSkin': "true",
                'showDanserLogo': "false",
                'showHitCounter': "true",
                'showSliderBreaks': "true",
                'verificationKey': ORDR_KEY,
            },
            files={'replayFile': replay_data}
        )
        if resp.status != 201:
            sys.stdout.write(f"Render submit failed for {score_id}: {resp.status}")
            return None
        data = await resp.json()
        return data['renderID']


async def poll_render(render_id: str) -> tuple[bool, str | None]:
    async with aiohttp.ClientSession() as session:
        resp = await session.get(f"{ORDR_API_URL}/{render_id}")
        data = await resp.json()
        if data['done']:
            return True, data['videoUrl']
        if data.get('failed'):
            raise Exception(f"Render failed: {data.get('errorCode')}")
        return False, None


async def skin_exists(skin_id: str) -> bool:
    async with aiohttp.ClientSession() as session:
        resp = await session.get(f"{SKIN_URL}?id={skin_id}")
        skin = await resp.json()
        return skin['found']
