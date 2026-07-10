AniList Taste Analyzer 1.2

Windows:
1. Double-click run_anime_analyzer.bat
2. Enter an AniList username
3. The HTML report opens automatically

Outputs:
- anime_taste_report.html
- anime_data.csv
- anime_data.json

Changes in 1.2:
- Genres ranked by adjusted top-rating rate
- Tags require at least 8 appearances by default
- New synthesized Taste Profile section
- Studios, staff, source material, formats, and decades are collapsible
- New recommendations section based on AniList recommendation links and taste overlap

Optional command-line examples:
  py anime_taste_analyzer.py username
  py anime_taste_analyzer.py username --no-staff
  py anime_taste_analyzer.py username --all-rated
  py anime_taste_analyzer.py username --min-count 10
