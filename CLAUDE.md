# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nurse shift schedule auto-generator for 24–26 nurses across a 3-shift system (Day/Evening/Night). Uses Google OR-Tools CP-SAT constraint solver. Written in Python, all documentation in Korean.

## Commands

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Run schedule generation (change nurse-count to 24/25/26)
PYTHONPATH=src python3 -m schedule_planner.cli \
  --config data/scheduler_config.sample.json \
  --nurse-pool data/nurse_pool_sample.csv \
  --nurse-count 24 \
  --output-dir output_common_24

# Run all tests
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Run a single test
PYTHONPATH=src python3 -m unittest tests.test_validator.TestValidator.test_method_name -v
```

## Architecture

**Execution flow:** CLI → load config/nurse pool → CP-SAT solver builds constraints → solve → validate → report (CSV + Markdown)

All source lives in `src/schedule_planner/`:

| Module | Role |
|--------|------|
| `cli.py` | Entry point, argument parsing, orchestration |
| `models.py` | Dataclasses: `Nurse`, `SchedulerConfig`, `DayRequirement`, `GeneratedSchedule` |
| `generator.py` | Core CP-SAT model: decision variables, hard constraints, soft penalties, solve (~600 lines) |
| `rules.py` | Soft penalty calculations for post-solve evaluation |
| `validator.py` | Post-generation hard constraint validation |
| `io_utils.py` | CSV/JSON I/O, nurse pool loading |
| `reporter.py` | CSV schedule + Markdown summary report output |

Tests are in `tests/test_validator.py` (17 cases covering validator and penalty logic).

## Shift System

Codes: `D` (Day), `E` (Evening), `N` (Night), `P` (PRN/part-time), `O` (Off)

**Daily staffing — weekdays:** D=6, E=5, N=4, P=1 | **weekends:** D=4, E=5, N=4, P=1

## Key Constraint Summary

The solver enforces numerous hard constraints (see `generator.py` and `docs/mvp-plan.md` for full list). The most important ones:

- **Forbidden shift patterns:** NE, ND, NP, NOD, NOE, EOD, OXO (X∈D/E/P), isolated single N
- **Night limits:** night-keep nurses get exactly 15 N/month (rest O); others max 7 N/month
- **Consecutive limits:** max 3 consecutive N; max consecutive work days per nurse config; 2+ consecutive N requires 2+ O after
- **Weekly hours ≤ 52**
- **Competency:** level 3 must have ≥1 per D/E/N shift; level 1 max 1 per shift; P requires level 2+
- **E team rules:** no N shifts, no weekday E (with exceptions), weekend E level 3 only
- **Center nurses:** day nurse = D only on weekdays; evening nurse = E only on weekdays
- **Team coverage:** teams A–D must cover all 30 days across D/E/N if capacity allows

Soft penalties (in objective function) handle fairness, team daily coverage gaps, DE balance, and preference violations.
- **DE balance:** `allowed_shift_types == "DE"` nurses get soft penalty (weight=50 × shortfall) if D or E < 5/month; skipped when team has ≤2 members capable of D or E (structural constraint)
- **Team daily coverage:** weight=15 per missing team×shift×day; soft because hard version conflicts with competency constraints

## Input Files

- `data/scheduler_config.sample.json` — year, month, nurse count, center nurse IDs, solver params
- `data/nurse_pool_sample.csv` — nurse roster with team, competency, shift restrictions, wanted-off dates
