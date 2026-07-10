AniList Taste Analyzer 1.7

Windows
1. Double-click run_anime_analyzer.bat
2. Enter an AniList username
3. The HTML report opens automatically

What changed in 1.4
- Split the project into maintainable modules
- Recommendations exclude every anime already present anywhere on the user's AniList
- Recommendations are divided into Best Matches, Hidden Gems, Because You Loved…, and Outside Your Comfort Zone
- Taste Profile rewritten as short analytical prose
- Tags are separated into high-, medium-, and low-confidence sections
- Subtle confidence label added to the Taste Profile
- Existing CSV and JSON exports preserved

Project layout
- main.py
- run_anime_analyzer.bat
- analyzer/api.py
- analyzer/data.py
- analyzer/profile.py
- analyzer/recommendations.py
- analyzer/report.py
- analyzer/exports.py
- analyzer/queries.py
- analyzer/util.py

Optional examples
  py main.py username
  py main.py username --no-staff
  py main.py username --all-rated
  py main.py username --min-count 10


What changed in 1.5
- Best Matches remains visible; other recommendation categories are collapsed
- Tags are ranked by usefulness, combining predictive impact and sample reliability
- Full tag ranking remains expandable
- Creative Staff is restored as a prominent section
- Added recurring Japanese voice actors
- Added expandable English voice actor rankings


What changed in 1.6
- Main tag ranking now favors semantically informative tags, not just correlation
- Descriptive tags such as Snowscape remain visible in a raw-correlation table
- Voice actor fetching now paginates through up to 150 character credits per anime
- Japanese and English VA tables now require only two recurring anime
- Recommendation explanations cite actual favorite seed shows and meaningful overlap
- Generic or unsupported recommendation claims were removed

Voice actor overhaul in 1.7
- Fetches cast per anime rather than through the unreliable multi-anime nested query.
- Follows character pagination up to 300 credits per title.
- Tracks the character names associated with each Japanese and English performer.
- Displays concrete role evidence beside recurring actors.
- Recurring performers still require appearances in at least two rated anime.
