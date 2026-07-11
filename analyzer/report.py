
from __future__ import annotations
import re, statistics
from collections import Counter
from datetime import datetime
from .util import esc, display_score
from .data import confidence_adjusted, adjusted_top_rate
from .profile import confidence_label
from .recommendations import recommendation_reason

def stat_rows(stats, overall, score_format, limit=20, rank_by_top_rate=False):
    overall_top=sum(s.top_rate*s.count for s in stats)/sum(s.count for s in stats) if stats else 0
    ranked=sorted(stats,key=(lambda s:(adjusted_top_rate(s,overall_top),s.count)) if rank_by_top_rate else (lambda s:(confidence_adjusted(s,overall),s.count)),reverse=True)[:limit]
    out=[]
    for s in ranked:
        lift_class="positive" if s.lift>score_format["max"]*.008 else "negative" if s.lift<-score_format["max"]*.008 else "neutral"
        top_lift=s.top_rate-overall_top
        top_class="positive" if top_lift>.03 else "negative" if top_lift<-.03 else "neutral"
        out.append(f"<tr><td>{esc(s.name)}</td><td>{s.count}</td><td>{display_score(s.average,score_format)}</td><td class='{lift_class}'>{s.lift:+.{score_format['decimals']+1}f}</td><td>{s.top_rate:.0%}</td><td class='{top_class}'>{top_lift:+.0%}</td></tr>")
    return "".join(out) or "<tr><td colspan='6' class='muted'>Not enough data.</td></tr>"

def group_table(title, stats, overall, score_format, limit=20, rank_by_top_rate=False, collapsible=False, note=None):
    section=f"""<section><h2>{esc(title)}</h2><p class='hint'>{esc(note or 'Ranked with a small-sample adjustment.')}</p><div class='table-wrap'><table><thead><tr><th>Name</th><th>Count</th><th>Average</th><th>Avg lift</th><th>Top-rate</th><th>Top-rate lift</th></tr></thead><tbody>{stat_rows(stats,overall,score_format,limit,rank_by_top_rate)}</tbody></table></div></section>"""
    return f"<details><summary>{esc(title)}</summary>{section}</details>" if collapsible else section


# Semantic value estimates how much a tag describes the core viewing experience.
# Low-value tags are still shown in the complete table; they simply do not
# dominate the main insight list because of accidental correlation.
LOW_SEMANTIC_TAGS = {
    "CGI", "Rotoscoping", "Achromatic", "Snowscape", "Desert", "Coastal",
    "Rural", "Urban", "Foreign", "Primarily Male Cast", "Primarily Female Cast",
    "Primarily Teen Cast", "Primarily Adult Cast", "Primarily Child Cast",
    "Heterosexual", "Bisexual", "Asexual", "Aromantic", "Flat Chest",
    "Tanned Skin", "Nudity", "Male Nudity", "Female Nudity", "Feet", "Chibi",
}
MEDIUM_SEMANTIC_TAGS = {
    "Male Protagonist", "Female Protagonist", "Elf", "Goblin", "Demons",
    "Vampire", "Monster Girl", "Monster Boy", "Animals", "Kemonomimi",
    "Nekomimi", "Guns", "Swordplay", "Spearplay", "Archery", "Trains",
    "School", "Urban Fantasy", "Medieval", "Historical", "Isekai",
}


def tag_semantic_weight(name: str) -> float:
    if name in LOW_SEMANTIC_TAGS:
        return 0.20
    if name in MEDIUM_SEMANTIC_TAGS:
        return 0.60
    return 1.0


def tag_predictive_strength(stat, overall_top, max_score):
    reliability = stat.count / (stat.count + 8.0)
    top_signal = abs(stat.top_rate - overall_top)
    avg_signal = abs(stat.lift) / max_score if max_score else 0.0
    return reliability * (0.72 * top_signal + 0.28 * avg_signal)


def tag_insight_score(stat, overall_top, max_score):
    return tag_predictive_strength(stat, overall_top, max_score) * tag_semantic_weight(stat.name)


