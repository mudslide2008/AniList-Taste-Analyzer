
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except ImportError as exc:
    raise RuntimeError(
        "The share-card generator requires Pillow. Run: py -m pip install Pillow"
    ) from exc


BG = "#08111f"
PANEL = "#0d1a2b"
PANEL_2 = "#11243a"
TEXT = "#f2f6fb"
MUTED = "#a7b5c8"
CYAN = "#55d9ee"
LINE = "#24435d"
GOOD = "#76e2ae"
GOLD = "#ffd369"


def _font_candidates(bold: bool = False) -> list[str]:
    windows = os.environ.get("WINDIR", r"C:\Windows")
    if bold:
        return [
            str(Path(windows) / "Fonts" / "segoeuib.ttf"),
            str(Path(windows) / "Fonts" / "arialbd.ttf"),
            "DejaVuSans-Bold.ttf",
        ]
    return [
        str(Path(windows) / "Fonts" / "segoeui.ttf"),
        str(Path(windows) / "Fonts" / "arial.ttf"),
        "DejaVuSans.ttf",
    ]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for candidate in _font_candidates(bold):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _wrap_pixels(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    paragraphs = str(text or "").splitlines() or [""]
    lines: list[str] = []

    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if _measure(draw, trial, font)[0] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)

    return lines


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_spacing: int = 10,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    lines = _wrap_pixels(draw, text, font, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]

    line_height = _measure(draw, "Ag", font)[1]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + line_spacing
    return y


def _rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str = PANEL,
    outline: str = LINE,
    radius: int = 24,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _gradient(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, BG)
    pixels = image.load()
    top = (11, 31, 52)
    bottom = (5, 12, 24)

    for y in range(height):
        ratio = y / max(1, height - 1)
        row = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(width):
            glow = max(0.0, 1.0 - math.dist((x / width, y / height), (0.72, 0.18)) / 0.55)
            pixels[x, y] = (
                min(255, int(row[0] + 0 * glow)),
                min(255, int(row[1] + 38 * glow)),
                min(255, int(row[2] + 55 * glow)),
            )
    return image


