
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


PACK_FILENAME = "artwork_asset_pack.png"
EXPECTED_SIZE = (1182, 1330)

COLUMNS = {
    "poster": (191, 505),
    "social": (510, 783),
    "quote": (788, 1141),
}

ROWS = {
    "exploration": (108, 209),
    "sci_fi": (215, 314),
    "fantasy": (320, 414),
    "mystery": (420, 514),
    "romance": (520, 604),
    "slice_of_life": (609, 691),
    "action": (696, 768),
    "horror": (774, 845),
    "historical": (851, 922),
    "adventure": (928, 998),
    "comedy": (1004, 1072),
    "sports": (1077, 1134),
    "music": (1139, 1196),
    "supernatural": (1202, 1259),
    "mecha": (1264, 1328),
}

CROPS = {
    theme: {
        kind: (x1, y1, x2, y2)
        for kind, (x1, x2) in COLUMNS.items()
    }
    for theme, (y1, y2) in ROWS.items()
}

# These are the exact rendered image regions.
OUTPUT_SIZES = {
    "poster": (1536, 500),
    "social": (1920, 625),
    "quote": (920, 300),
}

# The illustration is intentionally confined to the right side.
ART_BOXES = {
    "poster": (610, 0, 1536, 500),
    "social": (820, 0, 1920, 625),
    "quote": (390, 0, 920, 300),
}

FOCAL_X = {
    "poster": 0.88,
    "social": 0.90,
    "quote": 0.70,
}

THEME_KEYWORDS = {
    "exploration": {
        "exploration", "journey", "travel", "wilderness", "nature",
        "outdoor", "discovery",
    },
    "sci_fi": {
        "science fiction", "sci-fi", "space", "cyberpunk", "technology",
        "future", "robot",
    },
    "fantasy": {
        "fantasy", "magic", "dragon", "isekai", "medieval", "mythology",
    },
    "mystery": {
        "mystery", "crime", "detective", "conspiracy", "suspense",
        "psychological", "thriller",
    },
    "romance": {
        "romance", "love", "relationships", "school romance",
    },
    "slice_of_life": {
        "slice of life", "everyday life", "iyashikei", "family",
        "found family", "work",
    },
    "action": {
        "action", "battle", "gore", "revenge", "war", "survival",
    },
    "horror": {
        "horror", "fear", "occult", "dark", "body horror",
    },
    "historical": {
        "historical", "history", "period", "samurai",
    },
    "adventure": {
        "adventure", "dungeon", "quest", "worldbuilding", "agriculture",
    },
    "comedy": {
        "comedy", "parody", "gag humor", "humor",
    },
    "sports": {
        "sports", "competition", "team sports", "athletics",
    },
    "music": {
        "music", "band", "idol", "performance", "musical",
    },
    "supernatural": {
        "supernatural", "demons", "spirits", "curses", "youkai",
    },
    "mecha": {
        "mecha", "robots", "giant robot", "pilots",
    },
}


def choose_art_theme(
    username: str,
    themes: list[str],
    headline: str = "",
    summary: str = "",
) -> str:
    phrases = [str(value).casefold() for value in themes if value]
    text = " ".join(phrases + [headline.casefold(), summary.casefold()])

    scores: dict[str, int] = {}
    for category, keywords in THEME_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in phrases:
                score += 4
            elif keyword in text:
                score += 1
        scores[category] = score

    best_score = max(scores.values(), default=0)
    tied = sorted(category for category, score in scores.items() if score == best_score)

    if best_score > 0 and len(tied) == 1:
        return tied[0]

    identity = f"{username.casefold()}|{'|'.join(phrases)}|{headline.casefold()}"
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    choices = tied or sorted(CROPS)
    return choices[int.from_bytes(digest[:4], "big") % len(choices)]


