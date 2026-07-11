
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


PACK_FILENAME = "artwork_asset_pack.png"
EXPECTED_SIZE = (1182, 1330)

# Image-only cells in the new 15-theme asset sheet.
# Labels, icons, borders, and headers are excluded.
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

# Match the actual renderer slots.
OUTPUT_SIZES = {
    "poster": (1040, 760),
    "social": (1080, 1080),
    "quote": (760, 240),
}

# Fine-tuned focal points for ImageOps.fit.
CENTERING = {
    "poster": (0.62, 0.50),
    "social": (0.58, 0.50),
    "quote": (0.58, 0.50),
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
    tied = sorted(
        category for category, score in scores.items()
        if score == best_score
    )

    if best_score > 0 and len(tied) == 1:
        return tied[0]

    identity = f"{username.casefold()}|{'|'.join(phrases)}|{headline.casefold()}"
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    choices = tied or sorted(CROPS)
    return choices[int.from_bytes(digest[:4], "big") % len(choices)]


def extract_artwork_pack(project_root: Path) -> dict[str, dict[str, Path]]:
    source = project_root / "assets" / PACK_FILENAME
    if not source.exists():
        return {}

    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache_root = project_root / ".anilist_cache" / "artwork_pack" / digest
    manifest: dict[str, dict[str, Path]] = {}

    with Image.open(source) as pack:
        pack = pack.convert("RGB")
        if pack.size != EXPECTED_SIZE:
            # Artwork should never crash the main analyzer.
            return {}

        for category, variants in CROPS.items():
            manifest[category] = {}
            for kind, box in variants.items():
                output = cache_root / f"{category}_{kind}.jpg"
                manifest[category][kind] = output

                if output.exists():
                    continue

                output.parent.mkdir(parents=True, exist_ok=True)
                crop = pack.crop(box)
                crop = ImageEnhance.Color(crop).enhance(1.04)
                crop = ImageEnhance.Contrast(crop).enhance(1.04)

                crop = ImageOps.fit(
                    crop,
                    OUTPUT_SIZES[kind],
                    method=Image.Resampling.LANCZOS,
                    centering=CENTERING[kind],
                )
                crop.save(output, quality=95, optimize=True)

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
