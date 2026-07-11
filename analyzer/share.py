from __future__ import annotations

import base64
import hashlib
import html
import mimetypes
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from .share_pillow import write_share_assets as write_share_assets_pillow


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _signal_value(taste_glance: dict, label: str) -> str:
    return next(
        (str(value) for signal_label, value in taste_glance.get("signals", []) if signal_label == label),
        "",
    )


def _best_recommendation(rec_groups: dict | None) -> dict | None:
    return ((rec_groups or {}).get("Best matches") or [None])[0]


def _top_stats(stats: Iterable[Any], limit: int = 4) -> list[Any]:
    result = []
    for stat in stats:
        if getattr(stat, "name", ""):
            result.append(stat)
        if len(result) >= limit:
            break
    return result


def _creator_parts(value: str) -> tuple[str, str]:
    if " — " in value:
        name, role = value.split(" — ", 1)
        return name.strip(), role.strip()
    return value.strip(), ""


def _file_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _remote_data_uri(url: str, project_root: Path) -> str:
    if not url:
        return ""
    if url.startswith("data:"):
        return url

    cache_dir = project_root / ".anilist_cache" / "share_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cached = next(cache_dir.glob(f"{digest}.*"), None)

    if cached and cached.exists():
        return _file_data_uri(cached)

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AniList-Taste-Analyzer/3.2"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
            content_type = (response.headers.get_content_type() or "image/jpeg").lower()

        extension = mimetypes.guess_extension(content_type) or ".jpg"
        if extension == ".jpe":
            extension = ".jpg"

        cached = cache_dir / f"{digest}{extension}"
        cached.write_bytes(payload)
        return _file_data_uri(cached)
    except Exception:
        return ""


def _embedded_image_uri(value: str, project_root: Path) -> str:
    if not value:
        return ""
    if value.startswith("data:"):
        return value
    path = Path(value)
    if path.exists():
        return _file_data_uri(path)
    return _remote_data_uri(value, project_root)


def _hero_asset_uri(project_root: Path) -> str:
    for name in (
        "cover_background.jpg",
        "cover_background.png",
        "cover_background.webp",
        "default_hero.jpg",
    ):
        uri = _file_data_uri(project_root / "assets" / name)
        if uri:
            return uri
    return ""


def _quote_asset_uri(project_root: Path) -> str:
    for name in ("quote_background.jpg", "quote_background.png", "default_quote.jpg"):
        uri = _file_data_uri(project_root / "assets" / name)
        if uri:
            return uri
    return ""



def _row_theme_overlap(row: dict, themes: list[str]) -> int:
    terms = {
        str(value).casefold()
        for value in (row.get("tags") or []) + (row.get("genres") or [])
    }
    return sum(1 for theme in themes if theme.casefold() in terms)


def _hero_url(rows: list[dict], themes: list[str], rec_groups: dict | None, project_root: Path) -> str:
    custom = _hero_asset_uri(project_root)
    if custom:
        return custom

    candidates = [row for row in rows if row.get("banner_image") or row.get("cover_image")]
    candidates.sort(
        key=lambda row: (
            _row_theme_overlap(row, themes),
            row.get("rating") or 0,
            bool(row.get("banner_image")),
            row.get("favourites") or 0,
        ),
        reverse=True,
    )
    relevant = [row for row in candidates if _row_theme_overlap(row, themes) > 0]
    for row in relevant or candidates:
        url = row.get("banner_image") or row.get("cover_image")
        if url:
            return str(url)

    best = _best_recommendation(rec_groups)
    if best:
        return str(best.get("banner_image") or best.get("cover_image") or "")
    return ""


def _theme_description(name: str) -> str:
    descriptions = {
        "Travel": "Journeys, unfamiliar places, and the excitement of discovery.",
        "Historical": "Stories shaped by the past, legacy, and lived history.",
        "Survival": "Resourcefulness, perseverance, and pressure against the odds.",
        "Dungeon": "Exploration, danger, and discovery in unfamiliar worlds.",
        "Educational": "Learning is part of the entertainment rather than a lecture.",
        "Work": "People taking pride in a craft, profession, or shared goal.",
        "Coming of Age": "Growth through experience, failure, and changing relationships.",
        "Science": "Curiosity, experimentation, and understanding how things work.",
        "Music": "Practice, performance, expression, and mastery.",
        "Found Family": "Relationships built through trust rather than obligation.",
        "Agriculture": "Hands-on knowledge, systems, and patient improvement.",
        "Cooking": "Technique, experimentation, and care expressed through food.",
    }
    return descriptions.get(name, "A recurring theme strongly connected to top-rated anime.")