def _compose_destination_asset(source: Image.Image, kind: str) -> Image.Image:
    """Compose artwork for the real destination rather than stretching a crop."""
    width, height = OUTPUT_SIZES[kind]
    x1, y1, x2, y2 = ART_BOXES[kind]
    art_width = x2 - x1
    art_height = y2 - y1

    # A soft full-canvas atmospheric background avoids hard empty seams.
    atmosphere = ImageOps.fit(
        source,
        (width, height),
        method=Image.Resampling.LANCZOS,
        centering=(FOCAL_X[kind], 0.5),
    )
    atmosphere = atmosphere.filter(ImageFilter.GaussianBlur(radius=18))
    atmosphere = ImageEnhance.Brightness(atmosphere).enhance(0.34)
    atmosphere = ImageEnhance.Color(atmosphere).enhance(0.75)

    canvas = atmosphere.convert("RGBA")

    # Crisp illustration only occupies its intended right-hand region.
    foreground = ImageOps.fit(
        source,
        (art_width, art_height),
        method=Image.Resampling.LANCZOS,
        centering=(FOCAL_X[kind], 0.5),
    ).convert("RGBA")
    foreground = ImageEnhance.Contrast(foreground).enhance(1.04)
    foreground = ImageEnhance.Color(foreground).enhance(1.06)
    canvas.alpha_composite(foreground, (x1, y1))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Strong text-safe zone on the left, fading smoothly over the artwork.
    fade_start = int(width * (0.38 if kind != "quote" else 0.34))
    fade_end = int(width * (0.76 if kind != "quote" else 0.72))
    for x in range(width):
        if x <= fade_start:
            alpha = 246
        elif x >= fade_end:
            alpha = 10
        else:
            ratio = (x - fade_start) / max(1, fade_end - fade_start)
            alpha = int(246 * (1.0 - ratio) + 10 * ratio)
        draw.line((x, 0, x, height), fill=(4, 15, 27, alpha))

    # Gentle top/bottom vignette keeps white type readable without crushing art.
    vignette = max(22, height // 7)
    for y in range(vignette):
        alpha = int(70 * (1 - y / vignette))
        draw.line((0, y, width, y), fill=(2, 9, 18, alpha))
        draw.line((0, height - 1 - y, width, height - 1 - y), fill=(2, 9, 18, alpha))

    canvas = Image.alpha_composite(canvas, overlay)
    return canvas.convert("RGB")


def extract_artwork_pack(project_root: Path) -> dict[str, dict[str, Path]]:
    source = project_root / "assets" / PACK_FILENAME
    if not source.exists():
        return {}

    # Version tag ensures old badly composed cached crops are never reused.
    digest = hashlib.sha256(source.read_bytes() + b"destination-compose-v3").hexdigest()[:16]
    cache_root = project_root / ".anilist_cache" / "artwork_pack" / digest
    manifest: dict[str, dict[str, Path]] = {}

    with Image.open(source) as pack:
        pack = pack.convert("RGB")
        if pack.size != EXPECTED_SIZE:
            return {}

        for category, variants in CROPS.items():
            manifest[category] = {}
            for kind, box in variants.items():
                output = cache_root / f"{category}_{kind}.jpg"
                manifest[category][kind] = output

                if output.exists():
                    continue

                output.parent.mkdir(parents=True, exist_ok=True)
                source_crop = pack.crop(box)
                source_crop = ImageEnhance.Color(source_crop).enhance(1.04)
                source_crop = ImageEnhance.Contrast(source_crop).enhance(1.04)

                composed = _compose_destination_asset(source_crop, kind)
                composed.save(output, quality=95, optimize=True)

    return manifest


def selected_artwork(
    project_root: Path,
    username: str,
    themes: list[str],
    headline: str = "",
    summary: str = "",
) -> tuple[str, dict[str, Path]]:
    category = choose_art_theme(username, themes, headline, summary)
    manifest = extract_artwork_pack(project_root)
    return category, manifest.get(category, {})
