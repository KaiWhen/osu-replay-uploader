import random
import sys
import asyncio
import httplib2
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

httplib2.RETRIES = 1

MAX_RETRIES = 10
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError)
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]


async def upload_video(youtube, options: dict) -> str:
    body = dict(
        snippet=dict(
            title=options['title'],
            description=options['description'],
            tags=options.get('tags', '').split(',') if options.get('tags') else None,
            categoryId=options['category']
        ),
        status=dict(privacyStatus=options['privacyStatus'])
    )
    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(options['file'], chunksize=-1, resumable=True)
    )
    video_id = await _resumable_upload(insert_request)
    sys.stdout.write(f"Video id {video_id} was successfully uploaded.")
    return video_id


async def upload_thumbnail(youtube, video_id: str, thumb_path: str):
    insert_request = youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumb_path, chunksize=-1, resumable=True)
    )
    await _resumable_upload(insert_request)
    sys.stdout.write(f"Thumbnail uploaded for {video_id}.")


async def _resumable_upload(insert_request) -> dict:
    response = None
    error = None
    retry = 0

    while response is None:
        try:
            _, response = await asyncio.to_thread(insert_request.next_chunk)
            if response is not None and 'id' not in response and 'videoId' not in response:
                raise Exception(f"Unexpected upload response: {response}")
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = f"Retriable HTTP error {e.resp.status}: {e.content}"
            else:
                raise
        except RETRIABLE_EXCEPTIONS as e:
            error = f"Retriable error: {e}"

        if error:
            sys.stdout.write(error)
            retry += 1
            if retry > MAX_RETRIES:
                raise Exception("Max retries exceeded.")
            sleep_seconds = random.random() * (2 ** retry)
            sys.stdout.write(f"Retrying in {sleep_seconds:.1f}s...")
            await asyncio.sleep(sleep_seconds)
            error = None

    return response