def _theme_icon(name: str) -> str:
    key = name.casefold()
    if "travel" in key:
        path = '<path d="M12 21s7-4.8 7-11a7 7 0 1 0-14 0c0 6.2 7 11 7 11Z"/><circle cx="12" cy="10" r="2.3"/>'
    elif "histor" in key:
        path = '<path d="M4 19.5V5.8c3-1.4 5.7-1.2 8 0v13.7c-2.3-1.2-5-1.4-8 0Zm8-13.7c2.3-1.2 5-1.4 8 0v13.7c-3-1.4-5.7-1.2-8 0"/>'
    elif "survival" in key:
        path = '<path d="M12 22c4.2-2.2 6.5-5.1 6.5-8.7 0-2.8-1.7-5-4.2-6.4.2 2.6-1 4.3-2.3 5.1.1-3.9-2.1-6.7-5.3-9C7.3 7.3 5.5 9 5.5 12.7 5.5 16.8 8.1 20 12 22Z"/>'
    elif "dungeon" in key:
        path = '<path d="M4 4h16v4H4zM6 8v12m12-12v12M9 8v5m6-5v5M3 20h18"/>'
    elif "science" in key or "educational" in key:
        path = '<path d="M9 3h6m-5 0v5l-5.2 9a2 2 0 0 0 1.7 3h11a2 2 0 0 0 1.7-3L14 8V3M7.5 15h9"/>'
    elif "music" in key:
        path = '<path d="M9 18V5l10-2v13M9 18a3 3 0 1 1-3-3h3m10 1a3 3 0 1 1-3-3h3"/>'
    else:
        path = '<path d="M12 3 9.5 9H3l5 4-2 7 6-4 6 4-2-7 5-4h-6.5L12 3Z"/>'
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{path}</svg>'


def _person_card(stat: Any, project_root: Path, creator: bool = False) -> str:
    name, subtitle = _creator_parts(stat.name) if creator else (stat.name, "")
    image = _embedded_image_uri(getattr(stat, "image", "") or "", project_root)
    if image:
        avatar = f'<img src="{_esc(image)}" alt="">'
    else:
        initials = "".join(part[0] for part in name.split()[:2]).upper() or "?"
        avatar = f'<div class="avatar-fallback">{_esc(initials)}</div>'
    subtitle_html = f'<div class="person-role">{_esc(subtitle)}</div>' if subtitle else ""
    return (
        '<div class="person-row">'
        f'<div class="avatar">{avatar}</div>'
        '<div class="person-copy">'
        f'<div class="person-name">{_esc(name)}</div>{subtitle_html}'
        '</div></div>'
    )


def _recommendation_card(best: dict | None, project_root: Path) -> str:
    if not best:
        return '<div class="empty-state">No recommendation data available.</div>'
    cover = _embedded_image_uri(
        best.get("cover_image") or best.get("banner_image") or "",
        project_root,
    )
    image = f'<img class="rec-cover" src="{_esc(cover)}" alt="">' if cover else '<div class="rec-cover placeholder"></div>'
    reasons = best.get("matched_tags") or best.get("matched_genres") or best.get("reasons") or []
    reason = ", ".join(str(item) for item in reasons[:3])
    reason_html = f'<div class="rec-why">Why: {_esc(reason)}</div>' if reason else ""
    return (
        '<div class="recommendation">'
        f'{image}<div class="rec-copy"><div class="eyebrow">Best match</div>'
        f'<div class="rec-title">{_esc(best.get("title") or "—")}</div>{reason_html}'
        '</div></div>'
    )


