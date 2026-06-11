import asyncio
import socketio
import aiohttp
import sys
from pymongo.asynchronous.database import AsyncDatabase
from src.db.scores import get_score, insert_score
from src.config import (
    ORDR_BASE_API_URL,
    ORDR_KEY,
    ORDR_WS_PATH,
    DEFAULT_SKIN_ID,
    REPLAYS_DIR,
    ORDR_SKIN_PATH,
    ORDR_RENDER_PATH
)

sio = socketio.AsyncClient()
pending_renders: dict[str, asyncio.Future] = {}


@sio.on("render_done_json")
async def on_render_done(data):
    render_id = str(data["renderID"])
    if render_id in pending_renders:
        pending_renders[render_id].set_result(None)


@sio.on("render_failed_json")
async def on_render_failed(data):
    render_id = str(data["renderID"])
    if render_id in pending_renders:
        pending_renders[render_id].set_exception(
            Exception(f"Render failed: {data.get('errorCode')}")
        )


async def connect_ws():
    await sio.connect(ORDR_BASE_API_URL, socketio_path=ORDR_WS_PATH)


async def wait_for_render(render_id: str, timeout: int = 3600):
    future = asyncio.get_running_loop().create_future()
    pending_renders[str(render_id)] = future
    try:
        await asyncio.wait_for(future, timeout=timeout)
    finally:
        pending_renders.pop(str(render_id), None)


async def submit_render(db: AsyncDatabase, score_id: int, replay_data) -> str | None:
    score = await get_score(db, {'score_id': score_id})
    skin = await db['skins'].find_one({'user_id': score['user_id']})
    skin_id = skin['skin_id'] if skin else DEFAULT_SKIN_ID

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field('username', "o!IEBot")
        form.add_field('resolution', "1280x720")
        form.add_field('skin', str(skin_id))
        form.add_field('customSkin', "true")
        form.add_field('showDanserLogo', "false")
        form.add_field('showHitCounter', "true")
        form.add_field('showSliderBreaks', "true")
        form.add_field('verificationKey', ORDR_KEY)
        form.add_field('replayFile', replay_data)

        resp = await session.post(f"{ORDR_BASE_API_URL}{ORDR_RENDER_PATH}", data=form)
        if resp.status != 201:
            sys.stdout.write(f"Render submit failed for {score_id}: {resp.status}")
            return None
        data = await resp.json()
        return data['renderID']


# async def poll_render(render_id: str) -> tuple[bool, str | None]:
#     async with aiohttp.ClientSession() as session:
#         resp = await session.get(f"{ORDR_API_URL}/{render_id}")
#         data = await resp.json()
#         if data['done']:
#             return True, data['videoUrl']
#         if data.get('failed'):
#             raise Exception(f"Render failed: {data.get('errorCode')}")
#         return False, None


async def skin_exists(skin_id: str) -> bool:
    async with aiohttp.ClientSession() as session:
        resp = await session.get(f"{ORDR_BASE_API_URL}{ORDR_SKIN_PATH}?id={skin_id}")
        skin = await resp.json()
        return skin['found']


from src.db.mongo import db
from src.services.score import get_score_data

async def test():
    score_data = await get_score_data(1749350671)
    await insert_score(db, score_data)
    replay = open(REPLAYS_DIR / f"{1749350671}.osr", 'rb')
    data = await submit_render(db, 1749350671, replay)
    print(data)
    found = await skin_exists(DEFAULT_SKIN_ID)
    print(found)

# asyncio.run(test())
