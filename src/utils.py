import os
import shutil
import sys
import aiofiles
import aiohttp
import subprocess
from ossapi import Score
import pytesseract
from datetime import datetime, timezone
from PIL import Image
from zipfile import ZipFile
from osu_tools import OsuCalculator
from osrparse import Replay
from src.config import MAPS_DIR, REPLAYS_DIR, THUMBNAILS_DIR, VIDEOS_DIR

SPECIAL_CHARS = "\":@%^*?=,<>/|"
DIFFICULTY_MODS = {'EZ', 'HR', 'DT', 'NC', 'HT', 'DC'}
SPEED_MODS = {'DT', 'NC', 'HT', 'DC'}
MOD_ORDER = ['EZ', 'HT', 'DC', 'HD', 'TC', 'DT', 'NC', 'HR', 'FL', 'BL']


def to_rfc3339(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_diff_name(diff: str):
    diff_name = diff.casefold()
    for c in diff_name:
        if c in SPECIAL_CHARS:
            diff_name = diff_name.replace(c, "")
    return diff_name


def get_difficulty_mods(mods: list[str]) -> list[str]:
    return [mod for mod in mods if mod in DIFFICULTY_MODS]


def sort_mods(mods: list[str]) -> list[str]:
    return sorted(mods, key=lambda mod: MOD_ORDER.index(mod) if mod in MOD_ORDER else len(MOD_ORDER))


def ar_to_ms(ar: float) -> float:
    if ar <= 5:
        return 1800 - 120 * ar
    else:
        return 1200 - 150 * (ar - 5)


def ms_to_ar(ms: float) -> float:
    if ms >= 1200:
        return (1800 - ms) / 120
    else:
        return 5 + (1200 - ms) / 150


def calc_ar(base_ar: float, mods: list[str]) -> float:
    ar = base_ar
    if 'EZ' in mods:
        ar = ar / 2
    elif 'HR' in mods:
        ar = min(ar * 1.4, 10)

    if 'HT' in mods:
        ms = ar_to_ms(ar)
        ms = ms * (4 / 3)
        ar = ms_to_ar(ms)
    elif 'DT' in mods:
        ms = ar_to_ms(ar)
        ms = ms * (2 / 3)
        ar = ms_to_ar(ms)

    ar = max(-5, min(11, ar))
    return round(ar, 2)


def calc_od(base_od: float, mods: list[str]) -> float:
    od = base_od
    if 'EZ' in mods:
        od = od / 2
    elif 'HR' in mods:
        od = min(od * 1.4, 10)

    ms = 80 - 6 * od
    if 'DT' in mods:
        ms = ms * (2 / 3)
    elif 'HT' in mods:
        ms = ms * (4 / 3)

    return round((80 - ms) / 6, 2)


def calc_cs(base_cs: float, mods: list[str]) -> float:
    cs = base_cs
    if 'EZ' in mods:
        cs = cs / 2
    elif 'HR' in mods:
        cs = round(cs * 1.3, 1)

    return cs


def calc_bpm(base_bpm: float, mods: list[str]) -> float:
    bpm = base_bpm
    if "DT" in mods or "NC" in mods:
        bpm = round(bpm * 1.5)
    if "HT" in mods or "DC" in mods:
        bpm = round(bpm * 0.75)

    return bpm


def calc_map_difficulty(base_ar: float, base_od: float, base_cs: float,
                        base_bpm: float, mods: list[str]) -> tuple[float, float, float, float]:
    ar = calc_ar(base_ar, mods)
    od = calc_od(base_od, mods)
    cs = calc_cs(base_cs, mods)
    bpm = calc_bpm(base_bpm, mods)

    return ar, od, cs, bpm


async def map_difficulty_to_str(score_obj, mods: list[str], acc: float) -> tuple[str, str, str, str, str, float]:
    base_ar = score_obj.beatmap.ar
    base_od = score_obj.beatmap.accuracy
    base_cs = score_obj.beatmap.cs
    base_bpm = score_obj.beatmap.bpm
    base_star_rating = round(score_obj.beatmap.difficulty_rating, 2)

    difficulty_mods = get_difficulty_mods(mods)
    ar_str, od_str, cs_str, bpm_str = calc_map_difficulty(base_ar, base_od, base_cs, base_bpm, difficulty_mods)
    star_rating, pp = await calc_sr(score_obj, mods, acc)
    sr_string = star_rating if star_rating > 0 else base_star_rating

    ar, od, cs, bpm = calc_map_difficulty(base_ar, base_od, base_cs, base_bpm, mods)
    ar_str = str(ar) if len(difficulty_mods) == 0 else f"{base_ar} ({ar})"
    od_str = str(od) if len(difficulty_mods) == 0 else f"{base_od} ({od})"
    cs_str = str(cs) if 'EZ' not in mods and 'HR' not in mods else f"{base_cs} ({cs})"
    has_speed_mod = any(mod in SPEED_MODS for mod in mods)
    bpm_str = f"{base_bpm} ({bpm})" if has_speed_mod else str(bpm)

    return ar_str, od_str, cs_str, bpm_str, sr_string, pp


async def calc_sr(score_obj: Score, mods: list[str], acc: float):
    diff_name = parse_diff_name(score_obj.beatmap.version)
    set_id = score_obj.beatmapset.id
    map_dir = MAPS_DIR / f"{set_id}"
    if not os.path.exists(map_dir):
        os.mkdir(map_dir)
        try:
            await download_map(set_id)
        except Exception as e:
            sys.stdout.write(f"Error downloading map: {e}\n")
            return -1

    file_path = ""
    for fname in os.listdir(map_dir):
        if fname.casefold().endswith(f"[{diff_name}].osu"):
            file_path = f'maps/{set_id}/{fname}'

    if "CL" not in mods:
        mods.append("CL")
    
    misses = score_obj.statistics.miss if score_obj.statistics.miss else 0

    calc = OsuCalculator()
    res = calc.calculate(
        file_path=file_path,
        mode=0,
        mods=mods,
        acc=acc,
        misses=misses,
        combo=score_obj.max_combo,
        legacy_total_score=1000000
    )

    if res.is_success:
        return round(res.stars, 2), res.pp
    else:
        return -1, -1


def get_map_country_rank(score_obj, beatmap_score_obj):
    for count, score in enumerate(beatmap_score_obj.scores, start=1):
        if score.user_id == score_obj.user_id:
            return count
    return -1


async def download_map(set_id: int):
    urls = [
        f"https://catboy.best/d/{set_id}",
        f"https://beatconnect.io/b/{set_id}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        for url in urls:
            async with session.get(url) as r:
                sys.stdout.write(f"{url} -> status {r.status}\n")
                if r.ok:
                    map_file_path = MAPS_DIR / f"{set_id}/map.osz"
                    async with aiofiles.open(map_file_path, 'wb') as outfile:
                        async for chunk in r.content.iter_chunked(32768):
                            await outfile.write(chunk)
                    with ZipFile(map_file_path, 'r') as zip_ref:
                        zip_ref.extractall(MAPS_DIR / f"{set_id}")
                    return


def get_sb_from_video(score_id: int) -> int:
    video_path = VIDEOS_DIR / f"{score_id}.mp4"
    frame_path = f"{os.path.dirname(os.path.realpath(video_path))}/{score_id}.png"
    subprocess.run([
        "ffmpeg", "-n",
        "-sseof", "-6.9",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        f"{frame_path}"
    ], check=True)

    frame = Image.open(frame_path)
    region = frame.crop((199, 261, 259, 307))
    region = region.convert("L")
    region = region.resize((region.width * 3, region.height * 3), Image.LANCZOS)
    region = region.point(lambda px: 255 if px > 128 else 0)
    text = pytesseract.image_to_string(region, config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789")
    return int(text.strip()) if text.strip() else 0


def verify_replay_file(replay_path: str) -> bool:
    try:
        Replay.from_path(replay_path)
        return True
    except:
        return False


def clear_score_files(score_id: int):
    replay_path = REPLAYS_DIR / f"{score_id}.osr"
    video_path = VIDEOS_DIR / f"{score_id}.mp4"
    video_frame_path = VIDEOS_DIR / f"{score_id}.png"
    thumbnail_path = THUMBNAILS_DIR / f"{score_id}"
    if os.path.exists(replay_path):
        os.remove(replay_path)
    if os.path.exists(video_path):
        os.remove(video_path)
    if os.path.exists(video_frame_path):
        os.remove(video_frame_path)
    if os.path.exists(thumbnail_path):
        shutil.rmtree(thumbnail_path)


def is_majority_upper(s: str) -> bool:
    upper_count = sum(1 for ch in s if ch.isupper())
    lower_count = sum(1 for ch in s if ch.islower())

    if upper_count + lower_count == 0:
        return False

    return upper_count > lower_count
