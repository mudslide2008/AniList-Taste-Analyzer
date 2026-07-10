AniList Taste Analyzer 1.8

Windows
1. Double-click run_anime_analyzer.bat
2. Enter an AniList username
3. The HTML report opens automatically

Voice actor changes in 1.8
- Voice cast is fetched in batches of 10 anime instead of one request per anime.
- A first run with 153 anime should usually need roughly 16 initial cast requests,
  plus a few extra requests only for anime with more than 50 listed characters.
- Voice actor results are cached in .anilist_cache/voice_actors.json.
- The cache is shared between users, so analyzing friends' lists reuses cast data.
- Cache progress is saved after every successful request.
- If AniList throttles or the program is interrupted, rerunning resumes from cache.
- Japanese and English performers retain their character and anime examples.
- Use --refresh-va-cache only when you intentionally want to download cast data again.

Other features retained
- Semantically informative tag insights
- Grounded recommendation explanations
- Creative staff rankings
- Japanese voice actors with an expandable English subset
- CSV and JSON exports

Optional examples
  py main.py username
  py main.py username --no-staff
  py main.py username --all-rated
  py main.py username --refresh-va-cache
