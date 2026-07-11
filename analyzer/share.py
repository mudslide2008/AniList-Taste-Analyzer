
from __future__ import annotations

import struct
import unicodedata
import zlib
from pathlib import Path
from typing import Iterable


# Compact 5x7 bitmap font. The card deliberately uses uppercase ASCII so it
# remains portable and requires no bundled/system font files.
FONT = {
    " ": ["00000"] * 7,
    "A": ["01110","10001","10001","11111","10001","10001","10001"],
    "B": ["11110","10001","10001","11110","10001","10001","11110"],
    "C": ["01111","10000","10000","10000","10000","10000","01111"],
    "D": ["11110","10001","10001","10001","10001","10001","11110"],
    "E": ["11111","10000","10000","11110","10000","10000","11111"],
    "F": ["11111","10000","10000","11110","10000","10000","10000"],
    "G": ["01111","10000","10000","10111","10001","10001","01110"],
    "H": ["10001","10001","10001","11111","10001","10001","10001"],
    "I": ["11111","00100","00100","00100","00100","00100","11111"],
    "J": ["00111","00010","00010","00010","10010","10010","01100"],
    "K": ["10001","10010","10100","11000","10100","10010","10001"],
    "L": ["10000","10000","10000","10000","10000","10000","11111"],
    "M": ["10001","11011","10101","10101","10001","10001","10001"],
    "N": ["10001","11001","10101","10011","10001","10001","10001"],
    "O": ["01110","10001","10001","10001","10001","10001","01110"],
    "P": ["11110","10001","10001","11110","10000","10000","10000"],
    "Q": ["01110","10001","10001","10001","10101","10010","01101"],
    "R": ["11110","10001","10001","11110","10100","10010","10001"],
    "S": ["01111","10000","10000","01110","00001","00001","11110"],
    "T": ["11111","00100","00100","00100","00100","00100","00100"],
    "U": ["10001","10001","10001","10001","10001","10001","01110"],
    "V": ["10001","10001","10001","10001","10001","01010","00100"],
    "W": ["10001","10001","10001","10101","10101","10101","01010"],
    "X": ["10001","10001","01010","00100","01010","10001","10001"],
    "Y": ["10001","10001","01010","00100","00100","00100","00100"],
    "Z": ["11111","00001","00010","00100","01000","10000","11111"],
    "0": ["01110","10001","10011","10101","11001","10001","01110"],
    "1": ["00100","01100","00100","00100","00100","00100","01110"],
    "2": ["01110","10001","00001","00010","00100","01000","11111"],
    "3": ["11110","00001","00001","01110","00001","00001","11110"],
    "4": ["00010","00110","01010","10010","11111","00010","00010"],
    "5": ["11111","10000","10000","11110","00001","00001","11110"],
    "6": ["01110","10000","10000","11110","10001","10001","01110"],
    "7": ["11111","00001","00010","00100","01000","01000","01000"],
    "8": ["01110","10001","10001","01110","10001","10001","01110"],
    "9": ["01110","10001","10001","01111","00001","00001","01110"],
    "-": ["00000","00000","00000","11111","00000","00000","00000"],
    ".": ["00000","00000","00000","00000","00000","01100","01100"],
    ":": ["00000","01100","01100","00000","01100","01100","00000"],
    "/": ["00001","00010","00010","00100","01000","01000","10000"],
    "%": ["11001","11010","00100","01000","10110","00110","00000"],
    "&": ["01100","10010","10100","01000","10101","10010","01101"],
    "'": ["00100","00100","00000","00000","00000","00000","00000"],
    "(": ["00010","00100","01000","01000","01000","00100","00010"],
    ")": ["01000","00100","00010","00010","00010","00100","01000"],
    "+": ["00000","00100","00100","11111","00100","00100","00000"],
    "?": ["01110","10001","00001","00010","00100","00000","00100"],
}


