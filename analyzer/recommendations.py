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


def _strong_rating_base(rows) -> bool:
    rated_count = sum(1 for row in rows if row.get("rating") is not None)
    coverage = rated_count / len(rows) if rows else 0.0
    return rated_count >= 10 and coverage >= .35


def _fetch_recommendations_rated(rated_rows, all_entries, max_score, tag_stats, genre_stats):
    """Established recommendation behavior for well-rated lists."""
    seeds = sorted(
        rated_rows,
        key=lambda row: (
            row.get("rating") or 0,
            row.get("repeat") or 0,
            row.get("popularity") or 0,
        ),
        reverse=True,
    )
    seed_rows = [row for row in seeds if (row.get("rating") or 0) >= max_score][:18] or seeds[:12]
    if not seed_rows:
        return []

    seed_ids = [row["id"] for row in seed_rows]
    seed_lookup = {row["id"]: row for row in seed_rows}
    try:
        data = graphql(RECOMMENDATION_QUERY, {"ids": seed_ids})
    except AnalyzerError as exc:
        print(f"Recommendation fetch skipped: {exc}")
        return []

    existing_ids = {row["id"] for row in all_entries}
    tag_weight = {
        stat.name: max(0.0, stat.lift) + max(0.0, stat.top_rate - .4)
        for stat in tag_stats
        if stat.count >= 5
        and stat.lift is not None
        and stat.top_rate is not None
        and is_meaningful_tag(stat.name)
    }
    genre_weight = {
        stat.name: max(0.0, stat.lift) + max(0.0, stat.top_rate - .4)
        for stat in genre_stats
        if stat.count >= 5 and stat.lift is not None and stat.top_rate is not None
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
                    tag["name"] for tag in rec.get("tags") or []
                    if tag.get("rank", 0) >= 20
                    and not tag.get("isMediaSpoiler")
                    and not tag.get("isGeneralSpoiler")
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
                "history_mode": False,
            })
            recommendation_rating = max(0, node.get("rating") or 0)
            item["votes"] += recommendation_rating
            item["sources"] += 1
            item["seed_evidence"].append({
                "title": seed["title"],
                "rating": seed.get("rating"),
                "rated": True,
                "repeat": seed.get("repeat") or 0,
                "recommendation_rating": recommendation_rating,
            })

    for item in candidates.values():
        meaningful_tags = [tag for tag in set(item["tags"]) if is_meaningful_tag(tag)]
        tag_overlap = sum(tag_weight.get(tag, 0) for tag in meaningful_tags)
        genre_overlap = sum(genre_weight.get(genre, 0) for genre in set(item["genres"]))
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
            [tag for tag in meaningful_tags if tag_weight.get(tag, 0) > 0],
            key=lambda tag: tag_weight.get(tag, 0),
            reverse=True,
        )[:3]
        item["matched_genres"] = sorted(
            [genre for genre in set(item["genres"]) if genre_weight.get(genre, 0) > 0],
            key=lambda genre: genre_weight.get(genre, 0),
            reverse=True,
        )[:2]
        item["seed_evidence"] = sorted(
            item["seed_evidence"],
            key=lambda evidence: (
                evidence["recommendation_rating"],
                evidence["repeat"],
                evidence["rating"] or 0,
            ),
            reverse=True,
        )

    return sorted(
        candidates.values(),
        key=lambda item: (item["match_score"], item["popularity"]),
        reverse=True,
    )


