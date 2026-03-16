import unittest

from schedule_planner.generator import GeneratedSchedule, build_month_dates
from schedule_planner.models import Nurse, SchedulerConfig
from schedule_planner.reporter import format_assignment
from schedule_planner.rules import calculate_schedule_soft_penalty, calculate_soft_penalty
from schedule_planner.validator import validate_schedule


class ValidatorTest(unittest.TestCase):
    def test_calculate_soft_penalty_counts_documented_patterns(self) -> None:
        nurse = Nurse("N001", "김하린", team="A", competency_level=2)
        dates = build_month_dates(2026, 4)[:8]

        penalty = calculate_soft_penalty(
            ["E", "O", "D", "N", "O", "E", "D", "D"],
            nurse,
            dates,
            center_day_nurse_id="N999",
            center_evening_nurse_id="N998",
        )

        self.assertEqual(penalty, 0)

    def test_calculate_schedule_soft_penalty_includes_p_assignment_preference_and_fairness(self) -> None:
        dates = build_month_dates(2026, 4)[:1]
        nurses = [
            Nurse(f"N{index + 1:03d}", f"간호사{index + 1}", team="A", competency_level=2)
            for index in range(16)
        ]
        assignments = {nurse.nurse_id: ["D"] for nurse in nurses}
        assignments["N001"] = ["P"]
        assignments["N002"] = ["E"]
        assignments["N003"] = ["E"]
        assignments["N004"] = ["E"]
        assignments["N005"] = ["E"]
        assignments["N006"] = ["N"]
        assignments["N007"] = ["N"]
        assignments["N008"] = ["N"]
        assignments["N009"] = ["N"]

        penalty = calculate_schedule_soft_penalty(
            assignments,
            nurses,
            dates,
            center_day_nurse_id="N001",
            center_evening_nurse_id="N002",
        )

        self.assertEqual(penalty, 10000)

    def test_validate_schedule_detects_night_keep_non_night_assignment_and_wrong_monthly_total(self) -> None:
        nurse = Nurse("N001", "김하린", allowed_shift_types="N")
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:15],
                assignments={"N001": ["N"] * 14 + ["D"]},
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

        self.assertTrue(any("night keep 월간 N 고정 수량 불일치" in violation for violation in violations))
        self.assertTrue(any("night keep N/O 외 근무 배정" in violation for violation in violations))

    def test_validate_schedule_detects_invalid_center_assignment_types(self) -> None:
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:2],
                assignments={
                    "N001": ["P", "D"],
                    "N002": ["E", "P"],
                },
                hard_violations=[],
                soft_penalty=0,
            ),
            [
                Nurse("N001", "김하린", team="CENTER", competency_level=3),
                Nurse("N002", "이서윤", team="CENTER", competency_level=3),
            ],
            SchedulerConfig(
                year=2026,
                month=4,
                nurse_count=2,
                center_day_nurse_id="N001",
                center_evening_nurse_id="N002",
            ),
        )

        self.assertTrue(any("데이 중앙 근무자 D/O 외 배정" in violation for violation in violations))
        self.assertTrue(any("이브 중앙 근무자 E/O 외 배정" in violation for violation in violations))

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

    def test_validate_schedule_allows_day_shift_for_e_team_but_still_blocks_night(self) -> None:
        nurse = Nurse("N001", "김하린", team="E", competency_level=3)
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:2],
                assignments={"N001": ["D", "N"]},
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

        self.assertFalse(any("E팀 D 금지" in violation for violation in violations))
        self.assertTrue(any("E팀 N 금지" in violation for violation in violations))

    def test_validate_schedule_detects_allowed_shift_types_and_wanted_off(self) -> None:
        nurse = Nurse("N001", "김하린", allowed_shift_types="DE", wanted_off="2")
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:3],
                assignments={"N001": ["N", "D", "O"]},
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

        self.assertTrue(any("허용되지 않은 근무타입" in violation for violation in violations))
        self.assertTrue(any("wanted off 미반영" in violation for violation in violations))

    def test_validate_schedule_allows_weekday_e_team_evening_when_covering_center_wanted_off(self) -> None:
        nurses = [
            Nurse("N001", "김하린", team="CENTER", competency_level=3, wanted_off="1"),
            Nurse("N002", "이서윤", team="E", competency_level=3),
        ]
        violations = validate_schedule(
            GeneratedSchedule(
                dates=build_month_dates(2026, 4)[:1],
                assignments={
                    "N001": ["O"],
                    "N002": ["E"],
                },
                hard_violations=[],
                soft_penalty=0,
            ),
            nurses,
            SchedulerConfig(
                year=2026,
                month=4,
                nurse_count=2,
                center_day_nurse_id="N001",
                center_evening_nurse_id="N001",
            ),
        )

        self.assertFalse(any("E팀 평일 E 배정 금지" in violation for violation in violations))
        self.assertFalse(any("이브 중앙 근무자 미배정" in violation for violation in violations))

    def test_format_assignment_marks_wanted_off_as_w_o(self) -> None:
        nurse = Nurse("N001", "김하린", wanted_off="2")
        day = build_month_dates(2026, 4)[1]

        formatted = format_assignment("O", nurse, day)

        self.assertEqual(formatted, "W-O (2 UNASSIGNED)")


if __name__ == "__main__":
    unittest.main()
