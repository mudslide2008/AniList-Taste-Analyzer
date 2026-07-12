from __future__ import annotations

import argparse
import statistics
import sys
import webbrowser
from pathlib import Path

from analyzer.api import graphql, AnalyzerError
from analyzer.queries import LIST_QUERY
from analyzer.util import safe_name, score_info
from analyzer.data import (
    flatten_entries,
    normalize_entries,
    group_stats,
    staff_stats,
    voice_actor_stats,
)
from analyzer.profile import build_identity_profile, build_taste_at_glance
from analyzer.recommendations import fetch_recommendations, categorize_recommendations
from analyzer.report import build_html
from analyzer.exports import write_csv, write_json
from analyzer.share import write_share_assets


VALID_STATUSES = {"CURRENT", "PLANNING", "COMPLETED", "DROPPED", "PAUSED", "REPEATING"}
DEFAULT_STATUSES = ("COMPLETED",)


def parse_statuses(raw):
    values = {value.strip().upper() for value in raw.split(",") if value.strip()}
    invalid = values - VALID_STATUSES
    if invalid:
        raise argparse.ArgumentTypeError(f"Unknown status: {', '.join(sorted(invalid))}")
    return values


def main():
    parser = argparse.ArgumentParser(
        description="Analyze any public AniList anime list and create an HTML report."
    )
    parser.add_argument("username", nargs="?")
    parser.add_argument("--statuses", default=",".join(DEFAULT_STATUSES))
    parser.add_argument("--all-rated", action="store_true")
    parser.add_argument(
        "--include-unrated",
        action="store_true",
        help="Retained for compatibility; unrated anime are now included automatically.",
    )
    parser.add_argument("--spoiler-tags", action="store_true")
    parser.add_argument("--no-staff", action="store_true")
    parser.add_argument("--min-count", type=int, default=3)
    parser.add_argument("--output")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--refresh-va-cache",
        action="store_true",
        help="Delete cached voice cast data before running",
    )
    args = parser.parse_args()

    username = (args.username or input("AniList username: ")).strip()
    if not username:
        print("A username is required.", file=sys.stderr)
        return 2

    statuses = VALID_STATUSES if args.all_rated else parse_statuses(args.statuses)
    if args.refresh_va_cache:
        cache_path = Path(__file__).resolve().parent / ".anilist_cache" / "voice_actors.json"
        if cache_path.exists():
            cache_path.unlink()
            print("Voice actor cache cleared.")

    print(f"Fetching public anime list for {username}...")
    try:
        data = graphql(LIST_QUERY, {"userName": username})
        user = data.get("User")
        collection = data.get("MediaListCollection")
        if not user or not collection:
            raise AnalyzerError("User or public anime list was not found.")

        raw_entries = flatten_entries(collection)
        info = score_info(user)

        # Used only to exclude anything already present anywhere on the AniList.
        all_entries = normalize_entries(
            raw_entries,
            VALID_STATUSES,
            True,
            args.spoiler_tags,
            False,
            info,
        )

        # The analysis always uses every matching viewed entry. Ratings remain
        # optional evidence rather than a gate that removes shows from tags,
        # genres, staff, voice actors, or recommendations.
        rows = normalize_entries(
            raw_entries,
            statuses,
            True,
            args.spoiler_tags,
            not args.no_staff,
            info,
        )
        if not rows:
            raise AnalyzerError("No anime matched the selected statuses.")

        rated = [row for row in rows if row.get("rating") is not None]
        max_score = info["max"]
        overall = statistics.fmean(row["rating"] for row in rated) if rated else None

        stats = {
            "genres": group_stats(rows, "genres", overall, max(3, args.min_count), max_score),
            "all_tags": group_stats(rows, "tags", overall, 2, max_score),
            "studios": group_stats(rows, "studios", overall, max(3, args.min_count), max_score),
            "sources": group_stats(rows, "source", overall, max(3, args.min_count), max_score),
            "formats": group_stats(rows, "format", overall, max(3, args.min_count), max_score),
            "decades": group_stats(rows, "decade", overall, 1, max_score),
            "staff": staff_stats(rows, overall, max(3, args.min_count), max_score) if not args.no_staff else [],
            "japanese_vas": voice_actor_stats(rows, "japanese", overall, 2, max_score) if not args.no_staff else [],
            "english_vas": voice_actor_stats(rows, "english", overall, 2, max_score) if not args.no_staff else [],
        }

        recurring_tag_stats = [stat for stat in stats["all_tags"] if stat.count >= 8]
        identity = build_identity_profile(
            rows,
            stats["genres"],
            recurring_tag_stats,
            overall,
            max_score,
        )
        taste_glance = build_taste_at_glance(
            rows,
            stats["genres"],
            stats["all_tags"],
            overall,
            max_score,
        )
        recs = fetch_recommendations(
            rows,
            all_entries,
            max_score,
            recurring_tag_stats,
            stats["genres"],
        )
        rec_groups = categorize_recommendations(recs)

        out = Path(args.output or f"anilist_report_{safe_name(user['name'])}").resolve()
        out.mkdir(parents=True, exist_ok=True)
        html_path = out / "anime_taste_report.html"
        write_csv(rows, out / "anime_data.csv")
        write_json(user, rows, out / "anime_data.json")
        build_html(
            user,
            rows,
            all_entries,
            html_path,
            info,
            overall,
            stats,
            identity,
            taste_glance,
            rec_groups,
            not args.no_staff,
        )
        write_share_assets(
            user,
            taste_glance,
            stats,
            rows,
            info,
            overall,
            out,
            rec_groups,
        )

        print(f"\nHTML report: {html_path}")
        print(f"Social card:  {out / 'share_card.png'}")
        print(f"Taste cover:  {out / 'taste_cover.png'}")
        print(f"Text summary: {out / 'share_summary.txt'}")
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