def _fetch_recommendations_sparse(view_rows, all_entries, max_score, tag_stats, genre_stats):
    """Use full viewing history when ratings are too sparse to stand alone."""
    rated_rows = [row for row in view_rows if row.get("rating") is not None]
    coverage = len(rated_rows) / len(view_rows) if view_rows else 0.0
    rating_weight = (
        min(1.0, len(rated_rows) / 20.0) * min(1.0, coverage / .50)
        if view_rows else 0.0
    )

    rated_candidates = sorted(
        [row for row in rated_rows if (row.get("rating") or 0) >= max_score * .70],
        key=lambda row: (
            row.get("rating") or 0,
            row.get("repeat") or 0,
            row.get("favourites") or 0,
            row.get("popularity") or 0,
        ),
        reverse=True,
    )
    history_candidates = sorted(
        [
            row for row in view_rows
            if row.get("rating") is None or (row.get("rating") or 0) >= max_score * .70
        ],
        key=lambda row: (
            row.get("repeat") or 0,
            row.get("rating") is not None,
            row.get("rating") or 0,
            row.get("favourites") or 0,
            row.get("community_score") or 0,
            row.get("popularity") or 0,
        ),
        reverse=True,
    )

    target = min(18, len(view_rows))
    rated_target = min(len(rated_candidates), max(4, target // 2))
    seed_rows = []
    seen_seed_ids = set()

    def add_seed(row):
        if row["id"] not in seen_seed_ids and len(seed_rows) < target:
            seed_rows.append(row)
            seen_seed_ids.add(row["id"])

    for row in rated_candidates[:rated_target]:
        add_seed(row)
    for row in history_candidates:
        add_seed(row)
    for row in sorted(view_rows, key=lambda item: item.get("popularity") or 0, reverse=True):
        add_seed(row)

    if not seed_rows:
        return []

    seed_ids = [row["id"] for row in seed_rows]
    seed_lookup = {row["id"]: row for row in seed_rows}
    try:
        data = graphql(RECOMMENDATION_QUERY, {"ids": seed_ids})
    except AnalyzerError as exc:
        print(f"Recommendation fetch skipped: {exc}")
        return []

    existing_ids = {row["id"] for row in all_entries}
    max_tag_count = max((stat.count for stat in tag_stats), default=1)
    max_genre_count = max((stat.count for stat in genre_stats), default=1)

    def pattern_weight(stat, max_count):
        frequency = stat.count / max_count if max_count else 0.0
        rating_signal = 0.0
        if (
            stat.lift is not None
            and stat.top_rate is not None
            and getattr(stat, "rated_count", 0) >= 2
        ):
            rating_signal = (
                max(0.0, stat.lift / max_score)
                + max(0.0, stat.top_rate - .40)
            )
        return frequency * (1.0 - .45 * rating_weight) + rating_signal * rating_weight

    tag_weight = {
        stat.name: pattern_weight(stat, max_tag_count)
        for stat in tag_stats
        if stat.count >= 5 and is_meaningful_tag(stat.name)
    }
    genre_weight = {
        stat.name: pattern_weight(stat, max_genre_count)
        for stat in genre_stats
        if stat.count >= 5
    }

    candidates = {}
    for media in (data.get("Page") or {}).get("media") or []:
        seed_id = media.get("id")
        seed = seed_lookup.get(seed_id)
        if not seed:
            continue
        seed_rating = seed.get("rating")
        seed_strength = (
            .75 if seed_rating is None
            else .75 + .75 * max(0.0, min(1.0, seed_rating / max_score))
        )

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
                    tag["name"] for tag in rec.get("tags") or []
                    if tag.get("rank", 0) >= 20
                    and not tag.get("isMediaSpoiler")
                    and not tag.get("isGeneralSpoiler")
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
                "votes": 0.0,
                "sources": 0,
                "seed_strength": 0.0,
                "seed_evidence": [],
                "history_mode": True,
            })
            recommendation_rating = max(0, node.get("rating") or 0)
            item["votes"] += recommendation_rating * seed_strength
            item["sources"] += 1
            item["seed_strength"] += seed_strength
            item["seed_evidence"].append({
                "title": seed["title"],
                "rating": seed_rating,
                "rated": seed_rating is not None,
                "repeat": seed.get("repeat") or 0,
                "recommendation_rating": recommendation_rating,
            })

    for item in candidates.values():
        meaningful_tags = [tag for tag in set(item["tags"]) if is_meaningful_tag(tag)]
        tag_overlap = sum(tag_weight.get(tag, 0) for tag in meaningful_tags)
        genre_overlap = sum(genre_weight.get(genre, 0) for genre in set(item["genres"]))
        community = (item.get("community") or 0) / 100
        popularity_bonus = math.log10(max(10, item.get("popularity") or 10)) / 10
        item["match_score"] = (
            item["seed_strength"] * 2.1
            + math.log1p(item["votes"])
            + tag_overlap * 2.2
            + genre_overlap
            + community
            + popularity_bonus
        )
        item["matched_tags"] = sorted(
            [tag for tag in meaningful_tags if tag_weight.get(tag, 0) > 0],
            key=lambda tag: tag_weight.get(tag, 0),
            reverse=True,
        )[:3]
        item["matched_genres"] = sorted(
            [genre for genre in set(item["genres"]) if genre_weight.get(genre, 0) > 0],
            key=lambda genre: genre_weight.get(genre, 0),
            reverse=True,
        )[:2]
        item["seed_evidence"] = sorted(
            item["seed_evidence"],
            key=lambda evidence: (
                evidence["rated"],
                evidence["rating"] or 0,
                evidence["recommendation_rating"],
                evidence["repeat"],
            ),
            reverse=True,
        )

    return sorted(
        candidates.values(),
        key=lambda item: (item["match_score"], item["popularity"]),
        reverse=True,
    )


