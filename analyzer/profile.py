
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


TASTE_ARCHETYPES = {
    "curiosity and mastery": {
        "Educational", "Work", "Drawing", "Writing", "Music", "Acting",
        "Photography", "Cooking", "Agriculture", "Medicine", "Economics",
        "Engineering", "Entrepreneurship", "Food", "Art", "School Club",
    },
    "exploration and discovery": {
        "Travel", "Adventure", "Survival", "Dungeon", "Space", "Environmental",
        "Mythology", "Historical", "Archaeology", "Outdoor", "Wilderness",
    },
    "personal growth and connection": {
        "Coming of Age", "Rehabilitation", "Found Family", "Family Life",
        "Bullying", "Mentorship", "Friendship", "Adoption", "Orphan",
    },
    "high-stakes intensity": {
        "Revenge", "Crime", "Death Game", "Gore", "Tragedy", "War",
        "Survival", "Assassins", "Terrorism", "Psychological",
    },
    "worldbuilding and systems": {
        "Politics", "Economics", "Kingdom Management", "Isekai", "Magic",
        "Military", "Strategy", "Urban Fantasy", "Mythology", "Dungeon",
    },
}

LOW_INFORMATION_PROFILE_TAGS = {
    "Snowscape", "Desert", "Coastal", "Urban", "Rural", "Foreign", "CGI",
    "Primarily Male Cast", "Primarily Female Cast", "Primarily Teen Cast",
    "Primarily Adult Cast", "Male Protagonist", "Female Protagonist",
    "Heterosexual", "Nudity", "Male Nudity", "Female Nudity",
}


def build_taste_at_glance(rows, genres, tags, overall, max_score):
    """Create a compact, shareable overview without pretending to read minds."""
    ratings=[float(row["rating"]) for row in rows if row.get("rating") is not None]
    overall_top=sum(value>=max_score for value in ratings)/len(ratings)

    useful_tags=[
        tag for tag in tags
        if tag.count>=5 and tag.name not in LOW_INFORMATION_PROFILE_TAGS
    ]

    archetype_scores=[]
    for label, names in TASTE_ARCHETYPES.items():
        matches=[tag for tag in useful_tags if tag.name in names]
        if not matches:
            continue
        score=sum(
            max(0.0, tag.top_rate-overall_top) * (tag.count/(tag.count+8.0))
            + max(0.0, tag.lift/max_score) * .35
            for tag in matches
        )
        if score>0:
            archetype_scores.append((score,label,matches))
    archetype_scores.sort(reverse=True,key=lambda item:item[0])

    if archetype_scores:
        primary=archetype_scores[0]
        secondary=archetype_scores[1] if len(archetype_scores)>1 else None
        if secondary and secondary[0]>=primary[0]*.55:
            headline=f"A taste built around {primary[1]}—with a strong pull toward {secondary[1]}."
        else:
            headline=f"A taste built around {primary[1]}."
        matched=sorted(primary[2],key=lambda tag:(tag.top_rate-overall_top,tag.count),reverse=True)
        examples=", ".join(tag.name for tag in matched[:3])
        summary=(
            f"The strongest recurring signals are {examples}. Broad genre labels matter, "
            "but specific themes and the way a story uses them are more predictive of a top rating."
        )
    else:
        eligible=[genre for genre in genres if genre.count>=8]
        eligible.sort(key=lambda genre:(genre.top_rate-overall_top,genre.count),reverse=True)
        if eligible and eligible[0].top_rate-overall_top>=.07:
            headline=f"Broad taste, with {eligible[0].name} as the most reliable anchor."
        else:
            headline="Broad taste driven more by execution than by genre."
        summary=(
            "No single theme dominates strongly enough to define the list. Ratings appear to depend "
            "more on individual execution, momentum, and character investment than on category alone."
        )

    divergences=[
        row["rating"]-row["community_display"]
        for row in rows if row.get("community_display") is not None
    ]
    notable=sum(abs(value)>max_score*.12 for value in divergences)
    alignment=(
        "Highly personal" if notable>=len(divergences)*.28
        else "Somewhat independent" if notable>=len(divergences)*.15
        else "Usually aligned"
    )

    return {
        "headline": headline,
        "summary": summary,
        "signals": [
            ("Top-rating rate", f"{overall_top:.0%}"),
            ("Community alignment", alignment),
            ("Evidence base", f"{len(ratings)} rated anime"),
        ],
    }
