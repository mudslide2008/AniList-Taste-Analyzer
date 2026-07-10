
from __future__ import annotations
import html, re
from typing import Any, Iterable, Sequence

SCORE_FORMATS = {
    "POINT_3": {"max": 3.0, "label": "3-point", "decimals": 0},
    "POINT_5": {"max": 5.0, "label": "5-star", "decimals": 0},
    "POINT_10": {"max": 10.0, "label": "10-point", "decimals": 0},
    "POINT_10_DECIMAL": {"max": 10.0, "label": "10-point decimal", "decimals": 1},
    "POINT_100": {"max": 100.0, "label": "100-point", "decimals": 0},
}

def score_info(user: dict[str, Any]) -> dict[str, Any]:
    fmt = ((user.get("mediaListOptions") or {}).get("scoreFormat") or "POINT_100")
    info = dict(SCORE_FORMATS.get(fmt, SCORE_FORMATS["POINT_100"]))
    info["format"] = fmt
    return info

def display_score(value: float | None, info: dict[str, Any], suffix: bool = True) -> str:
    if value is None:
        return "—"
    decimals = info.get("decimals", 0)
    number = f"{value:.{decimals}f}"
    if info.get("format") == "POINT_5":
        rounded = max(0, min(5, int(round(value))))
        return ("★" * rounded + "☆" * (5 - rounded)) + (f" ({number}/5)" if suffix else "")
    return f"{number}/{int(info['max'])}" if suffix else number

def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("._") or "anilist_user"

def chunks(items: Sequence[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(items), size):
        yield list(items[index:index + size])

def fuzzy_date(value: dict[str, Any] | None) -> str:
    if not value or not value.get("year"):
        return ""
    parts = [str(value["year"])]
    if value.get("month"):
        parts.append(f"{value['month']:02d}")
    if value.get("day"):
        parts.append(f"{value['day']:02d}")
    return "-".join(parts)

def esc(value: Any) -> str:
    return html.escape(str(value))
