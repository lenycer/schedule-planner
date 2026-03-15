from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .generator import generate_schedule
from .io_utils import load_config, load_nurses, write_nurse_pool
from .reporter import write_report_md, write_schedule_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate monthly nurse schedule.")
    parser.add_argument("--config", default="data/scheduler_config.sample.json")
    parser.add_argument("--nurse-pool", default="data/nurse_pool_sample.csv")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--nurse-count", type=int, default=24)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = replace(load_config(args.config), nurse_count=args.nurse_count)
    nurses = load_nurses(args.nurse_pool, config.nurse_count)

    if config.center_day_nurse_id not in {nurse.nurse_id for nurse in nurses}:
        raise SystemExit("center_day_nurse_id 가 nurse pool에 없습니다.")
    if config.center_evening_nurse_id not in {nurse.nurse_id for nurse in nurses}:
        raise SystemExit("center_evening_nurse_id 가 nurse pool에 없습니다.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_nurse_pool(output_dir / "nurse_pool_resolved.csv", nurses)

    schedule = generate_schedule(config, nurses)

    schedule_csv = output_dir / f"monthly_schedule_{config.year:04d}_{config.month:02d}.csv"
    report_md = output_dir / f"schedule_report_{config.year:04d}_{config.month:02d}.md"

    write_schedule_csv(schedule_csv, schedule, nurses)
    write_report_md(report_md, schedule, nurses, config)

    print(schedule_csv)
    print(report_md)


if __name__ == "__main__":
    main()
