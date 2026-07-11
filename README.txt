AniList Taste Analyzer 3.0

Share-cover renderer redesign
- Primary cover rendering now uses HTML/CSS through installed Edge or Chrome.
- Produces taste_cover.html, taste_cover.png, share_card.html, and share_card.png.
- Uses layered hero artwork, SVG icons, responsive panels, portraits, and recommendation art.
- Browser layout replaces manual Pillow box placement.
- Pillow remains an automatic fallback if browser rendering fails.

Requirements
- Pillow
- Playwright Python package
- Microsoft Edge or Google Chrome installed

The Windows launcher installs Python dependencies automatically.
