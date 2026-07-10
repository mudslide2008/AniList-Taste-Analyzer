AniList Taste Analyzer 1.4

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
