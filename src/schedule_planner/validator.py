from __future__ import annotations

from collections import Counter

from .generator import GeneratedSchedule, allows_five_streak_exception, build_requirements
from .models import Nurse, SchedulerConfig, WORK_SHIFTS
from .rules import calculate_soft_penalty, weekly_hours


def validate_schedule(schedule: GeneratedSchedule, nurses: list[Nurse], config: SchedulerConfig) -> list[str]:
    violations: list[str] = []
    requirements = build_requirements(schedule.dates)
    nurse_by_id = {nurse.nurse_id: nurse for nurse in nurses}

    for nurse_id, row in schedule.assignments.items():
        violations.extend(validate_nurse_row(nurse_by_id[nurse_id], row))
        violations.extend(validate_five_streak_exception(nurse_by_id[nurse_id], row, schedule.dates, config))

    for day_index, requirement in enumerate(requirements):
        counts = Counter(schedule.assignments[nurse.nurse_id][day_index] for nurse in nurses)
        for shift, expected in requirement.demand.items():
            actual = counts.get(shift, 0)
            if actual != expected:
                violations.append(f"{requirement.day.isoformat()} {shift} 수요 불일치: expected={expected}, actual={actual}")
        violations.extend(validate_day_team_and_competency(schedule, nurses, day_index, requirement.day))

    for day_index, current in enumerate(schedule.dates):
        if current.weekday() < 5:
            if schedule.assignments[config.center_day_nurse_id][day_index] != "D":
                violations.append(f"{current.isoformat()} 데이 중앙 근무자 미배정")
            if schedule.assignments[config.center_evening_nurse_id][day_index] != "E":
                violations.append(f"{current.isoformat()} 이브 중앙 근무자 미배정")

    return violations


def validate_nurse_row(nurse: Nurse, row: list[str]) -> list[str]:
    violations: list[str] = []
    night_count = row.count("N")
    if night_count > nurse.max_nights_per_month:
        violations.append(f"{nurse.nurse_id} 월간 N 초과: {night_count}")

    consecutive_work = 0
    consecutive_n = 0
    for index, code in enumerate(row):
        if code in WORK_SHIFTS:
            consecutive_work += 1
        else:
            consecutive_work = 0

        if code == "N":
            consecutive_n += 1
        else:
            consecutive_n = 0

        if consecutive_work > nurse.max_consecutive_work_days:
            violations.append(f"{nurse.nurse_id} 연속근무 초과 at day {index + 1}")
        if consecutive_n > 3:
            violations.append(f"{nurse.nurse_id} 연속 N 초과 at day {index + 1}")

        if index >= 1 and row[index - 1] == "N" and code not in {"N", "O"}:
            violations.append(f"{nurse.nurse_id} N 다음날 금지 패턴 at day {index + 1}: N{code}")
        if index >= 1 and row[index - 1] == "E" and code == "D":
            violations.append(f"{nurse.nurse_id} ED 금지 패턴 at day {index + 1}")
        if index >= 2 and row[index - 2 : index + 1] == ["N", "O", "D"]:
            violations.append(f"{nurse.nurse_id} NOD 금지 패턴 at day {index + 1}")
        if index >= 2 and row[index - 2 : index + 1] == ["N", "O", "E"]:
            violations.append(f"{nurse.nurse_id} NOE 금지 패턴 at day {index + 1}")
        if index >= 2 and row[index - 2 : index + 1] == ["E", "O", "D"]:
            violations.append(f"{nurse.nurse_id} EOD 금지 패턴 at day {index + 1}")
        if index >= 2 and row[index - 2] == "O" and row[index - 1] in {"D", "E", "P"} and code == "O":
            violations.append(f"{nurse.nurse_id} O{row[index - 1]}O 금지 패턴 at day {index + 1}")

    for index in range(1, len(row) - 1):
        if row[index] == "N" and row[index - 1] != "N" and row[index + 1] != "N":
            violations.append(f"{nurse.nurse_id} 월중 단독 N 금지 패턴 at day {index + 1}")
        if row[index] == "O" and row[index - 1] == "N" and row[index + 1] != "O":
            streak = 1
            back = index - 2
            while back >= 0 and row[back] == "N":
                streak += 1
                back -= 1
            if streak >= 2:
                violations.append(f"{nurse.nurse_id} 2회 이상 N 이후 O 2개 미만 at day {index + 1}")

    for start, hours in enumerate(weekly_hours(row), start=1):
        if hours > 52:
            violations.append(f"{nurse.nurse_id} 주간 시간 초과 window={start}-{start + 6}: {hours}")

    return violations


