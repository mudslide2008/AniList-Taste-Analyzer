
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



def _row_theme_overlap(row: dict, themes: list[str]) -> int:
    row_terms = {
        str(value).casefold()
        for value in (row.get("tags") or []) + (row.get("genres") or [])
    }
    return sum(1 for theme in themes if theme.casefold() in row_terms)


def _hero_art(rows, rec_groups, project_root, themes):
    """Choose custom art first, then a thematically relevant favorite."""
    custom = next(
        (
            path
            for path in (
                project_root / "assets" / "cover_background.jpg",
                project_root / "assets" / "cover_background.png",
            )
            if path.exists()
        ),
        None,
    )
    if custom:
        try:
            return Image.open(custom).convert("RGB")
        except OSError:
            pass

    candidates = [
        row
        for row in rows
        if row.get("banner_image") or row.get("cover_image")
    ]
    candidates.sort(
        key=lambda row: (
            _row_theme_overlap(row, themes),
            row.get("rating") or 0,
            bool(row.get("banner_image")),
            row.get("favourites") or 0,
        ),
        reverse=True,
    )

    # Do not let a zero-overlap blockbuster automatically dominate the cover.
    relevant = [row for row in candidates if _row_theme_overlap(row, themes) > 0]
    for row in (relevant or candidates):
        art = _download_image(row.get("banner_image") or row.get("cover_image") or "")
        if art:
            return art

    best = _best_recommendation(rec_groups)
    if best:
        return _download_image(best.get("banner_image") or best.get("cover_image") or "")
    return None


def _initials(name: str) -> str:
    parts = [part for part in name.replace("—", " ").split() if part]
    if not parts:
        return "?"
    return "".join(part[0].upper() for part in parts[:2])


def _draw_person_row(canvas, draw, x, y, width, stat, role=False):
    diameter = 62
    avatar = _download_image(getattr(stat, "image", ""))
    if avatar:
        canvas.alpha_composite(_circle_crop(avatar, diameter), (x, y))
    else:
        draw.ellipse((x, y, x + diameter, y + diameter), fill="#174864", outline=LINE, width=2)
        initials = _initials(getattr(stat, "name", ""))
        initials_font = _font(18, True)
        tw, th = _measure(draw, initials, initials_font)
        draw.text(
            (x + (diameter - tw) / 2, y + (diameter - th) / 2 - 2),
            initials,
            font=initials_font,
            fill=TEXT,
        )

    name, subtitle = _creator_parts(stat.name) if role else (stat.name, "")
    name_font = _font(22, True)
    name_h, _ = _text_height(draw, name, name_font, width - 82, 3, 2)
    _draw_wrapped(draw, x + 80, y + 1, name, name_font, TEXT, width - 82, 3, 2)

    used_height = max(diameter, name_h)
    if subtitle:
        subtitle_y = y + name_h + 7
        subtitle_h, _ = _text_height(draw, subtitle, _font(16), width - 82, 3, 2)
        _draw_wrapped(draw, x + 80, subtitle_y, subtitle, _font(16), MUTED, width - 82, 3, 2)
        used_height = max(used_height, name_h + 7 + subtitle_h)

    return y + used_height + 18


def _draw_signal_card(draw, x, y, w, h, theme):
    _panel(draw, (x, y, x + w, y + h), fill=PANEL_ALT, radius=20)
    draw.ellipse((x + 22, y + 22, x + 60, y + 60), fill=CYAN)
    draw.text((x + 76, y + 23), theme.upper(), font=_font(21, True), fill=CYAN)
    descriptions = {
        "Travel": "Journeys, new places, and the excitement of the unknown.",
        "Historical": "Stories shaped by the past, legacy, and lived history.",
        "Survival": "Resourcefulness and perseverance against difficult odds.",
        "Dungeon": "Exploration, danger, and discovery in unfamiliar worlds.",
        "Educational": "Learning is part of the entertainment rather than a lecture.",
        "Work": "People taking pride in a craft, profession, or shared goal.",
        "Coming of Age": "Growth through experience, failure, and changing relationships.",
        "Science": "Curiosity, experimentation, and understanding how things work.",
        "Music": "Practice, performance, expression, and mastery.",
        "Found Family": "Relationships built through trust rather than obligation.",
    }
    description = descriptions.get(
        theme,
        "A recurring theme strongly connected to top-rated anime.",
    )
    _draw_wrapped(
        draw,
        x + 22,
        y + 78,
        description,
        _font(17),
        TEXT,
        w - 44,
        spacing=5,
        max_lines=5,
    )