def tag_sections(all_tag_stats, overall, score_format):
    if not all_tag_stats:
        return "<section><h2>Tags</h2><p class='muted'>Not enough tag data.</p></section>"
    total_mentions = sum(s.count for s in all_tag_stats)
    overall_top = sum(s.top_rate * s.count for s in all_tag_stats) / total_mentions if total_mentions else 0.0
    insight_ranked = sorted(
        all_tag_stats,
        key=lambda s: (tag_insight_score(s, overall_top, score_format["max"]), s.count),
        reverse=True,
    )
    predictive_ranked = sorted(
        all_tag_stats,
        key=lambda s: (tag_predictive_strength(s, overall_top, score_format["max"]), s.count),
        reverse=True,
    )
    max_insight = max((tag_insight_score(s, overall_top, score_format["max"]) for s in insight_ranked), default=1.0) or 1.0
    max_predictive = max((tag_predictive_strength(s, overall_top, score_format["max"]) for s in predictive_ranked), default=1.0) or 1.0

    def rows(stats, mode):
        body = []
        for stat in stats:
            raw = tag_insight_score(stat, overall_top, score_format["max"]) if mode == "insight" else tag_predictive_strength(stat, overall_top, score_format["max"])
            denominator = max_insight if mode == "insight" else max_predictive
            score = 100 * raw / denominator
            top_lift = stat.top_rate - overall_top
            direction = "Positive" if (top_lift + stat.lift / score_format["max"]) > 0 else "Negative"
            cls = "positive" if direction == "Positive" else "negative"
            semantic = "Core" if tag_semantic_weight(stat.name) >= .9 else "Supporting" if tag_semantic_weight(stat.name) >= .5 else "Descriptive"
            body.append(
                f"<tr><td>{esc(stat.name)}</td><td>{score:.0f}</td><td>{semantic}</td><td>{stat.count}</td>"
                f"<td class='{cls}'>{direction}</td><td>{display_score(stat.average, score_format)}</td>"
                f"<td>{stat.top_rate:.0%}</td><td class='{cls}'>{top_lift:+.0%}</td></tr>"
            )
        return ''.join(body) or "<tr><td colspan='8' class='muted'>No tags in this range.</td></tr>"

    head = "<thead><tr><th>Tag</th><th>Insight</th><th>Role</th><th>Count</th><th>Direction</th><th>Average</th><th>Top-rate</th><th>Top-rate lift</th></tr></thead>"
    main = f"""<section><h2>Most informative tags</h2><p class='hint'>Ranks tags by both predictive strength and how much they describe the core viewing experience. Purely visual, geographic, demographic, or technical tags are down-weighted—not removed.</p><div class='table-wrap'><table>{head}<tbody>{rows(insight_ranked[:20], 'insight')}</tbody></table></div></section>"""
    predictive = f"""<details><summary>Strongest raw tag correlations ({len(predictive_ranked)})</summary><section><h2>Strongest raw tag correlations</h2><p class='hint'>This view ignores semantic usefulness, so incidental tags such as weather or scenery may rank highly when they happen to correlate with ratings.</p><div class='table-wrap'><table>{head}<tbody>{rows(predictive_ranked, 'predictive')}</tbody></table></div></section></details>"""
    return main + predictive


def show_table(title, rows, score_format, limit=20):
    body=[]
    for row in rows[:limit]:
        community=row.get("community_display")
        delta=(row["rating"]-community) if community is not None else None
        delta_text="—" if delta is None else f"{delta:+.{score_format['decimals']+1}f}"
        body.append(f"<tr><td><a href='{esc(row['url'])}'>{esc(row['title'])}</a></td><td>{display_score(row['rating'],score_format)}</td><td>{display_score(community,score_format)}</td><td>{delta_text}</td></tr>")
    return f"<section><h2>{esc(title)}</h2><div class='table-wrap'><table><thead><tr><th>Anime</th><th>Your rating</th><th>Community</th><th>Difference</th></tr></thead><tbody>{''.join(body)}</tbody></table></div></section>"


def community_consensus_table(title, rows, score_format, limit=15):
    body=[]
    for row in rows[:limit]:
        community=row.get("community_display")
        delta=(row["rating"]-community) if community is not None else None
        delta_text="—" if delta is None else f"{delta:+.{score_format['decimals']+1}f}"
        body.append(
            f"<tr><td class='consensus-title'><a href='{esc(row['url'])}'>{esc(row['title'])}</a></td>"
            f"<td>{display_score(row['rating'],score_format)}</td>"
            f"<td>{display_score(community,score_format)}</td>"
            f"<td>{delta_text}</td></tr>"
        )
    return (
        f"<section class='consensus-panel'><h2>{esc(title)}</h2>"
        f"<table class='consensus-table'><thead><tr><th>Anime</th><th>Your rating</th>"
        f"<th>Community</th><th>Difference</th></tr></thead><tbody>{''.join(body)}</tbody></table></section>"
    )


