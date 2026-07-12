AniList Taste Analyzer 3.7.0

This release keeps the current report, share-card, and theme artwork design while making incomplete AniList ratings useful instead of excluding unrated shows from the analysis.

Analysis behavior
- Every completed matching anime contributes to watched counts, recurring tags, genres, staff, and voice-actor recurrence.
- Only scored anime contribute to averages, rating lift, top-rating rate, and other score-based calculations.
- Watched and rated counts are shown separately throughout the report and image exports.
- When at least 10 anime are rated and rating coverage is at least 35%, the established rating-first taste analysis remains in use.
- With sparse or zero ratings, the analyzer falls back to recurring patterns across the full viewing history rather than over-weighting a tiny scored sample.
- Voice actors can now appear based on roles across any watched shows, even when those shows are unrated.
- Recommendations use viewing-history evidence when the rating sample is sparse.

Artwork preserved unchanged
  assets/themes/exploration/hero_cover.png
  assets/themes/exploration/hero_social.png
  assets/themes/exploration/quote_banner.png

The distributable excludes generated reports, caches, Git metadata, and compiled Python files.


Version 3.8 additions
- The HTML report now ranks every title in Planning by likely taste fit.
- The ranking blends recurring viewing patterns, reliable rating correlations, and a smaller community-score tie-breaker.
- A planning_priority.csv file is written beside the normal report exports.
- Taste-cover signal icons now cover many more themes instead of falling back to the same star.
