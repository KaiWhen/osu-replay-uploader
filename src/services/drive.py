import asyncio
import sys
import aiohttp
import aiofiles
import re
from src.clients import get_drive


async def download_file(file_id: str, destination: str):
    drive = get_drive()
    drive.permissions().create(body={"role": "reader", "type": "anyone"}, fileId=file_id).execute()
    URL = "https://drive.google.com/uc?export=download"

    async with aiohttp.ClientSession() as session:
        async with session.get(URL, params={"id": file_id}) as response:
            await _save_response(response, destination)


async def _save_response(response: aiohttp.ClientResponse, destination: str):
    CHUNK_SIZE = 32768
    content_disposition = response.headers.get("content-disposition", "")
    match = re.findall('filename="(.+)"', content_disposition)
    filename = match[0] if match else destination

    sys.stdout.write(f"[+] Downloading {filename}")

    async with aiofiles.open(destination, "wb") as f:
        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
            if chunk:
                await f.write(chunk)


async def delete_file(file_id: str):
    drive = get_drive()
    await asyncio.to_thread(
        drive.files().delete(fileId=file_id).execute
    )
