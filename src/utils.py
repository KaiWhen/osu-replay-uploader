import math
import os
import re
from pathlib import Path
import shutil
import sys
import aiofiles
import aiohttp
import subprocess
from ossapi import Beatmap, Beatmapset, Score, Statistics
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
VALID_MODS_FOR_CALC = {'EZ', 'HT', 'DC', 'HD', 'TC', 'DT', 'NC', 'HR', 'FL', 'BL', 'SO'}


def to_rfc3339(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds_to_minutes(seconds):
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"


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


def calc_legacy_grade(score: Score, mods: list[str]) -> str:
    count_300 = score.statistics.great if score.statistics.great else 0
    count_100 = score.statistics.ok if score.statistics.ok else 0
    count_50 = score.statistics.meh if score.statistics.meh else 0
    count_miss = score.statistics.miss if score.statistics.miss else 0
    total = count_300 + count_100 + count_50 + count_miss
    if total == 0:
        return "D"

    ratio_300 = count_300 / total
    ratio_50 = count_50 / total

    if ratio_300 == 1.0:
        grade = "SS"
    elif ratio_300 > 0.9 and ratio_50 <= 0.01 and count_miss == 0:
        grade = "S"
    elif (ratio_300 > 0.8 and count_miss == 0) or ratio_300 > 0.9:
        grade = "A"
    elif (ratio_300 > 0.7 and count_miss == 0) or ratio_300 > 0.8:
        grade = "B"
    elif ratio_300 > 0.6:
        grade = "C"
    else:
        grade = "D"

    if 'HD' in mods or 'FL' in mods:
        if grade == "SS":
            return "SSH"
        if grade == "S":
            return "SH"

    return grade


def calc_ar(base_ar: float, mods: list[str]) -> float:
    ar = base_ar
    if 'EZ' in mods:
        ar = ar / 2
    elif 'HR' in mods:
        ar = min(ar * 1.4, 10)

    if 'HT' in mods or 'DC' in mods:
        ms = ar_to_ms(ar)
        ms = ms * (4 / 3)
        ar = ms_to_ar(ms)
    elif 'DT' in mods or 'NC' in mods:
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
    if 'DT' in mods or 'NC' in mods:
        ms = ms * (2 / 3)
    elif 'HT' in mods or 'DC' in mods:
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


async def map_difficulty_to_str(score_obj, mods: list[str], acc: float, if_fc: bool=False) -> tuple[str, str, str, str, str, float, float]:
    base_ar = score_obj.beatmap.ar
    base_od = score_obj.beatmap.accuracy
    base_cs = score_obj.beatmap.cs
    base_bpm = score_obj.beatmap.bpm
    base_star_rating = round(score_obj.beatmap.difficulty_rating, 2)

    difficulty_mods = get_difficulty_mods(mods)
    ar_str, od_str, cs_str, bpm_str = calc_map_difficulty(base_ar, base_od, base_cs, base_bpm, difficulty_mods)
    star_rating, pp, if_fc_pp = await calc_sr_pp(score_obj, mods, acc, if_fc)
    sr_string = star_rating if star_rating > 0 else base_star_rating

    ar, od, cs, bpm = calc_map_difficulty(base_ar, base_od, base_cs, base_bpm, mods)
    ar_str = str(ar) if len(difficulty_mods) == 0 else f"{base_ar} ({ar})"
    od_str = str(od) if len(difficulty_mods) == 0 else f"{base_od} ({od})"
    cs_str = str(cs) if 'EZ' not in mods and 'HR' not in mods else f"{base_cs} ({cs})"
    has_speed_mod = any(mod in SPEED_MODS for mod in mods)
    bpm_str = f"{round(base_bpm)} ({round(bpm)})" if has_speed_mod else str(round(bpm))

    return ar_str, od_str, cs_str, bpm_str, sr_string, pp, if_fc_pp


async def map_difficulty_to_str_nopp(beatmap: Beatmap, mods: list[str]) -> tuple[str, str, str, str]:
    base_ar = beatmap.ar
    base_od = beatmap.accuracy
    base_cs = beatmap.cs
    base_bpm = beatmap.bpm

    difficulty_mods = get_difficulty_mods(mods)
    ar_str, od_str, cs_str, bpm_str = calc_map_difficulty(base_ar, base_od, base_cs, base_bpm, difficulty_mods)

    ar, od, cs, bpm = calc_map_difficulty(base_ar, base_od, base_cs, base_bpm, mods)
    ar_str = str(ar) if len(difficulty_mods) == 0 else f"{base_ar} ({ar})"
    od_str = str(od) if len(difficulty_mods) == 0 else f"{base_od} ({od})"
    cs_str = str(cs) if 'EZ' not in mods and 'HR' not in mods else f"{base_cs} ({cs})"
    has_speed_mod = any(mod in SPEED_MODS for mod in mods)
    bpm_str = f"{round(base_bpm)} ({round(bpm)})" if has_speed_mod else str(round(bpm))

    return ar_str, od_str, cs_str, bpm_str


async def calc_sr_pp(score_obj: Score, mods: list[str], acc: float, if_fc: bool=False):
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
    original_file_path = ""
    for fname in os.listdir(map_dir):
        if fname.casefold().endswith(f"[{diff_name}].osu"):
            original_file_path = f'maps/{set_id}/{fname}'
            file_path = original_file_path
    
    stats = get_stats(score_obj)
    passed = score_obj.passed
    if not passed:
        total = stats['great'] + stats['ok'] + stats['meh'] + stats['miss']
        file_path = trim_hit_objects(file_path, total)

    misses = score_obj.statistics.miss if score_obj.statistics.miss else 0
    lazer = False
    if 'CL' not in mods:
        lazer = True

    calc = OsuCalculator()
    res = calc.calculate(
        file_path=file_path,
        mode=0,
        mods=mods,
        statistics=stats,
        acc=acc,
        misses=misses,
        combo=score_obj.max_combo,
        legacy_total_score=1000000 if not lazer else 0
    )

    original_res = None
    if not passed:
        original_res = calc.calculate(
            file_path=original_file_path,
            mode=0,
            mods=mods,
            statistics=stats,
            acc=acc,
            combo=score_obj.max_combo,
            legacy_total_score=1000000 if not lazer else 0
        )

    if_fc_res = None
    if if_fc:
        max_great = score_obj.beatmap.count_spinners + score_obj.beatmap.count_circles + score_obj.beatmap.count_sliders
        stats['great'] = max_great - stats['meh'] - stats['ok']
        stats['miss'] = 0
        if 'large_tick_hit' in stats:
            stats['large_tick_hit'] = score_obj.maximum_statistics.large_tick_hit
        acc = calc_stable_accuracy(stats) if lazer else calc_lazer_accuracy(stats, score_obj.maximum_statistics)
        if_fc_res = calc.calculate(
            file_path=original_file_path,
            mode=0,
            mods=mods,
            statistics=stats,
            acc=acc,
            legacy_total_score=1000000 if not lazer else 0
        )

    if res.is_success:
        if_fc_pp = if_fc_res.pp if if_fc_res else 0
        stars = math.floor((res.stars if passed else original_res.stars)*100) / 100.0
        return stars, res.pp, {'if_fc_pp': if_fc_pp, 'stats': stats}
    else:
        return -1, -1, -1


async def calc_pp_many(beatmap: Beatmap, beatmapset: Beatmapset, mods: list[str]):
    diff_name = parse_diff_name(beatmap.version)
    set_id = beatmapset.id
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
    
    if 'CL' not in mods:
        mods.append('CL')
    
    calc = OsuCalculator()
    results = calc.calculate_many([
        {"file_path": file_path, "mode": 0, "mods": mods, "acc": 95.0, "legacy_total_score": 1000000},
        {"file_path": file_path, "mode": 0, "mods": mods, "acc": 98.0, "legacy_total_score": 1000000},
        {"file_path": file_path, "mode": 0, "mods": mods, "acc": 99.0, "legacy_total_score": 1000000},
        {"file_path": file_path, "mode": 0, "mods": mods, "acc": 100.0, "legacy_total_score": 1000000},
    ])

    return results


def get_stats(score: Score):
    meh = score.statistics.meh or 0
    ok = score.statistics.ok or 0
    great = score.statistics.great or 0
    misses = score.statistics.miss or 0
    slider_tail_hit = score.statistics.slider_tail_hit or 0
    large_tick_hit = score.statistics.large_tick_hit or 0

    stats = {
        'great': great,
        'ok': ok,
        'meh': meh,
        'miss': misses
    }
    if slider_tail_hit > 0:
        stats['slider_tail_hit'] = slider_tail_hit
    if large_tick_hit > 0:
        stats['large_tick_hit'] = large_tick_hit
    return stats


def calc_stable_accuracy(stats) -> float:
    count_great = stats['great']
    count_ok = stats['ok']
    count_meh = stats['meh']
    count_miss = stats['miss']

    total = 300 * count_great + 100 * count_ok + 50 * count_meh
    max_ = 300 * (count_great + count_ok + count_meh + count_miss)

    if max_ == 0:
        return 0.0

    return math.floor((total / max_)*10000) / 100.0


def calc_lazer_accuracy(stats: dict, max_stats: Statistics) -> float:
    count_great = stats['great']
    count_ok = stats['ok']
    count_meh = stats['meh']
    count_miss = stats['miss']

    count_slider_tail_hit = stats['slider_tail_hit']
    count_slider_tails = max_stats.slider_tail_hit or 0

    count_large_tick_hit = stats['large_tick_hit']
    count_large_ticks = max_stats.large_tick_hit or 0

    total = 6 * count_great + 2 * count_ok + count_meh
    max_ = 6 * (count_great + count_ok + count_meh + count_miss)

    total += 3 * count_slider_tail_hit
    max_ += 3 * count_slider_tails

    total += 0.6 * count_large_tick_hit
    max_ += 0.6 * count_large_ticks

    if max_ == 0:
        return 0.0

    return math.floor((total / max_)*10000) / 100.0


def parse_map_args(args: str) -> tuple[int | None, list[str]]:
    parts = args.strip().split()
    map_id = None
    mods_str = None

    for part in parts:
        url_match = re.search(r'osu\.ppy\.sh/beatmapsets/\d+#osu/(\d+)', part)
        if url_match:
            map_id = int(url_match.group(1))
        elif part.isdigit():
            map_id = int(part)
        else:
            mods_str = part

    mods = []
    if mods_str:
        letters = re.sub(r'[^a-zA-Z]', '', mods_str).upper()
        mods = [letters[i:i+2] for i in range(0, len(letters), 2)]
    mods = [mod for mod in mods if mod in VALID_MODS_FOR_CALC]

    return map_id, mods


def get_map_country_rank(score_obj, beatmap_score_obj):
    for count, score in enumerate(beatmap_score_obj.scores, start=1):
        if score.id == score_obj.id:
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


def trim_hit_objects(osu_file_path: str, keep: int = 30):
    path = Path(osu_file_path)
    output_path = path.with_stem(path.stem + "_trimmed")

    with open(osu_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    hit_objects_idx = None
    for i, line in enumerate(lines):
        if line.strip() == '[HitObjects]':
            hit_objects_idx = i
            break

    if hit_objects_idx is None:
        raise Exception("No [HitObjects] section found")

    header = lines[:hit_objects_idx + 1]
    objects = [l for l in lines[hit_objects_idx + 1:] if l.strip()]
    trimmed = objects[:keep]

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(header)
        f.writelines(trimmed)
    
    return output_path
