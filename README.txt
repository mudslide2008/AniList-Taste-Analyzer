AniList Taste Analyzer 3.3

Artwork pool and aspect-ratio fixes
- Includes three bundled scenic artwork sets.
- Different users receive different scenes based on a stable hash of username
  and strongest themes.
- The same user receives the same scene on later runs.
- Each scene has a separately cropped image for:
  - taste_cover.png hero
  - share_card.png hero
  - quote panel
- Artwork is no longer recropped from one universal background file.
- Custom artwork still overrides bundled scenes:
  assets/cover_background.jpg
  assets/social_background.jpg
  assets/quote_background.jpg
- AniList artwork remains a fallback only when no bundled/custom art exists.

No AniList or VA cache rebuild is required.
