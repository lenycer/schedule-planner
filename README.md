# Nurse Schedule Planner MVP

간호사 월간 3교대 스케줄 생성기 MVP입니다.

- 생성 엔진: Python + OR-Tools CP-SAT
- 출력 형식: `csv`, `md`
- 지원 인원 수: `24`, `25`, `26`

## 현재 구현 범위

### 근무 코드

- `D`: 07:00 ~ 15:30
- `E`: 15:00 ~ 23:30
- `N`: 23:00 ~ 익일 07:30
- `O`: 휴무
- `P`: 10:00 ~ 18:30

### 일자별 필요 인원

- 평일: `D 6`, `E 5`, `N 4`, `P 1`
- 주말: `D 4`, `E 5`, `N 4`, `P 1`

### 중앙 근무자

- 평일 `D` 중앙 간호사 1명 고정
- 평일 `E` 중앙 간호사 1명 고정
- 중앙 간호사는 설정 파일에서 `nurse_id`로 입력

### 현재 반영된 하드 제약

- 하루 1인 1근무
- 요일별 필요 인원 충족
- `N` 연속 최대 3회
- 연속근무 최대 5일
- 월간 `N` 최대 8회
- 주간 근무시간 최대 52시간
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
  - `D`, `N` 금지 // TODO D 조건은 제거 필요 
  - 평일 `E` 금지
  - 주말 `E`는 역량 `3`만 가능
  - `P` 우선 배정 대상
  - `E` 팀 인원이 `P` 불가 패턴이면 타팀에 `P` 배정

### 출력 형식

- 근무표 표기 예:
  - `D (3 A)`
  - `N (1 B)`
  - `O (2 E)`
- 개인별 행 마지막에 `D/E/N/P/O` 카운트 출력
- 마지막 행에 일자별 `D/E/N/P/O` 카운트 출력

## 입력 파일

### 설정 파일

기본 설정 파일: [data/scheduler_config.sample.json](/Users/lenycer/git/schedule-planner/data/scheduler_config.sample.json)

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

기본 간호사 풀 파일: [data/nurse_pool_sample.csv](/Users/lenycer/git/schedule-planner/data/nurse_pool_sample.csv)

필수 컬럼:

```csv
nurse_id,name,team,competency_level,employment_type,max_nights_per_month,max_consecutive_work_days
```

## 실행 방법

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

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 생성 결과

출력 디렉터리에는 아래 파일이 생성됩니다.

- `monthly_schedule_YYYY_MM.csv`
- `schedule_report_YYYY_MM.md`
- `nurse_pool_resolved.csv`

## 현재 사용 기술

- Python 3
- OR-Tools CP-SAT

설치 예:

```bash
python3 -m pip install ortools
```

## 추가 작업 예정

### 1. 간호사 풀에 유연 근무 패턴 추가

- 컬럼 추가 예정: 예) `allowed_shift_patterns`
- 표기 예: `DE`, `DN`, `EN`, `EP`, `DP`
- 의미:
  - 정의된 근무 형태만 배정 가능
  - 값이 있을 때만 적용
  - 값이 비어 있으면 기존 전체 규칙만 적용