def summarize_schedule(schedule: GeneratedSchedule, nurses: list[Nurse]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for nurse in nurses:
        row = schedule.assignments[nurse.nurse_id]
        summary[nurse.nurse_id] = {
            "days": row.count("D"),
            "evenings": row.count("E"),
            "nights": row.count("N"),
            "prns": row.count("P"),
            "offs": row.count("O"),
            "max_consecutive_work": max_consecutive_workdays(row),
            "soft_penalty": calculate_soft_penalty(row),
        }
    return summary


def max_consecutive_workdays(row: list[str]) -> int:
    best = 0
    current = 0
    for code in row:
        if code in WORK_SHIFTS:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def validate_five_streak_exception(
    nurse: Nurse,
    row: list[str],
    dates: list,
    config: SchedulerConfig,
) -> list[str]:
    violations: list[str] = []
    for shift in ("D", "E", "P"):
        for start in range(len(row) - 4):
            if row[start : start + 5] != [shift] * 5:
                continue
            if allows_five_streak_exception(config, nurse, dates[start : start + 5], shift):
                continue
            violations.append(f"{nurse.nurse_id} {shift} 5연속 금지 at day {start + 5}")
    return violations


def validate_day_team_and_competency(
    schedule: GeneratedSchedule,
    nurses: list[Nurse],
    day_index: int,
    day,
) -> list[str]:
    violations: list[str] = []
    team_names = sorted({nurse.team for nurse in nurses if nurse.team in {"A", "B", "C", "D"}})
    for shift in ("D", "E", "N"):
        for team in team_names:
            count = sum(
                1
                for nurse in nurses
                if nurse.team == team and schedule.assignments[nurse.nurse_id][day_index] == shift
            )
            if count == 0:
                violations.append(f"{day.isoformat()} {team} {shift} 미배정")

    e_team_evening_total = sum(
        1
        for nurse in nurses
        if nurse.team == "E" and schedule.assignments[nurse.nurse_id][day_index] == "E"
    )
    e_team_evening_level3 = sum(
        1
        for nurse in nurses
        if nurse.team == "E" and nurse.competency_level == 3 and schedule.assignments[nurse.nurse_id][day_index] == "E"
    )
    if day.weekday() >= 5:
        if e_team_evening_level3 != 1:
            violations.append(f"{day.isoformat()} E팀 주말 E 중앙 미충족")
        if e_team_evening_total != e_team_evening_level3:
            violations.append(f"{day.isoformat()} E팀 주말 E 역량3 외 배정")
    elif e_team_evening_total != 0:
        violations.append(f"{day.isoformat()} E팀 평일 E 배정 금지")

    for shift in ("D", "E", "N"):
        level3_count = sum(
            1
            for nurse in nurses
            if nurse.competency_level == 3 and schedule.assignments[nurse.nurse_id][day_index] == shift
        )
        if level3_count == 0:
            violations.append(f"{day.isoformat()} {shift} 역량3 미배정")

    for shift in ("D", "E", "N", "P"):
        level1_count = sum(
            1
            for nurse in nurses
            if nurse.competency_level == 1 and schedule.assignments[nurse.nurse_id][day_index] == shift
        )
        if level1_count >= 2:
            violations.append(f"{day.isoformat()} {shift} 역량1 2명 이상")

    for nurse in nurses:
        if nurse.competency_level == 1 and schedule.assignments[nurse.nurse_id][day_index] == "P":
            violations.append(f"{day.isoformat()} {nurse.nurse_id} P 근무 역량1 금지")
        if nurse.team == "E":
            code = schedule.assignments[nurse.nurse_id][day_index]
            if code in {"D", "N"}:
                violations.append(f"{day.isoformat()} {nurse.nurse_id} E팀 {code} 금지")
            if day.weekday() < 5 and code == "E":
                violations.append(f"{day.isoformat()} {nurse.nurse_id} E팀 평일 E 금지")
            if day.weekday() >= 5 and code == "E" and nurse.competency_level != 3:
                violations.append(f"{day.isoformat()} {nurse.nurse_id} E팀 주말 E 역량3 필요")

    return violations
