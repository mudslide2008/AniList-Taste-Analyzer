
from __future__ import annotations
import json, math, statistics, time
from pathlib import Path
from collections import defaultdict
from typing import Any
from .api import graphql
from .queries import STAFF_QUERY
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



VOICE_CACHE_VERSION = 1
VOICE_BATCH_SIZE = 10
VOICE_MAX_CHARACTER_PAGES = 3


def _voice_cache_path() -> Path:
    """Store shared cast metadata beside the project, not inside each report."""
    project_root = Path(__file__).resolve().parent.parent
    return project_root / ".anilist_cache" / "voice_actors.json"


def _load_voice_cache() -> dict:
    path = _voice_cache_path()
    if not path.exists():
        return {"version": VOICE_CACHE_VERSION, "media": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != VOICE_CACHE_VERSION:
            return {"version": VOICE_CACHE_VERSION, "media": {}}
        payload.setdefault("media", {})
        return payload
    except (OSError, json.JSONDecodeError):
        return {"version": VOICE_CACHE_VERSION, "media": {}}


def _save_voice_cache(cache: dict) -> None:
    path = _voice_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _voice_batch_query(media_ids: list[int], character_page: int) -> str:
    """Build one GraphQL request containing several Media aliases."""
    fields = []
    for index, media_id in enumerate(media_ids):
        fields.append(f"""
        media_{index}: Media(id: {int(media_id)}, type: ANIME) {{
          id
          characters(page: {int(character_page)}, perPage: 50, sort: [ROLE, RELEVANCE, ID]) {{
            pageInfo {{ currentPage hasNextPage }}
            edges {{
              node {{ id name {{ full }} }}
              japaneseVoiceActors: voiceActors(language: JAPANESE, sort: RELEVANCE) {{
                id name {{ full }} siteUrl
              }}
              englishVoiceActors: voiceActors(language: ENGLISH, sort: RELEVANCE) {{
                id name {{ full }} siteUrl
              }}
            }}
          }}
        }}
        """)
    return "query {\n" + "\n".join(fields) + "\n}"


def _empty_voice_record() -> dict:
    return {
        "japanese": {},
        "english": {},
        "pages_fetched": [],
        "complete": False,
    }


def _merge_voice_page(record: dict, media: dict, page: int) -> bool:
    """Merge one characters page into a cache record.

    Returns whether AniList reports another page.
    """
    characters = (media or {}).get("characters") or {}
    for edge in characters.get("edges") or []:
        character = (
            (((edge.get("node") or {}).get("name") or {}).get("full") or "")
            .strip()
        )
        for language, field in (
            ("japanese", "japaneseVoiceActors"),
            ("english", "englishVoiceActors"),
        ):
            actors = record.setdefault(language, {})
            for actor in edge.get(field) or []:
                actor_id = actor.get("id")
                name = ((actor.get("name") or {}).get("full") or "").strip()
                if not name:
                    continue
                key = str(actor_id or name)
                item = actors.setdefault(key, {
                    "id": actor_id,
                    "name": name,
                    "url": actor.get("siteUrl") or "",
                    "characters": [],
                })
                if character and character not in item["characters"]:
                    item["characters"].append(character)

    pages = record.setdefault("pages_fetched", [])
    if page not in pages:
        pages.append(page)
        pages.sort()

    return bool((characters.get("pageInfo") or {}).get("hasNextPage"))


def _record_for_report(record: dict) -> dict[str, list[dict]]:
    return {
        "japanese": list((record.get("japanese") or {}).values()),
        "english": list((record.get("english") or {}).values()),
    }


def get_voice_actors(media_ids: list[int]) -> dict[int, dict[str, list[dict]]]:
    """Fetch cast metadata in batches and persist it in a resumable cache.

    The first run normally needs about one request per ten anime, plus extra
    batched requests only for unusually large casts. Later runs reuse cached
    media across every analyzed user.
    """
    requested_ids = list(dict.fromkeys(int(media_id) for media_id in media_ids))
    cache = _load_voice_cache()
    cached_media = cache["media"]

    missing_ids = [
        media_id
        for media_id in requested_ids
        if not (cached_media.get(str(media_id)) or {}).get("complete")
    ]

    if missing_ids:
        total_batches = math.ceil(len(missing_ids) / VOICE_BATCH_SIZE)
        print(
            f"Voice cast cache: {len(requested_ids) - len(missing_ids)} cached, "
            f"{len(missing_ids)} to fetch in about {total_batches} initial batches."
        )

    for batch_number, batch in enumerate(chunks(missing_ids, VOICE_BATCH_SIZE), start=1):
        pending = list(batch)
        for page in range(1, VOICE_MAX_CHARACTER_PAGES + 1):
            if not pending:
                break

            print(
                f"Fetching voice cast batch {batch_number}/"
                f"{math.ceil(len(missing_ids)/VOICE_BATCH_SIZE)} "
                f"(character page {page}, {len(pending)} anime)..."
            )
            query = _voice_batch_query(pending, page)
            response = graphql(query, {})

            next_page_ids = []
            for alias_index, media_id in enumerate(pending):
                media = response.get(f"media_{alias_index}") or {}
                record = cached_media.setdefault(str(media_id), _empty_voice_record())
                has_next = _merge_voice_page(record, media, page)
                if has_next and page < VOICE_MAX_CHARACTER_PAGES:
                    next_page_ids.append(media_id)
                else:
                    record["complete"] = True

            # Save after every successful request so an interrupted run resumes.
            _save_voice_cache(cache)
            pending = next_page_ids
            time.sleep(0.25)

    # A previously interrupted cache may contain records that have pages but
    # were never marked complete. Leave them uncached for the next run rather
    # than silently pretending the data is final.
    result = {}
    for media_id in requested_ids:
        record = cached_media.get(str(media_id)) or _empty_voice_record()
        result[media_id] = _record_for_report(record)
    return result

def voice_actor_stats(rows, language, overall, min_count, max_score):
    grouped = defaultdict(list)
    links = {}
    appearances = defaultdict(list)
    actor_names = {}
    for row in rows:
        rating = row.get("rating")
        if rating is None:
            continue
        seen = set()
        for actor in (row.get("voice_actors") or {}).get(language, []):
            actor_id = actor.get("id") or actor.get("name")
            if not actor_id or actor_id in seen:
                continue
            seen.add(actor_id)
            name = actor.get("name")
            if not name:
                continue
            actor_names[actor_id] = name
            grouped[actor_id].append(float(rating))
            links[actor_id] = actor.get("url") or ""
            appearances[actor_id].append({
                "anime": row.get("title") or "Unknown anime",
                "anime_url": row.get("url") or "",
                "characters": actor.get("characters") or [],
                "rating": float(rating),
            })
    result = []
    for actor_id, ratings in grouped.items():
        if len(ratings) >= min_count:
            avg = statistics.fmean(ratings)
            stat = GroupStat(actor_names[actor_id], len(ratings), avg, avg-overall,
                             sum(r >= max_score for r in ratings)/len(ratings), ratings)
            stat.url = links.get(actor_id, "")
            stat.appearances = sorted(
                appearances[actor_id],
                key=lambda item: (-item["rating"], item["anime"].lower()),
            )
            result.append(stat)
    return sorted(result, key=lambda x: (x.top_rate, x.average, x.count), reverse=True)

