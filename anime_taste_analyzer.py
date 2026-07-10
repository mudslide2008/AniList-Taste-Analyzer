#!/usr/bin/env python3
"""Unofficial AniList Taste Analyzer.

Fetches a public AniList anime list, analyzes ratings against AniList metadata,
and writes a self-contained HTML report plus CSV/JSON exports.

No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

API_URL = "https://graphql.anilist.co"
USER_AGENT = "Unofficial-AniList-Taste-Analyzer/1.2"
DEFAULT_STATUSES = ("COMPLETED",)
VALID_STATUSES = {
    "CURRENT", "PLANNING", "COMPLETED", "DROPPED", "PAUSED", "REPEATING"
}

LIST_QUERY = r"""
query ($userName: String!) {
  User(name: $userName) {
    id
    name
    siteUrl
    mediaListOptions { scoreFormat }
  }
  MediaListCollection(userName: $userName, type: ANIME) {
    lists {
      name
      isCustomList
      status
      entries {
        id
        status
        progress
        repeat
        scoreOriginal: score
        score3: score(format: POINT_3)
        score5: score(format: POINT_5)
        score10: score(format: POINT_10)
        score10Decimal: score(format: POINT_10_DECIMAL)
        score100: score(format: POINT_100)
        startedAt { year month day }
        completedAt { year month day }
        updatedAt
        media {
          id
          title { userPreferred romaji english native }
          format
          status
          episodes
          duration
          season
          seasonYear
          source
          genres
          meanScore
          averageScore
          popularity
          favourites
          siteUrl
          tags {
            name
            category
            rank
            isMediaSpoiler
            isGeneralSpoiler
          }
          studios(isMain: true) {
            nodes { id name siteUrl }
          }
        }
      }
    }
  }
}
"""

RECOMMENDATION_QUERY = r"""
query ($ids: [Int]) {
  Page(page: 1, perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      recommendations(perPage: 25, sort: RATING_DESC) {
        nodes {
          rating
          mediaRecommendation {
            id
            title { userPreferred romaji english }
            format
            seasonYear
            genres
            meanScore
            averageScore
            popularity
            siteUrl
            tags { name rank isMediaSpoiler isGeneralSpoiler }
          }
        }
      }
    }
  }
}
"""

STAFF_QUERY = r"""
query ($ids: [Int], $page: Int) {
  Page(page: $page, perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      staff(perPage: 25, sort: RELEVANCE) {
        edges {
          role
          node {
            id
            name { full }
            siteUrl
          }
        }
      }
    }
  }
}
"""


class AnalyzerError(RuntimeError):
    pass


def graphql(query: str, variables: dict[str, Any], retries: int = 4) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            API_URL,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
                if result.get("errors"):
                    messages = "; ".join(e.get("message", "Unknown GraphQL error") for e in result["errors"])
                    raise AnalyzerError(messages)
                return result["data"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < retries:
                wait = int(exc.headers.get("Retry-After", "10"))
                print(f"AniList rate limit reached; retrying in {wait} seconds...")
                time.sleep(wait)
                continue
            if exc.code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise AnalyzerError(f"AniList returned HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise AnalyzerError(f"Could not connect to AniList: {exc.reason}") from exc
    raise AnalyzerError("AniList request failed after retries.")


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

def flatten_entries(collection: dict[str, Any]) -> list[dict[str, Any]]:
    """Deduplicate entries hidden in both status and custom lists."""
    by_media: dict[int, dict[str, Any]] = {}
    for list_group in collection.get("lists") or []:
        for entry in list_group.get("entries") or []:
            media = entry.get("media") or {}
            media_id = media.get("id")
            if not media_id:
                continue
            previous = by_media.get(media_id)
            # Prefer the copy with a populated status/score.
            if previous is None or (entry.get("scoreOriginal") and not previous.get("scoreOriginal")):
                by_media[media_id] = entry
    return list(by_media.values())


def get_staff(media_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for batch_number, batch in enumerate(chunks(media_ids, 50), start=1):
        print(f"Fetching staff metadata batch {batch_number}/{math.ceil(len(media_ids)/50)}...")
        data = graphql(STAFF_QUERY, {"ids": batch, "page": 1})
        for media in data.get("Page", {}).get("media") or []:
            result[media["id"]] = (media.get("staff") or {}).get("edges") or []
        time.sleep(0.4)
    return result


def normalize_entries(entries: list[dict[str, Any]], statuses: set[str], include_unrated: bool,
                      include_spoiler_tags: bool, fetch_staff_data: bool,
                      score_format: dict[str, Any]) -> list[dict[str, Any]]:
    selected = []
    for entry in entries:
        if entry.get("status") not in statuses:
            continue
        score_key = {
            "POINT_3": "score3",
            "POINT_5": "score5",
            "POINT_10": "score10",
            "POINT_10_DECIMAL": "score10Decimal",
            "POINT_100": "score100",
        }.get(score_format["format"], "scoreOriginal")
        rating = entry.get(score_key) or 0
        rating100 = entry.get("score100") or 0
        if not include_unrated and rating <= 0:
            continue
        media = entry["media"]
        title_data = media.get("title") or {}
        title = title_data.get("english") or title_data.get("userPreferred") or title_data.get("romaji") or str(media["id"])
        tags = []
        for tag in media.get("tags") or []:
            if tag.get("rank", 0) < 20:
                continue
            if not include_spoiler_tags and (tag.get("isMediaSpoiler") or tag.get("isGeneralSpoiler")):
                continue
            tags.append(tag["name"])
        studios = [s["name"] for s in ((media.get("studios") or {}).get("nodes") or [])]
        community = media.get("meanScore") or media.get("averageScore")
        selected.append({
            "id": media["id"],
            "title": title,
            "romaji": title_data.get("romaji") or "",
            "rating": float(rating) if rating else None,
            "rating100": float(rating100) if rating100 else None,
            "score_format": score_format["format"],
            "status": entry.get("status") or "",
            "progress": entry.get("progress") or 0,
            "repeat": entry.get("repeat") or 0,
            "started": fuzzy_date(entry.get("startedAt")),
            "completed": fuzzy_date(entry.get("completedAt")),
            "format": media.get("format") or "Unknown",
            "episodes": media.get("episodes"),
            "duration": media.get("duration"),
            "season": media.get("season") or "",
            "year": media.get("seasonYear"),
            "decade": f"{(media['seasonYear']//10)*10}s" if media.get("seasonYear") else "Unknown",
            "source": media.get("source") or "Unknown",
            "genres": media.get("genres") or [],
            "tags": tags,
            "studios": studios or ["Unknown"],
            "community_score": community,
            "community_normalized": float(community) if community else None,
            "community_display": (float(community) / 100.0 * score_format["max"]) if community else None,
            "popularity": media.get("popularity") or 0,
            "favourites": media.get("favourites") or 0,
            "url": media.get("siteUrl") or f"https://anilist.co/anime/{media['id']}",
            "staff": [],
        })

    if fetch_staff_data and selected:
        staff_map = get_staff([row["id"] for row in selected])
        for row in selected:
            credits = []
            for edge in staff_map.get(row["id"], []):
                role = edge.get("role") or ""
                node = edge.get("node") or {}
                name = (node.get("name") or {}).get("full")
                # Roles most useful for creative-pattern analysis.
                if name and any(key in role.lower() for key in (
                    "director", "series composition", "script", "screenplay",
                    "original creator", "music", "character design"
                )):
                    credits.append({"name": name, "role": role, "url": node.get("siteUrl") or ""})
            row["staff"] = credits
    return selected


@dataclass
class GroupStat:
    name: str
    count: int
    average: float
    lift: float
    top_rate: float
    ratings: list[float]


def group_stats(rows: list[dict[str, Any]], field: str, overall: float, min_count: int, max_score: float) -> list[GroupStat]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        rating = row.get("rating")
        if rating is None:
            continue
        values = row.get(field, [])
        if not isinstance(values, list):
            values = [values]
        for value in set(v for v in values if v):
            grouped[str(value)].append(float(rating))
    stats = []
    for name, ratings in grouped.items():
        if len(ratings) < min_count:
            continue
        avg = statistics.fmean(ratings)
        stats.append(GroupStat(name, len(ratings), avg, avg - overall,
                               sum(r >= max_score for r in ratings) / len(ratings), ratings))
    return sorted(stats, key=lambda x: (x.average, x.count), reverse=True)


def staff_stats(rows: list[dict[str, Any]], overall: float, min_count: int, max_score: float) -> list[GroupStat]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        rating = row.get("rating")
        if rating is None:
            continue
        seen = set()
        for credit in row.get("staff", []):
            key = f"{credit['name']} — {credit['role']}"
            if key not in seen:
                grouped[key].append(float(rating))
                seen.add(key)
    result = []
    for name, ratings in grouped.items():
        if len(ratings) >= min_count:
            avg = statistics.fmean(ratings)
            result.append(GroupStat(name, len(ratings), avg, avg - overall,
                                    sum(r >= max_score for r in ratings) / len(ratings), ratings))
    return sorted(result, key=lambda x: (x.average, x.count), reverse=True)


def stars(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = max(0, min(5, int(round(value))))
    return "★" * rounded + "☆" * (5 - rounded)


def fmt(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def confidence_adjusted(stat: GroupStat, overall: float, prior_weight: float = 5.0) -> float:
    """Bayesian shrinkage avoids tiny groups dominating rankings."""
    return (stat.count * stat.average + prior_weight * overall) / (stat.count + prior_weight)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "id", "title", "romaji", "rating", "rating100", "score_format", "status", "format", "episodes", "duration",
        "year", "source", "genres", "tags", "studios", "community_score", "popularity",
        "started", "completed", "repeat", "url"
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (-(r.get("rating") or 0), r["title"].lower())):
            export = {key: row.get(key, "") for key in fields}
            for key in ("genres", "tags", "studios"):
                export[key] = " | ".join(export[key])
            writer.writerow(export)


def write_json(user: dict[str, Any], rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"generated_at": datetime.now().isoformat(), "user": user, "anime": rows},
                  handle, ensure_ascii=False, indent=2)


def esc(value: Any) -> str:
    return html.escape(str(value))



def adjusted_top_rate(stat: GroupStat, overall_top_rate: float, prior_weight: float = 8.0) -> float:
    top_count = stat.top_rate * stat.count
    return (top_count + prior_weight * overall_top_rate) / (stat.count + prior_weight)


def group_table(title: str, stats: list[GroupStat], overall: float, score_format: dict[str, Any],
                limit: int = 20, rank_by_top_rate: bool = False, collapsible: bool = False,
                note: str | None = None) -> str:
    overall_top = sum(s.top_rate * s.count for s in stats) / sum(s.count for s in stats) if stats else 0.0
    if rank_by_top_rate:
        ranked = sorted(stats, key=lambda s: (adjusted_top_rate(s, overall_top), s.count), reverse=True)[:limit]
    else:
        ranked = sorted(stats, key=lambda s: (confidence_adjusted(s, overall), s.count), reverse=True)[:limit]
    body = []
    for stat in ranked:
        lift_class = "positive" if stat.lift > score_format["max"] * .008 else "negative" if stat.lift < -score_format["max"] * .008 else "neutral"
        top_lift = stat.top_rate - overall_top
        top_class = "positive" if top_lift > .03 else "negative" if top_lift < -.03 else "neutral"
        body.append(
            f"<tr><td>{esc(stat.name)}</td><td>{stat.count}</td>"
            f"<td>{display_score(stat.average, score_format)}</td>"
            f"<td class='{lift_class}'>{stat.lift:+.{score_format['decimals'] + 1}f}</td>"
            f"<td>{stat.top_rate:.0%}</td><td class='{top_class}'>{top_lift:+.0%}</td></tr>"
        )
    if not body:
        body.append("<tr><td colspan='6' class='muted'>Not enough rated entries for this section.</td></tr>")
    hint = note or ("Ranked primarily by adjusted top-rating rate." if rank_by_top_rate else "Ranked with a small-sample adjustment. Lift is versus this user's overall average.")
    section = f"""
    <section><h2>{esc(title)}</h2>
      <p class="hint">{esc(hint)}</p>
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Count</th><th>Average</th><th>Avg lift</th><th>Top-rate</th><th>Top-rate lift</th></tr></thead>
      <tbody>{''.join(body)}</tbody></table></div>
    </section>"""
    return f"<details><summary>{esc(title)}</summary>{section}</details>" if collapsible else section


def decade_table(stats: list[GroupStat], overall: float, score_format: dict[str, Any]) -> str:
    def decade_key(stat: GroupStat) -> tuple[int, str]:
        match = re.match(r"(\d{4})s$", stat.name)
        return (int(match.group(1)) if match else -1, stat.name)
    ranked = sorted(stats, key=decade_key, reverse=True)
    body = []
    overall_top = sum(s.top_rate * s.count for s in stats) / sum(s.count for s in stats) if stats else 0.0
    for stat in ranked:
        lift_class = "positive" if stat.lift > score_format["max"] * .008 else "negative" if stat.lift < -score_format["max"] * .008 else "neutral"
        body.append(f"<tr><td>{esc(stat.name)}</td><td>{stat.count}</td><td>{display_score(stat.average, score_format)}</td><td class='{lift_class}'>{stat.lift:+.{score_format['decimals'] + 1}f}</td><td>{stat.top_rate:.0%}</td><td>{stat.top_rate-overall_top:+.0%}</td></tr>")
    if not body:
        body.append("<tr><td colspan='6' class='muted'>No dated entries were found.</td></tr>")
    return f"""<details><summary>Decades</summary><section><h2>Decades</h2><p class="hint">Every decade represented in the rated list is shown.</p><div class="table-wrap"><table><thead><tr><th>Decade</th><th>Count</th><th>Average</th><th>Avg lift</th><th>Top-rate</th><th>Top-rate lift</th></tr></thead><tbody>{''.join(body)}</tbody></table></div></section></details>"""


def show_table(title: str, rows: list[dict[str, Any]], score_format: dict[str, Any], limit: int = 20) -> str:
    body = []
    for row in rows[:limit]:
        community = row.get("community_display")
        delta = (row["rating"] - community) if community is not None else None
        delta_text = "—" if delta is None else f"{delta:+.{score_format['decimals'] + 1}f}"
        body.append(
            f"<tr><td><a href='{esc(row['url'])}'>{esc(row['title'])}</a></td>"
            f"<td>{display_score(row['rating'], score_format)}</td>"
            f"<td>{display_score(community, score_format)}</td><td>{delta_text}</td></tr>"
        )
    return f"""
    <section><h2>{esc(title)}</h2><div class="table-wrap"><table>
    <thead><tr><th>Anime</th><th>Your rating</th><th>Community</th><th>Difference</th></tr></thead>
    <tbody>{''.join(body)}</tbody></table></div></section>"""


def build_identity_profile(rows: list[dict[str, Any]], genres: list[GroupStat], tags: list[GroupStat],
                           overall: float, max_score: float) -> list[str]:
    ratings = [float(r["rating"]) for r in rows if r.get("rating") is not None]
    overall_top = sum(r >= max_score for r in ratings) / len(ratings)
    lines: list[str] = []

    eligible_genres = [g for g in genres if g.count >= 8]
    if eligible_genres:
        best = max(eligible_genres, key=lambda g: (g.top_rate - overall_top, g.count))
        worst = min(eligible_genres, key=lambda g: (g.top_rate - overall_top, -g.count))
        if best.top_rate - overall_top >= .08:
            lines.append(f"You top-rate {best.name} anime {best.top_rate:.0%} of the time, {best.top_rate-overall_top:+.0%} versus your normal rate.")
        if worst.top_rate - overall_top <= -.08:
            lines.append(f"{worst.name} is comparatively less reliable for you: only {worst.top_rate:.0%} reach your top score.")

    strong_tags = sorted([t for t in tags if t.count >= 8], key=lambda t: (t.top_rate - overall_top, t.count), reverse=True)
    if strong_tags:
        names = [t.name for t in strong_tags[:3] if t.top_rate - overall_top >= .12]
        if names:
            lines.append("Your clearest recurring high-score signals are " + ", ".join(names) + ".")

    divergences = [r["rating"] - r["community_display"] for r in rows if r.get("community_display") is not None]
    if divergences:
        mean_delta = statistics.fmean(divergences)
        above = sum(d > max_score * .12 for d in divergences)
        below = sum(d < -max_score * .12 for d in divergences)
        if abs(mean_delta) < max_score * .04:
            lines.append(f"Your average score is close to community consensus, but you have strong individual disagreements ({above} notably above and {below} notably below).")
        elif mean_delta > 0:
            lines.append("You rate anime somewhat more generously than the AniList community overall, while still having clear deal-breakers.")
        else:
            lines.append("You rate anime somewhat more critically than the AniList community overall, especially when a popular series loses you.")

    franchise_groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        base = re.sub(r"\b(season|part|cour|final season|the movie|movie|special)\b.*$", "", row["title"], flags=re.I).strip(" :-–—")
        if len(base) >= 4:
            franchise_groups[base].append(float(row["rating"]))
    declining = [vals for vals in franchise_groups.values() if len(vals) >= 3 and max(vals) - min(vals) >= max_score * .35]
    if declining:
        lines.append("You do not give franchises automatic loyalty points; several long-running series swing sharply between seasons.")

    if not lines:
        lines.append("Your taste is broad, so individual themes and execution predict your ratings better than genre alone.")
    return lines[:5]


def fetch_recommendations(rows: list[dict[str, Any]], max_score: float,
                          tag_stats: list[GroupStat], genre_stats: list[GroupStat]) -> list[dict[str, Any]]:
    seeds = sorted(rows, key=lambda r: (r.get("rating") or 0, r.get("repeat") or 0, r.get("popularity") or 0), reverse=True)
    seed_ids = [r["id"] for r in seeds if (r.get("rating") or 0) >= max_score][:15]
    if not seed_ids:
        seed_ids = [r["id"] for r in seeds[:10]]
    try:
        data = graphql(RECOMMENDATION_QUERY, {"ids": seed_ids})
    except AnalyzerError as exc:
        print(f"Recommendation fetch skipped: {exc}")
        return []

    watched = {r["id"] for r in rows}
    tag_weight = {s.name: max(0.0, s.lift) + max(0.0, s.top_rate - .4) for s in tag_stats if s.count >= 8}
    genre_weight = {s.name: max(0.0, s.lift) + max(0.0, s.top_rate - .4) for s in genre_stats if s.count >= 5}
    candidates: dict[int, dict[str, Any]] = {}
    for media in (data.get("Page") or {}).get("media") or []:
        for node in ((media.get("recommendations") or {}).get("nodes") or []):
            rec = node.get("mediaRecommendation") or {}
            rec_id = rec.get("id")
            if not rec_id or rec_id in watched:
                continue
            title_data = rec.get("title") or {}
            item = candidates.setdefault(rec_id, {
                "id": rec_id,
                "title": title_data.get("english") or title_data.get("userPreferred") or title_data.get("romaji") or str(rec_id),
                "url": rec.get("siteUrl") or f"https://anilist.co/anime/{rec_id}",
                "format": rec.get("format") or "Unknown",
                "year": rec.get("seasonYear"),
                "genres": rec.get("genres") or [],
                "tags": [t["name"] for t in rec.get("tags") or [] if t.get("rank", 0) >= 20 and not t.get("isMediaSpoiler") and not t.get("isGeneralSpoiler")],
                "community": rec.get("meanScore") or rec.get("averageScore"),
                "popularity": rec.get("popularity") or 0,
                "votes": 0,
                "sources": 0,
            })
            item["votes"] += max(0, node.get("rating") or 0)
            item["sources"] += 1

    for item in candidates.values():
        overlap = sum(tag_weight.get(t, 0) for t in set(item["tags"])) + sum(genre_weight.get(g, 0) for g in set(item["genres"]))
        community = (item.get("community") or 0) / 100
        popularity_bonus = math.log10(max(10, item.get("popularity") or 10)) / 10
        item["match_score"] = item["sources"] * 2.5 + math.log1p(item["votes"]) + overlap * 2 + community + popularity_bonus
        matched = sorted(set(item["tags"]), key=lambda t: tag_weight.get(t, 0), reverse=True)
        item["reasons"] = [m for m in matched if tag_weight.get(m, 0) > 0][:3]
        if not item["reasons"]:
            item["reasons"] = sorted(set(item["genres"]), key=lambda g: genre_weight.get(g, 0), reverse=True)[:2]
    return sorted(candidates.values(), key=lambda x: (x["match_score"], x["popularity"]), reverse=True)[:15]


def recommendations_table(recs: list[dict[str, Any]], score_format: dict[str, Any]) -> str:
    if not recs:
        return "<section><h2>Recommendations</h2><p class='muted'>AniList did not return enough recommendation data for this list.</p></section>"
    rows = []
    for rec in recs:
        community = (rec.get("community") / 100 * score_format["max"]) if rec.get("community") else None
        reason = ", ".join(rec.get("reasons") or []) or "recommended from multiple favorites"
        rows.append(f"<tr><td><a href='{esc(rec['url'])}'>{esc(rec['title'])}</a></td><td>{esc(rec.get('year') or '—')}</td><td>{esc(rec.get('format') or '—')}</td><td>{display_score(community, score_format)}</td><td>{esc(reason)}</td></tr>")
    return f"""<section><h2>Recommendations</h2><p class="hint">Aggregated from AniList recommendations attached to this user's highest-rated anime, then re-ranked using their strongest recurring genres and tags. Anything already on the analyzed list is excluded.</p><div class="table-wrap"><table><thead><tr><th>Anime</th><th>Year</th><th>Format</th><th>Community</th><th>Why it surfaced</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"""


