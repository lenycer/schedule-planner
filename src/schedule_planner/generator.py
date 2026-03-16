from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

try:
    from ortools.sat.python import cp_model
except ModuleNotFoundError:  # pragma: no cover - exercised in dependency-missing environments
    cp_model = None

from .models import DayRequirement, Nurse, SchedulerConfig, is_night_keep, parse_allowed_shift_types, parse_wanted_off_days
from .rules import (
    FIVE_STREAK_PENALTY,
    E_TEAM_LEVEL3_D_PENALTY,
    E_TEAM_LEVEL3_P_PENALTY,
    NON_E_TEAM_P_PENALTY,
    build_fairness_penalty,
)


SHIFTS = ("D", "E", "N", "O", "P")
WORK_SHIFTS = ("D", "E", "N", "P")
NIGHT_KEEP_MONTHLY_N_TARGET = 15
TEAM_DAILY_COVER_PENALTY = 3


@dataclass
class GeneratedSchedule:
    dates: list[date]
    assignments: dict[str, list[str]]
    hard_violations: list[str]
    soft_penalty: int


def build_month_dates(year: int, month: int) -> list[date]:
    _, last_day = calendar.monthrange(year, month)
    return [date(year, month, day) for day in range(1, last_day + 1)]


def build_requirements(dates: list[date]) -> list[DayRequirement]:
    requirements: list[DayRequirement] = []
    for current in dates:
        if current.weekday() < 5:
            demand = {"D": 6, "E": 5, "N": 4, "P": 1}
        else:
            demand = {"D": 4, "E": 5, "N": 4, "P": 1}
        requirements.append(DayRequirement(day=current, demand=demand))
    return requirements


def can_work_shift_on_day(
    nurse: Nurse,
    shift: str,
    current: date,
    config: SchedulerConfig,
    day_center_off_days: set[int],
    evening_center_off_days: set[int],
) -> bool:
    if shift == "O":
        return True
    if current.day in parse_wanted_off_days(nurse.wanted_off):
        return False

    allowed_shift_types = parse_allowed_shift_types(nurse.allowed_shift_types)
    if allowed_shift_types and shift not in allowed_shift_types:
        return False

    if nurse.competency_level == 1 and shift == "P":
        return False

    if nurse.nurse_id == config.center_day_nurse_id:
        return shift == "D" and (current.weekday() < 5 and current.day not in day_center_off_days)

    if nurse.nurse_id == config.center_evening_nurse_id:
        return shift == "E" and (current.weekday() < 5 and current.day not in evening_center_off_days)

    if nurse.team == "E":
        if shift == "N":
            return False
        if shift == "E":
            if current.weekday() >= 5:
                return nurse.competency_level == 3
            return current.day in evening_center_off_days and nurse.competency_level == 3

    return True


def max_assignable_days_in_segment(length: int, max_consecutive_work_days: int) -> int:
    if length <= 0:
        return 0
    cycle = max_consecutive_work_days + 1
    full_cycles, remainder = divmod(length, cycle)
    return full_cycles * max_consecutive_work_days + min(remainder, max_consecutive_work_days)


def estimate_nurse_shift_capacity(
    nurse: Nurse,
    shift: str,
    dates: list[date],
    config: SchedulerConfig,
    day_center_off_days: set[int],
    evening_center_off_days: set[int],
) -> int:
    eligible_days = [
        can_work_shift_on_day(
            nurse,
            shift,
            current,
            config,
            day_center_off_days,
            evening_center_off_days,
        )
        for current in dates
    ]
    capacity = 0
    current_segment = 0
    for eligible in eligible_days + [False]:
        if eligible:
            current_segment += 1
            continue
        capacity += max_assignable_days_in_segment(current_segment, nurse.max_consecutive_work_days)
        current_segment = 0
    if shift == "N":
        if is_night_keep(nurse):
            return min(capacity, NIGHT_KEEP_MONTHLY_N_TARGET)
        return min(capacity, nurse.max_nights_per_month)
    return capacity


def estimate_team_shift_capacity(
    nurses: list[Nurse],
    team: str,
    shift: str,
    dates: list[date],
    config: SchedulerConfig,
    day_center_off_days: set[int],
    evening_center_off_days: set[int],
) -> int:
    return sum(
        estimate_nurse_shift_capacity(
            nurse,
            shift,
            dates,
            config,
            day_center_off_days,
            evening_center_off_days,
        )
        for nurse in nurses
        if nurse.team == team
    )


