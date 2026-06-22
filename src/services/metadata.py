import math
from src.clients import osu
from src.config import COUNTRY_CODE, DEFAULT_SKIN_ID
from src.utils import calc_sr, get_sb_from_video, map_difficulty_to_str, sort_mods
from pymongo.asynchronous.database import AsyncDatabase


async def configure_metadata(db: AsyncDatabase, score_id: int, video_path: str):
    score_obj = await osu.score(score_id=score_id)
    user_obj = await osu.user(user=score_obj.user_id, mode="osu")
    username = score_obj._user.username
    acc = math.floor(score_obj.accuracy * 10000) / 100
    if acc == 100.0:
        acc = int(acc)

    sbs = get_sb_from_video(score_obj.id)
    status_string = score_obj.beatmap.status.__str__()[11:]

    mods = [mod.acronym for mod in score_obj.mods]
    description = await _create_description(db, score_obj, user_obj, acc, mods, sbs)
    if 'CL' in mods:
        mods.remove('CL')
    mods_str = "" if len(mods) == 0 else f"+{"".join(sort_mods(mods))}"

    _, calc_pp = await calc_sr(score_obj, mods, acc)

    if status_string == "LOVED":
        pp = round(calc_pp)
    else:
        pp = round(score_obj.pp)
    pp_str = f" {pp}PP"

    miss_str = ""
    misses = score_obj.statistics.miss
    if misses:
        miss_str = f" {misses}❌"
    elif sbs > 0 and not misses:
        miss_str = f" {sbs}xSB"
    elif sbs == 0 and not misses:
        miss_str = " FC"

    map_title = f"{score_obj.beatmapset.artist_unicode} - {score_obj.beatmapset.title} [{score_obj.beatmap.version}]"
    title_len = (
        len(map_title)
        + len(f"{username} | ")
        + len(f" {mods_str} ")
        + len(f" {acc}%")
        + len(pp_str)
        + len(miss_str)
    )
    if title_len > 100:
        title_elems = [
            f"{score_obj.beatmapset.artist_unicode}",
            f"{score_obj.beatmapset.title}",
            f"{score_obj.beatmap.version}"
        ]
        longest = max(title_elems, key=len)
        longest_idx = title_elems.index(longest)
        longest = longest[0:(len(longest) - ((title_len - 100) + 3))]
        longest += "..."
        title_elems[longest_idx] = longest
        map_title = f"{title_elems[0]} - {title_elems[1]} [{title_elems[2]}]"

    title = f"{username} | {map_title} {mods_str} {acc}%{pp_str}{miss_str}"
    special_chars = "<>"
    for c in title:
        if c in special_chars:
            title = title.replace(c, "")
    tag_title = score_obj.beatmapset.title
    for c in tag_title:
        if c in special_chars:
            tag_title = tag_title.replace(c, "")

    return {
        "file": video_path,
        "title": f"{title}",
        "description": f"{description}",
        "tags": f"osu!,osu ireland,{username},{tag_title} osu",
        "category": 20,
        "privacyStatus": "private",
        "thumb_path": ""
    }


async def _create_description(db: AsyncDatabase, score_obj, user_obj, acc: float, mods: list[str], sbs: int) -> str:
    ar_str, od_str, cs_str, bpm_str, sr_string, pp = await map_difficulty_to_str(score_obj, mods, acc)
    username = user_obj.username.replace(' ', '_')
    user_stats = user_obj.statistics
    global_rank = user_stats.global_rank
    country_rank = user_stats.country_rank
    play_count = user_stats.play_count
    play_time = round(user_obj.statistics.play_time/3600)

    meh = score_obj.statistics.meh if score_obj.statistics.meh else 0
    ok = score_obj.statistics.ok if score_obj.statistics.ok else 0
    great = score_obj.statistics.great if score_obj.statistics.great else 0
    misses = score_obj.statistics.miss if score_obj.statistics.miss else 0
    sb_string = f" {sbs}xSB" if sbs > 0 else ""
    hit_count_str = f"[{great}/{ok}/{meh}/{misses}]{sb_string}"
    status_str = score_obj.beatmap.status.__str__()[11:]
    pp_str = f"{round(score_obj.pp)}PP"
    if status_str == "LOVED":
        pp_str = f"{round(pp)}PP"

    user_skin = await db['skins'].find_one({ 'user_id': score_obj.user_id })
    skin_id = DEFAULT_SKIN_ID
    if user_skin:
        skin_id = user_skin['skin_id']

    description = [
        "👤 Player info",
        f"Profile: https://osu.ppy.sh/users/{score_obj.user_id}",
        f"Global # {global_rank} | {COUNTRY_CODE} # {country_rank} | {play_count} plays | {play_time} hrs",
        "",
        "🗺️ Map info",
        f"Map Link: https://osu.ppy.sh/b/{score_obj.beatmap.id}",
        f"{sr_string}⭐ | {status_str} | BPM: {bpm_str} | AR: {ar_str} | CS: {cs_str} | OD: {od_str}",
        "",
        "💯 Score info",
        f"Score Link: https://osu.ppy.sh/scores/{score_obj.id}",
        f"Date set: {str(score_obj.ended_at)[:-6]}",
        f"{pp_str} | {acc}% | {score_obj.max_combo}/{score_obj.beatmap.max_combo}x | {hit_count_str}",
        "",
        f"Skin: https://link.issou.best/skin/{skin_id}",
        "",
        "The uploads on this channel are automated using a bot.",
        "The bot currently tracks #1 global scores and top 10 personal pp plays of the top 100 players of Ireland.",
        "If you have a score you would like to see uploaded but does not meet the above requirements, "
        "just fill in this form here: https://forms.gle/ZABXAzAVnewbhSNr7",
        "If you would like your skin to be used in your replay, "
        "upload your skin to https://ordr.issou.best/skins/upload and use the /setskin command in the Discord.",
        "",
        "osu!Irish Discord: https://discord.gg/ZV2wshG538",
        "",
        "Replay rendering service: https://ordr.issou.best/",
        "Renderer: https://github.com/Wieku/danser-go",
        "",
        "Help keep things running: https://ko-fi.com/osuirelandreplays",
        "",
        "",
        f"#{username} #osuireland",
    ]

    return "\n".join(description)
