from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from ortools.sat.python import cp_model

from .models import DayRequirement, Nurse, SchedulerConfig


SHIFTS = ("D", "E", "N", "O", "P")
WORK_SHIFTS = ("D", "E", "N", "P")


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


def generate_schedule(config: SchedulerConfig, nurses: list[Nurse]) -> GeneratedSchedule:
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
    add_objective(model, shift_vars, nurses, dates)

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
    for day_idx, current in enumerate(dates):
        if current.weekday() < 5:
            model.Add(shift_vars[(day_center_idx, day_idx, "D")] == 1)
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
    for nurse_idx, nurse in enumerate(nurses):
        n_vars = [shift_vars[(nurse_idx, day_idx, "N")] for day_idx in range(total_days)]
        model.Add(sum(n_vars) <= nurse.max_nights_per_month)

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

        if nurse.team == "E":
            for day_idx, current in enumerate(dates):
                model.Add(shift_vars[(nurse_idx, day_idx, "D")] == 0)
                model.Add(shift_vars[(nurse_idx, day_idx, "N")] == 0)
                if current.weekday() < 5:
                    model.Add(shift_vars[(nurse_idx, day_idx, "E")] == 0)
                elif nurse.competency_level != 3:
                    model.Add(shift_vars[(nurse_idx, day_idx, "E")] == 0)

    for day_idx in range(total_days):
        for shift in ("D", "E", "N"):
            for team in regular_team_names:
                model.Add(
                    sum(
                        shift_vars[(nurse_idx, day_idx, shift)]
                        for nurse_idx, nurse in enumerate(nurses)
                        if nurse.team == team
                    )
                    >= 1
                )

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
            model.Add(
                sum(
                    shift_vars[(nurse_idx, day_idx, "E")]
                    for nurse_idx, nurse in enumerate(nurses)
                    if nurse.team == "E"
                )
                == 0
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
    nurses: list[Nurse],
    dates: list[date],
) -> None:
    total_days = len(dates)
    total_n_demand = sum(4 for _ in dates)
    total_work_demand = sum(16 if current.weekday() < 5 else 14 for current in dates)

    target_n_floor = total_n_demand // len(nurses)
    target_n_ceil = target_n_floor + (1 if total_n_demand % len(nurses) else 0)
    target_work_floor = total_work_demand // len(nurses)
    target_work_ceil = target_work_floor + (1 if total_work_demand % len(nurses) else 0)

    fairness_penalties: list[cp_model.IntVar] = []
    for nurse_idx, _ in enumerate(nurses):
        n_total = model.NewIntVar(0, total_days, f"n_total_{nurse_idx}")
        work_total = model.NewIntVar(0, total_days, f"work_total_{nurse_idx}")
        model.Add(n_total == sum(shift_vars[(nurse_idx, day_idx, "N")] for day_idx in range(total_days)))
        model.Add(work_total == sum(shift_vars[(nurse_idx, day_idx, shift)] for day_idx in range(total_days) for shift in WORK_SHIFTS))

        n_penalty = model.NewIntVar(0, total_days, f"n_penalty_{nurse_idx}")
        work_penalty = model.NewIntVar(0, total_days, f"work_penalty_{nurse_idx}")
        model.AddMaxEquality(n_penalty, [target_n_floor - n_total, n_total - target_n_ceil, 0])
        model.AddMaxEquality(work_penalty, [target_work_floor - work_total, work_total - target_work_ceil, 0])
        fairness_penalties.extend([n_penalty, work_penalty])

    non_e_team_p = []
    e_team_level3_p = []
    e_team_level2_p = []
    for nurse_idx, nurse in enumerate(nurses):
        for day_idx in range(total_days):
            if nurse.team != "E":
                non_e_team_p.append(shift_vars[(nurse_idx, day_idx, "P")])
            elif nurse.competency_level == 3:
                e_team_level3_p.append(shift_vars[(nurse_idx, day_idx, "P")])
            elif nurse.competency_level == 2:
                e_team_level2_p.append(shift_vars[(nurse_idx, day_idx, "P")])

    model.Minimize(
        10000 * sum(non_e_team_p)
        + 1000 * sum(e_team_level3_p)
        - 1000 * sum(e_team_level2_p)
        + sum(fairness_penalties)
    )
