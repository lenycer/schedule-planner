import unittest

from schedule_planner.generator import GeneratedSchedule, build_month_dates
from schedule_planner.models import Nurse, SchedulerConfig
from schedule_planner.validator import validate_schedule


class ValidatorTest(unittest.TestCase):
    def test_validate_schedule_detects_forbidden_patterns(self) -> None:
        nurses = [
            Nurse("N001", "김하린"),
            Nurse("N002", "이서윤"),
        ]
        config = SchedulerConfig(
            year=2026,
            month=4,
            nurse_count=2,
            center_day_nurse_id="N001",
            center_evening_nurse_id="N002",
        )
        dates = build_month_dates(2026, 4)[:4]
        schedule = GeneratedSchedule(
            dates=dates,
            assignments={
                "N001": ["N", "O", "D", "O"],
                "N002": ["E", "E", "E", "E"],
            },
            hard_violations=[],
            soft_penalty=0,
        )

        violations = validate_schedule(schedule, nurses, config)

        self.assertTrue(any("NOD" in violation for violation in violations))

    def test_validate_schedule_detects_ed_and_single_n(self) -> None:
        nurse = Nurse("N001", "김하린")
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:5],
                assignments={"N001": ["O", "E", "D", "N", "O"]},
                hard_violations=[],
                soft_penalty=0,
            ),
            [nurse],
            SchedulerConfig(
                year=2026,
                month=4,
                nurse_count=1,
                center_day_nurse_id="N001",
                center_evening_nurse_id="N001",
            ),
        )

        self.assertTrue(any("ED" in violation for violation in violations))
        self.assertTrue(any("단독 N" in violation for violation in violations))

    def test_validate_schedule_detects_noe(self) -> None:
        nurse = Nurse("N001", "김하린")
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:5],
                assignments={"N001": ["D", "N", "O", "E", "O"]},
                hard_violations=[],
                soft_penalty=0,
            ),
            [nurse],
            SchedulerConfig(
                year=2026,
                month=4,
                nurse_count=1,
                center_day_nurse_id="N001",
                center_evening_nurse_id="N001",
            ),
        )

        self.assertTrue(any("NOE" in violation for violation in violations))

    def test_validate_schedule_detects_eod_and_single_work_between_offs(self) -> None:
        nurse = Nurse("N001", "김하린")
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:6],
                assignments={"N001": ["E", "O", "D", "O", "P", "O"]},
                hard_violations=[],
                soft_penalty=0,
            ),
            [nurse],
            SchedulerConfig(
                year=2026,
                month=4,
                nurse_count=1,
                center_day_nurse_id="N001",
                center_evening_nurse_id="N001",
            ),
        )

        self.assertTrue(any("EOD" in violation for violation in violations))
        self.assertTrue(any("OPO" in violation or "ODO" in violation for violation in violations))

    def test_validate_schedule_detects_insufficient_off_after_multiple_nights(self) -> None:
        nurse = Nurse("N001", "김하린")
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:5],
                assignments={"N001": ["N", "N", "O", "D", "O"]},
                hard_violations=[],
                soft_penalty=0,
            ),
            [nurse],
            SchedulerConfig(
                year=2026,
                month=4,
                nurse_count=1,
                center_day_nurse_id="N001",
                center_evening_nurse_id="N001",
            ),
        )

        self.assertTrue(any("2회 이상 N 이후 O 2개 미만" in violation for violation in violations))


if __name__ == "__main__":
    unittest.main()
