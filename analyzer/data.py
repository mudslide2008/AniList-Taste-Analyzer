
from __future__ import annotations
import math, statistics, time
from collections import defaultdict
from typing import Any
from .api import graphql
from .queries import STAFF_QUERY, VOICE_ACTOR_QUERY
from .util import chunks, fuzzy_date
from .models import GroupStat

def flatten_entries(collection: dict[str, Any]) -> list[dict[str, Any]]:
    by_media: dict[int, dict[str, Any]] = {}
    for list_group in collection.get("lists") or []:
        for entry in list_group.get("entries") or []:
            media = entry.get("media") or {}
            media_id = media.get("id")
            if not media_id:
                continue
            previous = by_media.get(media_id)
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

def normalize_entries(entries, statuses, include_unrated, include_spoiler_tags, fetch_staff_data, score_format):
    selected = []
    for entry in entries:
        if entry.get("status") not in statuses:
            continue
        score_key = {
            "POINT_3": "score3", "POINT_5": "score5", "POINT_10": "score10",
            "POINT_10_DECIMAL": "score10Decimal", "POINT_100": "score100",
        }.get(score_format["format"], "scoreOriginal")
        rating = entry.get(score_key) or 0
        rating100 = entry.get("score100") or 0
        if not include_unrated and rating <= 0:
            continue
        media = entry["media"]
        title_data = media.get("title") or {}
        title = title_data.get("english") or title_data.get("userPreferred") or title_data.get("romaji") or str(media["id"])
        tags = []
        tag_details = []
        for tag in media.get("tags") or []:
            if tag.get("rank", 0) < 20:
                continue
            if not include_spoiler_tags and (tag.get("isMediaSpoiler") or tag.get("isGeneralSpoiler")):
                continue
            tags.append(tag["name"])
            tag_details.append({
                "name": tag["name"],
                "category": tag.get("category") or "Other",
                "rank": tag.get("rank") or 0,
            })
        studios = [s["name"] for s in ((media.get("studios") or {}).get("nodes") or [])]
        community = media.get("meanScore") or media.get("averageScore")
        selected.append({
            "id": media["id"], "title": title, "romaji": title_data.get("romaji") or "",
            "rating": float(rating) if rating else None,
            "rating100": float(rating100) if rating100 else None,
            "score_format": score_format["format"], "status": entry.get("status") or "",
            "progress": entry.get("progress") or 0, "repeat": entry.get("repeat") or 0,
            "started": fuzzy_date(entry.get("startedAt")), "completed": fuzzy_date(entry.get("completedAt")),
            "format": media.get("format") or "Unknown", "episodes": media.get("episodes"),
            "duration": media.get("duration"), "season": media.get("season") or "",
            "year": media.get("seasonYear"),
            "decade": f"{(media['seasonYear']//10)*10}s" if media.get("seasonYear") else "Unknown",
            "source": media.get("source") or "Unknown", "genres": media.get("genres") or [],
            "tags": tags, "tag_details": tag_details, "studios": studios or ["Unknown"], "community_score": community,
            "community_normalized": float(community) if community else None,
            "community_display": (float(community) / 100.0 * score_format["max"]) if community else None,
            "popularity": media.get("popularity") or 0, "favourites": media.get("favourites") or 0,
            "url": media.get("siteUrl") or f"https://anilist.co/anime/{media['id']}", "staff": [],
        })
    if fetch_staff_data and selected:
        staff_map = get_staff([row["id"] for row in selected])
        for row in selected:
            credits = []
            for edge in staff_map.get(row["id"], []):
                role = edge.get("role") or ""
                node = edge.get("node") or {}
                name = (node.get("name") or {}).get("full")
                if name and any(key in role.lower() for key in (
                    "director", "series composition", "script", "screenplay",
                    "original creator", "music", "character design"
                )):
                    credits.append({"name": name, "role": role, "url": node.get("siteUrl") or ""})
            row["staff"] = credits

    if fetch_staff_data and selected:
        voice_map = get_voice_actors([row["id"] for row in selected])
        for row in selected:
            row["voice_actors"] = voice_map.get(row["id"], {"japanese": [], "english": []})
    return selected