def _optional_background(canvas: Image.Image, project_root: Path) -> None:
    candidates = [
        project_root / "assets" / "cover_background.jpg",
        project_root / "assets" / "cover_background.png",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if not path:
        return

    try:
        art = Image.open(path).convert("RGB")
        art.thumbnail((canvas.width, 720), Image.Resampling.LANCZOS)
        crop = Image.new("RGB", (canvas.width, 720), BG)
        x = (canvas.width - art.width) // 2
        y = (720 - art.height) // 2
        crop.paste(art, (x, y))
        crop = crop.filter(ImageFilter.GaussianBlur(0.4))
        crop = ImageEnhance.Brightness(crop).enhance(0.55)
        overlay = Image.new("RGBA", crop.size, (5, 13, 25, 55))
        crop = Image.alpha_composite(crop.convert("RGBA"), overlay).convert("RGB")
        canvas.paste(crop, (0, 0))
    except OSError:
        pass


def _top_names(stats: Iterable[Any], limit: int = 4) -> list[str]:
    names: list[str] = []
    for stat in stats:
        name = getattr(stat, "name", "")
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _creator_parts(value: str) -> tuple[str, str]:
    if " — " in value:
        name, role = value.split(" — ", 1)
        return name.strip(), role.strip()
    return value.strip(), ""


def _theme_description(name: str) -> str:
    descriptions = {
        "Travel": "Journeys, new places, and the excitement of the unknown.",
        "Historical": "Stories shaped by the past, legacy, and lived history.",
        "Survival": "Resourcefulness, perseverance, and pressure against the odds.",
        "Dungeon": "Exploration, danger, discovery, and unfamiliar worlds.",
        "Educational": "Learning is part of the entertainment rather than a lecture.",
        "Work": "People taking pride in a craft, profession, or shared goal.",
        "Coming of Age": "Growth through experience, failure, and changing relationships.",
        "Music": "Performance, practice, expression, and mastery.",
        "Agriculture": "Hands-on knowledge, systems, and patient improvement.",
        "Cooking": "Technique, experimentation, and care expressed through food.",
        "Science": "Curiosity, experimentation, and understanding how things work.",
        "Found Family": "Relationships built through trust rather than obligation.",
        "Revenge": "Purpose, consequence, and emotionally charged forward momentum.",
        "Crime": "Moral pressure, danger, and people navigating hard choices.",
    }
    return descriptions.get(name, "A recurring theme strongly connected to top-rated anime.")


def _draw_metric(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    value: str,
    label: str,
) -> None:
    draw.text((x, y), value, font=_font(48, True), fill=TEXT)
    draw.text((x, y + 58), label.upper(), font=_font(19, True), fill=MUTED)


def _signal_value(taste_glance: dict, label: str) -> str:
    return next(
        (str(value) for signal_label, value in taste_glance.get("signals", []) if signal_label == label),
        "",
    )


def _best_recommendation(rec_groups: dict | None) -> dict | None:
    if not rec_groups:
        return None
    matches = rec_groups.get("Best matches") or []
    return matches[0] if matches else None


def _draw_cover(
    user: dict,
    taste_glance: dict,
    stats: dict,
    rows: list[dict],
    score_format: dict,
    overall: float,
    rec_groups: dict | None,
    output_dir: Path,
) -> None:
    size = (1600, 2200)
    project_root = Path(__file__).resolve().parent.parent
    image = _gradient(size)
    _optional_background(image, project_root)

    draw = ImageDraw.Draw(image)
    margin = 54
    content_left = 86
    content_right = 1514

    draw.rounded_rectangle(
        (28, 28, 1572, 2172),
        radius=30,
        outline=CYAN,
        width=3,
    )

    # Header
    username = str(user.get("name") or "AniList user")
    draw.text((content_left, 72), username, font=_font(82, True), fill=TEXT)
    draw.text((content_left, 166), "ANIME TASTE REPORT", font=_font(29, True), fill=CYAN)

    # Metrics panel
    metric_box = (1125, 68, 1504, 276)
    _rounded_panel(draw, metric_box, fill="#0a1728cc", radius=22)
    _draw_metric(draw, 1160, 92, str(len(rows)), "Rated anime")
    _draw_metric(draw, 1320, 92, f"{overall:.1f}/{int(score_format['max'])}", "Average")
    top_rate = _signal_value(taste_glance, "Top-rating rate")
    if top_rate:
        _draw_metric(draw, 1160, 188, top_rate, "Top-rating rate")

    # Big picture panel
    hero_top = 310
    hero_bottom = 760
    _rounded_panel(draw, (54, hero_top, 1546, hero_bottom), fill="#0b1829dd", radius=28)

    headline_font = _font(54, True)
    summary_font = _font(27)
    y = _draw_wrapped(
        draw,
        (content_left, hero_top + 48),
        taste_glance.get("headline") or "A personal anime taste profile.",
        headline_font,
        TEXT,
        1325,
        line_spacing=12,
        max_lines=3,
    )
    y += 24
    _draw_wrapped(
        draw,
        (content_left, y),
        taste_glance.get("summary") or "",
        summary_font,
        MUTED,
        1320,
        line_spacing=10,
        max_lines=5,
    )

    # Strongest signals
    themes = [str(theme) for theme in (taste_glance.get("themes") or []) if theme][:4]
    draw.text((content_left, 805), "YOUR STRONGEST SIGNALS", font=_font(31, True), fill=CYAN)

    card_y = 862
    gap = 18
    card_width = (content_right - content_left - gap * 3) // 4
    for index, theme in enumerate(themes):
        x = content_left + index * (card_width + gap)
        _rounded_panel(draw, (x, card_y, x + card_width, 1116), fill=PANEL_2, radius=20)
        draw.ellipse((x + 24, card_y + 28, x + 68, card_y + 72), fill=CYAN)
        draw.text((x + 84, card_y + 24), theme.upper(), font=_font(23, True), fill=CYAN)
        _draw_wrapped(
            draw,
            (x + 24, card_y + 88),
            _theme_description(theme),
            _font(20),
            TEXT,
            card_width - 48,
            line_spacing=7,
            max_lines=5,
        )

    # Lower three-column area
    lower_top = 1160
    lower_bottom = 1882
    col_gap = 18
    col_width = (content_right - content_left - col_gap * 2) // 3
    boxes = []
    for index in range(3):
        x1 = content_left + index * (col_width + col_gap)
        x2 = x1 + col_width
        boxes.append((x1, lower_top, x2, lower_bottom))
        _rounded_panel(draw, boxes[-1], fill=PANEL, radius=22)

    # Creators
    x1, y1, x2, _ = boxes[0]
    draw.text((x1 + 28, y1 + 26), "RECURRING CREATORS", font=_font(27, True), fill=CYAN)
    creator_y = y1 + 86
    for raw in _top_names(stats.get("staff") or [], 4):
        name, role = _creator_parts(raw)
        draw.ellipse((x1 + 28, creator_y + 3, x1 + 62, creator_y + 37), fill="#163b53")
        draw.text((x1 + 78, creator_y), name, font=_font(23, True), fill=TEXT)
        if role:
            creator_y = _draw_wrapped(
                draw,
                (x1 + 78, creator_y + 31),
                role,
                _font(18),
                MUTED,
                col_width - 118,
                line_spacing=4,
                max_lines=2,
            ) + 20
        else:
            creator_y += 62

    # Voice actors
    x1, y1, x2, _ = boxes[1]
    draw.text((x1 + 28, y1 + 26), "RECURRING JAPANESE VAS", font=_font(25, True), fill=CYAN)
    va_y = y1 + 86
    for name in _top_names(stats.get("japanese_vas") or [], 4):
        draw.ellipse((x1 + 28, va_y + 1, x1 + 62, va_y + 35), fill="#163b53")
        draw.text((x1 + 78, va_y), name, font=_font(23, True), fill=TEXT)
        va_y += 68

    # Highlights / best recommendation
    x1, y1, x2, _ = boxes[2]
    draw.text((x1 + 28, y1 + 26), "OTHER HIGHLIGHTS", font=_font(27, True), fill=CYAN)
    alignment = _signal_value(taste_glance, "Community alignment") or "—"
    draw.text((x1 + 28, y1 + 92), "COMMUNITY ALIGNMENT", font=_font(18, True), fill=MUTED)
    draw.text((x1 + 28, y1 + 126), alignment, font=_font(31, True), fill=CYAN)

    best = _best_recommendation(rec_groups)
    if best:
        draw.line((x1 + 28, y1 + 206, x2 - 28, y1 + 206), fill=LINE, width=2)
        draw.text((x1 + 28, y1 + 238), "BEST MATCH", font=_font(18, True), fill=MUTED)
        rec_y = _draw_wrapped(
            draw,
            (x1 + 28, y1 + 272),
            str(best.get("title") or "—"),
            _font(31, True),
            TEXT,
            col_width - 56,
            line_spacing=8,
            max_lines=3,
        )
        overlap = best.get("matched_tags") or best.get("matched_genres") or []
        if overlap:
            _draw_wrapped(
                draw,
                (x1 + 28, rec_y + 12),
                "Why: " + ", ".join(overlap[:3]),
                _font(19),
                MUTED,
                col_width - 56,
                line_spacing=5,
                max_lines=3,
            )

    # Closing insight (not duplicate statistics)
    quote_box = (content_left, 1924, content_right, 2088)
    _rounded_panel(draw, quote_box, fill="#0b1b2ddd", radius=22)
    draw.text((content_left + 28, 1950), "“", font=_font(74, True), fill=CYAN)
    closing = (
        "The full report explains the patterns behind these signals, "
        "shows the evidence, and keeps the interactive details expandable."
    )
    _draw_wrapped(
        draw,
        (content_left + 94, 1960),
        closing,
        _font(24),
        TEXT,
        1240,
        line_spacing=8,
        max_lines=3,
    )

    draw.text(
        (content_left, 2120),
        "GENERATED BY ANILIST TASTE ANALYZER",
        font=_font(20, True),
        fill=CYAN,
    )

    image.save(output_dir / "taste_cover.png", quality=95)


def _draw_social_card(
    user: dict,
    taste_glance: dict,
    rows: list[dict],
    score_format: dict,
    overall: float,
    output_dir: Path,
) -> None:
    size = (1920, 1080)
    image = _gradient(size)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((36, 36, 1884, 1044), radius=28, outline=CYAN, width=3)
    draw.text((92, 80), str(user.get("name") or "AniList user"), font=_font(86, True), fill=TEXT)
    draw.text((96, 178), "ANIME TASTE REPORT", font=_font(31, True), fill=CYAN)

    y = _draw_wrapped(
        draw,
        (96, 284),
        taste_glance.get("headline") or "A personal anime taste profile.",
        _font(58, True),
        TEXT,
        1440,
        line_spacing=14,
        max_lines=3,
    )
    y += 22
    _draw_wrapped(
        draw,
        (96, y),
        taste_glance.get("summary") or "",
        _font(28),
        MUTED,
        1450,
        line_spacing=10,
        max_lines=4,
    )

    _rounded_panel(draw, (1490, 78, 1825, 382), fill=PANEL, radius=22)
    _draw_metric(draw, 1530, 112, str(len(rows)), "Rated anime")
    _draw_metric(draw, 1530, 212, f"{overall:.1f}/{int(score_format['max'])}", "Average")
    top_rate = _signal_value(taste_glance, "Top-rating rate")
    if top_rate:
        _draw_metric(draw, 1530, 312, top_rate, "Top rate")

    themes = [str(theme) for theme in (taste_glance.get("themes") or []) if theme][:4]
    draw.text((96, 740), "STRONGEST SIGNALS", font=_font(28, True), fill=CYAN)
    x = 96
    for theme in themes:
        width = max(250, _measure(draw, theme.upper(), _font(24, True))[0] + 58)
        draw.rounded_rectangle((x, 792, x + width, 862), radius=18, fill=PANEL_2, outline=LINE)
        draw.text((x + 28, 811), theme.upper(), font=_font(24, True), fill=TEXT)
        x += width + 18

    draw.text((96, 980), "GENERATED BY ANILIST TASTE ANALYZER", font=_font(20, True), fill=CYAN)
    image.save(output_dir / "share_card.png", quality=95)


def write_share_assets(
    user: dict,
    taste_glance: dict,
    stats: dict,
    rows: list[dict],
    score_format: dict,
    overall: float,
    output_dir: Path,
    rec_groups: dict | None = None,
) -> None:
    _draw_social_card(user, taste_glance, rows, score_format, overall, output_dir)
    _draw_cover(user, taste_glance, stats, rows, score_format, overall, rec_groups, output_dir)

    themes = [str(theme) for theme in (taste_glance.get("themes") or []) if theme]
    creators = [_creator_parts(value)[0] for value in _top_names(stats.get("staff") or [], 4)]
    voices = _top_names(stats.get("japanese_vas") or [], 4)
    best = _best_recommendation(rec_groups)

    summary = [
        f"{user.get('name') or 'AniList user'}'s Anime Taste Report",
        "",
        taste_glance.get("headline") or "",
        taste_glance.get("summary") or "",
        "",
        f"{len(rows)} rated anime | Average: {overall:.1f}/{int(score_format['max'])}",
    ]
    if themes:
        summary.extend(["", "Strongest signals: " + ", ".join(themes)])
    if creators:
        summary.extend(["", "Recurring creators: " + ", ".join(creators)])
    if voices:
        summary.extend(["", "Recurring Japanese VAs: " + ", ".join(voices)])
    if best:
        summary.extend(["", "Best recommendation match: " + str(best.get("title") or "—")])
    summary.extend([
        "",
        "A full interactive report and shareable PNG cover were generated alongside this summary.",
    ])

    (output_dir / "share_summary.txt").write_text("\n".join(summary), encoding="utf-8")