def community_consensus_section(positive, negative, score_format):
    return (
        "<details class='consensus-details'><summary>Community consensus comparisons</summary>"
        "<div class='consensus-stack'>"
        + community_consensus_table("Most above community consensus",positive,score_format,15)
        + community_consensus_table("Most below community consensus",negative,score_format,15)
        + "</div></details>"
    )

def rec_table(title, recs, score_format):
    if not recs: return ""
    body=[]
    for rec in recs:
        community=(rec.get("community")/100*score_format["max"]) if rec.get("community") else None
        reason = recommendation_reason(rec, title)
        body.append(f"<tr><td><a href='{esc(rec['url'])}'>{esc(rec['title'])}</a></td><td>{esc(rec.get('year') or '—')}</td><td>{display_score(community,score_format)}</td><td>{esc(reason)}</td></tr>")
    return f"<section class='rec-block'><h3>{esc(title)}</h3><div class='table-wrap'><table><thead><tr><th>Anime</th><th>Year</th><th>Community</th><th>Why</th></tr></thead><tbody>{''.join(body)}</tbody></table></div></section>"

def recommendations_section(groups, score_format):
    best = groups.get("Best matches") or []
    if not best and not any(groups.values()):
        return "<section><h2>Recommendations</h2><p class='muted'>AniList did not return enough recommendation data.</p></section>"
    main = rec_table("Best matches", best, score_format)
    extras=[]
    for name in ("Hidden gems", "Because you loved…", "Outside your comfort zone"):
        recs=groups.get(name) or []
        if recs:
            extras.append(f"<details class='rec-details'><summary>{esc(name)} ({len(recs)})</summary>{rec_table(name,recs,score_format)}</details>")
    return "<section><h2>Recommendations</h2><p class='hint'>Everything already present anywhere on this AniList is excluded. Best matches are shown first; alternate recommendation views are expandable.</p>"+main+''.join(extras)+"</section>"

def linked_stat_rows(stats, overall, score_format, limit=20, show_roles=False):
    overall_top=sum(s.top_rate*s.count for s in stats)/sum(s.count for s in stats) if stats else 0
    ranked=sorted(stats,key=lambda s:(adjusted_top_rate(s,overall_top),s.count),reverse=True)[:limit]
    body=[]
    for stat in ranked:
        name=f"<a href='{esc(getattr(stat,'url',''))}'>{esc(stat.name)}</a>" if getattr(stat,'url','') else esc(stat.name)
        top_lift=stat.top_rate-overall_top
        cls="positive" if top_lift>.03 else "negative" if top_lift<-.03 else "neutral"
        cells=(
            f"<td>{name}</td><td>{stat.count}</td>"
            f"<td>{display_score(stat.average,score_format)}</td>"
            f"<td>{stat.top_rate:.0%}</td><td class='{cls}'>{top_lift:+.0%}</td>"
        )
        body.append(f"<tr>{cells}</tr>")
    return ''.join(body) or "<tr><td colspan='5' class='muted'>Not enough recurring credits.</td></tr>"


def people_table(title, stats, overall, score_format, note, collapsible=False, show_roles=False):
    section=f"""<section><h2>{esc(title)}</h2><p class='hint'>{esc(note)}</p><div class='table-wrap'><table><thead><tr><th>Name</th><th>Anime</th><th>Average</th><th>Top-rate</th><th>Top-rate lift</th></tr></thead><tbody>{linked_stat_rows(stats,overall,score_format)}</tbody></table></div></section>"""
    return f"<details><summary>{esc(title)}</summary>{section}</details>" if collapsible else section


def _clean_role_label(role):
    character=(role.get("character") or "Unknown character").strip()
    note=(role.get("role_notes") or "").strip()
    if note and note.lower() not in character.lower():
        character=f"{character} — {note}"
    return character


