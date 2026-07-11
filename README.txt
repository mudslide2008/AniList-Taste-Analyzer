AniList Taste Analyzer 3.1.1

Image rendering hotfix
- Fixed malformed inline CSS variables used for hero and quote artwork.
- The previous output nested double quotes inside style="...", causing browsers
  to discard --hero-image and --quote-image silently.
- Image URLs now use single quotes inside CSS url(...).
- Bundled default artwork and custom artwork now render in both HTML and PNG.
- Added no-repeat to image backgrounds.

No cache rebuild is required.
