# Nurse Schedule Planner MVP

간호사 월간 3교대 스케줄 생성기 MVP입니다.

- 생성 엔진: Python + OR-Tools CP-SAT
- 출력 형식: `csv`, `md`
- 지원 인원 수: `24`, `25`, `26`

## 개요

- 대상 근무: `D`, `E`, `N`, `O`, `P`
- 입력: 설정 JSON + 간호사 풀 CSV
- 출력:
  - `monthly_schedule_YYYY_MM.csv`
  - `schedule_report_YYYY_MM.md`
  - `nurse_pool_resolved.csv`
- 생성 후 `validator` 로 하드 제약을 다시 검증합니다.

## 근무 코드

- `D`: 07:00 ~ 15:30
- `E`: 15:00 ~ 23:30
- `N`: 23:00 ~ 익일 07:30
- `O`: 휴무
- `P`: 10:00 ~ 18:30

## 일자별 필요 인원

- 평일: `D 6`, `E 5`, `N 4`, `P 1`
- 주말: `D 4`, `E 5`, `N 4`, `P 1`

## 중앙 근무자

- 평일 `D` 중앙 간호사 1명 고정
- 평일 `E` 중앙 간호사 1명 고정
- 중앙 간호사는 설정 파일에서 `nurse_id` 로 입력
- 중앙 근무자의 `wanted_off` 가 있으면 해당 평일 고정 배정은 면제
- 평일 중앙 `D` 근무자의 `wanted_off` 발생 시 `E` 팀 역량 `3` 인원이 `D` 대체
- 평일 중앙 `E` 근무자의 `wanted_off` 발생 시 `E` 팀 역량 `3` 인원이 `E` 대체

## 현재 구현된 하드 제약

### 공통 배정 제약

- 하루 1인 1근무
- 요일별 필요 인원 충족
- `allowed_shift_types` 가 지정된 경우 해당 근무 타입만 배정 가능
- `wanted_off` 로 지정된 날짜는 반드시 `O`

### 개인별 연속/횟수 제약

- 월간 `N` 최대 `max_nights_per_month`
- 연속근무 최대 `max_consecutive_work_days`
- `N` 연속 최대 3회
- 주간 연속 7일 윈도우 기준 근무시간 최대 52시간

### 금지 패턴

- `NE`, `ND`, `NP` 금지
- `ED` 금지
- `NOD` 금지
- `NOE` 금지
- `EOD` 금지
- 월중 단독 `N` 금지
- 2회 이상 연속 `N` 뒤에는 `O` 최소 2개 필요
- `OEO`, `ODO`, `OPO` 금지
- `DDDDD`, `EEEEE`, `PPPPP` 금지
- 예외:
  - 평일 중앙 `D` 간호사의 `D` 5연속 허용
  - 평일 중앙 `E` 간호사의 `E` 5연속 허용

### 팀/역량 제약

- 팀: `A`, `B`, `C`, `D`, `E`, `CENTER`
- `A~D` 팀은 매일 `D`, `E`, `N`에 최소 1명씩 존재
- `D/E/N` 각 시간대에는 역량 레벨 `3` 최소 1명 필수
- `D/E/N/P` 각 시간대에는 역량 레벨 `1` 최대 1명
- `P` 근무는 역량 레벨 `2` 또는 `3`만 가능
- `E` 팀 규칙:
  - `N` 금지
  - 평일 `E` 금지
  - 단, 평일 중앙 `E` 근무자의 `wanted_off` 발생일에는 `E` 팀 역량 `3` 1명이 `E` 대체
  - 주말 `E`는 역량 `3`만 가능
  - 평일 중앙 `D` 근무자의 `wanted_off` 발생일에는 `E` 팀 역량 `3` 1명 이상이 `D` 대체
  - `D`는 가능

## 현재 구현된 soft penalty

- `DDDDD`, `EEEEE`, `PPPPP` 5연속
  - 단, 평일 중앙 `D/E` 5연속 예외는 penalty 제외