def fetch_recommendations(view_rows, all_entries, max_score, tag_stats, genre_stats):
    rated_rows = [row for row in view_rows if row.get("rating") is not None]
    if _strong_rating_base(view_rows):
        return _fetch_recommendations_rated(
            rated_rows,
            all_entries,
            max_score,
            tag_stats,
            genre_stats,
        )
    return _fetch_recommendations_sparse(
        view_rows,
        all_entries,
        max_score,
        tag_stats,
        genre_stats,
    )


def recommendation_reason(rec: dict, category: str) -> str:
    evidence = rec.get("seed_evidence") or []
    strong_seeds = [
        item["title"] for item in evidence
        if item.get("recommendation_rating", 0) > 0
    ][:3]
    rated_seeds = [
        item["title"] for item in evidence
        if item.get("rated", item.get("rating") is not None)
        and item.get("recommendation_rating", 0) > 0
    ][:3]
    tags = rec.get("matched_tags") or []
    genres = rec.get("matched_genres") or []

    if category == "Because you loved…" and rated_seeds:
        return f"Directly recommended from {rated_seeds[0]}."
    if category == "From your viewing history" and strong_seeds:
        return f"Recommended from {strong_seeds[0]} in the viewing history."

    parts = []
    if len(strong_seeds) >= 2:
        noun = "favorites" if not rec.get("history_mode") else "watched entries"
        parts.append(
            f"Recommended from {len(strong_seeds)} {noun}, including {strong_seeds[0]} and {strong_seeds[1]}"
        )
    elif strong_seeds:
        parts.append(f"Recommended from {strong_seeds[0]}")
    elif rec.get("sources", 0) >= 2:
        source_label = "viewed entries" if rec.get("history_mode") else "top-rated entries"
        parts.append(f"Connected to {rec['sources']} {source_label}")

    if tags:
        parts.append("meaningful overlap: " + ", ".join(tags))
    elif genres:
        parts.append("genre overlap: " + ", ".join(genres))

    if category == "Hidden gems":
        parts.append("lower-popularity pick")
    elif category == "Outside your comfort zone":
        parts.append("strong community reception with limited usual overlap")

    if not parts:
        return (
            "Surfaced repeatedly through AniList recommendations from the viewing history."
            if rec.get("history_mode")
            else "Surfaced repeatedly through AniList recommendations from top-rated entries."
        )
    return "; ".join(parts) + "."


def categorize_recommendations(recs):
    used = set()
    best = []
    for rec in recs:
        if rec["id"] not in used and len(best) < 8:
            best.append(rec)
            used.add(rec["id"])

    hidden = []
    for rec in sorted(
        recs,
        key=lambda item: (item["match_score"], -item["popularity"]),
        reverse=True,
    ):
        if (
            rec["id"] not in used
            and rec.get("popularity", 0) < 100000
            and len(hidden) < 6
        ):
            hidden.append(rec)
            used.add(rec["id"])

    evidence_group = []
    for rec in recs:
        if rec["id"] not in used and rec.get("seed_evidence") and len(evidence_group) < 6:
            evidence_group.append(rec)
            used.add(rec["id"])

    outside = []
    for rec in sorted(
        recs,
        key=lambda item: (item.get("community") or 0, item["match_score"]),
        reverse=True,
    ):
        overlap = len(rec.get("matched_tags") or []) + len(rec.get("matched_genres") or [])
        if rec["id"] not in used and overlap <= 1 and len(outside) < 4:
            outside.append(rec)
            used.add(rec["id"])

    history_mode = any(rec.get("history_mode") for rec in recs)
    return {
        "Best matches": best,
        "Hidden gems": hidden,
        "Because you loved…": [] if history_mode else evidence_group,
        "From your viewing history": evidence_group if history_mode else [],
        "Outside your comfort zone": outside,
    }
