AniList Taste Analyzer 2.6

Cover improvements
- Uses AniList banner/cover art automatically for the hero image.
- Uses the best recommendation's cover image in the highlights panel.
- Preserves staff portrait URLs where AniList provides them.
- Adds support for portrait rendering in creator rows.
- Uses measured, dynamic text heights so text stays inside panels.
- Keeps optional assets/cover_background.jpg or .png as an override.
- Reworked the cover layout to more closely match the polished dashboard reference.

Artwork selection order
1. assets/cover_background.jpg or .png
2. Banner art from a top-rated anime
3. Cover art from a top-rated anime
4. Best recommendation artwork
5. Built-in gradient fallback

No AniList cache rebuild is required, but existing cached raw anime exports will not
contain the new artwork fields until the analyzer is run again.
