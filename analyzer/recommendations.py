
from __future__ import annotations
import math
from .api import graphql, AnalyzerError
from .queries import RECOMMENDATION_QUERY

# Tags that usually describe presentation, geography, demographics, or a small
# surface detail rather than the core viewing experience. They remain visible
# in the tag tables, but are not used to justify recommendations.
LOW_EXPLANATION_VALUE = {
    "CGI", "Rotoscoping", "Achromatic", "Snowscape", "Desert", "Coastal",
    "Rural", "Urban", "Foreign", "Primarily Male Cast", "Primarily Female Cast",
    "Primarily Teen Cast", "Primarily Adult Cast", "Primarily Child Cast",
    "Male Protagonist", "Female Protagonist", "Heterosexual", "Bisexual",
    "Asexual", "Aromantic", "LGBTQ+ Themes", "Flat Chest", "Tanned Skin",
    "Nudity", "Male Nudity", "Female Nudity", "Feet", "Chibi",
}


def is_meaningful_tag(name: str) -> bool:
    return bool(name) and name not in LOW_EXPLANATION_VALUE


def fetch_recommendations(rated_rows, all_entries, max_score, tag_stats, genre_stats):
    seeds = sorted(
        rated_rows,
        key=lambda r: (r.get("rating") or 0, r.get("repeat") or 0, r.get("popularity") or 0),
        reverse=True,
    )
    seed_rows = [r for r in seeds if (r.get("rating") or 0) >= max_score][:18] or seeds[:12]
    seed_ids = [r["id"] for r in seed_rows]
    seed_lookup = {r["id"]: r for r in seed_rows}
    try:
        data = graphql(RECOMMENDATION_QUERY, {"ids": seed_ids})
    except AnalyzerError as exc:
        print(f"Recommendation fetch skipped: {exc}")
        return []

    existing_ids = {r["id"] for r in all_entries}
    tag_weight = {
        s.name: max(0.0, s.lift) + max(0.0, s.top_rate - .4)
        for s in tag_stats if s.count >= 5 and is_meaningful_tag(s.name)
    }
    genre_weight = {
        s.name: max(0.0, s.lift) + max(0.0, s.top_rate - .4)
        for s in genre_stats if s.count >= 5
    }

    candidates = {}
    for media in (data.get("Page") or {}).get("media") or []:
        seed_id = media.get("id")
        seed = seed_lookup.get(seed_id)
        if not seed:
            continue
        for node in ((media.get("recommendations") or {}).get("nodes") or []):
            rec = node.get("mediaRecommendation") or {}
            rec_id = rec.get("id")
            if not rec_id or rec_id in existing_ids:
                continue
            title_data = rec.get("title") or {}
            item = candidates.setdefault(rec_id, {
                "id": rec_id,
                "title": title_data.get("english") or title_data.get("userPreferred") or title_data.get("romaji") or str(rec_id),
                "url": rec.get("siteUrl") or f"https://anilist.co/anime/{rec_id}",
                "format": rec.get("format") or "Unknown",
                "year": rec.get("seasonYear"),
                "genres": rec.get("genres") or [],
                "tags": [
                    t["name"] for t in rec.get("tags") or []
                    if t.get("rank", 0) >= 20 and not t.get("isMediaSpoiler") and not t.get("isGeneralSpoiler")
                ],
                "community": rec.get("meanScore") or rec.get("averageScore"),
                "popularity": rec.get("popularity") or 0,
                "banner_image": rec.get("bannerImage") or "",
                "cover_image": (
                    (rec.get("coverImage") or {}).get("extraLarge")
                    or (rec.get("coverImage") or {}).get("large")
                    or ""
                ),
                "cover_color": (rec.get("coverImage") or {}).get("color") or "",
                "votes": 0,
                "sources": 0,
                "seed_evidence": [],
            })
            recommendation_rating = max(0, node.get("rating") or 0)
            item["votes"] += recommendation_rating
            item["sources"] += 1
            item["seed_evidence"].append({
                "title": seed["title"],
                "rating": seed.get("rating"),
                "repeat": seed.get("repeat") or 0,
                "recommendation_rating": recommendation_rating,
            })

    for item in candidates.values():
        meaningful_tags = [t for t in set(item["tags"]) if is_meaningful_tag(t)]
        tag_overlap = sum(tag_weight.get(t, 0) for t in meaningful_tags)
        genre_overlap = sum(genre_weight.get(g, 0) for g in set(item["genres"]))
        community = (item.get("community") or 0) / 100
        popularity_bonus = math.log10(max(10, item.get("popularity") or 10)) / 10
        item["match_score"] = (
            item["sources"] * 2.5
            + math.log1p(item["votes"])
            + tag_overlap * 2.2
            + genre_overlap
            + community
            + popularity_bonus
        )
        item["matched_tags"] = sorted(
            [t for t in meaningful_tags if tag_weight.get(t, 0) > 0],
            key=lambda t: tag_weight.get(t, 0),
            reverse=True,
        )[:3]
        item["matched_genres"] = sorted(
            [g for g in set(item["genres"]) if genre_weight.get(g, 0) > 0],
            key=lambda g: genre_weight.get(g, 0),
            reverse=True,
        )[:2]
        item["seed_evidence"] = sorted(
            item["seed_evidence"],
            key=lambda e: (e["recommendation_rating"], e["repeat"], e["rating"] or 0),
            reverse=True,
        )

    return sorted(candidates.values(), key=lambda x: (x["match_score"], x["popularity"]), reverse=True)