def group_stats(rows, field, overall, min_count, max_score):
    grouped = defaultdict(list)
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
        stats.append(GroupStat(name, len(ratings), avg, avg-overall,
                               sum(r >= max_score for r in ratings)/len(ratings), ratings))
    return sorted(stats, key=lambda x: (x.average, x.count), reverse=True)

def staff_stats(rows, overall, min_count, max_score):
    grouped = defaultdict(list)
    for row in rows:
        rating = row.get("rating")
        if rating is None: continue
        seen=set()
        for credit in row.get("staff", []):
            key=f"{credit['name']} — {credit['role']}"
            if key not in seen:
                grouped[key].append(float(rating)); seen.add(key)
    result=[]
    for name, ratings in grouped.items():
        if len(ratings)>=min_count:
            avg=statistics.fmean(ratings)
            result.append(GroupStat(name,len(ratings),avg,avg-overall,
                                    sum(r>=max_score for r in ratings)/len(ratings),ratings))
    return sorted(result,key=lambda x:(x.average,x.count),reverse=True)

def confidence_adjusted(stat, overall, prior_weight=5.0):
    return (stat.count*stat.average + prior_weight*overall)/(stat.count+prior_weight)

def adjusted_top_rate(stat, overall_top_rate, prior_weight=8.0):
    top_count=stat.top_rate*stat.count
    return (top_count+prior_weight*overall_top_rate)/(stat.count+prior_weight)



def get_voice_actors(media_ids: list[int]) -> dict[int, dict[str, list[dict]]]:
    """Fetch recurring Japanese and English performers.

    AniList paginates character credits independently for every anime. Fetch up
    to three 50-character pages so long-running or ensemble shows do not lose
    most of their cast. Each actor is deduplicated once per anime.
    """
    result: dict[int, dict[str, list[dict]]] = defaultdict(lambda: {"japanese": [], "english": []})
    batches = list(chunks(media_ids, 25))
    for batch_number, batch in enumerate(batches, start=1):
        print(f"Fetching voice actors batch {batch_number}/{len(batches)}...")
        active_ids = set(batch)
        seen_by_media = {
            media_id: {"japanese": set(), "english": set()}
            for media_id in batch
        }
        for character_page in range(1, 4):
            if not active_ids:
                break
            data = graphql(VOICE_ACTOR_QUERY, {
                "ids": sorted(active_ids),
                "characterPage": character_page,
            })
            next_active = set()
            for media in (data.get("Page") or {}).get("media") or []:
                media_id = media.get("id")
                if not media_id:
                    continue
                characters = media.get("characters") or {}
                if (characters.get("pageInfo") or {}).get("hasNextPage"):
                    next_active.add(media_id)
                for edge in characters.get("edges") or []:
                    for key, field in (("japanese", "japaneseVoiceActors"), ("english", "englishVoiceActors")):
                        for actor in edge.get(field) or []:
                            actor_id = actor.get("id")
                            name = ((actor.get("name") or {}).get("full") or "").strip()
                            identity = actor_id or name
                            if not name or identity in seen_by_media[media_id][key]:
                                continue
                            seen_by_media[media_id][key].add(identity)
                            result[media_id][key].append({
                                "id": actor_id,
                                "name": name,
                                "url": actor.get("siteUrl") or "",
                            })
            active_ids = next_active
            time.sleep(0.35)
    return result


def voice_actor_stats(rows, language, overall, min_count, max_score):
    grouped = defaultdict(list)
    links = {}
    for row in rows:
        rating = row.get("rating")
        if rating is None:
            continue
        seen = set()
        for actor in (row.get("voice_actors") or {}).get(language, []):
            actor_id = actor.get("id") or actor.get("name")
            if actor_id in seen:
                continue
            seen.add(actor_id)
            name = actor.get("name")
            if name:
                grouped[name].append(float(rating))
                links[name] = actor.get("url") or ""
    result = []
    for name, ratings in grouped.items():
        if len(ratings) >= min_count:
            avg = statistics.fmean(ratings)
            stat = GroupStat(name, len(ratings), avg, avg-overall,
                             sum(r >= max_score for r in ratings)/len(ratings), ratings)
            stat.url = links.get(name, "")
            result.append(stat)
    return sorted(result, key=lambda x: (x.average, x.count), reverse=True)
