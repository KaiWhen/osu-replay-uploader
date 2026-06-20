import asyncio
from datetime import datetime
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


@sio.on("disconnect")
async def on_disconnect():
    sys.stdout.write(f"[{datetime.now()}] websocket disconnected\n")
    sys.stdout.flush()


@sio.on("connect")
async def on_connect():
    sys.stdout.write(f"[{datetime.now()}] websocket connected\n")
    sys.stdout.flush()


async def connect_ws():
    await sio.connect(ORDR_BASE_API_URL, socketio_path=ORDR_WS_PATH, wait_timeout=10)


async def wait_for_render(render_id: str, timeout: int = 900):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{ORDR_BASE_API_URL}{ORDR_RENDER_PATH}", params={"renderID": render_id}) as resp:
            data = await resp.json()
            renders = data.get("renders", [])
            if renders and renders[0].get("progress") == "Done.":
                return
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
        form.add_field('resolution', "1920x1080")
        form.add_field('skin', str(skin_id))
        form.add_field('customSkin', "true")
        form.add_field('showDanserLogo', "false")
        form.add_field('showHitCounter', "true")
        form.add_field('showSliderBreaks', "true")
        form.add_field('showAimErrorMeter', "true")
        form.add_field('showScoreboard', "true")
        form.add_field('showAvatarsOnScoreboard', "true")
        form.add_field('showStrainGraph', "true")
        form.add_field('addPitch', "true")
        form.add_field('verificationKey', ORDR_KEY)
        form.add_field('replayFile', replay_data, filename=f"{score_id}.osr", content_type='application/octet-stream')

        resp = await session.post(f"{ORDR_BASE_API_URL}{ORDR_RENDER_PATH}", data=form)
        if resp.status != 201:
            sys.stdout.write(f"Render submit failed for {score_id}: {resp.status}\n")
            return None
        data = await resp.json()
        return data['renderID']


async def skin_exists(skin_id: str) -> bool:
    async with aiohttp.ClientSession() as session:
        resp = await session.get(f"{ORDR_BASE_API_URL}{ORDR_SKIN_PATH}?id={skin_id}")
        skin = await resp.json()
        return skin['found']
