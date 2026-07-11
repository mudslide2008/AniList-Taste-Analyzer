
from __future__ import annotations

import io
import math
import os
import urllib.request
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
except ImportError as exc:
    raise RuntimeError(
        "The share-card generator requires Pillow. Run: py -m pip install Pillow"
    ) from exc


BG = "#07111e"
PANEL = "#0b1a2b"
PANEL_ALT = "#10263c"
TEXT = "#f4f7fb"
MUTED = "#a8b7ca"
CYAN = "#54d9ee"
LINE = "#28516c"
GOOD = "#78e5b4"
GOLD = "#ffd36a"


def _font_candidates(bold: bool = False) -> list[str]:
    windows = os.environ.get("WINDIR", r"C:\Windows")
    return [
        str(Path(windows) / "Fonts" / ("segoeuib.ttf" if bold else "segoeui.ttf")),
        str(Path(windows) / "Fonts" / ("arialbd.ttf" if bold else "arial.ttf")),
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for candidate in _font_candidates(bold):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _wrap_pixels(draw, text, font, max_width):
    words = str(text or "").replace("\n", " \n ").split()
    lines, current = [], ""
    for word in words:
        if word == "\n":
            if current:
                lines.append(current)
                current = ""
            continue
        trial = word if not current else f"{current} {word}"
        if _measure(draw, trial, font)[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _text_height(draw, text, font, max_width, spacing=8, max_lines=None):
    lines = _wrap_pixels(draw, text, font, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]
    line_h = _measure(draw, "Ag", font)[1]
    return max(0, len(lines) * line_h + max(0, len(lines) - 1) * spacing), lines


def _draw_wrapped(draw, x, y, text, font, fill, max_width, spacing=8, max_lines=None):
    _, lines = _text_height(draw, text, font, max_width, spacing, max_lines)
    line_h = _measure(draw, "Ag", font)[1]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h + spacing
    return y


def _panel(draw, box, fill=PANEL, outline=LINE, radius=24, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _download_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AniList-Taste-Analyzer/2.6"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return Image.open(io.BytesIO(response.read())).convert("RGB")
    except Exception:
        return None


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))


def _circle_crop(image: Image.Image, diameter: int) -> Image.Image:
    square = ImageOps.fit(image, (diameter, diameter), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    result.paste(square.convert("RGBA"), (0, 0), mask)
    return result


def _gradient(size):
    width, height = size
    image = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (
            int(8 * (1-ratio) + 3 * ratio),
            int(28 * (1-ratio) + 10 * ratio),
            int(48 * (1-ratio) + 22 * ratio),
        )
        draw.line((0, y, width, y), fill=color)
    return image


def _top_names(stats: Iterable[Any], limit: int = 4) -> list[Any]:
    result = []
    for stat in stats:
        if getattr(stat, "name", ""):
            result.append(stat)
        if len(result) >= limit:
            break
    return result


def _creator_parts(value: str) -> tuple[str, str]:
    return tuple(part.strip() for part in value.split(" — ", 1)) if " — " in value else (value.strip(), "")


def _signal_value(taste_glance, label):
    return next((str(v) for k, v in taste_glance.get("signals", []) if k == label), "")


def _best_recommendation(rec_groups):
    return ((rec_groups or {}).get("Best matches") or [None])[0]


def _hero_art(rows, rec_groups, project_root):
    custom = next(
        (p for p in [
            project_root / "assets" / "cover_background.jpg",
            project_root / "assets" / "cover_background.png",
        ] if p.exists()),
        None,
    )
    if custom:
        try:
            return Image.open(custom).convert("RGB")
        except OSError:
            pass

    top_rows = sorted(
        rows,
        key=lambda row: (
            row.get("rating") or 0,
            bool(row.get("banner_image")),
            row.get("popularity") or 0,
        ),
        reverse=True,
    )
    for row in top_rows:
        art = _download_image(row.get("banner_image") or row.get("cover_image") or "")
        if art:
            return art

    best = _best_recommendation(rec_groups)
    if best:
        return _download_image(best.get("banner_image") or best.get("cover_image") or "")
    return None


def _draw_person_row(canvas, draw, x, y, width, stat, role=False):
    avatar = _download_image(getattr(stat, "image", ""))
    if avatar:
        canvas.alpha_composite(_circle_crop(avatar, 58), (x, y))
    else:
        draw.ellipse((x, y, x+58, y+58), fill="#174864")
    name, subtitle = _creator_parts(stat.name) if role else (stat.name, "")
    draw.text((x+76, y+2), name, font=_font(23, True), fill=TEXT)
    if subtitle:
        _draw_wrapped(draw, x+76, y+32, subtitle, _font(17), MUTED, width-80, spacing=4, max_lines=2)
    return y + 76


def _draw_signal_card(draw, x, y, w, h, theme):
    _panel(draw, (x, y, x+w, y+h), fill=PANEL_ALT, radius=20)
    draw.ellipse((x+24, y+24, x+64, y+64), fill=CYAN)
    draw.text((x+82, y+24), theme.upper(), font=_font(22, True), fill=CYAN)
    desc = {
        "Travel": "Journeys, new places, and the excitement of the unknown.",
        "Historical": "Stories shaped by the past, legacy, and lived history.",
        "Survival": "Resourcefulness and perseverance against difficult odds.",
        "Dungeon": "Exploration, danger, and discovery in unfamiliar worlds.",
        "Educational": "Learning is part of the entertainment rather than a lecture.",
        "Work": "People taking pride in a craft, profession, or shared goal.",
        "Coming of Age": "Growth through experience, failure, and changing relationships.",
        "Science": "Curiosity, experimentation, and understanding how things work.",
    }.get(theme, "A recurring theme strongly connected to top-rated anime.")
    _draw_wrapped(draw, x+24, y+84, desc, _font(18), TEXT, w-48, spacing=6, max_lines=5)


def _draw_cover(user, taste_glance, stats, rows, score_format, overall, rec_groups, output_dir):
    W, H = 1600, 2200
    image = _gradient((W, H)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    project_root = Path(__file__).resolve().parent.parent

    draw.rounded_rectangle((28, 28, W-28, H-28), radius=28, outline=CYAN, width=3)

    art = _hero_art(rows, rec_groups, project_root)
    hero = (54, 54, W-54, 720)
    if art:
        art = _cover_crop(art, (hero[2]-hero[0], hero[3]-hero[1])).convert("RGBA")
        art = ImageEnhance.Brightness(art).enhance(0.58)
        image.alpha_composite(art, (hero[0], hero[1]))
        shade = Image.new("RGBA", (hero[2]-hero[0], hero[3]-hero[1]), (4, 12, 24, 0))
        shade_draw = ImageDraw.Draw(shade)
        for x in range(shade.width):
            alpha = int(225 * max(0, 1 - x / (shade.width * 0.72)))
            shade_draw.line((x, 0, x, shade.height), fill=(4, 12, 24, alpha))
        image.alpha_composite(shade, (hero[0], hero[1]))
    else:
        _panel(draw, hero, fill=PANEL, radius=24)

    # Header and metrics.
    draw.text((88, 88), str(user.get("name") or "AniList user"), font=_font(78, True), fill=TEXT)
    draw.text((92, 176), "ANIME TASTE REPORT", font=_font(28, True), fill=CYAN)

    metric_box = (1220, 78, 1510, 322)
    _panel(draw, metric_box, fill="#081526e8", radius=22)
    draw.text((1260, 104), str(len(rows)), font=_font(46, True), fill=TEXT)
    draw.text((1262, 158), "RATED ANIME", font=_font(16, True), fill=MUTED)
    draw.text((1260, 198), f"{overall:.1f}/{int(score_format['max'])}", font=_font(40, True), fill=TEXT)
    draw.text((1262, 246), "AVERAGE", font=_font(16, True), fill=MUTED)
    top = _signal_value(taste_glance, "Top-rating rate")
    if top:
        draw.text((1400, 198), top, font=_font(40, True), fill=TEXT)
        draw.text((1402, 246), "TOP RATE", font=_font(16, True), fill=MUTED)

    headline = taste_glance.get("headline") or "A personal anime taste profile."
    headline_font = _font(48, True)
    headline_h, _ = _text_height(draw, headline, headline_font, 1000, 10, 3)
    summary = taste_glance.get("summary") or ""
    summary_font = _font(24)
    summary_h, _ = _text_height(draw, summary, summary_font, 960, 8, 5)
    hero_text_y = 300
    _draw_wrapped(draw, 88, hero_text_y, headline, headline_font, TEXT, 1000, 10, 3)
    _draw_wrapped(draw, 88, hero_text_y+headline_h+24, summary, summary_font, TEXT, 960, 8, 5)

    # Signals.
    signal_title_y = 760
    draw.text((88, signal_title_y), "YOUR STRONGEST SIGNALS", font=_font(30, True), fill=CYAN)
    themes = [str(t) for t in (taste_glance.get("themes") or []) if t][:4]
    card_y, gap = 820, 18
    card_w = (1424 - gap*3) // 4
    for i, theme in enumerate(themes):
        _draw_signal_card(draw, 88+i*(card_w+gap), card_y, card_w, 260, theme)

    # Lower columns.
    lower_y, lower_h = 1120, 700
    gap = 18
    col_w = (1424-gap*2)//3
    boxes = [(88+i*(col_w+gap), lower_y, 88+i*(col_w+gap)+col_w, lower_y+lower_h) for i in range(3)]
    for box in boxes:
        _panel(draw, box, fill=PANEL, radius=22)

    # Creators.
    x1,y1,x2,y2 = boxes[0]
    draw.text((x1+26,y1+24),"RECURRING CREATORS",font=_font(25,True),fill=CYAN)
    y = y1+80
    for stat in _top_names(stats.get("staff") or [],4):
        y = _draw_person_row(image, draw, x1+26, y, col_w-52, stat, role=True)

    # VAs.
    x1,y1,x2,y2 = boxes[1]
    draw.text((x1+26,y1+24),"RECURRING JAPANESE VAS",font=_font(24,True),fill=CYAN)
    y = y1+80
    for stat in _top_names(stats.get("japanese_vas") or [],4):
        y = _draw_person_row(image, draw, x1+26, y, col_w-52, stat, role=False)

    # Highlights.
    x1,y1,x2,y2 = boxes[2]
    draw.text((x1+26,y1+24),"OTHER HIGHLIGHTS",font=_font(25,True),fill=CYAN)
    alignment = _signal_value(taste_glance,"Community alignment") or "—"
    draw.text((x1+26,y1+90),"COMMUNITY ALIGNMENT",font=_font(17,True),fill=MUTED)
    _draw_wrapped(draw,x1+26,y1+122,alignment,_font(29,True),CYAN,col_w-52,6,2)
    draw.line((x1+26,y1+205,x2-26,y1+205),fill=LINE,width=2)

    best = _best_recommendation(rec_groups)
    if best:
        draw.text((x1+26,y1+236),"BEST MATCH",font=_font(17,True),fill=MUTED)
        cover = _download_image(best.get("cover_image") or "")
        cover_w, cover_h = 118, 168
        if cover:
            image.alpha_composite(_cover_crop(cover,(cover_w,cover_h)).convert("RGBA"),(x1+26,y1+280))
        text_x = x1+26+(cover_w+18 if cover else 0)
        text_w = x2-26-text_x
        rec_y = _draw_wrapped(draw,text_x,y1+280,best.get("title") or "—",_font(28,True),TEXT,text_w,6,3)
        reasons = best.get("matched_tags") or best.get("matched_genres") or []
        if reasons:
            _draw_wrapped(draw,text_x,rec_y+10,"Why: "+", ".join(reasons[:3]),_font(18),MUTED,text_w,5,4)

    # Closing.
    quote_top = 1860
    _panel(draw,(88,quote_top,1512,2072),fill=PANEL_ALT,radius=22)
    draw.text((116,quote_top+26),"“",font=_font(74,True),fill=CYAN)
    closing = (
        "The full report explains the evidence behind these patterns and keeps "
        "the detailed creators, voice actors, ratings, and recommendations interactive."
    )
    _draw_wrapped(draw,190,quote_top+46,closing,_font(23),TEXT,1260,8,4)
    draw.text((88,2124),"GENERATED BY ANILIST TASTE ANALYZER",font=_font(19,True),fill=CYAN)

    image.convert("RGB").save(output_dir/"taste_cover.png",quality=95)


def _draw_social_card(user,taste_glance,rows,score_format,overall,output_dir):
    W,H=1920,1080
    image=_gradient((W,H)).convert("RGBA")
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((34,34,W-34,H-34),radius=28,outline=CYAN,width=3)
    draw.text((92,78),str(user.get("name") or "AniList user"),font=_font(84,True),fill=TEXT)
    draw.text((96,174),"ANIME TASTE REPORT",font=_font(30,True),fill=CYAN)
    _draw_wrapped(draw,96,286,taste_glance.get("headline") or "",_font(56,True),TEXT,1420,14,3)
    _draw_wrapped(draw,96,566,taste_glance.get("summary") or "",_font(27),MUTED,1450,10,4)
    _panel(draw,(1500,74,1828,378),fill=PANEL,radius=22)
    draw.text((1536,100),str(len(rows)),font=_font(46,True),fill=TEXT)
    draw.text((1538,154),"RATED ANIME",font=_font(16,True),fill=MUTED)
    draw.text((1536,204),f"{overall:.1f}/{int(score_format['max'])}",font=_font(40,True),fill=TEXT)
    draw.text((1538,250),"AVERAGE",font=_font(16,True),fill=MUTED)
    top=_signal_value(taste_glance,"Top-rating rate")
    if top:
        draw.text((1536,296),top,font=_font(40,True),fill=TEXT)
        draw.text((1538,342),"TOP RATE",font=_font(16,True),fill=MUTED)
    draw.text((96,980),"GENERATED BY ANILIST TASTE ANALYZER",font=_font(19,True),fill=CYAN)
    image.convert("RGB").save(output_dir/"share_card.png",quality=95)


def write_share_assets(user,taste_glance,stats,rows,score_format,overall,output_dir,rec_groups=None):
    _draw_social_card(user,taste_glance,rows,score_format,overall,output_dir)
    _draw_cover(user,taste_glance,stats,rows,score_format,overall,rec_groups,output_dir)

    best=_best_recommendation(rec_groups)
    summary=[
        f"{user.get('name') or 'AniList user'}'s Anime Taste Report",
        "",
        taste_glance.get("headline") or "",
        taste_glance.get("summary") or "",
        "",
        f"{len(rows)} rated anime | Average: {overall:.1f}/{int(score_format['max'])}",
    ]
    if taste_glance.get("themes"):
        summary.extend(["","Strongest signals: "+", ".join(taste_glance["themes"][:4])])
    if best:
        summary.extend(["","Best recommendation match: "+str(best.get("title") or "—")])
    summary.extend(["","A full interactive report and shareable PNG cover were generated alongside this summary."])
    (output_dir/"share_summary.txt").write_text("\n".join(summary),encoding="utf-8")
