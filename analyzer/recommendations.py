
from __future__ import annotations
import math
from .api import graphql, AnalyzerError
from .queries import RECOMMENDATION_QUERY

def fetch_recommendations(rated_rows, all_entries, max_score, tag_stats, genre_stats):
    seeds=sorted(rated_rows,key=lambda r:(r.get("rating") or 0,r.get("repeat") or 0,r.get("popularity") or 0),reverse=True)
    seed_rows=[r for r in seeds if (r.get("rating") or 0)>=max_score][:15] or seeds[:10]
    seed_ids=[r["id"] for r in seed_rows]
    seed_titles={r["id"]:r["title"] for r in seed_rows}
    try:
        data=graphql(RECOMMENDATION_QUERY,{"ids":seed_ids})
    except AnalyzerError as exc:
        print(f"Recommendation fetch skipped: {exc}")
        return []

    # Exclude every anime anywhere on the user's AniList, regardless of status or score.
    existing_ids={r["id"] for r in all_entries}
    tag_weight={s.name:max(0.0,s.lift)+max(0.0,s.top_rate-.4) for s in tag_stats if s.count>=5}
    genre_weight={s.name:max(0.0,s.lift)+max(0.0,s.top_rate-.4) for s in genre_stats if s.count>=5}

    candidates={}
    for media in (data.get("Page") or {}).get("media") or []:
        seed_id=media.get("id")
        seed_title=seed_titles.get(seed_id,"a favorite")
        for node in ((media.get("recommendations") or {}).get("nodes") or []):
            rec=node.get("mediaRecommendation") or {}
            rec_id=rec.get("id")
            if not rec_id or rec_id in existing_ids: continue
            title_data=rec.get("title") or {}
            item=candidates.setdefault(rec_id,{
                "id":rec_id,
                "title":title_data.get("english") or title_data.get("userPreferred") or title_data.get("romaji") or str(rec_id),
                "url":rec.get("siteUrl") or f"https://anilist.co/anime/{rec_id}",
                "format":rec.get("format") or "Unknown",
                "year":rec.get("seasonYear"),
                "genres":rec.get("genres") or [],
                "tags":[t["name"] for t in rec.get("tags") or [] if t.get("rank",0)>=20 and not t.get("isMediaSpoiler") and not t.get("isGeneralSpoiler")],
                "community":rec.get("meanScore") or rec.get("averageScore"),
                "popularity":rec.get("popularity") or 0,
                "votes":0,"sources":0,"seed_titles":set(),
            })
            item["votes"]+=max(0,node.get("rating") or 0)
            item["sources"]+=1
            item["seed_titles"].add(seed_title)

    for item in candidates.values():
        overlap=sum(tag_weight.get(t,0) for t in set(item["tags"]))+sum(genre_weight.get(g,0) for g in set(item["genres"]))
        community=(item.get("community") or 0)/100
        popularity_bonus=math.log10(max(10,item.get("popularity") or 10))/10
        item["match_score"]=item["sources"]*2.5+math.log1p(item["votes"])+overlap*2+community+popularity_bonus
        matched=sorted(set(item["tags"]),key=lambda t:tag_weight.get(t,0),reverse=True)
        item["reasons"]=[m for m in matched if tag_weight.get(m,0)>0][:3]
        if not item["reasons"]:
            item["reasons"]=sorted(set(item["genres"]),key=lambda g:genre_weight.get(g,0),reverse=True)[:2]
        item["seed_titles"]=sorted(item["seed_titles"])

    return sorted(candidates.values(),key=lambda x:(x["match_score"],x["popularity"]),reverse=True)

def categorize_recommendations(recs):
    used=set()
    best=[]
    for r in recs:
        if r["id"] not in used and len(best)<8:
            best.append(r); used.add(r["id"])
    hidden=[]
    for r in sorted(recs,key=lambda x:(x["match_score"],-x["popularity"]),reverse=True):
        if r["id"] not in used and r.get("popularity",0)<100000 and len(hidden)<6:
            hidden.append(r); used.add(r["id"])
    because=[]
    for r in recs:
        if r["id"] not in used and r.get("seed_titles") and len(because)<6:
            because.append(r); used.add(r["id"])
    outside=[]
    for r in sorted(recs,key=lambda x:(x.get("community") or 0,x["match_score"]),reverse=True):
        overlap=len(r.get("reasons") or [])
        if r["id"] not in used and overlap<=1 and len(outside)<4:
            outside.append(r); used.add(r["id"])
    return {"Best matches":best,"Hidden gems":hidden,"Because you loved…":because,"Outside your comfort zone":outside}
