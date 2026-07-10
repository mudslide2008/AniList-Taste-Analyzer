
from __future__ import annotations
import re, statistics
from collections import defaultdict

def confidence_label(count: int) -> str:
    if count >= 100: return "High"
    if count >= 40: return "Moderate"
    return "Early"

def build_identity_profile(rows, genres, tags, overall, max_score):
    ratings=[float(r["rating"]) for r in rows if r.get("rating") is not None]
    overall_top=sum(r>=max_score for r in ratings)/len(ratings)
    paragraphs=[]

    strong_genres=sorted([g for g in genres if g.count>=8],
        key=lambda g:(g.top_rate-overall_top,g.count), reverse=True)
    weak_genres=sorted([g for g in genres if g.count>=8],
        key=lambda g:(g.top_rate-overall_top,-g.count))
    strong_tags=sorted([t for t in tags if t.count>=8],
        key=lambda t:(t.top_rate-overall_top,t.count), reverse=True)

    positives=[t.name for t in strong_tags if t.top_rate-overall_top>=.10][:4]
    if positives:
        paragraphs.append(
            "The clearest pattern in this list is not a single genre, but a cluster of recurring themes. "
            + ", ".join(positives[:-1]) + (f", and {positives[-1]}" if len(positives)>1 else positives[0])
            + " appear disproportionately often among the highest-rated entries."
        )
    elif strong_genres:
        best=strong_genres[0]
        paragraphs.append(
            f"{best.name} is the most reliable broad category in this list, but genre alone is a weak predictor. "
            "The ratings vary more by execution and specific themes than by setting."
        )
    else:
        paragraphs.append("This list is broad enough that execution and theme appear to matter more than genre labels.")

    if strong_genres and weak_genres:
        best=strong_genres[0]; worst=weak_genres[0]
        if best.top_rate-overall_top>=.08 and worst.top_rate-overall_top<=-.08:
            paragraphs.append(
                f"{best.name} performs noticeably above the user's normal top-rating rate, while {worst.name} is less dependable. "
                "That does not mean either category is automatically good or bad; it shows which ones more often convert into favorites."
            )

    divergences=[r["rating"]-r["community_display"] for r in rows if r.get("community_display") is not None]
    if divergences:
        above=sum(d>max_score*.12 for d in divergences)
        below=sum(d<-max_score*.12 for d in divergences)
        mean_delta=statistics.fmean(divergences)
        if abs(mean_delta)<max_score*.04:
            paragraphs.append(
                f"Overall scoring stays fairly close to AniList consensus, but the list is not consensus-driven: "
                f"{above} entries sit notably above the community and {below} sit notably below it."
            )
        elif mean_delta>0:
            paragraphs.append("The user rates somewhat more generously than AniList overall, while still showing clear deal-breakers.")
        else:
            paragraphs.append("The user rates somewhat more critically than AniList overall, especially when a popular series loses momentum.")

    franchise_groups=defaultdict(list)
    for row in rows:
        base=re.sub(r"\b(season|part|cour|final season|the movie|movie|special)\b.*$","",row["title"],flags=re.I).strip(" :-–—")
        if len(base)>=4: franchise_groups[base].append(float(row["rating"]))
    swings=[vals for vals in franchise_groups.values() if len(vals)>=3 and max(vals)-min(vals)>=max_score*.35]
    if swings:
        paragraphs.append(
            "Franchise loyalty is limited: later seasons are not protected by earlier goodwill, and several long-running series move sharply up or down."
        )

    return paragraphs[:4]