def recommendation_reason(rec: dict, category: str) -> str:
    evidence = rec.get("seed_evidence") or []
    strong_seeds = [e["title"] for e in evidence if e.get("recommendation_rating", 0) > 0][:3]
    tags = rec.get("matched_tags") or []
    genres = rec.get("matched_genres") or []

    if category == "Because you loved…" and strong_seeds:
        return f"Directly recommended from {strong_seeds[0]}."

    parts = []
    if len(strong_seeds) >= 2:
        parts.append(f"Recommended from {len(strong_seeds)} favorites, including {strong_seeds[0]} and {strong_seeds[1]}")
    elif strong_seeds:
        parts.append(f"Recommended from {strong_seeds[0]}")
    elif rec.get("sources", 0) >= 2:
        parts.append(f"Connected to {rec['sources']} top-rated entries")

    if tags:
        parts.append("meaningful overlap: " + ", ".join(tags))
    elif genres:
        parts.append("genre overlap: " + ", ".join(genres))

    if category == "Hidden gems":
        parts.append("lower-popularity pick")
    elif category == "Outside your comfort zone":
        parts.append("strong community reception with limited usual overlap")

    if not parts:
        return "Surfaced repeatedly through AniList recommendations from top-rated entries."
    return "; ".join(parts) + "."


def categorize_recommendations(recs):
    used = set()
    best = []
    for rec in recs:
        if rec["id"] not in used and len(best) < 8:
            best.append(rec); used.add(rec["id"])
    hidden = []
    for rec in sorted(recs, key=lambda x: (x["match_score"], -x["popularity"]), reverse=True):
        if rec["id"] not in used and rec.get("popularity", 0) < 100000 and len(hidden) < 6:
            hidden.append(rec); used.add(rec["id"])
    because = []
    for rec in recs:
        if rec["id"] not in used and rec.get("seed_evidence") and len(because) < 6:
            because.append(rec); used.add(rec["id"])
    outside = []
    for rec in sorted(recs, key=lambda x: (x.get("community") or 0, x["match_score"]), reverse=True):
        overlap = len(rec.get("matched_tags") or []) + len(rec.get("matched_genres") or [])
        if rec["id"] not in used and overlap <= 1 and len(outside) < 4:
            outside.append(rec); used.add(rec["id"])
    return {
        "Best matches": best,
        "Hidden gems": hidden,
        "Because you loved…": because,
        "Outside your comfort zone": outside,
    }
