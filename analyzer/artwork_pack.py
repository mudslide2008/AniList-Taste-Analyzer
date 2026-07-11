
from __future__ import annotations
from pathlib import Path

DEFAULT_THEME = "exploration"

def choose_art_theme(
    username: str,
    themes: list[str],
    headline: str = "",
    summary: str = "",
) -> str:
    return DEFAULT_THEME

def selected_artwork(
    project_root: Path,
    username: str,
    themes: list[str],
    headline: str = "",
    summary: str = "",
) -> tuple[str, dict[str, Path]]:
    theme = choose_art_theme(username, themes, headline, summary)
    folder = project_root / "assets" / "themes" / theme
    paths = {
        "poster": folder / "hero_cover.png",
        "social": folder / "hero_social.png",
        "quote": folder / "quote_banner.png",
    }
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing theme artwork:\n" + "\n".join(str(path) for path in missing)
        )
    return theme, paths