def _consolidate_actor_appearances(stat):
    """Merge season-level appearances into one entry per franchise.

    Character names are deduplicated within each role group. Individual season
    titles remain available as a compact count/list, but never inflate the
    franchise count displayed for an actor.
    """
    franchises={}
    for appearance in getattr(stat,"appearances",[]):
        franchise_id=appearance.get("franchise_id")
        if franchise_id is None:
            franchise_id=appearance.get("anime_url") or appearance.get("anime")
        item=franchises.setdefault(franchise_id,{
            "id":franchise_id,
            "titles":[],
            "urls":[],
            "rating":appearance.get("franchise_rating",appearance.get("rating",stat.average)),
            "MAIN":set(),
            "SUPPORTING":set(),
            "BACKGROUND":set(),
            "UNKNOWN":set(),
        })
        title=appearance.get("anime") or "Unknown anime"
        url=appearance.get("anime_url") or ""
        if title not in item["titles"]:
            item["titles"].append(title)
            item["urls"].append(url)
        for role in appearance.get("roles") or []:
            prominence=(role.get("role") or "UNKNOWN").upper()
            if prominence not in item:
                prominence="UNKNOWN"
            item[prominence].add(_clean_role_label(role))

    def relevance(item):
        return (
            bool(item["MAIN"]),
            bool(item["SUPPORTING"]),
            item.get("rating") or 0,
            len(item["MAIN"])+len(item["SUPPORTING"])+len(item["BACKGROUND"]),
            (item["titles"][0] if item["titles"] else "").lower(),
        )
    return sorted(franchises.values(),key=relevance,reverse=True)


def _franchise_name(item):
    titles=item.get("titles") or ["Unknown anime"]
    first=titles[0]
    # Prefer the shortest connected title as the compact franchise label.
    base=min(titles,key=lambda value:(len(value),value.lower()))
    return base, len(titles)


def _role_lines(franchises, role_name, show_all=False, initial_limit=5):
    relevant=[item for item in franchises if item.get(role_name)]
    if not relevant:
        return ""

    def line(item):
        title, season_count=_franchise_name(item)
        urls=item.get("urls") or []
        url=next((value for value in urls if value),"")
        title_html=f"<a href='{esc(url)}'>{esc(title)}</a>" if url else esc(title)
        season_note=f" <span class='season-count'>({season_count} entries)</span>" if season_count>1 else ""
        characters=", ".join(esc(value) for value in sorted(item[role_name],key=str.lower))
        return f"<li><span class='va-characters'>{characters}</span><span class='va-anime'> — {title_html}{season_note}</span></li>"

    if show_all or len(relevant)<=initial_limit:
        return f"<ul class='va-role-list'>{''.join(line(item) for item in relevant)}</ul>"

    visible=relevant[:initial_limit]
    hidden=relevant[initial_limit:]
    return (
        f"<ul class='va-role-list'>{''.join(line(item) for item in visible)}</ul>"
        f"<details class='va-more'><summary>Show {len(hidden)} more</summary>"
        f"<ul class='va-role-list'>{''.join(line(item) for item in hidden)}</ul></details>"
    )


def _actor_card(stat, score_format, compact=False):
    franchises=_consolidate_actor_appearances(stat)
    main_count=sum(1 for item in franchises if item["MAIN"])
    supporting_count=sum(1 for item in franchises if item["SUPPORTING"])
    background_count=sum(1 for item in franchises if item["BACKGROUND"])

    actor_name=(
        f"<a href='{esc(getattr(stat,'url',''))}'>{esc(stat.name)}</a>"
        if getattr(stat,'url','') else esc(stat.name)
    )
    main_html=_role_lines(franchises,"MAIN",show_all=True)
    supporting_html=_role_lines(franchises,"SUPPORTING",show_all=False)
    background_html=_role_lines(franchises,"BACKGROUND",show_all=False)

    role_sections=[]
    if main_html:
        role_sections.append(f"<div class='va-role-section'><h4>Main roles <span>{main_count}</span></h4>{main_html}</div>")
    if supporting_html:
        role_sections.append(
            f"<details class='va-role-section'><summary>Supporting roles ({supporting_count})</summary>{supporting_html}</details>"
        )
    if background_html:
        role_sections.append(
            f"<details class='va-role-section'><summary>Background roles ({background_count})</summary>{background_html}</details>"
        )

    card_body=''.join(role_sections)
    if compact:
        card_body=(
            f"<details class='va-card-details'><summary>Show roles</summary>"
            f"{card_body}</details>"
        )

    return (
        "<article class='va-card'>"
        f"<div class='va-card-head'><div><h3>{actor_name}</h3>"
        f"<div class='hint'>{stat.count} distinct franchises · {main_count} Main</div></div>"
        f"<div class='va-score'><strong>{display_score(stat.average,score_format)}</strong>"
        f"<span>{stat.top_rate:.0%} top-rated</span></div></div>"
        f"{card_body}"
        "</article>"
    )


