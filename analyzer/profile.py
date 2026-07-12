from __future__ import annotations
import re, statistics
from collections import defaultdict


def confidence_label(count: int) -> str:
    if count >= 100: return "High"
    if count >= 40: return "Moderate"
    return "Early"


def _rating_base(rows):
    ratings = [float(row["rating"]) for row in rows if row.get("rating") is not None]
    watched_count = len(rows)
    coverage = len(ratings) / watched_count if watched_count else 0.0
    return ratings, watched_count, coverage


def _strong_rating_base(rows) -> bool:
    ratings, watched_count, coverage = _rating_base(rows)
    return len(ratings) >= 10 and coverage >= .35


def build_identity_profile(rows, genres, tags, overall, max_score):
    ratings, watched_count, coverage = _rating_base(rows)
    rated_count = len(ratings)
    paragraphs = []

    if _strong_rating_base(rows):
        overall_top = sum(value >= max_score for value in ratings) / rated_count
        strong_genres = sorted(
            [genre for genre in genres if getattr(genre, "rated_count", 0) >= 8 and genre.top_rate is not None],
            key=lambda genre: (genre.top_rate - overall_top, genre.count),
            reverse=True,
        )
        weak_genres = sorted(
            [genre for genre in genres if getattr(genre, "rated_count", 0) >= 8 and genre.top_rate is not None],
            key=lambda genre: (genre.top_rate - overall_top, -genre.count),
        )
        strong_tags = sorted(
            [tag for tag in tags if getattr(tag, "rated_count", 0) >= 8 and tag.top_rate is not None],
            key=lambda tag: (tag.top_rate - overall_top, tag.count),
            reverse=True,
        )

        positives = [tag.name for tag in strong_tags if tag.top_rate - overall_top >= .10][:4]
        if positives:
            paragraphs.append(
                "The clearest pattern in this list is not a single genre, but a cluster of recurring themes. "
                + ", ".join(positives[:-1])
                + (f", and {positives[-1]}" if len(positives) > 1 else positives[0])
                + " appear disproportionately often among the highest-rated entries."
            )
        elif strong_genres:
            best = strong_genres[0]
            paragraphs.append(
                f"{best.name} is the most reliable broad category in this list, but genre alone is a weak predictor. "
                "The ratings vary more by execution and specific themes than by setting."
            )
        else:
            paragraphs.append("This list is broad enough that execution and theme appear to matter more than genre labels.")

        if strong_genres and weak_genres:
            best = strong_genres[0]
            worst = weak_genres[0]
            if best.top_rate - overall_top >= .08 and worst.top_rate - overall_top <= -.08:
                paragraphs.append(
                    f"{best.name} performs noticeably above the user's normal top-rating rate, while {worst.name} is less dependable. "
                    "That does not mean either category is automatically good or bad; it shows which ones more often convert into favorites."
                )
    else:
        recurring_tags = sorted(
            [tag for tag in tags if tag.count >= max(3, min(8, watched_count // 12 or 3))],
            key=lambda tag: (tag.count, getattr(tag, "rated_count", 0)),
            reverse=True,
        )
        recurring_genres = sorted(genres, key=lambda genre: genre.count, reverse=True)
        if recurring_tags:
            names = [tag.name for tag in recurring_tags[:4]]
            joined = ", ".join(names[:-1]) + (f", and {names[-1]}" if len(names) > 1 else names[0])
            paragraphs.append(
                f"Across the full {watched_count}-anime viewing history, the clearest recurring themes are {joined}. "
                "These describe what repeatedly appears in the list, whether or not every title was scored."
            )
        elif recurring_genres:
            names = [genre.name for genre in recurring_genres[:3]]
            paragraphs.append(
                "The viewing history is broad, but its most common genre anchors are " + ", ".join(names) + "."
            )
        else:
            paragraphs.append("The viewing history is broad enough that no single category dominates strongly.")

        if rated_count == 0:
            paragraphs.append(
                "None of the analyzed anime have a user rating, so this report focuses on viewing recurrence rather than claiming rating preferences."
            )
        else:
            paragraphs.append(
                f"Only {rated_count} of {watched_count} analyzed anime are rated ({coverage:.0%}). "
                "Those scores are still shown where useful, but they are not allowed to outweigh the much larger viewing history."
            )

    divergences = [
        row["rating"] - row["community_display"]
        for row in rows
        if row.get("rating") is not None and row.get("community_display") is not None
    ]
    if len(divergences) >= 5:
        above = sum(delta > max_score * .12 for delta in divergences)
        below = sum(delta < -max_score * .12 for delta in divergences)
        mean_delta = statistics.fmean(divergences)
        if abs(mean_delta) < max_score * .04:
            paragraphs.append(
                f"Overall scoring stays fairly close to AniList consensus, but the list is not consensus-driven: "
                f"{above} entries sit notably above the community and {below} sit notably below it."
            )
        elif mean_delta > 0:
            paragraphs.append("The user rates somewhat more generously than AniList overall, while still showing clear deal-breakers.")
        else:
            paragraphs.append("The user rates somewhat more critically than AniList overall, especially when a popular series loses momentum.")

    franchise_groups = defaultdict(list)
    for row in rows:
        if row.get("rating") is None:
            continue
        base = re.sub(r"\b(season|part|cour|final season|the movie|movie|special)\b.*$", "", row["title"], flags=re.I).strip(" :-–—")
        if len(base) >= 4:
            franchise_groups[base].append(float(row["rating"]))
    swings = [
        values for values in franchise_groups.values()
        if len(values) >= 3 and max(values) - min(values) >= max_score * .35
    ]
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
    """Create a compact overview without ignoring unrated viewing history."""
    ratings, watched_count, coverage = _rating_base(rows)
    rated_count = len(ratings)
    overall_top = sum(value >= max_score for value in ratings) / rated_count if rated_count else 0.0

    useful_tags = [
        tag for tag in tags
        if tag.count >= 5 and tag.name not in LOW_INFORMATION_PROFILE_TAGS
    ]

    if _strong_rating_base(rows):
        # Preserve the established behavior for well-rated lists. ``rated_count``
        # replaces raw occurrence count only when some entries are unrated.
        archetype_scores = []
        for label, names in TASTE_ARCHETYPES.items():
            matches = [
                tag for tag in useful_tags
                if tag.name in names and tag.top_rate is not None and tag.lift is not None
            ]
            if not matches:
                continue
            score = sum(
                max(0.0, tag.top_rate - overall_top)
                * (getattr(tag, "rated_count", tag.count) / (getattr(tag, "rated_count", tag.count) + 8.0))
                + max(0.0, tag.lift / max_score) * .35
                for tag in matches
            )
            if score > 0:
                archetype_scores.append((score, label, matches))
        archetype_scores.sort(reverse=True, key=lambda item: item[0])

        if archetype_scores:
            primary = archetype_scores[0]
            secondary = archetype_scores[1] if len(archetype_scores) > 1 else None
            if secondary and secondary[0] >= primary[0] * .55:
                headline = f"A taste built around {primary[1]}—with a strong pull toward {secondary[1]}."
            else:
                headline = f"A taste built around {primary[1]}."
            matched = sorted(
                primary[2],
                key=lambda tag: (tag.top_rate - overall_top, tag.count),
                reverse=True,
            )
            examples = ", ".join(tag.name for tag in matched[:3])
            themes = [tag.name for tag in matched[:4]]
            summary = (
                f"The strongest recurring signals are {examples}. Broad genre labels matter, "
                "but specific themes and the way a story uses them are more predictive of a top rating."
            )
        else:
            eligible = [genre for genre in genres if getattr(genre, "rated_count", 0) >= 8 and genre.top_rate is not None]
            eligible.sort(key=lambda genre: (genre.top_rate - overall_top, genre.count), reverse=True)
            if eligible and eligible[0].top_rate - overall_top >= .07:
                headline = f"Broad taste, with {eligible[0].name} as the most reliable anchor."
            else:
                headline = "Broad taste driven more by execution than by genre."
            themes = [genre.name for genre in eligible[:4]] if eligible else []
            summary = (
                "No single theme dominates strongly enough to define the list. Ratings appear to depend "
                "more on individual execution, momentum, and character investment than on category alone."
            )
    else:
        # Sparse ratings: base the identity on recurrence across every watched
        # entry and do not let a handful of scores define the whole profile.
        min_count = max(3, min(5, watched_count // 20 or 3))
        useful_tags = [
            tag for tag in tags
            if tag.count >= min_count and tag.name not in LOW_INFORMATION_PROFILE_TAGS
        ]

        def frequency_score(tag):
            return (tag.count / watched_count if watched_count else 0.0)

        archetype_scores = []
        for label, names in TASTE_ARCHETYPES.items():
            matches = [tag for tag in useful_tags if tag.name in names]
            if matches:
                archetype_scores.append((sum(frequency_score(tag) for tag in matches), label, matches))
        archetype_scores.sort(reverse=True, key=lambda item: item[0])

        if archetype_scores:
            primary = archetype_scores[0]
            secondary = archetype_scores[1] if len(archetype_scores) > 1 else None
            if secondary and secondary[0] >= primary[0] * .55:
                headline = f"A taste built around {primary[1]}—with a strong pull toward {secondary[1]}."
            else:
                headline = f"A taste built around {primary[1]}."
            matched = sorted(primary[2], key=lambda tag: (tag.count, tag.name), reverse=True)
            themes = [tag.name for tag in matched[:4]]
            examples = ", ".join(themes[:3])
            if rated_count:
                summary = (
                    f"Across the full viewing history, the most recurring signals are {examples}. "
                    "Because only part of the list is rated, this describes what they consistently watch without over-reading a small score sample."
                )
            else:
                summary = (
                    f"Across the full viewing history, the most recurring signals are {examples}. "
                    "With no user ratings available, this describes what they consistently watch rather than what they score highest."
                )
        else:
            eligible = sorted(genres, key=lambda genre: genre.count, reverse=True)
            themes = [genre.name for genre in eligible[:4]]
            if themes:
                headline = f"Broad taste, anchored by {themes[0]}."
                summary = (
                    "No single theme dominates strongly enough to define the list. The overview therefore emphasizes the categories that recur most across the full viewing history."
                )
            else:
                headline = "Broad taste driven more by individual shows than by category."
                summary = "There is not enough repeated category data to identify a dominant viewing pattern."

    divergences = [
        row["rating"] - row["community_display"]
        for row in rows
        if row.get("rating") is not None and row.get("community_display") is not None
    ]
    if len(divergences) >= 5:
        notable = sum(abs(value) > max_score * .12 for value in divergences)
        alignment = (
            "Highly personal" if notable >= len(divergences) * .28
            else "Somewhat independent" if notable >= len(divergences) * .15
            else "Usually aligned"
        )
    else:
        alignment = "Not enough ratings"

    return {
        "headline": headline,
        "summary": summary,
        "themes": themes,
        "watched_count": watched_count,
        "rated_count": rated_count,
        "rating_coverage": coverage,
        "signals": [
            ("Watched anime", str(watched_count)),
            ("Rated anime", str(rated_count)),
            ("Rating coverage", f"{coverage:.0%}"),
            ("Top-rating rate", f"{overall_top:.0%}" if rated_count else "—"),
            ("Community alignment", alignment),
        ],
    }