def build_html(user: dict[str, Any], rows: list[dict[str, Any]], output: Path,
               min_count: int, include_staff: bool) -> None:
    score_format = score_info(user)
    max_score = score_format["max"]
    ratings = [float(r["rating"]) for r in rows if r.get("rating") is not None]
    overall = statistics.fmean(ratings) if ratings else 0.0
    top_count = sum(r >= max_score for r in ratings)

    genre_stats = group_stats(rows, "genres", overall, max(3, min_count), max_score)
    tag_stats = group_stats(rows, "tags", overall, max(8, min_count), max_score)
    studio_stats_list = group_stats(rows, "studios", overall, max(3, min_count), max_score)
    source_stats = group_stats(rows, "source", overall, max(3, min_count), max_score)
    format_stats = group_stats(rows, "format", overall, max(3, min_count), max_score)
    decades = group_stats(rows, "decade", overall, 1, max_score)

    divergences = [r for r in rows if r.get("community_display") is not None]
    positive = sorted(divergences, key=lambda r: r["rating"] - r["community_display"], reverse=True)
    negative = sorted(divergences, key=lambda r: r["rating"] - r["community_display"])
    top_fives = sorted([r for r in rows if r.get("rating") == max_score], key=lambda r: (r.get("popularity", 0), r["title"]), reverse=True)
    low_rated = sorted(rows, key=lambda r: (r.get("rating") or 99, r["title"]))
    identity = build_identity_profile(rows, genre_stats, tag_stats, overall, max_score)
    recommendations = fetch_recommendations(rows, max_score, tag_stats, genre_stats)

    dist_blocks = []
    if score_format["format"] in {"POINT_3", "POINT_5", "POINT_10"}:
        distribution = Counter(int(round(r)) for r in ratings)
        max_dist = max(distribution.values(), default=1)
        for score in range(int(max_score), 0, -1):
            count = distribution[score]
            width = 100 * count / max_dist
            label = display_score(float(score), score_format, suffix=False)
            dist_blocks.append(f"<div class='dist-row'><span>{label}</span><div class='bar'><i style='width:{width:.1f}%'></i></div><b>{count}</b></div>")
    else:
        band_counts = Counter(min(9, max(0, int((r / max_score) * 10))) for r in ratings)
        max_dist = max(band_counts.values(), default=1)
        for band in range(9, -1, -1):
            count = band_counts[band]
            low = band * max_score / 10
            high = (band + 1) * max_score / 10
            label = f"{low:.{score_format['decimals']}f}–{high:.{score_format['decimals']}f}"
            width = 100 * count / max_dist
            dist_blocks.append(f"<div class='dist-row'><span>{label}</span><div class='bar'><i style='width:{width:.1f}%'></i></div><b>{count}</b></div>")

    summary_cards = f"""
    <div class="cards">
      <div class="card"><span>Rated anime</span><strong>{len(ratings)}</strong></div>
      <div class="card"><span>Scoring system</span><strong>{esc(score_format['label'])}</strong></div>
      <div class="card"><span>Average</span><strong>{display_score(overall, score_format)}</strong></div>
      <div class="card"><span>Top ratings</span><strong>{top_count}</strong></div>
      <div class="card"><span>Top-rating rate</span><strong>{top_count/len(ratings):.0%}</strong></div>
    </div>""" if ratings else ""

    profile_html = "".join(f"<li>{esc(line)}</li>" for line in identity)
    primary_tables = group_table("Genres", genre_stats, overall, score_format, rank_by_top_rate=True,
                                 note="Ranked by adjusted top-rating rate rather than nearly identical averages.")
    primary_tables += group_table("Tags", tag_stats, overall, score_format, rank_by_top_rate=True,
                                  note=f"Only tags appearing at least {max(8, min_count)} times are eligible, reducing small-sample noise.")

    secondary = group_table("Studios", studio_stats_list, overall, score_format, collapsible=True)
    secondary += group_table("Source material", source_stats, overall, score_format, collapsible=True)
    secondary += group_table("Formats", format_stats, overall, score_format, collapsible=True)
    secondary += decade_table(decades, overall, score_format)
    if include_staff:
        secondary += group_table("Recurring creative staff", staff_stats(rows, overall, max(3, min_count), max_score), overall, score_format, collapsible=True)

    all_rows = []
    for row in sorted(rows, key=lambda r: (-(r.get("rating") or 0), r["title"].lower())):
        all_rows.append(
            f"<tr><td><a href='{esc(row['url'])}'>{esc(row['title'])}</a></td>"
            f"<td>{display_score(row.get('rating'), score_format)}</td><td>{esc(row['status'])}</td>"
            f"<td>{esc(row['format'])}</td><td>{esc(row.get('year') or '—')}</td>"
            f"<td>{esc(', '.join(row['genres']))}</td></tr>"
        )

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(user['name'])} — Anime Taste Report</title>
<style>
:root{{--bg:#0c111b;--panel:#151c29;--panel2:#1b2534;--text:#edf2f7;--muted:#9eacc0;--accent:#62d6e8;--line:#2b394c;--good:#70d49b;--bad:#ff8e8e}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}} main{{max-width:1180px;margin:auto;padding:34px 20px 80px}}
.hero{{padding:28px;background:linear-gradient(135deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:18px}}
h1{{margin:0 0 6px;font-size:clamp(28px,5vw,48px)}} h2{{margin:0 0 8px;font-size:24px}} .muted,.hint{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0 0}} .card{{background:rgba(0,0,0,.18);border:1px solid var(--line);border-radius:12px;padding:14px}}
.card span{{display:block;color:var(--muted)}} .card strong{{font-size:25px}} section{{margin-top:28px;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:18px}} .grid section{{margin-top:28px}}
.table-wrap{{overflow:auto}} table{{width:100%;border-collapse:collapse;min-width:680px}} th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}} th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
.positive{{color:var(--good)}} .negative{{color:var(--bad)}} .neutral{{color:var(--muted)}} .dist-row{{display:grid;grid-template-columns:90px 1fr 40px;gap:10px;align-items:center;margin:10px 0}}
.bar{{height:12px;background:#263346;border-radius:999px;overflow:hidden}} .bar i{{display:block;height:100%;background:var(--accent);border-radius:inherit}} details{{margin-top:22px}} summary{{cursor:pointer;font-size:20px;font-weight:700;padding:14px 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px}}
details[open] summary{{border-radius:12px 12px 0 0}} details > section{{margin-top:0;border-radius:0 0 16px 16px}} .profile-list{{margin:12px 0 0;padding-left:22px}} .profile-list li{{margin:10px 0}}
footer{{margin-top:36px;color:var(--muted);font-size:13px}}
@media(max-width:650px){{main{{padding:16px 10px 50px}}section,.hero{{padding:15px}}}}
</style></head><body><main>
<div class="hero"><div class="muted">Unofficial AniList taste analysis</div><h1>{esc(user['name'])}</h1>
<div><a href="{esc(user.get('siteUrl',''))}">Open AniList profile</a> · Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</div>{summary_cards}</div>
<section><h2>Taste profile</h2><p class="hint">A concise synthesis of the strongest patterns in this list—not a personality diagnosis.</p><ul class="profile-list">{profile_html}</ul></section>
{recommendations_table(recommendations, score_format)}
<section><h2>Rating distribution</h2>{''.join(dist_blocks)}</section>
<div class="grid">{show_table('Most above community consensus', positive, score_format, 15)}{show_table('Most below community consensus', negative, score_format, 15)}</div>
{primary_tables}
{show_table('Most popular top-rated picks', top_fives, score_format, 20)}
{show_table('Lowest-rated completed picks', low_rated, score_format, 20)}
<h2 style="margin-top:34px">More detail</h2>{secondary}
<details><summary>All analyzed anime ({len(rows)})</summary><section><div class="table-wrap"><table><thead><tr><th>Anime</th><th>Rating</th><th>List status</th><th>Format</th><th>Year</th><th>Genres</th></tr></thead><tbody>{''.join(all_rows)}</tbody></table></div></section></details>
<footer>Uses publicly available data from AniList's GraphQL API. Recommendations are heuristic, not guarantees. Rankings describe this list only; correlation is not causation.</footer>
</main></body></html>"""
    output.write_text(document, encoding="utf-8")


def print_console_summary(user: dict[str, Any], rows: list[dict[str, Any]], min_count: int) -> None:
    ratings = [r["rating"] for r in rows if r.get("rating") is not None]
    overall = statistics.fmean(ratings)
    info = score_info(user)
    max_score = info["max"]
    overall_top = sum(r >= max_score for r in ratings) / len(ratings)
    print("\n" + "=" * 68)
    print(f"ANIME TASTE REPORT: {user['name']}")
    print("=" * 68)
    print(f"Rated entries analyzed: {len(ratings)}")
    print(f"Scoring system:         {info['label']} ({info['format']})")
    print(f"Average rating:         {display_score(overall, info)}")
    print(f"Top ratings:            {sum(r >= max_score for r in ratings)}")

    for label, field, threshold in (("genres", "genres", max(3, min_count)), ("tags", "tags", max(8, min_count)), ("studios", "studios", max(3, min_count))):
        stats = group_stats(rows, field, overall, threshold, max_score)
        ranked = sorted(stats, key=lambda s: adjusted_top_rate(s, overall_top), reverse=True)[:8]
        print(f"\nTop {label} (minimum {threshold} entries):")
        for stat in ranked:
            print(f"  {stat.name:<34.34} {stat.top_rate:>7.0%} top-rate  ({stat.count} shows, {stat.top_rate-overall_top:+.0%})")

def parse_statuses(raw: str) -> set[str]:
    values = {v.strip().upper() for v in raw.split(",") if v.strip()}
    invalid = values - VALID_STATUSES
    if invalid:
        raise argparse.ArgumentTypeError(f"Unknown status: {', '.join(sorted(invalid))}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze any public AniList anime list and create an HTML report.")
    parser.add_argument("username", nargs="?", help="AniList username (you will be prompted if omitted)")
    parser.add_argument("--statuses", default=",".join(DEFAULT_STATUSES),
                        help="Comma-separated statuses to analyze (default: COMPLETED). Example: COMPLETED,DROPPED")
    parser.add_argument("--all-rated", action="store_true", help="Analyze rated entries from every list status")
    parser.add_argument("--include-unrated", action="store_true", help="Include unrated entries in raw exports (not averages)")
    parser.add_argument("--spoiler-tags", action="store_true", help="Include spoiler-marked AniList tags")
    parser.add_argument("--no-staff", action="store_true", help="Skip the extra staff/director/composer requests")
    parser.add_argument("--min-count", type=int, default=3, help="Minimum appearances for group rankings (default: 3)")
    parser.add_argument("--output", help="Output directory (default: anilist_report_USERNAME)")
    parser.add_argument("--no-open", action="store_true", help="Do not automatically open the HTML report")
    args = parser.parse_args()

    username = (args.username or input("AniList username: ")).strip()
    if not username:
        print("A username is required.", file=sys.stderr)
        return 2
    statuses = VALID_STATUSES if args.all_rated else parse_statuses(args.statuses)

    print(f"Fetching public anime list for {username}...")
    try:
        data = graphql(LIST_QUERY, {"userName": username})
        user = data.get("User")
        collection = data.get("MediaListCollection")
        if not user or not collection:
            raise AnalyzerError("User or public anime list was not found.")
        raw_entries = flatten_entries(collection)
        format_info = score_info(user)
        rows = normalize_entries(raw_entries, statuses, args.include_unrated,
                                 args.spoiler_tags, not args.no_staff, format_info)
        rated_rows = [r for r in rows if r.get("rating") is not None]
        if not rated_rows:
            raise AnalyzerError("No rated anime matched the selected statuses.")

        output_dir = Path(args.output or f"anilist_report_{safe_name(user['name'])}").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        html_path = output_dir / "anime_taste_report.html"
        csv_path = output_dir / "anime_data.csv"
        json_path = output_dir / "anime_data.json"

        write_csv(rows, csv_path)
        write_json(user, rows, json_path)
        build_html(user, rated_rows, html_path, max(1, args.min_count), not args.no_staff)
        print_console_summary(user, rated_rows, max(1, args.min_count))

        print("\nFiles created:")
        print(f"  HTML report: {html_path}")
        print(f"  CSV data:    {csv_path}")
        print(f"  JSON data:   {json_path}")
        if not args.no_open:
            webbrowser.open(html_path.as_uri())
        return 0
    except (AnalyzerError, ValueError, KeyError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
