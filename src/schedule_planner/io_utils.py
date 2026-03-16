from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import Nurse, SchedulerConfig


KOREAN_NAME_POOL = [
    "김하린", "이서윤", "박지우", "최도윤", "정하윤", "조시우", "윤서아", "한민재",
    "오유진", "서지호", "강나윤", "임준서", "신예린", "황지안", "송도현", "문서진",
    "백하은", "유태오", "남시아", "노현우", "고채원", "배지후", "주다은", "안서준",
    "마유나", "장예나", "차은호", "양지민", "허가온", "류서현",
]


CSV_ENCODING = "utf-8-sig"


def load_config(path: str | Path) -> SchedulerConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SchedulerConfig(
        year=data["year"],
        month=data["month"],
        nurse_count=data.get("nurse_count", 24),
        center_day_nurse_id=data["center_day_nurse_id"],
        center_evening_nurse_id=data["center_evening_nurse_id"],
        random_seed=data.get("random_seed", 7),
        max_attempts=data.get("max_attempts", 5000),
    )


def load_nurses(path: str | Path | None, nurse_count: int) -> list[Nurse]:
    if path and Path(path).exists():
        with Path(path).open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        nurses = [
            Nurse(
                nurse_id=row["nurse_id"],
                name=row["name"],
                team=row.get("team", "UNASSIGNED"),
                competency_level=int(row.get("competency_level", 2)),
                employment_type=row.get("employment_type", "FULL_TIME"),
                max_nights_per_month=int(row.get("max_nights_per_month", 8)),
                max_consecutive_work_days=int(row.get("max_consecutive_work_days", 5)),
                allowed_shift_types=row.get("allowed_shift_types", ""),
                wanted_off=row.get("wanted_off", ""),
            )
            for row in rows[:nurse_count]
        ]
        if len(nurses) >= nurse_count:
            return nurses
        generated = generate_random_nurses(nurse_count - len(nurses), start_index=len(nurses))
        return nurses + generated

    return generate_random_nurses(nurse_count)


def generate_random_nurses(nurse_count: int, start_index: int = 0) -> list[Nurse]:
    nurses: list[Nurse] = []
    for index in range(nurse_count):
        absolute_index = start_index + index
        name = KOREAN_NAME_POOL[absolute_index % len(KOREAN_NAME_POOL)]
        suffix = absolute_index // len(KOREAN_NAME_POOL)
        display_name = f"{name}{suffix + 1}" if suffix else name
        nurses.append(
            Nurse(
                nurse_id=f"N{absolute_index + 1:03d}",
                name=display_name,
                team="UNASSIGNED",
                competency_level=2,
            )
        )
    return nurses


def write_nurse_pool(path: str | Path, nurses: list[Nurse]) -> None:
    with Path(path).open("w", encoding=CSV_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "nurse_id",
                "name",
                "team",
                "competency_level",
                "employment_type",
                "max_nights_per_month",
                "max_consecutive_work_days",
                "allowed_shift_types",
                "wanted_off",
            ]
        )
        for nurse in nurses:
            writer.writerow(
                [
                    nurse.nurse_id,
                    nurse.name,
                    nurse.team,
                    nurse.competency_level,
                    nurse.employment_type,
                    nurse.max_nights_per_month,
                    nurse.max_consecutive_work_days,
                    nurse.allowed_shift_types,
                    nurse.wanted_off,
                ]
            )