def generate_schedule(config: SchedulerConfig, nurses: list[Nurse]) -> GeneratedSchedule:
    if cp_model is None:
        raise RuntimeError("ortools 가 설치되지 않아 스케줄을 생성할 수 없습니다. `pip install -r requirements.txt` 를 먼저 실행하세요.")

    dates = build_month_dates(config.year, config.month)
    requirements = build_requirements(dates)
    model = cp_model.CpModel()

    nurse_ids = [nurse.nurse_id for nurse in nurses]
    nurse_index = {nurse_id: index for index, nurse_id in enumerate(nurse_ids)}
    shift_vars: dict[tuple[int, int, str], cp_model.IntVar] = {}

    for nurse_idx, _ in enumerate(nurses):
        for day_idx, _ in enumerate(dates):
            for shift in SHIFTS:
                shift_vars[(nurse_idx, day_idx, shift)] = model.NewBoolVar(f"x_{nurse_idx}_{day_idx}_{shift}")

    for nurse_idx, _ in enumerate(nurses):
        for day_idx, _ in enumerate(dates):
            model.AddExactlyOne(shift_vars[(nurse_idx, day_idx, shift)] for shift in SHIFTS)

    for day_idx, requirement in enumerate(requirements):
        for shift in ("D", "E", "N", "P"):
            model.Add(sum(shift_vars[(nurse_idx, day_idx, shift)] for nurse_idx in range(len(nurses))) == requirement.demand[shift])

    apply_fixed_assignments(model, shift_vars, config, nurses, dates, nurse_index)
    apply_hard_constraints(model, shift_vars, config, nurses, dates)
    add_objective(model, shift_vars, config, nurses, dates)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = config.random_seed

    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        raise RuntimeError("유효한 스케줄을 생성하지 못했습니다. 설정 또는 인원 수를 조정하세요.")

    assignments: dict[str, list[str]] = {}
    for nurse_idx, nurse in enumerate(nurses):
        row: list[str] = []
        for day_idx, _ in enumerate(dates):
            for shift in SHIFTS:
                if solver.Value(shift_vars[(nurse_idx, day_idx, shift)]):
                    row.append(shift)
                    break
        assignments[nurse.nurse_id] = row

    objective_value = int(solver.ObjectiveValue()) if status == cp_model.OPTIMAL else int(solver.ObjectiveValue())
    return GeneratedSchedule(dates=dates, assignments=assignments, hard_violations=[], soft_penalty=objective_value)


def apply_fixed_assignments(
    model: cp_model.CpModel,
    shift_vars: dict[tuple[int, int, str], cp_model.IntVar],
    config: SchedulerConfig,
    nurses: list[Nurse],
    dates: list[date],
    nurse_index: dict[str, int],
) -> None:
    day_center_idx = nurse_index[config.center_day_nurse_id]
    evening_center_idx = nurse_index[config.center_evening_nurse_id]
    nurse_by_id = {nurse.nurse_id: nurse for nurse in nurses}
    day_center_off_days = parse_wanted_off_days(nurse_by_id[config.center_day_nurse_id].wanted_off)
    evening_center_off_days = parse_wanted_off_days(nurse_by_id[config.center_evening_nurse_id].wanted_off)
    for day_idx, current in enumerate(dates):
        if current.weekday() < 5:
            if current.day not in day_center_off_days:
                model.Add(shift_vars[(day_center_idx, day_idx, "D")] == 1)
            if current.day not in evening_center_off_days:
                model.Add(shift_vars[(evening_center_idx, day_idx, "E")] == 1)


