
from __future__ import annotations
import re, statistics
from collections import Counter
from datetime import datetime
from .util import esc, display_score
from .data import confidence_adjusted, adjusted_top_rate
from .profile import confidence_label

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

def tag_sections(all_tag_stats, overall, score_format):
    high=[s for s in all_tag_stats if s.count>=10]
    medium=[s for s in all_tag_stats if 5<=s.count<=9]
    low=[s for s in all_tag_stats if 2<=s.count<=4]
    main=group_table("Top predictive tags",high,overall,score_format,20,True,False,
                     "High-confidence tags only: at least 10 appearances. Rarer tags remain available below.")
    medium_html=group_table("Medium-confidence tags",medium,overall,score_format,30,True,True,
                            "These appeared 5–9 times. Useful signals, but more vulnerable to small-sample noise.")
    low_html=group_table("Low-confidence tags",low,overall,score_format,40,True,True,
                         "These appeared 2–4 times. Treat them as curiosities rather than conclusions.")
    return main+medium_html+low_html

def show_table(title, rows, score_format, limit=20):
    body=[]
    for row in rows[:limit]:
        community=row.get("community_display")
        delta=(row["rating"]-community) if community is not None else None
        delta_text="—" if delta is None else f"{delta:+.{score_format['decimals']+1}f}"
        body.append(f"<tr><td><a href='{esc(row['url'])}'>{esc(row['title'])}</a></td><td>{display_score(row['rating'],score_format)}</td><td>{display_score(community,score_format)}</td><td>{delta_text}</td></tr>")
    return f"<section><h2>{esc(title)}</h2><div class='table-wrap'><table><thead><tr><th>Anime</th><th>Your rating</th><th>Community</th><th>Difference</th></tr></thead><tbody>{''.join(body)}</tbody></table></div></section>"

def rec_table(title, recs, score_format):
    if not recs: return ""
    body=[]
    for rec in recs:
        community=(rec.get("community")/100*score_format["max"]) if rec.get("community") else None
        if title=="Because you loved…":
            seed=(rec.get("seed_titles") or ["a favorite"])[0]
            reason=f"Because you loved {seed}"
        elif title=="Hidden gems":
            reason="Lower-popularity match"
        elif title=="Outside your comfort zone":
            reason="Strong community reception despite weaker profile overlap"
        else:
            reason=", ".join(rec.get("reasons") or []) or "recommended from multiple favorites"
        body.append(f"<tr><td><a href='{esc(rec['url'])}'>{esc(rec['title'])}</a></td><td>{esc(rec.get('year') or '—')}</td><td>{display_score(community,score_format)}</td><td>{esc(reason)}</td></tr>")
    return f"<section class='rec-block'><h3>{esc(title)}</h3><div class='table-wrap'><table><thead><tr><th>Anime</th><th>Year</th><th>Community</th><th>Why</th></tr></thead><tbody>{''.join(body)}</tbody></table></div></section>"

def recommendations_section(groups, score_format):
    chunks=[rec_table(name,recs,score_format) for name,recs in groups.items() if recs]
    if not chunks:
        return "<section><h2>Recommendations</h2><p class='muted'>AniList did not return enough recommendation data.</p></section>"
    return "<section><h2>Recommendations</h2><p class='hint'>Everything already present anywhere on this AniList is excluded.</p>"+"".join(chunks)+"</section>"

def build_html(user, rows, all_entries, output, score_format, overall, stats, identity, recommendation_groups, include_staff):
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
    confidence=confidence_label(len(ratings))
    primary=group_table("Genres",stats["genres"],overall,score_format,20,True,False,"Ranked by adjusted top-rating rate.")
    primary+=tag_sections(stats["all_tags"],overall,score_format)
    secondary=group_table("Studios",stats["studios"],overall,score_format,20,False,True)
    secondary+=group_table("Source material",stats["sources"],overall,score_format,20,False,True)
    secondary+=group_table("Formats",stats["formats"],overall,score_format,20,False,True)
    secondary+=group_table("Decades",stats["decades"],overall,score_format,20,False,True)
    if include_staff:
        secondary+=group_table("Recurring creative staff",stats["staff"],overall,score_format,20,False,True)

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
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:680px}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}}.positive{{color:var(--good)}}.negative{{color:var(--bad)}}.neutral{{color:var(--muted)}}
.dist-row{{display:grid;grid-template-columns:90px 1fr 40px;gap:10px;align-items:center;margin:10px 0}}.bar{{height:12px;background:#263346;border-radius:999px;overflow:hidden}}.bar i{{display:block;height:100%;background:var(--accent);border-radius:inherit}}
details{{margin-top:22px}}summary{{cursor:pointer;font-size:20px;font-weight:700;padding:14px 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px}}details[open] summary{{border-radius:12px 12px 0 0}}details>section{{margin-top:0;border-radius:0 0 16px 16px}}
footer{{margin-top:36px;color:var(--muted);font-size:13px}}@media(max-width:650px){{main{{padding:16px 10px 50px}}section,.hero{{padding:15px}}}}
</style></head><body><main>
<div class='hero'><div class='muted'>Unofficial AniList taste analysis</div><h1>{esc(user['name'])}</h1><div><a href='{esc(user.get('siteUrl',''))}'>Open AniList profile</a> · Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</div>
<div class='cards'><div class='card'><span>Rated anime</span><strong>{len(ratings)}</strong></div><div class='card'><span>Scoring system</span><strong>{esc(score_format['label'])}</strong></div><div class='card'><span>Average</span><strong>{display_score(overall,score_format)}</strong></div><div class='card'><span>Top ratings</span><strong>{top_count}</strong></div><div class='card'><span>Top-rating rate</span><strong>{top_count/len(ratings):.0%}</strong></div></div></div>
<section><h2>Taste profile</h2><div class='confidence'>Confidence: {confidence} · based on {len(ratings)} rated anime</div>{profile_html}</section>
{recommendations_section(recommendation_groups,score_format)}
<section><h2>Rating distribution</h2>{''.join(dist)}</section>
<div class='grid'>{show_table('Most above community consensus',positive,score_format,15)}{show_table('Most below community consensus',negative,score_format,15)}</div>
{primary}{show_table('Most popular top-rated picks',top_rows,score_format,20)}{show_table('Lowest-rated completed picks',low_rows,score_format,20)}
<h2 style='margin-top:34px'>More detail</h2>{secondary}
<details><summary>All analyzed anime ({len(rows)})</summary><section><div class='table-wrap'><table><thead><tr><th>Anime</th><th>Rating</th><th>List status</th><th>Format</th><th>Year</th><th>Genres</th></tr></thead><tbody>{''.join(all_rows)}</tbody></table></div></section></details>
<footer>Uses publicly available data from AniList's GraphQL API. Recommendations are heuristic, not guarantees. Correlation is not causation.</footer>
</main></body></html>"""
    output.write_text(html_doc,encoding="utf-8")