def voice_actor_section(title, stats, score_format, collapsible=False):
    ranked=sorted(
        stats,
        key=lambda stat:(
            sum(1 for item in _consolidate_actor_appearances(stat) if item["MAIN"]),
            stat.count,
            stat.top_rate,
            stat.average,
            stat.name.lower(),
        ),
        reverse=True,
    )
    if not ranked:
        content="<section><h2>{}</h2><p class='muted'>Not enough recurring credits.</p></section>".format(esc(title))
    else:
        featured=[]
        other=[]
        for stat in ranked:
            main_count=sum(1 for item in _consolidate_actor_appearances(stat) if item["MAIN"])
            (featured if main_count>=2 else other).append(stat)

        featured_html=''.join(_actor_card(stat,score_format) for stat in featured)
        if not featured_html:
            featured_html="<p class='muted'>No actors recur in two distinct Main-role franchises.</p>"

        other_html=""
        if other:
            cards=''.join(_actor_card(stat,score_format,compact=True) for stat in other)
            other_html=(
                f"<details class='va-other'><summary>Other recurring VAs ({len(other)})</summary>"
                "<p class='hint'>Actors with one or zero distinct Main-role franchises. Their full Supporting and Background credits remain available.</p>"
                f"<div class='va-grid va-grid-compact'>{cards}</div></details>"
            )

        content=(
            f"<section><h2>{esc(title)}</h2>"
            "<p class='hint'>Actors recurring as leads across at least two distinct franchises are shown first. One-off leads and actors known only from Supporting or Background roles are grouped below.</p>"
            f"<div class='va-grid'>{featured_html}</div>{other_html}</section>"
        )
    return f"<details><summary>{esc(title)}</summary>{content}</details>" if collapsible else content

def voice_actor_tables(japanese_stats, english_stats, overall, score_format):
    return (
        voice_actor_section("Japanese voice actors",japanese_stats,score_format,collapsible=True)
        + voice_actor_section("English voice actors",english_stats,score_format,collapsible=True)
    )

def build_html(user, rows, all_entries, output, score_format, overall, stats, identity, taste_glance, recommendation_groups, include_staff):
    ratings=[float(r["rating"]) for r in rows if r.get("rating") is not None]
    max_score=score_format["max"]
    top_count=sum(r>=max_score for r in ratings)
    dist=[]
    distribution=Counter(int(round(r)) for r in ratings)
    max_dist=max(distribution.values(),default=1)
    if score_format["format"] in {"POINT_3","POINT_5","POINT_10"}:
        for score in range(int(max_score),0,-1):
            count=distribution[score]; width=100*count/max_dist
            dist.append(f"<div class='dist-row'><span>{display_score(float(score),score_format,False)}</span><div class='bar'><i style='width:{width:.1f}%'></i></div><b>{count}</b></div>")
    else:
        bands=Counter(min(9,max(0,int((r/max_score)*10))) for r in ratings)
        max_band=max(bands.values(),default=1)
        for band in range(9,-1,-1):
            count=bands[band]; low=band*max_score/10; high=(band+1)*max_score/10
            dist.append(f"<div class='dist-row'><span>{low:.{score_format['decimals']}f}–{high:.{score_format['decimals']}f}</span><div class='bar'><i style='width:{100*count/max_band:.1f}%'></i></div><b>{count}</b></div>")

    divergences=[r for r in rows if r.get("community_display") is not None]
    positive=sorted(divergences,key=lambda r:r["rating"]-r["community_display"],reverse=True)
    negative=sorted(divergences,key=lambda r:r["rating"]-r["community_display"])
    top_rows=sorted([r for r in rows if r.get("rating")==max_score],key=lambda r:(r.get("popularity",0),r["title"]),reverse=True)
    low_rows=sorted(rows,key=lambda r:(r.get("rating") or 99,r["title"]))

    profile_html="".join(f"<p>{esc(p)}</p>" for p in identity)
    glance_signals="".join(
        f"<div class='glance-signal'><span>{esc(label)}</span><strong>{esc(value)}</strong></div>"
        for label,value in taste_glance.get("signals",[])
    )
    glance_html=(
        "<section class='taste-glance'><div class='eyebrow'>Taste at a glance</div>"
        f"<h2>{esc(taste_glance.get('headline',''))}</h2>"
        f"<p>{esc(taste_glance.get('summary',''))}</p>"
        f"<div class='glance-signals'>{glance_signals}</div></section>"
    )
    confidence=confidence_label(len(ratings))
    primary=group_table("Genres",stats["genres"],overall,score_format,20,True,False,"Ranked by adjusted top-rating rate.")
    primary+=tag_sections(stats["all_tags"],overall,score_format)
    people = ""
    if include_staff:
        people += people_table(
            "Creative staff",
            stats["staff"],
            overall,
            score_format,
            "Recurring directors, writers, composers, creators, and designers associated with higher-rated anime.",
        )
        people += voice_actor_tables(
            stats["japanese_vas"],
            stats["english_vas"],
            overall,
            score_format,
        )

    secondary=group_table("Studios",stats["studios"],overall,score_format,20,False,True)
    secondary+=group_table("Source material",stats["sources"],overall,score_format,20,False,True)
    secondary+=group_table("Formats",stats["formats"],overall,score_format,20,False,True)
    secondary+=group_table("Decades",stats["decades"],overall,score_format,20,False,True)


    all_rows=[]
    for row in sorted(rows,key=lambda r:(-(r.get("rating") or 0),r["title"].lower())):
        all_rows.append(f"<tr><td><a href='{esc(row['url'])}'>{esc(row['title'])}</a></td><td>{display_score(row.get('rating'),score_format)}</td><td>{esc(row['status'])}</td><td>{esc(row['format'])}</td><td>{esc(row.get('year') or '—')}</td><td>{esc(', '.join(row['genres']))}</td></tr>")

    html_doc=f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(user['name'])} — Anime Taste Report</title>