def _ascii(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return normalized.encode("ascii", "ignore").decode("ascii").upper()


def _wrap(text: str, max_chars: int) -> list[str]:
    words = _ascii(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposed = word if not current else f"{current} {word}"
        if len(proposed) <= max_chars:
            current = proposed
        else:
            if current:
                lines.append(current)
            current = word[:max_chars]
    if current:
        lines.append(current)
    return lines


class Canvas:
    def __init__(self, width: int, height: int, background: tuple[int, int, int]):
        self.width = width
        self.height = height
        self.pixels = bytearray(background * (width * height))

    def rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + width), min(self.height, y + height)
        for py in range(y0, y1):
            start = (py * self.width + x0) * 3
            self.pixels[start:start + (x1 - x0) * 3] = bytes(color) * (x1 - x0)

    def text(self, x: int, y: int, value: str, scale: int, color: tuple[int, int, int]) -> None:
        cursor_x = x
        for char in _ascii(value):
            glyph = FONT.get(char, FONT["?"])
            for row_index, row in enumerate(glyph):
                for col_index, enabled in enumerate(row):
                    if enabled == "1":
                        self.rect(
                            cursor_x + col_index * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            color,
                        )
            cursor_x += 6 * scale

    def save_png(self, path: Path) -> None:
        raw = bytearray()
        stride = self.width * 3
        for row in range(self.height):
            raw.append(0)
            start = row * stride
            raw.extend(self.pixels[start:start + stride])

        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        png = bytearray(b"\x89PNG\r\n\x1a\n")
        png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)))
        png.extend(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        png.extend(chunk(b"IEND", b""))
        path.write_bytes(png)


def _top_names(stats: Iterable, limit: int = 2) -> list[str]:
    names = []
    for stat in stats:
        name = getattr(stat, "name", "")
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _fit_lines(text: str, max_chars: int, max_lines: int) -> list[str]:
    lines = _wrap(text, max_chars)
    if len(lines) <= max_lines:
        return lines
    clipped = lines[:max_lines]
    if clipped:
        clipped[-1] = clipped[-1][: max(0, max_chars - 3)].rstrip() + "..."
    return clipped


def _draw_text_block(
    card: Canvas,
    x: int,
    y: int,
    lines: list[str],
    scale: int,
    color: tuple[int, int, int],
    line_gap: int,
) -> int:
    for line in lines:
        card.text(x, y, line, scale, color)
        y += 7 * scale + line_gap
    return y


def write_share_assets(user, taste_glance, stats, rows, score_format, overall, output_dir: Path) -> None:
    username = user.get("name") or "AniList user"
    themes = [str(theme) for theme in (taste_glance.get("themes") or []) if theme]
    creators = _top_names(stats.get("staff") or [], 2)
    voices = _top_names(stats.get("japanese_vas") or [], 2)

    card = Canvas(1200, 675, (12, 17, 27))
    card.rect(0, 0, 1200, 12, (98, 214, 232))
    card.rect(56, 48, 1088, 579, (21, 28, 41))
    card.rect(56, 48, 9, 579, (98, 214, 232))

    # Header
    username_lines = _fit_lines(username, 24, 1)
    card.text(92, 78, username_lines[0] if username_lines else "ANILIST USER", 7, (237, 242, 247))
    card.text(94, 144, "ANIME TASTE REPORT", 3, (98, 214, 232))

    # Headline: capped to two lines to guarantee room below.
    headline = taste_glance.get("headline") or "A PERSONAL ANIME TASTE PROFILE"
    headline_lines = _fit_lines(headline, 44, 2)
    y = _draw_text_block(card, 94, 202, headline_lines, 5, (237, 242, 247), 10)

    # Divider positioned dynamically after headline.
    divider_y = max(332, y + 12)
    card.rect(94, divider_y, 1010, 2, (43, 57, 76))

    # Stats row
    stats_y = divider_y + 34
    card.text(94, stats_y, f"{len(rows)} RATED ANIME", 3, (158, 172, 192))
    card.text(455, stats_y, f"AVERAGE {overall:.1f}/{int(score_format['max'])}", 3, (158, 172, 192))
    top_rate = next((value for label, value in taste_glance.get("signals", []) if label == "Top-rating rate"), "")
    if top_rate:
        card.text(850, stats_y, f"TOP RATE {top_rate}", 3, (158, 172, 192))

    # Themes: wrapped and capped.
    section_y = stats_y + 64
    if themes:
        card.text(94, section_y, "STRONGEST THEMES", 3, (98, 214, 232))
        theme_text = " / ".join(themes[:4])
        theme_lines = _fit_lines(theme_text, 48, 2)
        section_y = _draw_text_block(card, 94, section_y + 34, theme_lines, 3, (237, 242, 247), 8) + 10

    # Bottom metadata columns. Each is wrapped independently and capped.
    bottom_y = min(max(section_y + 8, 520), 548)

    if creators:
        card.text(94, bottom_y, "RECURRING CREATORS", 2, (158, 172, 192))
        creator_lines = _fit_lines(" / ".join(creators), 34, 2)
        _draw_text_block(card, 94, bottom_y + 26, creator_lines, 2, (237, 242, 247), 6)

    if voices:
        card.text(650, bottom_y, "RECURRING VOICES", 2, (158, 172, 192))
        voice_lines = _fit_lines(" / ".join(voices), 34, 2)
        _draw_text_block(card, 650, bottom_y + 26, voice_lines, 2, (237, 242, 247), 6)

    card.text(92, 642, "GENERATED BY ANILIST TASTE ANALYZER", 2, (98, 214, 232))
    card.save_png(output_dir / "share_card.png")

    summary_lines = [
        f"{username}'s Anime Taste Report",
        "",
        f"{len(rows)} rated anime | Average: {overall:.1f}/{int(score_format['max'])}",
        "",
        taste_glance.get("headline") or "",
        taste_glance.get("summary") or "",
    ]
    if themes:
        summary_lines.extend(["", "Strongest themes: " + ", ".join(themes[:4])])
    if creators:
        summary_lines.extend(["", "Recurring creators: " + ", ".join(creators)])
    if voices:
        summary_lines.extend(["", "Recurring Japanese VAs: " + ", ".join(voices)])

    # Do not imply the HTML is downloadable or linked from this text file.
    summary_lines.extend([
        "",
        "A full interactive HTML report was generated alongside this summary.",
    ])

    (output_dir / "share_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
