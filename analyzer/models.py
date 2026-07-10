
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class GroupStat:
    name: str
    count: int
    average: float
    lift: float
    top_rate: float
    ratings: list[float]