<style>
:root{{--bg:#0c111b;--panel:#151c29;--panel2:#1b2534;--text:#edf2f7;--muted:#9eacc0;--accent:#62d6e8;--line:#2b394c;--good:#70d49b;--bad:#ff8e8e}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}main{{max-width:1180px;margin:auto;padding:34px 20px 80px}}
.hero{{padding:28px;background:linear-gradient(135deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:18px}}h1{{margin:0 0 6px;font-size:clamp(28px,5vw,48px)}}h2{{margin:0 0 8px;font-size:24px}}h3{{margin:20px 0 8px;font-size:18px}}.muted,.hint{{color:var(--muted)}}.confidence{{font-size:12px;color:var(--muted);margin-top:4px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0 0}}.card{{background:rgba(0,0,0,.18);border:1px solid var(--line);border-radius:12px;padding:14px}}.card span{{display:block;color:var(--muted)}}.card strong{{font-size:25px}}
section{{margin-top:28px;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px}}.rec-block{{margin-top:16px;background:var(--panel2)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:18px}}.grid section{{margin-top:28px}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:680px}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}}.consensus-details{{margin-top:28px}}.consensus-stack{{display:grid;gap:18px;padding-top:14px}}.consensus-panel{{margin-top:0}}.consensus-table{{width:100%;min-width:0;table-layout:fixed}}.consensus-table th:first-child,.consensus-table td:first-child{{width:46%}}.consensus-table th:not(:first-child),.consensus-table td:not(:first-child){{width:18%;text-align:center}}.consensus-title{{overflow-wrap:anywhere;word-break:normal}}th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}}.positive{{color:var(--good)}}.negative{{color:var(--bad)}}.neutral{{color:var(--muted)}}
.dist-row{{display:grid;grid-template-columns:90px 1fr 40px;gap:10px;align-items:center;margin:10px 0}}.bar{{height:12px;background:#263346;border-radius:999px;overflow:hidden}}.bar i{{display:block;height:100%;background:var(--accent);border-radius:inherit}}
details{{margin-top:22px}}summary{{cursor:pointer;font-size:20px;font-weight:700;padding:14px 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px}}details[open] summary{{border-radius:12px 12px 0 0}}details>section{{margin-top:0;border-radius:0 0 16px 16px}}.rec-details{{margin-top:12px}}.rec-details summary{{font-size:16px;background:var(--panel2);padding:10px 14px}}.rec-details .rec-block{{border-radius:0 0 12px 12px;margin-top:0}}
.va-grid{{display:grid;gap:14px}}.va-card{{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:16px}}.va-card-head{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}}.va-card h3{{margin:0;font-size:20px}}.va-score{{text-align:right;white-space:nowrap}}.va-score strong,.va-score span{{display:block}}.va-score span,.season-count{{color:var(--muted);font-size:12px}}.va-role-section{{margin-top:14px}}.va-role-section h4{{margin:0 0 7px;font-size:15px}}.va-role-section h4 span{{color:var(--muted);font-weight:400}}.va-role-section>summary{{font-size:14px;padding:8px 10px;background:rgba(0,0,0,.14)}}.va-role-list{{margin:7px 0 0;padding-left:20px}}.va-role-list li{{margin:5px 0}}.va-characters{{font-weight:600}}.va-anime{{color:var(--muted)}}.va-more{{margin:8px 0 0 20px}}.va-more>summary{{display:inline-block;font-size:12px;padding:5px 9px;background:rgba(0,0,0,.16)}}.va-other{{margin-top:18px}}.va-other>summary{{font-size:17px;background:var(--panel2)}}.va-grid-compact{{margin-top:12px}}.va-card-details{{margin-top:10px}}.va-card-details>summary{{font-size:13px;padding:7px 10px;background:rgba(0,0,0,.14)}}.taste-glance{{background:linear-gradient(135deg,var(--panel2),var(--panel));border-color:rgba(98,214,232,.35)}}.taste-glance .eyebrow{{color:var(--accent);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.12em}}.taste-glance h2{{font-size:clamp(22px,4vw,34px);max-width:900px;margin-top:7px}}.taste-glance>p{{max-width:850px;font-size:16px}}.glance-signals{{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}}.glance-signal{{background:rgba(0,0,0,.18);border:1px solid var(--line);border-radius:10px;padding:9px 12px}}.glance-signal span,.glance-signal strong{{display:block}}.glance-signal span{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}footer{{margin-top:36px;color:var(--muted);font-size:13px}}@media(max-width:650px){{main{{padding:16px 10px 50px}}section,.hero{{padding:15px}}.consensus-table th,.consensus-table td{{padding:8px 5px;font-size:12px}}.consensus-table th:first-child,.consensus-table td:first-child{{width:40%}}.consensus-table th:not(:first-child),.consensus-table td:not(:first-child){{width:20%}}}}
</style></head><body><main>
<div class='hero'><div class='muted'>Unofficial AniList taste analysis</div><h1>{esc(user['name'])}</h1><div><a href='{esc(user.get('siteUrl',''))}'>Open AniList profile</a> · Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</div>
<div class='cards'><div class='card'><span>Rated anime</span><strong>{len(ratings)}</strong></div><div class='card'><span>Scoring system</span><strong>{esc(score_format['label'])}</strong></div><div class='card'><span>Average</span><strong>{display_score(overall,score_format)}</strong></div><div class='card'><span>Top ratings</span><strong>{top_count}</strong></div><div class='card'><span>Top-rating rate</span><strong>{top_count/len(ratings):.0%}</strong></div></div></div>
{glance_html}
<details class='taste-details'><summary>Detailed taste profile</summary><section><h2>Detailed taste profile</h2><div class='confidence'>Confidence: {confidence} · based on {len(ratings)} rated anime</div>{profile_html}</section></details>
{recommendations_section(recommendation_groups,score_format)}
<section><h2>Rating distribution</h2>{''.join(dist)}</section>
{community_consensus_section(positive,negative,score_format)}
{primary}{people}{show_table('Most popular top-rated picks',top_rows,score_format,20)}{show_table('Lowest-rated completed picks',low_rows,score_format,20)}
<h2 style='margin-top:34px'>More detail</h2>{secondary}
<details><summary>All analyzed anime ({len(rows)})</summary><section><div class='table-wrap'><table><thead><tr><th>Anime</th><th>Rating</th><th>List status</th><th>Format</th><th>Year</th><th>Genres</th></tr></thead><tbody>{''.join(all_rows)}</tbody></table></div></section></details>
<footer>Uses publicly available data from AniList's GraphQL API. Recommendations are heuristic, not guarantees. Correlation is not causation.</footer>
</main></body></html>"""
    output.write_text(html_doc,encoding="utf-8")
