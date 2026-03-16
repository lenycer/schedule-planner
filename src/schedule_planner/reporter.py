from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .generator import GeneratedSchedule, build_requirements
from .io_utils import CSV_ENCODING
from .models import Nurse, SchedulerConfig, parse_wanted_off_days
from .validator import summarize_schedule


WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]


def format_schedule_header(day) -> str:
    return f"{day.isoformat()}({WEEKDAY_LABELS[day.weekday()]})"


def format_team(team: str) -> str:
    return team


def format_assignment(code: str, nurse: Nurse, day) -> str:
    display_code = "W-O" if code == "O" and day.day in parse_wanted_off_days(nurse.wanted_off) else code
    return f"{display_code} ({nurse.competency_level} {format_team(nurse.team)})"


def write_schedule_csv(path: str | Path, schedule: GeneratedSchedule, nurses: list[Nurse]) -> None:
    with Path(path).open("w", encoding=CSV_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        headers = [
            "nurse_id",
            "name",
            *[format_schedule_header(day) for day in schedule.dates],
            "count_D",
            "count_E",
            "count_N",
            "count_P",
            "count_O",
        ]
        writer.writerow(headers)
        for nurse in nurses:
            row = schedule.assignments[nurse.nurse_id]
            writer.writerow(
                [
                    nurse.nurse_id,
                    nurse.name,
                    *[format_assignment(code, nurse, schedule.dates[index]) for index, code in enumerate(row)],
                    row.count("D"),
                    row.count("E"),
                    row.count("N"),
                    row.count("P"),
                    row.count("O"),
                ]
            )

        shift_labels = {
            "D": "일자별 D 수",
            "E": "일자별 E 수",
            "N": "일자별 N 수",
            "P": "일자별 P 수",
            "O": "일자별 O 수",
        }
        for shift in ("D", "E", "N", "P", "O"):
            daily_counts = [
                sum(1 for nurse in nurses if schedule.assignments[nurse.nurse_id][day_index] == shift)
                for day_index in range(len(schedule.dates))
            ]
            writer.writerow(
                [
                    f"COUNT_{shift}",
                    shift_labels[shift],
                    *daily_counts,
                    sum(daily_counts) if shift == "D" else "",
                    sum(daily_counts) if shift == "E" else "",
                    sum(daily_counts) if shift == "N" else "",
                    sum(daily_counts) if shift == "P" else "",
                    sum(daily_counts) if shift == "O" else "",
                ]
            )


def write_report_md(
    path: str | Path,
    schedule: GeneratedSchedule,
    nurses: list[Nurse],
    config: SchedulerConfig,
) -> None:
    summary = summarize_schedule(schedule, nurses, config)
    requirements = build_requirements(schedule.dates)
    lines = [
        f"# Schedule Report {config.year:04d}-{config.month:02d}",
        "",
        "## Result",
        f"- Hard constraint violations (validated): {0 if not schedule.hard_violations else len(schedule.hard_violations)}",
        f"- Soft penalty (patterns + P assignment preference + fairness): {schedule.soft_penalty}",
        f"- Nurse count: {len(nurses)}",
        "",
        "## Central Nurses",
        f"- Day center: {config.center_day_nurse_id}",
        f"- Evening center: {config.center_evening_nurse_id}",
        "",
        "## Per Nurse Summary",
        "| nurse_id | nights | max_consecutive_work | soft_penalty |",
        "| --- | ---: | ---: | ---: |",
    ]

    for nurse in nurses:
        nurse_summary = summary[nurse.nurse_id]
        lines.append(
            f"| {nurse.nurse_id} | {nurse_summary['nights']} | {nurse_summary['max_consecutive_work']} | {nurse_summary['soft_penalty']} |"
        )

    lines.extend(["", "## Daily Coverage", "| date | D | E | N | P | O |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for day_index, requirement in enumerate(requirements):
        counts = Counter(schedule.assignments[nurse.nurse_id][day_index] for nurse in nurses)
        lines.append(
            f"| {requirement.day.isoformat()} | {counts.get('D', 0)} | {counts.get('E', 0)} | {counts.get('N', 0)} | {counts.get('P', 0)} | {counts.get('O', 0)} |"
        )

    if schedule.hard_violations:
        lines.extend(["", "## Violations"])
        for violation in schedule.hard_violations:
            lines.append(f"- {violation}")
    else:
        lines.extend(["", "## Violations", "- none"])

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
