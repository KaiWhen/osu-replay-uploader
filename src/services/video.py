import os
from pathlib import Path
from src.config import VIDEOS_DIR, ORDR_BASE_API_URL, ORDR_DL_LINK_PATH
import aiohttp
import aiofiles


async def download_video(render_id: str, score_id: int) -> Path:
    video_path = VIDEOS_DIR / f"{score_id}.mp4"
    if os.path.exists(video_path):
        return str(video_path)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{ORDR_BASE_API_URL}{ORDR_DL_LINK_PATH}", params={"id": render_id}) as resp:
            data = await resp.json()
            dl_url = data["url"]

        async with session.get(dl_url) as resp:
            async with aiofiles.open(video_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(32768):
                    await f.write(chunk)

    return str(video_path)
