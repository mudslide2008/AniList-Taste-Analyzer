
from __future__ import annotations
import argparse, statistics, sys, webbrowser
from pathlib import Path
from analyzer.api import graphql, AnalyzerError
from analyzer.queries import LIST_QUERY
from analyzer.util import safe_name, score_info
from analyzer.data import flatten_entries, normalize_entries, group_stats, staff_stats, voice_actor_stats
from analyzer.profile import build_identity_profile, build_taste_at_glance
from analyzer.recommendations import fetch_recommendations, categorize_recommendations
from analyzer.report import build_html
from analyzer.exports import write_csv, write_json

VALID_STATUSES={"CURRENT","PLANNING","COMPLETED","DROPPED","PAUSED","REPEATING"}
DEFAULT_STATUSES=("COMPLETED",)

def parse_statuses(raw):
    values={v.strip().upper() for v in raw.split(",") if v.strip()}
    invalid=values-VALID_STATUSES
    if invalid: raise argparse.ArgumentTypeError(f"Unknown status: {', '.join(sorted(invalid))}")
    return values

def main():
    parser=argparse.ArgumentParser(description="Analyze any public AniList anime list and create an HTML report.")
    parser.add_argument("username",nargs="?")
    parser.add_argument("--statuses",default=",".join(DEFAULT_STATUSES))
    parser.add_argument("--all-rated",action="store_true")
    parser.add_argument("--include-unrated",action="store_true")
    parser.add_argument("--spoiler-tags",action="store_true")
    parser.add_argument("--no-staff",action="store_true")
    parser.add_argument("--min-count",type=int,default=3)
    parser.add_argument("--output")
    parser.add_argument("--no-open",action="store_true")
    parser.add_argument("--refresh-va-cache",action="store_true",help="Delete cached voice cast data before running")
    args=parser.parse_args()

    username=(args.username or input("AniList username: ")).strip()
    if not username:
        print("A username is required.",file=sys.stderr); return 2
    statuses=VALID_STATUSES if args.all_rated else parse_statuses(args.statuses)
    if args.refresh_va_cache:
        cache_path=Path(__file__).resolve().parent/".anilist_cache"/"voice_actors.json"
        if cache_path.exists():
            cache_path.unlink()
            print("Voice actor cache cleared.")

    print(f"Fetching public anime list for {username}...")
    try:
        data=graphql(LIST_QUERY,{"userName":username})
        user=data.get("User"); collection=data.get("MediaListCollection")
        if not user or not collection: raise AnalyzerError("User or public anime list was not found.")
        raw_entries=flatten_entries(collection)
        info=score_info(user)

        # Full list for recommendation exclusion, regardless of status or score.
        all_entries=normalize_entries(raw_entries,VALID_STATUSES,True,args.spoiler_tags,False,info)
        rows=normalize_entries(raw_entries,statuses,args.include_unrated,args.spoiler_tags,not args.no_staff,info)
        rated=[r for r in rows if r.get("rating") is not None]
        if not rated: raise AnalyzerError("No rated anime matched the selected statuses.")

        max_score=info["max"]; overall=statistics.fmean(r["rating"] for r in rated)
        stats={
            "genres":group_stats(rated,"genres",overall,max(3,args.min_count),max_score),
            "all_tags":group_stats(rated,"tags",overall,2,max_score),
            "studios":group_stats(rated,"studios",overall,max(3,args.min_count),max_score),
            "sources":group_stats(rated,"source",overall,max(3,args.min_count),max_score),
            "formats":group_stats(rated,"format",overall,max(3,args.min_count),max_score),
            "decades":group_stats(rated,"decade",overall,1,max_score),
            "staff":staff_stats(rated,overall,max(3,args.min_count),max_score) if not args.no_staff else [],
            "japanese_vas":voice_actor_stats(rated,"japanese",overall,2,max_score) if not args.no_staff else [],
            "english_vas":voice_actor_stats(rated,"english",overall,2,max_score) if not args.no_staff else [],
        }
        high_tag_stats=[s for s in stats["all_tags"] if s.count>=8]
        identity=build_identity_profile(rated,stats["genres"],high_tag_stats,overall,max_score)
        taste_glance=build_taste_at_glance(rated,stats["genres"],stats["all_tags"],overall,max_score)
        recs=fetch_recommendations(rated,all_entries,max_score,high_tag_stats,stats["genres"])
        rec_groups=categorize_recommendations(recs)

        out=Path(args.output or f"anilist_report_{safe_name(user['name'])}").resolve()
        out.mkdir(parents=True,exist_ok=True)
        html_path=out/"anime_taste_report.html"
        write_csv(rows,out/"anime_data.csv")
        write_json(user,rows,out/"anime_data.json")
        build_html(user,rated,all_entries,html_path,info,overall,stats,identity,taste_glance,rec_groups,not args.no_staff)

        print(f"\nHTML report: {html_path}")
        if not args.no_open: webbrowser.open(html_path.as_uri())
        return 0
    except (AnalyzerError,ValueError,KeyError) as exc:
        print(f"\nError: {exc}",file=sys.stderr); return 1
    except KeyboardInterrupt:
        print("\nCancelled."); return 130

if __name__=="__main__":
    raise SystemExit(main())
