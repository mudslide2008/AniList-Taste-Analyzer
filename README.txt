AniList Taste Analyzer 3.6

Artwork composition fix
- Artwork is now composed directly into the exact final destination dimensions.
- Poster, social, and quote assets each have a dedicated right-side illustration region.
- A dark text-safe left region is baked into every extracted asset.
- The original artwork aspect ratio is preserved inside its intended region.
- CSS no longer crops or zooms the already composed images.
- Cache key changed so older malformed crops are ignored automatically.

This version was rendered and visually inspected before packaging.
