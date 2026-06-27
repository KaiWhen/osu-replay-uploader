import os
import sys
import aiohttp
import math
import re
from PIL import Image, ImageFont, ImageDraw, ImageFilter
from src.clients import osu
from src.config import THUMBNAILS_DIR
from src.utils import (
    calc_bpm,
    calc_legacy_grade,
    calc_sr,
    download_map,
    get_map_country_rank,
    is_majority_upper,
    sort_mods,
    get_sb_from_video
)


async def create_thumbnail(score_id: int) -> str:
    thumb_path = THUMBNAILS_DIR / str(score_id) / f"{score_id}.png"
    if os.path.exists(thumb_path):
        return str(thumb_path)

    score_obj = await osu.score(score_id=score_id)
    user_obj = await osu.user(user=score_obj.user_id)
    beatmap_score_obj = await osu.beatmap_scores(beatmap_id=score_obj.beatmap.id, mode="osu", type="country")
    scores_top50 = await osu.user_scores(user_id=score_obj.user_id, type="best", limit=50, mode="osu")

    set_id = score_obj.beatmapset.id
    diff = score_obj.beatmap.version
    bg_path = await get_map_bg(set_id, diff)

    if not os.path.exists(THUMBNAILS_DIR / str(score_id)):
        os.mkdir(THUMBNAILS_DIR / str(score_id))
    
    user_id = score_obj.user_id
    status_string = score_obj.beatmap.status.__str__()[11:]
    mods = [mod.acronym for mod in score_obj.mods]

    rank = score_obj.rank.__str__()[6:]
    if 'CL' in mods:
        rank = calc_legacy_grade(score_obj, mods)

    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://a.ppy.sh/{user_id}") as r:
            avatar_data = await r.read()
            avatar_path = THUMBNAILS_DIR / str(score_id) / f"{user_id}.png"
            with open(avatar_path, 'wb') as outfile:
                outfile.write(avatar_data)

    ratio = 1.5

    thumbnail = Image.open(bg_path).convert('RGBA').resize((1280, 720))
    base = Image.open("thumbnails/assets/base.png").convert('RGBA')
    rank_image = Image.open(f"thumbnails/assets/ranks/{rank}.png").convert('RGBA')
    sr_image = Image.open(f"thumbnails/assets/sr_graphic/{status_string}.png").convert('RGBA')
    avatar = Image.open(avatar_path).convert('RGBA').resize((round(256/ratio), round(256/ratio)))
    pb_image = Image.open("thumbnails/assets/pb.png").convert('RGBA')
    fc_image = Image.open("thumbnails/assets/FC.png").convert('RGBA')

    country_ranking = get_map_country_rank(score_obj, beatmap_score_obj)
    
    pb_text = None
    for count, score in enumerate(scores_top50, start=1):
        if score_obj.id == score.id:
            pb_text = f"#{count}"
            break

    acc = math.floor(score_obj.accuracy * 10000) / 100
    acc_text = f"{'%.2f' % acc}%"
    username_text = f"{user_obj.username}"

    if country_ranking > 0:
        country_ranking_text = f"#{country_ranking}"
        country_rank_text = f"#{user_obj.statistics.country_rank}"
    else:
        country_ranking_text = f"#-"
        country_rank_text = f"#-"

    global_ranking_text = f"#{score_obj.rank_global}"
    global_rank_text = f"#{user_obj.statistics.global_rank}"

    title_text = f"{score_obj.beatmapset.artist} - {score_obj.beatmapset.title}"
    title_majority_upper = is_majority_upper(title_text)
    title_x_offset = 0
    if not title_majority_upper and len(title_text) > 42:
        title_text = title_text[:39] + "..."
        title_x_offset = 20
    elif title_majority_upper and len(title_text) > 35:
        title_text = title_text[:32] + "..."
        title_x_offset = 20

    diff_text = f"[{score_obj.beatmap.version}]"
    diff_majority_upper = is_majority_upper(diff_text)
    if not diff_majority_upper and len(diff_text) > 32:
        diff_text = diff_text[:28] + "...]"
    elif diff_majority_upper and len(diff_text) > 28:
        diff_text = diff_text[:24] + "...]"

    sliderbreaks = get_sb_from_video(score_id)
    misses = score_obj.statistics.miss
    miss_text = ""
    miss_text_colour = (255, 255, 255)
    if not misses and sliderbreaks == 0:
        miss_text = "FC"
    elif misses and misses > 0:
        miss_text = f"{misses}x"
        miss_text_colour = (255, 0, 0)
    elif sliderbreaks > 0 and not misses:
        miss_text = f"{sliderbreaks}xSB"

    base_star_rating = round(score_obj.beatmap.difficulty_rating, 2)
    sr_text = f"{base_star_rating}"
    sr, pp = await calc_sr(score_obj, mods, acc)
    if sr > 0:
        sr_text = f"{sr}"
    sr_font_size = 62
    sr_text_y_offset = 0
    sr_text_x_offset = 0
    if len(sr_text) > 4:
        sr_font_size = 54
        sr_text_y_offset = 4
        sr_text_x_offset = -12

    pp_text = "0PP"
    if status_string in ['RANKED', 'APPROVED']:
        pp_text = f"{round(score_obj.pp)}PP"
    elif status_string == 'LOVED':
        pp_text = f"{round(pp)}PP"

    acc_pp_font_size = 62
    acc_pp_y_adj = 0
    if len(pp_text) > 5 and len(acc_text) > 6:
        acc_pp_font_size = 58
        acc_pp_y_adj = 3

    base_bpm = score_obj.beatmap.bpm
    bpm = calc_bpm(base_bpm, mods)
    bpm_text = f"{round(bpm)}bpm"

    futura_medium = THUMBNAILS_DIR / "assets/fonts/futura_medium.ttf"
    nexa_heavy = THUMBNAILS_DIR / "assets/fonts/Nexa-Heavy.ttf"
    google_flex_regular = THUMBNAILS_DIR / "assets/fonts/GoogleSansFlex-Regular.ttf"
    google_flex_medium = THUMBNAILS_DIR / "assets/fonts/GoogleSansFlex-Medium.ttf"

    title_font = ImageFont.truetype(futura_medium, 62)
    diff_font = ImageFont.truetype(futura_medium, 54)
    acc_font = ImageFont.truetype(google_flex_regular, acc_pp_font_size)
    pp_font = ImageFont.truetype(google_flex_medium, acc_pp_font_size)
    sr_font = ImageFont.truetype(google_flex_medium, sr_font_size)
    ranking_font = ImageFont.truetype(nexa_heavy, 35)
    country_font = ImageFont.truetype(nexa_heavy, 42)
    user_font = ImageFont.truetype(futura_medium, 45)
    miss_font = ImageFont.truetype(google_flex_medium, 105 if 'SB' in miss_text else 125)
    bpm_font = ImageFont.truetype(google_flex_medium, 38)

    thumbnail.paste(base, (0, 0), base)
    thumbnail.paste(rank_image, (0, 0), rank_image)
    thumbnail.paste(sr_image, (0, 0), sr_image)

    thumbnail = apply_drop_shadow(thumbnail, avatar, (11, 533))

    bg_w, _ = thumbnail.size
    sorted_mods = sort_mods(mods)
    mod_w = 140
    mods_length = mod_w * (len(mods) - 1)
    mods_offset = (bg_w - mods_length) // 2
    count = 0
    for mod in sorted_mods:
        if mod == 'CL':
            continue
        mod_image = Image.open(THUMBNAILS_DIR / f"assets/mods/mod_{mod}.png").convert('RGBA').resize((150, 122))
        thumbnail.paste(mod_image, ((mods_offset + mod_w*count) - 20, 430), mod_image)
        count = count + 1
    
    # sr text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (620 + sr_text_x_offset, 5 + sr_text_y_offset),
        sr_text,
        (255, 255, 255),
        font=sr_font
    )
    # bpm text
    image = ImageDraw.Draw(thumbnail)
    _, _, bpm_w, _ = image.textbbox((0, 0), bpm_text, font=bpm_font)
    bpm_box_left = 1054
    bpm_box_right = 1239
    bpm_box_center_x = (bpm_box_left + bpm_box_right) // 2
    bpm_x = bpm_box_center_x - bpm_w // 2
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (bpm_x, 40),
        bpm_text,
        (255, 255, 255),
        font=bpm_font,
        shadow_offset=(0, 1),
        shadow_color=(0,0,0,191),
        shadow_blur=2,
        letter_spacing=1
    )
    # acc text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (420 if len(pp_text) <= 5 and len(acc_text) <= 6 else 400, 310 + acc_pp_y_adj),
        acc_text,
        (255, 255, 255),
        font=acc_font,
        shadow_color=(0,0,0,170),
        shadow_blur=8
    )
    # pp text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (668 if len(pp_text) <= 5 and len(acc_text) <= 6
            else (648 if len(acc_text) <= 6
            else (677 if len(pp_text) <= 5
            else 659)), 310 + acc_pp_y_adj),
        pp_text,
        (0, 255, 0),
        font=pp_font,
        shadow_offset=(0, 8),
        shadow_color=(0,0,0,170),
        shadow_blur=8,
        clone_blur_radius=10,
        glow_color=(0, 255, 0),
        glow_opacity=0.5
    )
    # diff text
    image = ImageDraw.Draw(thumbnail)
    _, _, diff_w, _ = image.textbbox((0, 0), diff_text, font=diff_font)
    thumbnail = draw_text_with_shadow(
        thumbnail,
        ((bg_w - diff_w)/2, 210),
        diff_text,
        (255, 255, 255),
        font=diff_font,
        shadow_offset=(0, 8),
        shadow_color=(0,0,0,120),
        shadow_blur=8,
        letter_spacing=-0.75
    )
    # map country ranking text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (90, 397), 
        country_ranking_text,
        (255, 255, 255),
        font=ranking_font,
        shadow_color=(0,0,0,100),
        shadow_blur=2
    )
    # map global ranking text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (90, 320),
        global_ranking_text,
        (255, 255, 255),
        font=ranking_font,
        shadow_color=(0,0,0,100),
        shadow_blur=2
    )
    # username text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (204, 653),
        username_text,
        (255, 255, 255),
        font=user_font,
        shadow_color=(0,0,0,100),
        shadow_blur=2
    )
    # country rank text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (264, 534), 
        country_rank_text,
        (255, 255, 255),
        font=country_font,
        shadow_color=(0,0,0,100),
        shadow_blur=2
    )
    # global rank text
    thumbnail = draw_text_with_shadow(
        thumbnail,
        (264, 598),
        global_rank_text,
        (255, 255, 255),
        font=country_font,
        shadow_color=(0,0,0,100),
        shadow_blur=2
    )
    if pb_text:
        thumbnail.paste(pb_image, (0, 0), pb_image)
        thumbnail = draw_text_with_shadow(
            thumbnail,
            (90, 240),
            pb_text,
            (255, 255, 255),
            font=ranking_font,
            shadow_color=(0,0,0,100),
            shadow_blur=2
        )
    if miss_text == "FC":
        thumbnail.paste(fc_image, (0, 0), fc_image)
    elif 'SB' in miss_text:
        thumbnail = draw_text_with_shadow(
            thumbnail,
            (23, 5),
            miss_text,
            miss_text_colour,
            font=miss_font,
            shadow_offset=(0, 4),
            shadow_color=(0,0,0,170),
            shadow_blur=8,
            clone_blur_radius=15,
            glow_color=miss_text_colour,
            glow_opacity=0.7,
            letter_spacing=-1
        )
    else:
        thumbnail = draw_text_with_shadow(
            thumbnail,
            (23, -10),
            miss_text,
            miss_text_colour,
            font=miss_font,
            shadow_offset=(0, 4),
            shadow_color=(0,0,0,170),
            shadow_blur=8,
            clone_blur_radius=20,
            glow_color=miss_text_colour,
            glow_opacity=0.6,
            letter_spacing=-1
        )

    image = ImageDraw.Draw(thumbnail)
    # title text
    _, _, title_w, _ = image.textbbox((0, 0), title_text, font=title_font)
    draw_text_with_spacing(
        image,
        ((bg_w - title_w)/2 + 1 + title_x_offset, 137),
        title_text, (26, 26, 26),
        font=title_font,
        stroke_width=1,
        spacing=-1
    )
    draw_text_with_spacing(
        image,
        ((bg_w - title_w)/2 + title_x_offset, 135),
        title_text,
        (255, 255, 255),
        font=title_font,
        spacing=-1
    )

    thumbnail = thumbnail.convert('RGB')
    thumbnail.save(thumb_path)

    return str(thumb_path)


