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

## 근무 할당 로직 (CP-SAT solver)

### 동작 원리

수기 작성과 달리, CP-SAT solver 는 **순서대로 한 명씩 배치**하는 것이 아니라 **모든 변수와 제약을 한꺼번에 선언**한 뒤 동시에 만족하는 해를 탐색합니다.

### 실행 흐름 (`generator.py`)

```
1. 변수 선언
   간호사 × 일 × 근무타입(D/E/N/O/P) = BoolVar (0 또는 1)
   → "N003이 4월1일에 N인가?" 같은 변수가 수천 개 생성

2. 기본 제약 등록
   - 각 간호사×일에 정확히 1개 근무 배정 (AddExactlyOne)
   - 각 일의 수요 충족 (평일 D=6/E=5/N=4/P=1 등)

3. 하드 제약 일괄 등록 (apply_hard_constraints)
   - wanted_off → O 강제
   - allowed_shift_types 제한
   - night keep = N 정확히 15회
   - 비night keep ≤ 7N
   - 연속근무, 금지패턴(NE, ND, NOD 등), 주간 52시간
   - 역량/E팀/센터 간호사 제한
   - 팀 월간 커버리지

4. 소프트 패널티(목적함수) 등록 (add_objective)
   - 공정성, P배정 선호, 팀 일간 커버, DE 밸런스 등에 가중치 부여
   - model.Minimize(총 패널티)

5. 솔버 탐색
   - 8개 워커, 60초 제한
   - 모든 하드 제약을 만족하면서 소프트 패널티가 최소인 해를 탐색
```

### 하드 제약 vs 소프트 패널티

| 구분 | 하드 제약 | 소프트 패널티 |
|------|----------|-------------|
| 성격 | **반드시** 만족해야 함 | 가능하면 만족하도록 **유도** |
| 위반 시 | 스케줄 생성 실패 (INFEASIBLE) | 패널티 점수 증가 |
| 예시 | wanted_off=O, N≤7, NE금지 | 팀 일간 커버, DE 밸런스 |

### 제약 간 우선순위

solver 는 모든 하드 제약을 동시에 만족시켜야 하므로, 제약 간 우선순위가 아닌 **동시 충족**입니다. 다만 실질적인 효과로 보면:

1. **wanted_off** — `O` 로 고정되므로 가장 먼저 확정
2. **N 관련 제약** — 가장 제약이 많아 (night keep 15회 고정, 비night keep ≤7, 연속3회, NE/ND/NP/NOD/NOE 금지, 2N 이후 2O 필수) solver 내부적으로 초기에 결정되는 경향
3. **역량/팀 제약** — 역량3 필수, 역량1 제한, E팀 규칙 등
4. **나머지 패턴 제약** — ED 금지, OXO 금지, 5연속 금지 등

소프트 패널티 간에는 **가중치**로 우선순위가 결정됩니다:

| 패널티 | 가중치 | 설명 |
|--------|--------|------|
| 비E팀 P 배정 | 10,000 | P는 E팀 위주로 배정 |
| E팀 역량3 P 배정 | 1,000 | E팀 역량3은 P보다 D/E 우선 |
| E팀 역량3 일반 D 배정 | 100 | 센터 대체일 외 D 지양 |
| DE 밸런스 미달 | 50 × 부족분 | 5 미달 시 부족한 만큼 비례 |
| 중앙 근무자 평일 O | 20 | 평일 근무 유도 |
| 팀 일간 커버 미충족 | 15 | 매일 D/E/N 존재 유도 |
| 5연속 동일 근무 | 5 | DDDDD, EEEEE, PPPPP |
| 야간/총근무 공정성 | 1~2 | 균등 배분 유도 |

## 중앙 근무자

- 중앙 간호사는 설정 파일에서 `nurse_id` 로 입력
- 데이 중앙 간호사는 `D` 또는 `O` 만 가능
- 이브 중앙 간호사는 `E` 또는 `O` 만 가능
- 평일에는 가능하면 각각 `D`, `E` 로 배정되도록 soft penalty 를 둡니다.
- 중앙 근무자의 `wanted_off` 는 일반 간호사와 동일하게 확정 `O`
- 중앙 근무자는 `최소 O 10개` 하드 제약 대상이 아닙니다.
  - 따라서 월별 달력 구조에 따라 주말 `O` 8개만 가질 수도 있습니다.
- 평일 중앙 `D` 근무자의 `wanted_off` 발생 시 `E` 팀 역량 `3` 인원이 `D` 대체
- 평일 중앙 `E` 근무자의 `wanted_off` 발생 시 `E` 팀 역량 `3` 인원이 `E` 대체

## 현재 구현된 하드 제약

### 공통 배정 제약

- 하루 1인 1근무
- 요일별 필요 인원 충족
- `allowed_shift_types` 가 지정된 경우 해당 근무 타입만 배정 가능
- `allowed_shift_types` 에 적힌 모든 근무는 월간 결과에 최소 1회 이상 반드시 존재
  - 예: `DE` 이면 월간 `D >= 1`, `E >= 1`
- `wanted_off` 로 지정된 날짜는 반드시 `O`

### 개인별 연속/횟수 제약

- `allowed_shift_types == "N"` 인 경우 `night keep` 으로 간주
  - 월간 `N` 은 정확히 `15`개
  - 나머지는 모두 `O`
  - `D/E/P` 는 배정되지 않음