def apply_hard_constraints(
    model: cp_model.CpModel,
    shift_vars: dict[tuple[int, int, str], cp_model.IntVar],
    config: SchedulerConfig,
    nurses: list[Nurse],
    dates: list[date],
) -> None:
    total_days = len(dates)
    regular_team_names = sorted({nurse.team for nurse in nurses if nurse.team in {"A", "B", "C", "D"}})
    day_center_off_days = parse_wanted_off_days(next(nurse.wanted_off for nurse in nurses if nurse.nurse_id == config.center_day_nurse_id))
    evening_center_off_days = parse_wanted_off_days(next(nurse.wanted_off for nurse in nurses if nurse.nurse_id == config.center_evening_nurse_id))

    for nurse_idx, nurse in enumerate(nurses):
        allowed_shift_types = parse_allowed_shift_types(nurse.allowed_shift_types)
        wanted_off_days = parse_wanted_off_days(nurse.wanted_off)
        n_vars = [shift_vars[(nurse_idx, day_idx, "N")] for day_idx in range(total_days)]
        if is_night_keep(nurse):
            model.Add(sum(n_vars) == NIGHT_KEEP_MONTHLY_N_TARGET)
        else:
            model.Add(sum(n_vars) <= nurse.max_nights_per_month)

        for day_idx, current in enumerate(dates):
            if wanted_off_days and current.day in wanted_off_days:
                model.Add(shift_vars[(nurse_idx, day_idx, "O")] == 1)
            if allowed_shift_types:
                for shift in WORK_SHIFTS:
                    if shift not in allowed_shift_types:
                        model.Add(shift_vars[(nurse_idx, day_idx, shift)] == 0)

        work_vars = [sum(shift_vars[(nurse_idx, day_idx, shift)] for shift in WORK_SHIFTS) for day_idx in range(total_days)]

        for start in range(total_days - 5):
            model.Add(sum(work_vars[start : start + 6]) <= nurse.max_consecutive_work_days)

        for start in range(total_days - 3):
            model.Add(sum(n_vars[start : start + 4]) <= 3)

        for day_idx in range(total_days - 1):
            model.Add(shift_vars[(nurse_idx, day_idx, "N")] + shift_vars[(nurse_idx, day_idx + 1, "D")] <= 1)
            model.Add(shift_vars[(nurse_idx, day_idx, "N")] + shift_vars[(nurse_idx, day_idx + 1, "E")] <= 1)
            model.Add(shift_vars[(nurse_idx, day_idx, "N")] + shift_vars[(nurse_idx, day_idx + 1, "P")] <= 1)
            model.Add(shift_vars[(nurse_idx, day_idx, "E")] + shift_vars[(nurse_idx, day_idx + 1, "D")] <= 1)

        for day_idx in range(1, total_days - 1):
            model.Add(shift_vars[(nurse_idx, day_idx, "N")] <= shift_vars[(nurse_idx, day_idx - 1, "N")] + shift_vars[(nurse_idx, day_idx + 1, "N")])

        for day_idx in range(total_days - 2):
            model.Add(
                shift_vars[(nurse_idx, day_idx, "N")]
                + shift_vars[(nurse_idx, day_idx + 1, "O")]
                + shift_vars[(nurse_idx, day_idx + 2, "D")]
                <= 2
            )
            model.Add(
                shift_vars[(nurse_idx, day_idx, "N")]
                + shift_vars[(nurse_idx, day_idx + 1, "O")]
                + shift_vars[(nurse_idx, day_idx + 2, "E")]
                <= 2
            )
            model.Add(
                shift_vars[(nurse_idx, day_idx, "E")]
                + shift_vars[(nurse_idx, day_idx + 1, "O")]
                + shift_vars[(nurse_idx, day_idx + 2, "D")]
                <= 2
            )
            for shift in ("D", "E", "P"):
                model.Add(
                    shift_vars[(nurse_idx, day_idx, "O")]
                    + shift_vars[(nurse_idx, day_idx + 1, shift)]
                    + shift_vars[(nurse_idx, day_idx + 2, "O")]
                    <= 2
                )

        for day_idx in range(2, total_days - 1):
            model.Add(
                shift_vars[(nurse_idx, day_idx - 2, "N")]
                + shift_vars[(nurse_idx, day_idx - 1, "N")]
                + shift_vars[(nurse_idx, day_idx, "O")]
                - 2
                <= shift_vars[(nurse_idx, day_idx + 1, "O")]
            )

        for shift in ("D", "E", "P"):
            for start in range(total_days - 4):
                if allows_five_streak_exception(config, nurses[nurse_idx], dates[start : start + 5], shift):
                    continue
                model.Add(sum(shift_vars[(nurse_idx, day_idx, shift)] for day_idx in range(start, start + 5)) <= 4)

        for start in range(total_days - 6):
            weekly_hours = []
            for day_idx in range(start, start + 7):
                day_hours = model.NewIntVar(0, 8, f"hours_{nurse_idx}_{day_idx}")
                model.Add(day_hours == 8 * sum(shift_vars[(nurse_idx, day_idx, shift)] for shift in WORK_SHIFTS))
                weekly_hours.append(day_hours)
            model.Add(sum(weekly_hours) <= 52)

        if nurse.competency_level == 1:
            for day_idx in range(total_days):
                model.Add(shift_vars[(nurse_idx, day_idx, "P")] == 0)

        if nurse.nurse_id == config.center_day_nurse_id:
            for day_idx in range(total_days):
                model.Add(shift_vars[(nurse_idx, day_idx, "E")] == 0)
                model.Add(shift_vars[(nurse_idx, day_idx, "N")] == 0)
                model.Add(shift_vars[(nurse_idx, day_idx, "P")] == 0)

        if nurse.nurse_id == config.center_evening_nurse_id:
            for day_idx in range(total_days):
                model.Add(shift_vars[(nurse_idx, day_idx, "D")] == 0)
                model.Add(shift_vars[(nurse_idx, day_idx, "N")] == 0)
                model.Add(shift_vars[(nurse_idx, day_idx, "P")] == 0)

        if nurse.team == "E":
            for day_idx, current in enumerate(dates):
                model.Add(shift_vars[(nurse_idx, day_idx, "N")] == 0)
                if current.weekday() < 5 and current.day not in evening_center_off_days:
                    model.Add(shift_vars[(nurse_idx, day_idx, "E")] == 0)
                elif nurse.competency_level != 3:
                    model.Add(shift_vars[(nurse_idx, day_idx, "E")] == 0)

    for team in regular_team_names:
        for shift in ("D", "E", "N"):
            team_capacity = estimate_team_shift_capacity(
                nurses,
                team,
                shift,
                dates,
                config,
                day_center_off_days,
                evening_center_off_days,
            )
            if team_capacity >= total_days:
                model.Add(
                    sum(
                        shift_vars[(nurse_idx, day_idx, shift)]
                        for nurse_idx, nurse in enumerate(nurses)
                        if nurse.team == team
                        for day_idx in range(total_days)
                    )
                    >= total_days
                )

    for day_idx in range(total_days):

        if dates[day_idx].weekday() >= 5:
            model.Add(
                sum(
                    shift_vars[(nurse_idx, day_idx, "E")]
                    for nurse_idx, nurse in enumerate(nurses)
                    if nurse.team == "E" and nurse.competency_level == 3
                )
                == 1
            )
        else:
            weekday_e_team_evening = sum(
                shift_vars[(nurse_idx, day_idx, "E")]
                for nurse_idx, nurse in enumerate(nurses)
                if nurse.team == "E"
            )
            weekday_e_team_evening_level3 = sum(
                shift_vars[(nurse_idx, day_idx, "E")]
                for nurse_idx, nurse in enumerate(nurses)
                if nurse.team == "E" and nurse.competency_level == 3
            )
            if dates[day_idx].day in evening_center_off_days:
                model.Add(weekday_e_team_evening_level3 == 1)
                model.Add(weekday_e_team_evening == weekday_e_team_evening_level3)
            else:
                model.Add(weekday_e_team_evening == 0)

        if dates[day_idx].weekday() < 5 and dates[day_idx].day in day_center_off_days:
            model.Add(
                sum(
                    shift_vars[(nurse_idx, day_idx, "D")]
                    for nurse_idx, nurse in enumerate(nurses)
                    if nurse.team == "E" and nurse.competency_level == 3
                )
                >= 1
            )

        for shift in ("D", "E", "N"):
            model.Add(
                sum(
                    shift_vars[(nurse_idx, day_idx, shift)]
                    for nurse_idx, nurse in enumerate(nurses)
                    if nurse.competency_level == 3
                )
                >= 1
            )

        for shift in ("D", "E", "N", "P"):
            model.Add(
                sum(
                    shift_vars[(nurse_idx, day_idx, shift)]
                    for nurse_idx, nurse in enumerate(nurses)
                    if nurse.competency_level == 1
                )
                <= 1
            )