def draw_text_with_spacing(draw, pos, text, fill, font, stroke_fill=(255,255,255), stroke_width=0, spacing=1):
    x, y = pos
    for char in text:
        draw.text((x, y), char, font=font, fill=fill, stroke_fill=stroke_fill, stroke_width=stroke_width)
        bbox = font.getbbox(char)
        x += bbox[2] - bbox[0] + spacing


def draw_text_with_shadow(
    base, pos, text, fill, font,
    shadow_color=(0, 0, 0, 77),
    shadow_offset=(0, 2),
    shadow_blur=2,
    letter_spacing=0,
    clone_blur_radius=0,
    glow_color=(255, 255, 255),
    glow_opacity=1.0
):
    x, y = pos

    def render_text_layer(color):
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        cx = x
        for char in text:
            draw.text((cx, y), char, font=font, fill=color)
            bbox = font.getbbox(char)
            cx += bbox[2] - bbox[0] + letter_spacing
        return layer

    text_layer = render_text_layer(fill)

    if clone_blur_radius > 0:
        _, _, _, a = text_layer.split()
        a = a.filter(ImageFilter.GaussianBlur(radius=clone_blur_radius))
        a = a.point(lambda px: int(px * glow_opacity))
        glow_layer = Image.new("RGBA", base.size, glow_color + (0,))
        glow_layer.putalpha(a)

    shadow_layer = render_text_layer(shadow_color)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    shadow_shifted = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_shifted.paste(shadow_layer, shadow_offset)

    base = Image.alpha_composite(base, shadow_shifted)
    if clone_blur_radius > 0:
        base = Image.alpha_composite(base, glow_layer)
    base = Image.alpha_composite(base, text_layer)
    return base


