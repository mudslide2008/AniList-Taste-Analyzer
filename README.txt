AniList Taste Analyzer 1.9.1

Windows
1. Replace the previous project files with this version.
2. Double-click run_anime_analyzer.bat.
3. Enter an AniList username.

Voice actor fixes
- The analyzer no longer trusts AniList's voiceActors(language: ...) filter.
- It fetches each cast once and classifies performers using Staff.languageV2.
- Japanese and English sections are therefore separated locally and explicitly.
- AniList character roles are retained as MAIN, SUPPORTING, or BACKGROUND.
- The report displays prominence totals and labels each listed character role.
- The VA cache schema was updated, so old v1.8 cast data is automatically ignored
  and downloaded again in batched form.
- Batched fetching and resumable caching from v1.8 remain intact.

Cache
- Stored in .anilist_cache/voice_actors.json
- Automatically refreshed because v1.9 uses cache version 2.
- To clear it manually:
  py main.py username --refresh-va-cache


1.9.1 hotfix
- Fixed malformed GraphQL batch query strings caused by literal \\n characters.
