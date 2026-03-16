from __future__ import annotations

from datetime import date

from .models import Nurse, SHIFT_HOURS, WORK_SHIFTS, parse_wanted_off_days


FIVE_STREAK_PENALTY = 5
NON_E_TEAM_P_PENALTY = 10000
E_TEAM_LEVEL3_P_PENALTY = 1000
E_TEAM_LEVEL3_D_PENALTY = 100


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


def calculate_soft_penalty(
    schedule_row: list[str],
    nurse: Nurse,
    dates: list[date],
    center_day_nurse_id: str,
    center_evening_nurse_id: str,
    day_center_off_days: set[int] | None = None,
) -> int:
    penalty = 0

    for shift in ("D", "E", "P"):
        for start in range(len(schedule_row) - 4):
            if schedule_row[start : start + 5] != [shift] * 5:
                continue
            if allows_five_streak_exception(
                nurse,
                dates[start : start + 5],
                shift,
                center_day_nurse_id,
                center_evening_nurse_id,
            ):
                continue
            penalty += FIVE_STREAK_PENALTY

    penalty += calculate_p_assignment_penalty(schedule_row, nurse)
    penalty += calculate_e_team_day_penalty(
        schedule_row,
        nurse,
        dates,
        day_center_off_days or set(),
    )
    return penalty


def calculate_p_assignment_penalty(schedule_row: list[str], nurse: Nurse) -> int:
    p_count = schedule_row.count("P")
    if p_count == 0:
        return 0
    if nurse.team != "E":
        return p_count * NON_E_TEAM_P_PENALTY
    if nurse.competency_level == 3:
        return p_count * E_TEAM_LEVEL3_P_PENALTY
    return 0


def calculate_e_team_day_penalty(
    schedule_row: list[str],
    nurse: Nurse,
    dates: list[date],
    day_center_off_days: set[int],
) -> int:
    if nurse.team != "E" or nurse.competency_level != 3:
        return 0
    penalty = 0
    for index, code in enumerate(schedule_row):
        if code != "D":
            continue
        if dates[index].day in day_center_off_days:
            continue
        penalty += E_TEAM_LEVEL3_D_PENALTY
    return penalty


def calculate_schedule_soft_penalty(
    assignments: dict[str, list[str]],
    nurses: list[Nurse],
    dates: list[date],
    center_day_nurse_id: str,
    center_evening_nurse_id: str,
) -> int:
    total_days = len(dates)
    total_n_demand = len(dates) * 4
    total_work_demand = sum(16 if current.weekday() < 5 else 14 for current in dates)
    nurse_by_id = {nurse.nurse_id: nurse for nurse in nurses}
    day_center_off_days = parse_wanted_off_days(nurse_by_id[center_day_nurse_id].wanted_off)

    penalty = 0
    for nurse in nurses:
        row = assignments[nurse.nurse_id]
        penalty += calculate_soft_penalty(
            row,
            nurse,
            dates,
            center_day_nurse_id,
            center_evening_nurse_id,
            day_center_off_days,
        )

    for nurse in nurses:
        row = assignments[nurse.nurse_id]
        penalty += calculate_fairness_penalty(row.count("N"), total_n_demand, len(nurses))
        work_total = sum(1 for code in row if code in WORK_SHIFTS)
        penalty += calculate_fairness_penalty(work_total, total_work_demand, len(nurses))

    return penalty


def calculate_fairness_penalty(actual: int, total_demand: int, nurse_count: int) -> int:
    floor_target = total_demand // nurse_count
    ceil_target = floor_target + (1 if total_demand % nurse_count else 0)
    if actual < floor_target:
        return floor_target - actual
    if actual > ceil_target:
        return actual - ceil_target
    return 0


def build_fairness_penalty(
    model,
    n_total,
    work_total,
    total_days: int,
    nurse_count: int,
    dates: list[date],
    nurse_idx: int,
):
    total_n_demand = len(dates) * 4
    total_work_demand = sum(16 if current.weekday() < 5 else 14 for current in dates)
    n_floor = total_n_demand // nurse_count
    n_ceil = n_floor + (1 if total_n_demand % nurse_count else 0)
    work_floor = total_work_demand // nurse_count
    work_ceil = work_floor + (1 if total_work_demand % nurse_count else 0)

    n_penalty = model.NewIntVar(0, total_days, f"n_penalty_{nurse_idx}")
    work_penalty = model.NewIntVar(0, total_days, f"work_penalty_{nurse_idx}")
    model.AddMaxEquality(n_penalty, [n_floor - n_total, n_total - n_ceil, 0])
    model.AddMaxEquality(work_penalty, [work_floor - work_total, work_total - work_ceil, 0])
    return [n_penalty, work_penalty]


def allows_five_streak_exception(
    nurse: Nurse,
    window_dates: list[date],
    shift: str,
    center_day_nurse_id: str,
    center_evening_nurse_id: str,
) -> bool:
    if len(window_dates) != 5 or any(current.weekday() >= 5 for current in window_dates):
        return False
    if shift == "D" and nurse.nurse_id == center_day_nurse_id:
        return True
    if shift == "E" and nurse.nurse_id == center_evening_nurse_id:
        return True
    return False
