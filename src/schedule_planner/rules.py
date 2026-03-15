from __future__ import annotations

from .models import Nurse, SHIFT_HOURS, WORK_SHIFTS


def is_weekday(day_index: int, weekday: int) -> bool:
    return weekday < 5


def count_monthly_shift(schedule_row: list[str | None], shift: str) -> int:
    return sum(1 for code in schedule_row if code == shift)


def consecutive_shift_count(schedule_row: list[str | None], day_index: int, shift: str) -> int:
    count = 0
    for index in range(day_index, -1, -1):
        if schedule_row[index] == shift:
            count += 1
            continue
        break
    return count


def consecutive_workdays_after_assignment(schedule_row: list[str | None], day_index: int, shift: str) -> int:
    count = 0
    for index in range(day_index - 1, -1, -1):
        if schedule_row[index] in WORK_SHIFTS:
            count += 1
            continue
        break
    return count + (1 if shift in WORK_SHIFTS else 0)


def previous_codes(schedule_row: list[str | None], day_index: int) -> tuple[str | None, str | None]:
    prev_1 = schedule_row[day_index - 1] if day_index - 1 >= 0 else None
    prev_2 = schedule_row[day_index - 2] if day_index - 2 >= 0 else None
    return prev_1, prev_2


def code_at(schedule_row: list[str | None], index: int) -> str | None:
    if index < 0 or index >= len(schedule_row):
        return None
    return schedule_row[index]


def trailing_night_streak(schedule_row: list[str | None], end_index: int) -> int:
    count = 0
    for index in range(end_index, -1, -1):
        if schedule_row[index] == "N":
            count += 1
            continue
        break
    return count


def can_assign_shift(
    nurse: Nurse,
    schedule_row: list[str | None],
    day_index: int,
    shift: str,
    fixed_assignments: dict[int, str],
) -> bool:
    current = schedule_row[day_index]
    if current is not None and current != shift:
        return False
    if current == shift:
        return True

    fixed_shift = fixed_assignments.get(day_index)
    if fixed_shift and fixed_shift != shift:
        return False

    prev_1, prev_2 = previous_codes(schedule_row, day_index)
    prev_3 = code_at(schedule_row, day_index - 3)
    last_index = len(schedule_row) - 1

    if prev_1 == "N" and shift not in {"N", "O"}:
        return False
    if prev_1 == "E" and shift == "D":
        return False
    if prev_2 == "N" and prev_1 == "O" and shift == "E":
        return False
    if prev_2 == "N" and prev_1 == "O" and shift == "D":
        return False
    if prev_2 == "E" and prev_1 == "O" and shift == "D":
        return False
    if prev_2 == "O" and prev_1 in {"D", "E", "P"} and shift == "O":
        return False
    if prev_1 == "O" and prev_2 == "N" and trailing_night_streak(schedule_row, day_index - 2) >= 2 and shift != "O":
        return False
    if (
        shift == "O"
        and prev_1 == "N"
        and prev_2 != "N"
        and 0 < day_index - 1 < last_index
    ):
        return False

    if shift == "N":
        if count_monthly_shift(schedule_row, "N") >= nurse.max_nights_per_month:
            return False
        if consecutive_shift_count(schedule_row, day_index - 1, "N") >= 3:
            return False

    if shift in WORK_SHIFTS:
        if consecutive_workdays_after_assignment(schedule_row, day_index, shift) > nurse.max_consecutive_work_days:
            return False
        if shift in {"D", "E", "P"} and consecutive_shift_count(schedule_row, day_index - 1, shift) >= 4:
            return False

    return True


def weekly_hours(schedule_row: list[str]) -> list[int]:
    values: list[int] = []
    for start in range(len(schedule_row)):
        window = schedule_row[start : start + 7]
        if not window:
            continue
        values.append(sum(SHIFT_HOURS[code] for code in window))
    return values


def calculate_soft_penalty(schedule_row: list[str]) -> int:
    penalty = 0
    return penalty
