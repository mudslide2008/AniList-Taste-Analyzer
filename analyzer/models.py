from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class GroupStat:
    """A recurring feature across the viewed list.

    ``count`` is the number of watched entries (or distinct franchises for
    voice actors). Rating fields only use entries that actually have a user
    score, and ``rated_count`` makes that coverage explicit.
    """

    name: str
    count: int
    average: float | None
    lift: float | None
    top_rate: float | None
    ratings: list[float] = field(default_factory=list)
    rated_count: int = 0
