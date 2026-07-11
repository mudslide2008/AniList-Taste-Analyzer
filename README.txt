AniList Taste Analyzer 2.5

Share-cover redesign
- Replaced the custom bitmap font with Pillow and real system fonts.
- Proper pixel-measured word wrapping and spacing.
- Redesigned 1600x2200 taste_cover.png with:
  - big-picture taste summary
  - strongest signals
  - recurring creators
  - recurring Japanese VAs
  - community alignment
  - best recommendation match
- Removed redundant repeated statistics and signal lists.
- Retained a cleaner 1920x1080 share_card.png.
- Optional assets/cover_background.jpg or .png support.
- The Windows launcher automatically installs Pillow if needed.

Install manually if required:
  py -m pip install Pillow

No AniList cache rebuild is required.