- `night keep` 제외 모든 간호사는 월간 `N` 최대 `7`
  - 실제 적용 값은 `min(max_nights_per_month, 7)`
- 일반 근무자만 월간 `O` 최소 `10`
  - 중앙 근무자는 제외
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
- `D/E/N` 각 시간대에는 역량 레벨 `3` 최소 1명 필수
- `D/E/N/P` 각 시간대에는 역량 레벨 `1` 최대 1명
- `P` 근무는 역량 레벨 `2` 또는 `3`만 가능
- `A~D` 팀 월간 커버 규칙
  - 각 팀은 해당 월의 `D`, `E`, `N` 총 수량을 자기 팀 인력으로 커버할 수 있는 경우, 그 근무를 월간 일수만큼 반드시 커버해야 합니다.
  - 예: 2026년 4월이면 `D`, `E`, `N` 각각 `30`개
  - 단, 팀 구성상 어떤 근무를 월간 `30`개 채울 수 없는 경우에는 그 부족 자체를 하드 위반으로 보지 않습니다.
  - 예: `N, EN, EN, EN, DE` 처럼 `D` 를 월간 30개 만들 수 없는 구조는 허용
- `E` 팀 규칙:
  - `N` 금지
  - 평일 `E` 금지
  - 단, 평일 중앙 `E` 근무자의 `wanted_off` 발생일에는 `E` 팀 역량 `3` 1명이 `E` 대체
  - 주말 `E`는 역량 `3`만 가능
  - 평일 중앙 `D` 근무자의 `wanted_off` 발생일에는 `E` 팀 역량 `3` 1명 이상이 `D` 대체
  - `D`는 가능

## 현재 구현된 soft penalty

- `DDDDD`, `EEEEE`, `PPPPP` 5연속 (weight=5)
  - 단, 중앙 근무자의 평일 `D/E` 5연속 예외는 penalty 제외
- `P` 배정 선호 위반
  - 비 `E` 팀의 `P` 배정은 큰 penalty (weight=10,000)
  - `E` 팀 역량 `3` 의 `P` 배정은 중간 penalty (weight=1,000)
- `E` 팀 역량 `3` 의 일반 `D` 배정 (weight=100)
  - 평일 중앙 `D` 대체일은 제외
  - 결과적으로 `D` 는 레벨 `2` 를 우선하고 필요 시 레벨 `3` 도 가능
- 중앙 근무자의 평일 `O` (weight=20)
  - 하드 금지는 아니고 penalty 대상입니다.
  - 즉 중앙도 평일 추가 `O` 가 가능하지만 가능하면 평일 `D/E` 를 유지하도록 유도합니다.
- DE 밸런스 (weight=50 × 부족분)
  - `allowed_shift_types == "DE"` 인 간호사의 D, E 각각 월간 최소 5회 유도
  - 부족분에 비례하여 패널티 증가 (예: E=2이면 (5-2)×50=150)
  - 팀 내 D 또는 E 가능 인원이 2명 이하인 경우 구조적 한계로 패널티 미적용
    - 예: C팀에서 D 가능 간호사가 1명(DE 간호사 본인)뿐이면 D에 고정될 수밖에 없으므로 제외
- `A~D` 팀의 일별 `D/E/N` 존재 (weight=15)
  - 가능한 경우 각 팀이 매일 `D`, `E`, `N` 를 모두 갖도록 penalty 를 둡니다.
  - 다만 이 규칙은 하드 제약이 아니라 선호 조건입니다.
  - 역량 제약(역량3 필수, 역량1 제한)과 팀 구성 특성상 하드 제약으로 적용하면 INFEASIBLE 이 발생할 수 있어 소프트 패널티로 운용합니다.
- 야간/총근무 공정성 편차 (weight=1~2)
  - 전체 `N` 수요와 총 근무 수요를 인원수로 나눈 목표 범위를 벗어나면 penalty

## 입력 파일

### 설정 파일

기본 설정 파일: `data/scheduler_config.sample.json`

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

기본 간호사 풀 파일: `data/nurse_pool_sample.csv`

필수 컬럼:

```csv
nurse_id,name,team,competency_level,employment_type,max_nights_per_month,max_consecutive_work_days,allowed_shift_types,wanted_off
```

- `allowed_shift_types`
  - 예: `DE`
  - 표기된 근무 타입만 배정 가능
  - 표기된 각 근무는 월간 결과에 최소 1회 이상 반드시 포함되어야 함
  - `O` 는 표기 여부와 무관하게 항상 가능
  - `N` 만 단독 표기된 경우 `night keep` 으로 해석
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
  --nurse-pool output_common_24/nurse_pool_resolved.csv \
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
- `allowed_shift_types == "N"` 은 일반 야간 가능 인력이 아니라 `night keep` 으로 처리됩니다.
- 일반 근무자는 `O >= 10`, 중앙 근무자는 이 최소 `O` 제약에서 제외됩니다.
- `A~D` 팀의 `D/E/N` 일별 존재는 soft penalty 이고, 월간 커버 가능 시 `30개` 충족은 hard 제약입니다.
- `W-O` 는 출력용 표기이며 내부 검증과 집계에서는 `O` 로 처리합니다.
- DE 밸런스 패널티는 팀 구성상 한계가 있는 간호사(팀 내 D 또는 E 가능 인원 ≤ 2명)에는 적용되지 않습니다. 이 경우 validator 리포트에도 해당 간호사의 DE 미달은 표시되지 않습니다.
