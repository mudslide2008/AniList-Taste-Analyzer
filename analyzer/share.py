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

from .artwork_pack import selected_artwork
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



def _artwork_for_report(
    project_root: Path,
    user: dict,
    taste_glance: dict,
) -> tuple[str, dict[str, str]]:
    username = str(user.get("name") or "AniList user")
    themes = [str(value) for value in (taste_glance.get("themes") or []) if value][:4]

    try:
        category, paths = selected_artwork(
            project_root,
            username,
            themes,
            str(taste_glance.get("headline") or ""),
            str(taste_glance.get("summary") or ""),
        )
    except Exception as exc:
        print(f"Artwork pack could not be loaded; using background fallback: {exc}")
        return "fallback", {}

    return category, {
        kind: _file_data_uri(path)
        for kind, path in paths.items()
        if path.exists()
    }


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
:root { --panel:rgba(8,23,39,.94); --line:#2c5e78; --cyan:#55d9ee; --text:#f6f8fc; --muted:#a9b9cc; --hero-image:none; --quote-image:none; }
* { box-sizing:border-box; }
html,body { margin:0; width:1600px; background:linear-gradient(180deg,#081a2d,#040b15); color:var(--text); font-family:"Segoe UI",Arial,sans-serif; }
body { padding:20px; }
.poster { border:2px solid var(--cyan); border-radius:28px; overflow:hidden; background:#06111e; }
.hero { position:relative; min-height:500px; padding:38px 58px 34px; overflow:hidden; background:#061321; }
.hero::before { content:""; position:absolute; inset:0; background-image:var(--hero-image); background-size:100% 100%; background-position:center; background-repeat:no-repeat; }
.hero::after { content:""; position:absolute; inset:0; background:linear-gradient(90deg,rgba(4,14,25,.99) 0%,rgba(4,14,25,.96) 34%,rgba(4,14,25,.68) 56%,rgba(4,14,25,.08) 84%),linear-gradient(180deg,transparent 62%,#06111e 100%); border-bottom:2px solid rgba(85,217,238,.48); }
.hero > * { position:relative; z-index:1; }
.header-row { display:grid; grid-template-columns:minmax(0,1fr) 330px; gap:36px; }
.username { margin:0; font-size:72px; line-height:.95; font-weight:900; letter-spacing:-2px; }
.report-label { margin-top:14px; color:var(--cyan); font-weight:800; font-size:22px; letter-spacing:2.6px; text-transform:uppercase; }
.metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; padding:18px; border:1px solid rgba(85,217,238,.45); border-radius:20px; background:rgba(4,16,29,.88); }
.metric { text-align:center; } .metric-icon { display:none; } .metric strong { display:block; font-size:28px; } .metric span { display:block; margin-top:6px; color:var(--muted); text-transform:uppercase; font-size:11px; }
.hero-copy { width:930px; margin-top:42px; }
.hero-copy h2 { margin:0; font-size:42px; line-height:1.15; } .hero-copy p { margin:18px 0 0; max-width:860px; font-size:21px; line-height:1.48; color:#d6dfeb; }
.content { padding:30px 38px 26px; }
.section-title { display:flex; align-items:center; justify-content:center; gap:18px; margin:0 0 22px; color:var(--cyan); text-transform:uppercase; font-size:26px; }
.signals { display:grid; grid-template-columns:repeat(4,1fr); gap:18px; }
.signal-card { min-height:205px; display:grid; grid-template-columns:58px 1fr; gap:14px; padding:22px 20px; border:1px solid var(--line); border-radius:20px; background:linear-gradient(145deg,rgba(16,44,69,.94),rgba(8,25,42,.94)); }
.signal-icon,.signal-icon svg { width:50px; height:50px; color:var(--cyan); fill:none; stroke:currentColor; stroke-width:1.8; }
.signal-card h3 { margin:3px 0 10px; color:var(--cyan); font-size:20px; } .signal-card p { margin:0; font-size:16px; line-height:1.42; }
.dashboard { display:grid; grid-template-columns:1fr 1fr 1.02fr; gap:18px; margin-top:24px; }
.panel { border:1px solid var(--line); border-radius:21px; background:linear-gradient(180deg,rgba(9,27,45,.96),rgba(6,20,34,.96)); overflow:hidden; }
.panel-header { padding:20px 22px 10px; color:var(--cyan); text-transform:uppercase; font-size:21px; font-weight:800; }
.people-list { padding:4px 22px 20px; }
.person-row { display:grid; grid-template-columns:60px 1fr; gap:14px; align-items:center; min-height:76px; padding:8px 0; border-bottom:1px dashed rgba(85,217,238,.22); }
.avatar { width:54px; height:54px; border-radius:50%; overflow:hidden; background:#174866; } .avatar img { width:100%; height:100%; object-fit:cover; }
.avatar-fallback { width:100%; height:100%; display:grid; place-items:center; font-weight:900; }
.person-name { font-size:19px; font-weight:800; } .person-role { margin-top:4px; color:var(--muted); font-size:14px; }
.highlights { padding:6px 22px 22px; } .highlight-block { padding:16px 0 18px; border-bottom:1px solid var(--line); }
.eyebrow { color:var(--muted); text-transform:uppercase; font-size:14px; font-weight:800; } .alignment { margin-top:7px; color:var(--cyan); font-size:28px; font-weight:900; }
.recommendation { display:grid; grid-template-columns:112px 1fr; gap:16px; margin-top:10px; } .rec-cover { width:112px; height:160px; object-fit:cover; border-radius:12px; } .rec-title { margin-top:8px; font-size:25px; font-weight:900; } .rec-why { margin-top:10px; color:var(--muted); font-size:15px; }
.quote { position:relative; display:grid; grid-template-columns:58px 1fr; gap:14px; margin-top:22px; min-height:190px; padding:28px 590px 28px 28px; border:1px solid var(--line); border-radius:20px; overflow:hidden; background:#0a2034; }
.quote::before { content:""; position:absolute; right:0; top:0; bottom:0; width:920px; background-image:var(--quote-image); background-size:100% 100%; background-position:center; }
.quote::after { content:""; position:absolute; inset:0; background:linear-gradient(90deg,#0a2034 0%,rgba(10,32,52,.98) 42%,rgba(10,32,52,.58) 66%,rgba(10,32,52,.04) 92%); }
.quote > * { position:relative; z-index:1; } .quote-mark { color:var(--cyan); font-size:68px; } .quote p { margin:4px 0 0; font-size:18px; line-height:1.48; }
.footer { text-align:center; padding:18px 0 2px; color:var(--cyan); font-size:16px; letter-spacing:2px; text-transform:uppercase; }
'''



def _poster_html(user, taste_glance, stats, rows, score_format, overall, rec_groups):
    project_root = Path(__file__).resolve().parent.parent
    themes = [str(value) for value in (taste_glance.get("themes") or []) if value][:4]
    art_category, artwork = _artwork_for_report(
        project_root,
        user,
        taste_glance,
    )
    hero = artwork.get("poster", "")
    quote_art = artwork.get("quote", "")
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
    art_category, artwork = _artwork_for_report(
        project_root,
        user,
        taste_glance,
    )
    hero = artwork.get("social", "")
    hero_style = f"--hero-image:url('{_esc(hero)}');" if hero else ""
    theme_chips = "".join(f'<span>{_esc(theme)}</span>' for theme in themes)
    best = _best_recommendation(rec_groups)
    best_text = _esc(best.get("title") if best else "—")
    top_rate = _signal_value(taste_glance, "Top-rating rate") or "—"
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
:root{{--cyan:#55d9ee;--text:#f4f7fb;--muted:#a9b9cc;--hero-image:none}}*{{box-sizing:border-box}}html,body{{margin:0;width:1920px;height:1080px;background:#06111e;color:var(--text);font-family:"Segoe UI",Arial,sans-serif}}
.card{{position:relative;width:1920px;height:1080px;overflow:hidden;border:3px solid var(--cyan);border-radius:30px;background:#06111e}}
.card::before{{content:"";position:absolute;left:0;right:0;top:0;height:625px;background-image:var(--hero-image);background-size:100% 100%;background-position:center;background-repeat:no-repeat}}
.card::after{{content:"";position:absolute;left:0;right:0;top:0;height:625px;background:linear-gradient(90deg,rgba(4,14,25,.99) 0%,rgba(4,14,25,.94) 36%,rgba(4,14,25,.45) 64%,rgba(4,14,25,.06) 88%),linear-gradient(180deg,transparent 62%,#06111e 100%);pointer-events:none}}
.card>*{{position:relative;z-index:1}}
.content{{position:absolute;left:86px;top:62px;width:1130px}}h1{{margin:0;font-size:84px;line-height:.95;font-weight:900;letter-spacing:-3px}}.label{{margin-top:18px;color:var(--cyan);font-size:29px;font-weight:800;letter-spacing:3px;text-transform:uppercase}}h2{{margin:58px 0 0;font-size:52px;line-height:1.14;letter-spacing:-1.5px}}p{{margin:22px 0 0;width:930px;color:#d3deea;font-size:24px;line-height:1.5}}
.metrics{{position:absolute;right:72px;top:64px;width:340px;padding:28px;border:1px solid rgba(85,217,238,.45);border-radius:22px;background:rgba(4,16,29,.9)}}.metric{{margin-bottom:22px}}.metric:last-child{{margin-bottom:0}}.metric b{{display:block;font-size:44px}}.metric span{{display:block;color:var(--muted);font-size:16px;text-transform:uppercase}}
.bottom{{position:absolute;left:86px;right:86px;top:675px;bottom:58px;display:grid;grid-template-columns:1fr 470px;gap:30px;align-items:stretch;border-top:1px solid rgba(85,217,238,.35);padding-top:56px}}.chips{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;position:relative}}.chips::before{{content:"STRONGEST SIGNALS";position:absolute;top:-40px;left:0;color:var(--cyan);font-size:20px;font-weight:800;letter-spacing:1px}}.chips span{{display:flex;align-items:center;justify-content:center;padding:18px 22px;border:1px solid #2c5e78;border-radius:18px;background:linear-gradient(145deg,rgba(16,44,69,.95),rgba(8,25,42,.95));font-weight:800;font-size:25px}}.best{{align-self:stretch;display:flex;flex-direction:column;justify-content:center;min-width:470px;padding:28px 30px;border:1px solid #2c5e78;border-radius:18px;background:linear-gradient(145deg,rgba(16,44,69,.95),rgba(8,25,42,.95))}}.best small{{display:block;color:var(--muted);font-size:17px;text-transform:uppercase}}.best strong{{display:block;margin-top:10px;font-size:34px}}
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
            if full_page and page.locator(".poster").count():
                page.locator(".poster").screenshot(path=str(output_path), animations="disabled")
            else:
                page.screenshot(path=str(output_path), full_page=False, animations="disabled")
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