def allows_five_streak_exception(
    config: SchedulerConfig,
    nurse: Nurse,
    window_dates: list[date],
    shift: str,
) -> bool:
    if len(window_dates) != 5 or any(current.weekday() >= 5 for current in window_dates):
        return False
    if shift == "D" and nurse.nurse_id == config.center_day_nurse_id:
        return True
    if shift == "E" and nurse.nurse_id == config.center_evening_nurse_id:
        return True
    return False


def add_objective(
    model: cp_model.CpModel,
    shift_vars: dict[tuple[int, int, str], cp_model.IntVar],
    config: SchedulerConfig,
    nurses: list[Nurse],
    dates: list[date],
) -> None:
    total_days = len(dates)
    day_center_off_days = parse_wanted_off_days(next(nurse.wanted_off for nurse in nurses if nurse.nurse_id == config.center_day_nurse_id))
    fairness_penalties: list[cp_model.IntVar] = []
    assignment_penalties: list[cp_model.IntVar] = []
    team_cover_penalties: list[cp_model.IntVar] = []
    regular_team_names = sorted({nurse.team for nurse in nurses if nurse.team in {"A", "B", "C", "D"}})

    for nurse_idx, _ in enumerate(nurses):
        n_total = model.NewIntVar(0, total_days, f"n_total_{nurse_idx}")
        work_total = model.NewIntVar(0, total_days, f"work_total_{nurse_idx}")
        model.Add(n_total == sum(shift_vars[(nurse_idx, day_idx, "N")] for day_idx in range(total_days)))
        model.Add(work_total == sum(shift_vars[(nurse_idx, day_idx, shift)] for day_idx in range(total_days) for shift in WORK_SHIFTS))

        fairness_penalties.extend(
            build_fairness_penalty(model, n_total, work_total, total_days, len(nurses), dates, nurse_idx)
        )

    for nurse_idx, nurse in enumerate(nurses):
        for day_idx in range(total_days):
            p_assignment = shift_vars[(nurse_idx, day_idx, "P")]
            if nurse.team != "E":
                assignment_penalties.append(_weighted_term(model, p_assignment, NON_E_TEAM_P_PENALTY, f"non_e_team_p_{nurse_idx}_{day_idx}"))
            elif nurse.competency_level == 3:
                assignment_penalties.append(_weighted_term(model, p_assignment, E_TEAM_LEVEL3_P_PENALTY, f"e_team_lvl3_p_{nurse_idx}_{day_idx}"))
                if dates[day_idx].day not in day_center_off_days:
                    assignment_penalties.append(
                        _weighted_term(
                            model,
                            shift_vars[(nurse_idx, day_idx, "D")],
                            E_TEAM_LEVEL3_D_PENALTY,
                            f"e_team_lvl3_d_{nurse_idx}_{day_idx}",
                        )
                    )

        for shift in ("D", "E", "P"):
            for start in range(total_days - 4):
                if allows_five_streak_exception(config, nurse, dates[start : start + 5], shift):
                    continue
                assignment_penalties.append(
                    _pattern_penalty(
                        model,
                        [shift_vars[(nurse_idx, day_idx, shift)] for day_idx in range(start, start + 5)],
                        FIVE_STREAK_PENALTY,
                        f"{shift.lower()}_streak_{nurse_idx}_{start}",
                    )
                )

    for day_idx in range(total_days):
        for shift in ("D", "E", "N"):
            for team in regular_team_names:
                team_count = sum(
                    shift_vars[(nurse_idx, day_idx, shift)]
                    for nurse_idx, nurse in enumerate(nurses)
                    if nurse.team == team
                )
                missing_team_shift = model.NewBoolVar(f"missing_{team}_{shift}_{day_idx}")
                model.Add(team_count == 0).OnlyEnforceIf(missing_team_shift)
                model.Add(team_count >= 1).OnlyEnforceIf(missing_team_shift.Not())
                team_cover_penalties.append(
                    _weighted_term(
                        model,
                        missing_team_shift,
                        TEAM_DAILY_COVER_PENALTY,
                        f"missing_{team}_{shift}_{day_idx}",
                    )
                )

    model.Minimize(
        sum(assignment_penalties)
        + sum(fairness_penalties)
        + sum(team_cover_penalties)
    )


def _pattern_penalty(
    model: cp_model.CpModel,
    variables: list[cp_model.IntVar],
    weight: int,
    name: str,
) -> cp_model.IntVar:
    indicator = model.NewBoolVar(f"{name}_hit")
    model.AddBoolAnd(variables).OnlyEnforceIf(indicator)
    model.AddBoolOr([variable.Not() for variable in variables]).OnlyEnforceIf(indicator.Not())
    return _weighted_term(model, indicator, weight, name)


def _weighted_term(
    model: cp_model.CpModel,
    source_var: cp_model.IntVar,
    weight: int,
    name: str,
) -> cp_model.IntVar:
    weighted = model.NewIntVar(0, weight, f"{name}_weighted")
    model.Add(weighted == weight * source_var)
    return weighted