POSTER_CSS = r'''
:root {
  --bg:#06111e; --panel:rgba(8,23,39,.94); --panel-soft:rgba(13,35,56,.9);
  --line:#2c5e78; --cyan:#55d9ee; --text:#f6f8fc; --muted:#a9b9cc; --hero-image:none; --quote-image:none;
}
* { box-sizing:border-box; }
html,body {
  margin:0; width:1600px; min-height:2200px;
  background:radial-gradient(circle at 70% 4%,rgba(22,100,137,.32),transparent 36%),
             linear-gradient(180deg,#081a2d 0%,#06111e 58%,#040b15 100%);
  color:var(--text); font-family:"Segoe UI",Arial,sans-serif;
}
body { padding:20px; }
.poster { min-height:2160px; border:2px solid var(--cyan); border-radius:28px; overflow:hidden; background:rgba(3,12,22,.68); box-shadow:0 25px 80px rgba(0,0,0,.45),inset 0 0 50px rgba(37,198,226,.05); }
.hero {
  position:relative;
  min-height:690px;
  padding:54px 58px 46px;
  overflow:hidden;
  background:linear-gradient(135deg,#061321 0%,#071827 58%,#07111d 100%);
}
.hero::before {
  content:"";
  position:absolute;
  inset:0 0 0 43%;
  background-image:var(--hero-image);
  background-size:cover;
  background-position:center 68%;
  background-repeat:no-repeat;
  opacity:.94;
}
.hero::after {
  content:"";
  position:absolute;
  inset:0;
  background:
    linear-gradient(90deg,#061321 0%,rgba(6,19,33,.98) 31%,rgba(6,19,33,.78) 52%,rgba(6,19,33,.15) 82%),
    linear-gradient(180deg,transparent 66%,#06111e 100%);
  border-bottom:2px solid rgba(85,217,238,.5);
  pointer-events:none;
}
.hero > * { position:relative; z-index:1; }
.header-row { display:grid; grid-template-columns:minmax(0,1fr) 340px; gap:42px; align-items:start; }
.username { margin:0; font-size:86px; line-height:.95; font-weight:900; letter-spacing:-3px; text-shadow:0 4px 30px rgba(0,0,0,.6); }
.report-label { display:flex; align-items:center; gap:18px; margin-top:18px; color:var(--cyan); font-weight:800; font-size:26px; letter-spacing:3px; text-transform:uppercase; }
.report-label::after { content:""; width:260px; height:2px; background:linear-gradient(90deg,var(--cyan),transparent); }
.metrics { display:grid; gap:20px; padding:28px 30px; border:1px solid rgba(85,217,238,.45); border-radius:22px; background:rgba(4,16,29,.9); backdrop-filter:blur(10px); box-shadow:0 16px 40px rgba(0,0,0,.28); }
.metric { display:grid; grid-template-columns:62px 1fr; align-items:center; gap:14px; }
.metric-icon { width:48px; height:48px; display:grid; place-items:center; color:var(--cyan); }
.metric-icon svg { width:42px; height:42px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
.metric strong { display:block; font-size:42px; line-height:1; }
.metric span { display:block; margin-top:6px; color:var(--muted); text-transform:uppercase; font-size:15px; font-weight:700; letter-spacing:.7px; }
.hero-copy { width:980px; margin-top:58px; }
.hero-copy h2 { margin:0; font-size:52px; line-height:1.16; letter-spacing:-1.4px; }
.hero-copy p { margin:26px 0 0; max-width:900px; font-size:25px; line-height:1.55; color:#d6dfeb; text-shadow:0 2px 16px rgba(0,0,0,.65); }
.content { padding:34px 38px 26px; }
.section-title { display:flex; align-items:center; gap:18px; justify-content:center; margin:0 0 24px; color:var(--cyan); text-transform:uppercase; font-size:28px; letter-spacing:1.2px; }
.section-title::before,.section-title::after { content:""; width:130px; height:1px; background:linear-gradient(90deg,transparent,var(--cyan)); }
.section-title::after { transform:scaleX(-1); }
.signals { display:grid; grid-template-columns:repeat(4,1fr); gap:18px; }
.signal-card { min-height:225px; display:grid; grid-template-columns:68px 1fr; gap:16px; padding:25px 22px; border:1px solid var(--line); border-radius:20px; background:linear-gradient(145deg,rgba(16,44,69,.94),rgba(8,25,42,.94)); }
.signal-icon { width:60px; height:60px; color:var(--cyan); }
.signal-icon svg { width:60px; height:60px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
.signal-card h3 { margin:3px 0 12px; color:var(--cyan); font-size:22px; text-transform:uppercase; }
.signal-card p { margin:0; color:#dce5ef; font-size:18px; line-height:1.45; }
.dashboard { display:grid; grid-template-columns:1fr 1fr 1.02fr; gap:18px; margin-top:26px; align-items:stretch; }
.panel { border:1px solid var(--line); border-radius:21px; background:linear-gradient(180deg,rgba(9,27,45,.96),rgba(6,20,34,.96)); overflow:hidden; box-shadow:0 14px 34px rgba(0,0,0,.2); }
.panel-header { padding:22px 24px 12px; color:var(--cyan); text-transform:uppercase; font-size:23px; font-weight:800; letter-spacing:.7px; }
.people-list { padding:4px 24px 22px; }
.person-row { display:grid; grid-template-columns:66px 1fr; gap:15px; align-items:center; min-height:82px; padding:10px 0; border-bottom:1px dashed rgba(85,217,238,.22); }
.person-row:last-child { border-bottom:0; }
.avatar { width:58px; height:58px; border-radius:50%; overflow:hidden; background:#174866; border:1px solid rgba(85,217,238,.25); }
.avatar img { width:100%; height:100%; object-fit:cover; }
.avatar-fallback { width:100%; height:100%; display:grid; place-items:center; font-weight:900; color:var(--text); }
.person-name { font-size:21px; line-height:1.2; font-weight:800; }
.person-role { margin-top:5px; color:var(--muted); font-size:16px; line-height:1.28; }
.highlights { padding:6px 24px 24px; }
.highlight-block { padding:18px 0 21px; border-bottom:1px solid var(--line); }
.highlight-block:last-child { border-bottom:0; }
.eyebrow { color:var(--muted); text-transform:uppercase; font-size:15px; font-weight:800; letter-spacing:.8px; }
.alignment { margin-top:8px; color:var(--cyan); font-size:31px; line-height:1.15; font-weight:900; }
.recommendation { display:grid; grid-template-columns:125px 1fr; gap:18px; margin-top:10px; align-items:start; }
.rec-cover { width:125px; height:178px; object-fit:cover; border-radius:12px; border:1px solid var(--line); background:#132b42; }
.rec-title { margin-top:8px; font-size:29px; line-height:1.16; font-weight:900; }
.rec-why { margin-top:12px; color:var(--muted); font-size:17px; line-height:1.42; }
.quote {
  position:relative;
  display:grid;
  grid-template-columns:64px 1fr;
  gap:16px;
  align-items:start;
  margin-top:24px;
  min-height:168px;
  padding:27px 420px 27px 28px;
  border:1px solid var(--line);
  border-radius:20px;
  overflow:hidden;
  background-color:#0a2034;
  background-image:
    linear-gradient(90deg,rgba(8,33,52,1) 0%,rgba(8,28,47,.98) 46%,rgba(8,23,39,.35) 72%,rgba(8,23,39,.08) 100%),
    var(--quote-image);
  background-size:100% 100%, 46% auto;
  background-position:center, right center;
  background-repeat:no-repeat;
}
.quote-mark { color:var(--cyan); font-size:74px; line-height:.8; font-weight:900; }
.quote p { margin:4px 0 0; font-size:20px; line-height:1.5; color:#e4ebf3; }
.footer { display:flex; align-items:center; justify-content:center; gap:18px; padding:18px 0 2px; color:var(--cyan); font-size:18px; letter-spacing:2px; text-transform:uppercase; }
.footer::before,.footer::after { content:""; width:250px; height:1px; background:linear-gradient(90deg,transparent,var(--cyan)); }
.footer::after { transform:scaleX(-1); }
'''


