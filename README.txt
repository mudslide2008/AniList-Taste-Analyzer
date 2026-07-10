AniList Taste Analyzer 1.9.5

Franchise deduplication fix
- The data layer already grouped connected seasons into franchises.
- The role-specific report formatter was accidentally replacing the franchise
  count with the number of season appearances.
- VA appearances now retain their franchise ID and franchise-level rating.
- Main, supporting, and background VA tables count distinct franchises.
- Multiple seasons remain visible as examples, but contribute only one count
  and one averaged rating per franchise.
- No voice actor cache rebuild is required for this update.
