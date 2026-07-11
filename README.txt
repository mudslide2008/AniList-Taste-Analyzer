AniList Taste Analyzer 2.7

Share-image fixes
- Hero artwork is chosen by overlap with the report's strongest themes, not just
  by popularity among top-rated shows.
- The social card now uses artwork on the right and fills its lower section with
  themes and the best recommendation instead of leaving a large empty area.
- Japanese VA portraits are now fetched and cached.
- Missing portraits display initials instead of empty circles.
- Creator/VA rows wrap names and roles safely.
- Lower cover panels use content-driven heights instead of fixed 700px boxes.
- The cover is cropped to its actual content height, removing dead space.
- Recommendation cover art is larger and better integrated.
- Existing custom assets/cover_background.jpg or .png still override automatic art.

The VA cache schema changed, so the analyzer will rebuild voice-actor cache data once.