def _poster_html(user, taste_glance, stats, rows, score_format, overall, rec_groups):
    project_root = Path(__file__).resolve().parent.parent
    themes = [str(value) for value in (taste_glance.get("themes") or []) if value][:4]
    hero = _embedded_image_uri(
        _hero_url(rows, themes, rec_groups, project_root),
        project_root,
    )
    quote_art = _embedded_image_uri(_quote_asset_uri(project_root), project_root)
    hero_style = f"--hero-image:url('{_esc(hero)}');" if hero else ""
    quote_style = f"--quote-image:url('{_esc(quote_art)}');" if quote_art else ""

    creators = "".join(
        _person_card(stat, project_root, True)
        for stat in _top_stats(stats.get("staff") or [], 4)
    )
    vas = "".join(
        _person_card(stat, project_root, False)
        for stat in _top_stats(stats.get("japanese_vas") or [], 4)
    )
    signal_cards = "".join(
        '<article class="signal-card">'
        f'<div class="signal-icon">{_theme_icon(theme)}</div>'
        f'<div><h3>{_esc(theme)}</h3><p>{_esc(_theme_description(theme))}</p></div>'
        '</article>'
        for theme in themes
    )
    top_rate = _signal_value(taste_glance, "Top-rating rate") or "—"
    alignment = _signal_value(taste_glance, "Community alignment") or "Personal"
    best = _best_recommendation(rec_groups)

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=1600, initial-scale=1"><style>{POSTER_CSS}</style></head>
<body style="{hero_style}{quote_style}"><div class="poster">
<section class="hero"><div class="header-row"><div><h1 class="username">{_esc(user.get("name") or "AniList user")}</h1><div class="report-label">Anime Taste Report</div></div>
<aside class="metrics">
<div class="metric"><div class="metric-icon">{_theme_icon("Educational")}</div><div><strong>{len(rows)}</strong><span>Rated anime</span></div></div>
<div class="metric"><div class="metric-icon"><svg viewBox="0 0 24 24"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/></svg></div><div><strong>{overall:.1f}/{int(score_format["max"])}</strong><span>Average rating</span></div></div>
<div class="metric"><div class="metric-icon"><svg viewBox="0 0 24 24"><path d="M4 20V14m5 6V9m5 11V5m5 15V2"/></svg></div><div><strong>{_esc(top_rate)}</strong><span>Top-rating rate</span></div></div>
</aside></div><div class="hero-copy"><h2>{_esc(taste_glance.get("headline") or "A personal anime taste profile.")}</h2><p>{_esc(taste_glance.get("summary") or "")}</p></div></section>
<main class="content"><h2 class="section-title">Your strongest signals</h2><section class="signals">{signal_cards}</section>
<section class="dashboard"><article class="panel"><div class="panel-header">Recurring creators</div><div class="people-list">{creators}</div></article>
<article class="panel"><div class="panel-header">Recurring Japanese VAs</div><div class="people-list">{vas}</div></article>
<article class="panel"><div class="panel-header">Other highlights</div><div class="highlights"><div class="highlight-block"><div class="eyebrow">Community alignment</div><div class="alignment">{_esc(alignment)}</div></div><div class="highlight-block">{_recommendation_card(best, project_root)}</div></div></article></section>
<section class="quote"><div class="quote-mark">“</div><p>The full report explains the evidence behind these patterns and keeps detailed creators, voice actors, ratings, and recommendations interactive.</p></section>
<footer class="footer">Generated by AniList Taste Analyzer</footer></main></div></body></html>'''


def _social_html(user, taste_glance, rows, score_format, overall, rec_groups):
    project_root = Path(__file__).resolve().parent.parent
    themes = [str(value) for value in (taste_glance.get("themes") or []) if value][:4]
    hero = _embedded_image_uri(
        _hero_url(rows, themes, rec_groups, project_root),
        project_root,
    )
    hero_style = f"--hero-image:url('{_esc(hero)}');" if hero else ""
    theme_chips = "".join(f'<span>{_esc(theme)}</span>' for theme in themes)
    best = _best_recommendation(rec_groups)
    best_text = _esc(best.get("title") if best else "—")
    top_rate = _signal_value(taste_glance, "Top-rating rate") or "—"
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
:root{{--cyan:#55d9ee;--text:#f4f7fb;--muted:#a9b9cc;--hero-image:none}}*{{box-sizing:border-box}}html,body{{margin:0;width:1920px;height:1080px;background:#06111e;color:var(--text);font-family:"Segoe UI",Arial,sans-serif}}
.card{{position:relative;width:1920px;height:1080px;overflow:hidden;border:3px solid var(--cyan);border-radius:30px;background:linear-gradient(135deg,#061321,#07111e)}}
.card::before{{content:"";position:absolute;inset:0 0 0 44%;background-image:var(--hero-image);background-size:cover;background-position:center 68%;background-repeat:no-repeat}}
.card::after{{content:"";position:absolute;inset:0;background:linear-gradient(90deg,#061321 0%,rgba(6,19,33,.98) 35%,rgba(6,19,33,.76) 55%,rgba(6,19,33,.08) 84%);pointer-events:none}}
.card>*{{position:relative;z-index:1}}
.content{{position:absolute;left:86px;top:72px;width:1130px}}h1{{margin:0;font-size:92px;line-height:.95;font-weight:900;letter-spacing:-3px}}.label{{margin-top:18px;color:var(--cyan);font-size:29px;font-weight:800;letter-spacing:3px;text-transform:uppercase}}h2{{margin:70px 0 0;font-size:58px;line-height:1.14;letter-spacing:-1.5px}}p{{margin:26px 0 0;width:980px;color:#d3deea;font-size:27px;line-height:1.5}}
.metrics{{position:absolute;right:72px;top:64px;width:340px;padding:28px;border:1px solid rgba(85,217,238,.45);border-radius:22px;background:rgba(4,16,29,.9)}}.metric{{margin-bottom:22px}}.metric:last-child{{margin-bottom:0}}.metric b{{display:block;font-size:44px}}.metric span{{display:block;color:var(--muted);font-size:16px;text-transform:uppercase}}
.bottom{{position:absolute;left:86px;right:86px;bottom:78px;display:flex;align-items:flex-end;justify-content:space-between;gap:30px}}.chips{{display:flex;flex-wrap:wrap;gap:12px;max-width:1050px}}.chips span{{padding:13px 20px;border:1px solid #2c5e78;border-radius:999px;background:rgba(13,35,56,.9);font-weight:800;font-size:20px}}.best{{min-width:450px;padding:20px 24px;border:1px solid #2c5e78;border-radius:18px;background:rgba(8,23,39,.92)}}.best small{{display:block;color:var(--muted);font-size:15px;text-transform:uppercase}}.best strong{{display:block;margin-top:7px;font-size:29px}}
</style></head><body style="{hero_style}"><div class="card"><div class="content"><h1>{_esc(user.get("name") or "AniList user")}</h1><div class="label">Anime Taste Report</div><h2>{_esc(taste_glance.get("headline") or "")}</h2><p>{_esc(taste_glance.get("summary") or "")}</p></div><div class="metrics"><div class="metric"><b>{len(rows)}</b><span>Rated anime</span></div><div class="metric"><b>{overall:.1f}/{int(score_format["max"])}</b><span>Average</span></div><div class="metric"><b>{_esc(top_rate)}</b><span>Top-rating rate</span></div></div><div class="bottom"><div class="chips">{theme_chips}</div><div class="best"><small>Best match</small><strong>{best_text}</strong></div></div></div></body></html>'''


