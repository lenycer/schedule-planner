from __future__ import annotations

from dataclasses import dataclass
from datetime import date


SHIFT_CODES = ("D", "E", "N", "O", "P")
WORK_SHIFTS = {"D", "E", "N", "P"}
SHIFT_HOURS = {"D": 8, "E": 8, "N": 8, "P": 8, "O": 0}


@dataclass(frozen=True)
class Nurse:
    nurse_id: str
    name: str
    team: str = "UNASSIGNED"
    competency_level: int = 2
    employment_type: str = "FULL_TIME"
    max_nights_per_month: int = 8
    max_consecutive_work_days: int = 5


@dataclass(frozen=True)
class SchedulerConfig:
    year: int
    month: int
    nurse_count: int
    center_day_nurse_id: str
    center_evening_nurse_id: str
    random_seed: int = 7
    max_attempts: int = 5000


@dataclass(frozen=True)
class DayRequirement:
    day: date
    demand: dict[str, int]