def apply_drop_shadow(base, img, pos,
    shadow_color=(0, 0, 0, 70),
    shadow_offset=(-1, 2),
    shadow_blur=4
):
    _, _, _, a = img.split()
    shadow_img = Image.new("RGBA", img.size, shadow_color)
    opacity = shadow_color[3] / 255
    a_scaled = a.point(lambda px: int(px * opacity))
    shadow_img.putalpha(a_scaled)

    shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_layer.paste(shadow_img, (pos[0] + shadow_offset[0], pos[1] + shadow_offset[1]))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))

    img_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    img_layer.paste(img, pos, img)

    base = Image.alpha_composite(base, shadow_layer)
    base = Image.alpha_composite(base, img_layer)
    return base


async def get_map_bg(set_id: int, diff: str) -> str:
    if not os.path.exists(f"maps/{set_id}"):
        os.mkdir(f"maps/{set_id}")
    
    bg_path = None
    backup_bg_path = THUMBNAILS_DIR / "assets/default.png"

    map_dir = os.listdir(f"maps/{set_id}")
    if len(map_dir) == 0:
        try:
            await download_map(set_id)
        except Exception as e:
            sys.stdout.write(f"Error downloading map: {e}\n")
            return backup_bg_path

    special_chars = "\":@%^*?=,<>/|"
    diff_name = diff.casefold()

    for fname in os.listdir(f'maps/{set_id}'):
        for c in diff_name:
            if c in special_chars:
                diff_name = diff_name.replace(c, "")
        if fname.casefold().endswith(f"[{diff_name}].osu"):
            f = open(f"maps/{set_id}/{fname}", 'r')
            file_strings = re.findall('(?:")([^"]*)(?:")', f.read())
            # print(file_strings)
            for string in file_strings:
                if (string.casefold().endswith(".png")
                    or string.casefold().endswith(".jpg")
                    or string.casefold().endswith(".jpeg")):
                    bg_path = f"maps/{set_id}/{string}"
                    continue
        elif (not fname.casefold().endswith(".png")
              and not fname.casefold().endswith(".jpg")
              and not fname.casefold().endswith(".jpeg")
              and not fname.casefold().endswith(".osu")):
            if os.path.isdir(f"maps/{set_id}/{fname}"):
                continue
            else:
                os.remove(f"maps/{set_id}/{fname}")
        elif fname.casefold().endswith(".png") or fname.casefold().endswith(".jpg") or fname.casefold().endswith(".jpeg"):
            backup_bg_path = f"maps/{set_id}/{fname}"
    if bg_path is not None:
        file_exists = os.path.exists(bg_path)
        if not file_exists:
            bg_path = backup_bg_path
    else:
        bg_path = backup_bg_path
    return bg_path