def _launch_browser(playwright):
    attempts = [
        lambda: playwright.chromium.launch(channel="msedge", headless=True),
        lambda: playwright.chromium.launch(channel="chrome", headless=True),
    ]

    executable_candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for executable in executable_candidates:
        if executable and Path(executable).exists():
            attempts.append(
                lambda executable=executable: playwright.chromium.launch(
                    executable_path=executable, headless=True
                )
            )

    attempts.append(lambda: playwright.chromium.launch(headless=True))
    errors = []
    for attempt in attempts:
        try:
            return attempt()
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("Could not launch Edge/Chrome for cover rendering. " + " | ".join(errors[-2:]))


def _render_html(html_text: str, output_path: Path, width: int, height: int, full_page: bool = False) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.set_content(html_text, wait_until="networkidle", timeout=60000)
            page.screenshot(path=str(output_path), full_page=full_page, animations="disabled")
        finally:
            browser.close()


def write_share_assets(user, taste_glance, stats, rows, score_format, overall, output_dir, rec_groups=None):
    poster_html = _poster_html(user, taste_glance, stats, rows, score_format, overall, rec_groups)
    social_html = _social_html(user, taste_glance, rows, score_format, overall, rec_groups)
    (output_dir / "taste_cover.html").write_text(poster_html, encoding="utf-8")
    (output_dir / "share_card.html").write_text(social_html, encoding="utf-8")
    try:
        _render_html(poster_html, output_dir / "taste_cover.png", 1600, 2200, full_page=True)
        _render_html(social_html, output_dir / "share_card.png", 1920, 1080, full_page=False)
    except Exception as exc:
        print(f"Browser cover rendering failed; using Pillow fallback: {exc}")
        write_share_assets_pillow(user, taste_glance, stats, rows, score_format, overall, output_dir, rec_groups)
    best = _best_recommendation(rec_groups)
    summary = [f"{user.get('name') or 'AniList user'}'s Anime Taste Report", "", taste_glance.get("headline") or "", taste_glance.get("summary") or "", "", f"{len(rows)} rated anime | Average: {overall:.1f}/{int(score_format['max'])}"]
    if taste_glance.get("themes"):
        summary.extend(["", "Strongest signals: " + ", ".join(taste_glance["themes"][:4])])
    if best:
        summary.extend(["", "Best recommendation match: " + str(best.get("title") or "—")])
    summary.extend(["", "A full interactive report, HTML cover, and shareable PNG were generated alongside this summary."])
    (output_dir / "share_summary.txt").write_text("\n".join(summary), encoding="utf-8")