def _people_panel_height(draw, stats, width, role):
    height = 78
    for stat in stats:
        name, subtitle = _creator_parts(stat.name) if role else (stat.name, "")
        name_h, _ = _text_height(draw, name, _font(22, True), width - 116, 3, 2)
        row_h = max(62, name_h)
        if subtitle:
            subtitle_h, _ = _text_height(draw, subtitle, _font(16), width - 116, 3, 2)
            row_h = max(row_h, name_h + 7 + subtitle_h)
        height += row_h + 18
    return height + 22


def _highlights_panel_height(draw, best, width):
    height = 150
    if best:
        title_h, _ = _text_height(draw, best.get("title") or "—", _font(28, True), width - 200, 6, 3)
        reasons = best.get("matched_tags") or best.get("matched_genres") or []
        reason_h = 0
        if reasons:
            reason_h, _ = _text_height(
                draw,
                "Why: " + ", ".join(reasons[:3]),
                _font(17),
                width - 200,
                4,
                4,
            )
        height = max(height, 250 + title_h + reason_h)
    return height + 32


def _draw_cover(user, taste_glance, stats, rows, score_format, overall, rec_groups, output_dir):
    W, H = 1600, 2020
    image = _gradient((W, H)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    project_root = Path(__file__).resolve().parent.parent
    themes = [str(value) for value in (taste_glance.get("themes") or []) if value][:4]

    draw.rounded_rectangle((28, 28, W - 28, H - 28), radius=28, outline=CYAN, width=3)

    # Hero: image primarily on the right, readable dark area on the left.
    hero = (54, 54, W - 54, 665)
    art = _hero_art(rows, rec_groups, project_root, themes)
    if art:
        art = _cover_crop(art, (hero[2] - hero[0], hero[3] - hero[1])).convert("RGBA")
        art = ImageEnhance.Color(art).enhance(0.82)
        art = ImageEnhance.Brightness(art).enhance(0.70)
        image.alpha_composite(art, (hero[0], hero[1]))

        shade = Image.new("RGBA", (hero[2] - hero[0], hero[3] - hero[1]), (0, 0, 0, 0))
        shade_draw = ImageDraw.Draw(shade)
        for x in range(shade.width):
            position = x / max(1, shade.width - 1)
            alpha = int(245 * max(0.08, 1.0 - position / 0.72))
            shade_draw.line((x, 0, x, shade.height), fill=(4, 12, 24, alpha))
        shade_draw.rectangle((0, shade.height - 90, shade.width, shade.height), fill=(4, 12, 24, 110))
        image.alpha_composite(shade, (hero[0], hero[1]))
    else:
        _panel(draw, hero, fill=PANEL, radius=24)

    # Header.
    username = str(user.get("name") or "AniList user")
    draw.text((88, 82), username, font=_font(70, True), fill=TEXT)
    draw.text((92, 162), "ANIME TASTE REPORT", font=_font(27, True), fill=CYAN)

    metric_box = (1214, 76, 1510, 292)
    _panel(draw, metric_box, fill="#081526ee", radius=22)
    draw.text((1248, 98), str(len(rows)), font=_font(43, True), fill=TEXT)
    draw.text((1250, 148), "RATED ANIME", font=_font(15, True), fill=MUTED)
    draw.text((1248, 184), f"{overall:.1f}/{int(score_format['max'])}", font=_font(36, True), fill=TEXT)
    draw.text((1250, 226), "AVERAGE", font=_font(15, True), fill=MUTED)
    top = _signal_value(taste_glance, "Top-rating rate")
    if top:
        draw.text((1390, 184), top, font=_font(36, True), fill=TEXT)
        draw.text((1392, 226), "TOP RATE", font=_font(15, True), fill=MUTED)

    headline = taste_glance.get("headline") or "A personal anime taste profile."
    headline_font = _font(43, True)
    headline_h, _ = _text_height(draw, headline, headline_font, 1020, 9, 3)
    summary = taste_glance.get("summary") or ""
    summary_font = _font(22)
    summary_h, _ = _text_height(draw, summary, summary_font, 960, 7, 5)
    text_y = 262
    _draw_wrapped(draw, 88, text_y, headline, headline_font, TEXT, 1020, 9, 3)
    _draw_wrapped(draw, 88, text_y + headline_h + 19, summary, summary_font, TEXT, 960, 7, 5)

    # Signal row.
    draw.text((88, 706), "YOUR STRONGEST SIGNALS", font=_font(28, True), fill=CYAN)
    card_y, gap = 754, 16
    card_w = (1424 - gap * 3) // 4
    for index, theme in enumerate(themes):
        _draw_signal_card(draw, 88 + index * (card_w + gap), card_y, card_w, 230, theme)

    # Content-driven lower panels.
    creators = _top_names(stats.get("staff") or [], 4)
    voice_actors = _top_names(stats.get("japanese_vas") or [], 4)
    best = _best_recommendation(rec_groups)

    lower_y = 1024
    gap = 16
    col_w = (1424 - gap * 2) // 3
    creator_h = _people_panel_height(draw, creators, col_w - 52, role=True)
    va_h = _people_panel_height(draw, voice_actors, col_w - 52, role=False)
    highlight_h = _highlights_panel_height(draw, best, col_w - 52)
    lower_h = max(430, creator_h, va_h, highlight_h)

    boxes = [
        (88 + index * (col_w + gap), lower_y, 88 + index * (col_w + gap) + col_w, lower_y + lower_h)
        for index in range(3)
    ]
    for box in boxes:
        _panel(draw, box, fill=PANEL, radius=22)

    # Creators.
    x1, y1, x2, y2 = boxes[0]
    draw.text((x1 + 24, y1 + 22), "RECURRING CREATORS", font=_font(23, True), fill=CYAN)
    y = y1 + 70
    for stat in creators:
        y = _draw_person_row(image, draw, x1 + 24, y, col_w - 48, stat, role=True)

    # VAs.
    x1, y1, x2, y2 = boxes[1]
    draw.text((x1 + 24, y1 + 22), "RECURRING JAPANESE VAS", font=_font(22, True), fill=CYAN)
    y = y1 + 70
    for stat in voice_actors:
        y = _draw_person_row(image, draw, x1 + 24, y, col_w - 48, stat, role=False)

    # Highlights.
    x1, y1, x2, y2 = boxes[2]
    draw.text((x1 + 24, y1 + 22), "OTHER HIGHLIGHTS", font=_font(23, True), fill=CYAN)
    alignment = _signal_value(taste_glance, "Community alignment") or "—"
    draw.text((x1 + 24, y1 + 78), "COMMUNITY ALIGNMENT", font=_font(16, True), fill=MUTED)
    _draw_wrapped(draw, x1 + 24, y1 + 108, alignment, _font(27, True), CYAN, col_w - 48, 5, 2)

    divider_y = y1 + 174
    draw.line((x1 + 24, divider_y, x2 - 24, divider_y), fill=LINE, width=2)

    if best:
        draw.text((x1 + 24, divider_y + 24), "BEST MATCH", font=_font(16, True), fill=MUTED)
        cover = _download_image(best.get("cover_image") or best.get("banner_image") or "")
        cover_w, cover_h = 128, 184
        cover_y = divider_y + 62
        if cover:
            cover_image = _cover_crop(cover, (cover_w, cover_h)).convert("RGBA")
            image.alpha_composite(cover_image, (x1 + 24, cover_y))
            draw.rounded_rectangle(
                (x1 + 24, cover_y, x1 + 24 + cover_w, cover_y + cover_h),
                radius=12,
                outline=LINE,
                width=2,
            )

        text_x = x1 + 24 + (cover_w + 18 if cover else 0)
        text_w = x2 - 24 - text_x
        rec_y = _draw_wrapped(
            draw,
            text_x,
            cover_y,
            best.get("title") or "—",
            _font(27, True),
            TEXT,
            text_w,
            5,
            3,
        )
        reasons = best.get("matched_tags") or best.get("matched_genres") or []
        if reasons:
            _draw_wrapped(
                draw,
                text_x,
                rec_y + 10,
                "Why: " + ", ".join(reasons[:3]),
                _font(17),
                MUTED,
                text_w,
                4,
                4,
            )

    # Closing panel follows actual lower content instead of fixed dead space.
    quote_top = lower_y + lower_h + 26
    quote_bottom = quote_top + 154
    _panel(draw, (88, quote_top, 1512, quote_bottom), fill=PANEL_ALT, radius=22)
    draw.text((114, quote_top + 20), "“", font=_font(64, True), fill=CYAN)
    closing = (
        "The full report explains the evidence behind these patterns and keeps "
        "the detailed creators, voice actors, ratings, and recommendations interactive."
    )
    _draw_wrapped(draw, 184, quote_top + 38, closing, _font(21), TEXT, 1260, 7, 3)

    footer_y = quote_bottom + 34
    draw.text((88, footer_y), "GENERATED BY ANILIST TASTE ANALYZER", font=_font(18, True), fill=CYAN)

    # Crop unused bottom area while keeping a comfortable margin.
    final_height = min(H, footer_y + 74)
    image = image.crop((0, 0, W, final_height))
    image.convert("RGB").save(output_dir / "taste_cover.png", quality=95)


def _draw_social_card(user, taste_glance, rows, score_format, overall, output_dir, rec_groups=None):
    W, H = 1920, 1080
    image = _gradient((W, H)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    project_root = Path(__file__).resolve().parent.parent
    themes = [str(value) for value in (taste_glance.get("themes") or []) if value][:4]

    draw.rounded_rectangle((34, 34, W - 34, H - 34), radius=28, outline=CYAN, width=3)

    # Use the same thematically selected artwork, positioned on the right.
    art = _hero_art(rows, rec_groups, project_root, themes)
    if art:
        art_box = (960, 34, W - 34, H - 34)
        art = _cover_crop(art, (art_box[2] - art_box[0], art_box[3] - art_box[1])).convert("RGBA")
        art = ImageEnhance.Brightness(art).enhance(0.72)
        image.alpha_composite(art, (art_box[0], art_box[1]))

        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shade_draw = ImageDraw.Draw(shade)
        for x in range(W):
            if x < 1220:
                alpha = int(242 * max(0, 1 - x / 1220))
            else:
                alpha = 20
            shade_draw.line((x, 0, x, H), fill=(4, 12, 24, alpha))
        image.alpha_composite(shade)

    draw = ImageDraw.Draw(image)
    draw.text((92, 72), str(user.get("name") or "AniList user"), font=_font(78, True), fill=TEXT)
    draw.text((96, 160), "ANIME TASTE REPORT", font=_font(28, True), fill=CYAN)

    headline = taste_glance.get("headline") or ""
    headline_h, _ = _text_height(draw, headline, _font(49, True), 1080, 11, 3)
    _draw_wrapped(draw, 96, 270, headline, _font(49, True), TEXT, 1080, 11, 3)

    summary_y = 270 + headline_h + 24
    _draw_wrapped(
        draw,
        96,
        summary_y,
        taste_glance.get("summary") or "",
        _font(24),
        MUTED,
        1000,
        8,
        4,
    )

    metric_box = (1490, 72, 1818, 360)
    _panel(draw, metric_box, fill="#081526ee", radius=22)
    draw.text((1528, 98), str(len(rows)), font=_font(44, True), fill=TEXT)
    draw.text((1530, 148), "RATED ANIME", font=_font(15, True), fill=MUTED)
    draw.text((1528, 194), f"{overall:.1f}/{int(score_format['max'])}", font=_font(38, True), fill=TEXT)
    draw.text((1530, 238), "AVERAGE", font=_font(15, True), fill=MUTED)
    top = _signal_value(taste_glance, "Top-rating rate")
    if top:
        draw.text((1528, 280), top, font=_font(38, True), fill=TEXT)
        draw.text((1530, 324), "TOP RATE", font=_font(15, True), fill=MUTED)

    # Fill the previous empty lower area with themes and a recommendation.
    draw.text((96, 760), "STRONGEST SIGNALS", font=_font(25, True), fill=CYAN)
    chip_x = 96
    for theme in themes:
        label_font = _font(21, True)
        label_w, _ = _measure(draw, theme.upper(), label_font)
        chip_w = label_w + 46
        draw.rounded_rectangle((chip_x, 808, chip_x + chip_w, 866), radius=16, fill=PANEL_ALT, outline=LINE)
        draw.text((chip_x + 23, 823), theme.upper(), font=label_font, fill=TEXT)
        chip_x += chip_w + 14

    best = _best_recommendation(rec_groups)
    if best:
        _panel(draw, (96, 898, 890, 1006), fill=PANEL, radius=18)
        draw.text((120, 918), "BEST MATCH", font=_font(16, True), fill=MUTED)
        _draw_wrapped(
            draw,
            120,
            948,
            best.get("title") or "—",
            _font(27, True),
            TEXT,
            720,
            4,
            2,
        )

    draw.text((96, 1020), "GENERATED BY ANILIST TASTE ANALYZER", font=_font(17, True), fill=CYAN)
    image.convert("RGB").save(output_dir / "share_card.png", quality=95)


def write_share_assets(user, taste_glance, stats, rows, score_format, overall, output_dir, rec_groups=None):
    _draw_social_card(
        user,
        taste_glance,
        rows,
        score_format,
        overall,
        output_dir,
        rec_groups,
    )
    _draw_cover(
        user,
        taste_glance,
        stats,
        rows,
        score_format,
        overall,
        rec_groups,
        output_dir,
    )

    best = _best_recommendation(rec_groups)
    summary = [
        f"{user.get('name') or 'AniList user'}'s Anime Taste Report",
        "",
        taste_glance.get("headline") or "",
        taste_glance.get("summary") or "",
        "",
        f"{len(rows)} rated anime | Average: {overall:.1f}/{int(score_format['max'])}",
    ]
    if taste_glance.get("themes"):
        summary.extend(["", "Strongest signals: " + ", ".join(taste_glance["themes"][:4])])
    if best:
        summary.extend(["", "Best recommendation match: " + str(best.get("title") or "—")])
    summary.extend([
        "",
        "A full interactive report and shareable PNG cover were generated alongside this summary.",
    ])
    (output_dir / "share_summary.txt").write_text("\n".join(summary), encoding="utf-8")