- `P` 배정 선호 위반
  - 비 `E` 팀의 `P` 배정은 큰 penalty
  - `E` 팀 역량 `3` 의 `P` 배정은 중간 penalty
- `E` 팀 역량 `3` 의 일반 `D` 배정
  - 평일 중앙 `D` 대체일은 제외
  - 결과적으로 `D` 는 레벨 `2` 를 우선하고 필요 시 레벨 `3` 도 가능
- 야간/총근무 공정성 편차
  - 전체 `N` 수요와 총 근무 수요를 인원수로 나눈 목표 범위를 벗어나면 penalty

## 입력 파일

### 설정 파일

기본 설정 파일: [data/scheduler_config.sample.json](/Users/P202052/git/schedule-planner/data/scheduler_config.sample.json)

예시:

```json
{
  "year": 2026,
  "month": 4,
  "nurse_count": 24,
  "center_day_nurse_id": "N001",
  "center_evening_nurse_id": "N002",
  "random_seed": 7,
  "max_attempts": 5000
}
```

### 간호사 풀 파일

기본 간호사 풀 파일: [data/nurse_pool_sample.csv](/Users/P202052/git/schedule-planner/data/nurse_pool_sample.csv)

필수 컬럼:

```csv
nurse_id,name,team,competency_level,employment_type,max_nights_per_month,max_consecutive_work_days,allowed_shift_types,wanted_off
```

- `allowed_shift_types`
  - 예: `DE`
  - 표기된 근무 타입만 배정 가능
  - `O` 는 표기 여부와 무관하게 항상 가능
- `wanted_off`
  - 예: `2,5,19`
  - 해당 일자는 확정 휴무
  - 결과 CSV 에서는 `W-O` 로 표기되며 실제 값은 `O` 로 계산

## 실행 방법

먼저 의존성을 설치합니다.

```bash
python3 -m pip install -r requirements.txt
```

### 24명 기준 실행

```bash
PYTHONPATH=src python3 -m schedule_planner.cli \
  --config data/scheduler_config.sample.json \
  --nurse-pool data/nurse_pool_sample.csv \
  --nurse-count 24 \
  --output-dir output_common_24
```

### 25명 / 26명 실행

```bash
PYTHONPATH=src python3 -m schedule_planner.cli \
  --config data/scheduler_config.sample.json \
  --nurse-pool data/nurse_pool_sample.csv \
  --nurse-count 25 \
  --output-dir output_common_25
```

```bash
PYTHONPATH=src python3 -m schedule_planner.cli \
  --config data/scheduler_config.sample.json \
  --nurse-pool data/nurse_pool_sample.csv \
  --nurse-count 26 \
  --output-dir output_common_26
```

### 다른 간호사 풀 파일 사용

```bash
PYTHONPATH=src python3 -m schedule_planner.cli \
  --config data/scheduler_config.sample.json \
  --nurse-pool data/my_nurse_pool.csv \
  --nurse-count 24 \
  --output-dir output_custom_24
```

## 검증 및 리포트

- 생성 직후 `validator` 로 하드 제약을 다시 검증합니다.
- 리포트의 `Hard constraint violations` 는 solver 결과가 아니라 재검증 결과를 표시합니다.
- 리포트의 `Soft penalty` 는 위 soft penalty 항목 합산 결과입니다.
- CSV 표기 예:
  - `D (3 A)`
  - `N (1 B)`
  - `O (2 E)`
  - `W-O (2 A)`
- 개인별 행 마지막에 `D/E/N/P/O` 카운트 출력
- 마지막 행에 일자별 `D/E/N/P/O` 카운트 출력

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 현재 사용 기술

- Python 3
- OR-Tools CP-SAT

## 제약 해석 주의

- `wanted_off` 는 해당 날짜의 확정 휴무이므로 다른 모든 근무 제약보다 우선합니다.
- `allowed_shift_types` 는 근무 타입 제한만 의미하며 `O` 제한은 하지 않습니다.
- `W-O` 는 출력용 표기이며 내부 검증과 집계에서는 `O` 로 처리합니다.
