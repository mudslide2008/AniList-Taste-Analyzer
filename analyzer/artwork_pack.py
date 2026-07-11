
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageEnhance


PACK_FILENAME = "artwork_asset_pack.png"

CROPS = {
    "exploration": {
        "poster": (265, 123, 704, 305),
        "social": (712, 123, 1048, 305),
        "quote": (1063, 168, 1511, 280),
    },
    "sci_fi": {
        "poster": (265, 319, 704, 492),
        "social": (712, 319, 1048, 492),
        "quote": (1063, 363, 1511, 468),
    },
    "fantasy": {
        "poster": (265, 507, 704, 671),
        "social": (712, 507, 1048, 671),
        "quote": (1063, 552, 1511, 657),
    },
    "mystery": {
        "poster": (265, 685, 704, 833),
        "social": (712, 685, 1048, 833),
        "quote": (1063, 721, 1511, 821),
    },
    "romance": {
        "poster": (265, 845, 704, 1001),
        "social": (712, 845, 1048, 1001),
        "quote": (1063, 887, 1511, 998),
    },
}

OUTPUT_SIZES = {
    "poster": (1040, 760),
    "social": (1080, 1080),
    "quote": (760, 240),
}

THEME_KEYWORDS = {
    "exploration": {
        "adventure", "agriculture", "dungeon", "exploration", "historical",
        "journey", "nature", "outdoor", "survival", "travel", "wilderness",
        "worldbuilding",
    },
    "sci_fi": {
        "artificial intelligence", "cyberpunk", "future", "futuristic",
        "mecha", "robot", "robots", "science fiction", "sci-fi", "space",
        "technology",
    },
    "fantasy": {
        "action", "demons", "dragon", "dragons", "fantasy", "gore",
        "isekai", "magic", "medieval", "mythology", "revenge",
        "supernatural", "war",
    },
    "mystery": {
        "conspiracy", "crime", "detective", "horror", "mystery",
        "psychological", "secrets", "suspense", "thriller",
    },
    "romance": {
        "coming of age", "drama", "family", "found family", "love",
        "relationships", "romance", "school", "slice of life",
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

    scores = {}
    for category, keywords in THEME_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in phrases:
                score += 3
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


def extract_artwork_pack(project_root: Path) -> dict[str, dict[str, Path]]:
    source = project_root / "assets" / PACK_FILENAME
    if not source.exists():
        raise FileNotFoundError(
            f"Missing {source}. Keep artwork_asset_pack.png in the assets folder."
        )

    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache_root = project_root / ".anilist_cache" / "artwork_pack" / digest
    manifest: dict[str, dict[str, Path]] = {}

    with Image.open(source) as pack:
        pack = pack.convert("RGB")
        if pack.size != (1536, 1024):
            raise ValueError(
                f"{PACK_FILENAME} must be 1536x1024, not {pack.size[0]}x{pack.size[1]}."
            )

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
                crop = crop.resize(OUTPUT_SIZES[kind], Image.Resampling.LANCZOS)
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
    return category, manifest[category]
