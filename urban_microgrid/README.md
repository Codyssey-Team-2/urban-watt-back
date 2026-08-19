# Urban-MicroGrid

미기후 융합 지역 전력수요 · 피크 위험 예측 — 계산식 코드베이스

**Watt the hell (2조)** / AI Energy

---

## 설치 및 실행

```bash
pip install pandas numpy scipy scikit-learn openpyxl statsmodels
python -m urban_microgrid.run_demo
```

GIS 파이프라인을 쓰려면 추가로 `geopandas`, `shapely`, `pyproj`.

백엔드 API 는 `fastapi` · `uvicorn` · `pydantic` 만 있으면 뜬다
(원자료·pandas 없이 실측 스냅샷 서빙 → `docs/05_백엔드_실행가이드.md`).

```bash
uvicorn urban_microgrid.api.main:app --reload --port 8000
```

---

## 구조

```
urban_microgrid/
├── config.py       모든 경로·상수·수식 파라미터 (여기만 수정)
├── io_loaders.py   원자료 적재 — 형식 차이를 여기서 전부 흡수
├── features.py     ①~⑤ 피복률·MCI·ΔT·기저수요·정규화 R
├── models.py       ⑥~⑧ 전환온도·민감도·상호작용·예측
├── evaluate.py     ⑨~⑪ 성능지표·경보·통계검정
├── run_demo.py     전체 파이프라인
└── api/            FastAPI 백엔드 (계약: docs/02)
```

---

## 수식 ↔ 함수 대응표

| # | 수식 | 함수 |
|---|---|---|
| ① | `ISR = ΣA_불투수 / A_전체 × 100` | `features.coverage_ratios` |
| ① | `MCI = ISR − VCR` | `features.microclimate_index` |
| ② | `ΔT = T_sdot − T_asos` | `features.delta_t` |
| ② | `UHI_night = mean(ΔT \| 야간)` | `features.night_uhi` |
| ③ | `B(d,h,w) = median{P \| 쾌적일}` | `features.baseline_demand` |
| ④ | `CSL = max(0, P − B)` | `features.cooling_sensitive_load` |
| ⑤ | `R = CSL / B × 100` | `features.cooling_sensitive_load` |
| ⑥ | `R = α + β·max(0,T−T*) + 통제` | `models.fit_changepoint` |
| ⑦ | `R = β₀+β₁T+β₂MCI+β₃(MCI×T)` | `models.fit_interaction` |
| ⑧ | Ablation (기상만 vs +미기후) | `models.fit_predict` + `evaluate.ablation_report` |
| ⑨ | `개선율 = (RMSE_base−RMSE_micro)/RMSE_base` | `evaluate.improvement_rate` |
| ⑩ | `θ(d) = quantile(P, 0.95)` | `evaluate.peak_threshold` |
| ⑩ | Precision / Recall / 리드타임 | `evaluate.alarm_metrics`, `lead_time` |
| ⑪ | 대응표본 t-검정 | `evaluate.paired_test` |

---

## 설계 원칙 (코드에 강제되어 있음)

**1. 비교는 항상 정규화 지표 R 로**
절대 kWh 로 두 동을 비교하면 "동네 크기 차이"를 보게 된다.
`cooling_sensitive_load` 가 R 을 자동 생성한다.

**2. 순환논리 차단**
예측 타깃은 실측 총전력(`kwh`). 냉방 민감도는 예측 대상이 아니라
모델의 **해석 산출물**(`fit_changepoint` 의 β)이다.

**3. 임계치는 동별 상대 기준**
절대 kWh 임계는 큰 동을 항상 위험으로 만든다.
`peak_threshold` 는 동별 백분위를 쓴다.

**4. 랜덤 분할 금지**
`time_split` 만 제공한다. 시계열에서 랜덤 K-fold 는 데이터 누수다.

**5. 측정하지 않은 성능 수치는 만들지 않는다**
`improvement_rate` 는 실제 두 모델을 돌린 결과에서만 계산된다.

---

## 알려진 데이터 함정 (코드가 방어함)

| 함정 | 방어 위치 |
|---|---|
| 진관동 법정동코드는 **11400** (10800은 다른 동) | `config.DONGS` |
| 전력 CSV 완전중복 약 50% | `io_loaders._to_hourly` |
| 스프레드시트 절단(1,048,575행) | `load_power_csv` 경고 |
| 시각 표기 0100~2400 → 정시 변환 | `hm_to_timestamp` |
| 경위도에서 면적 계산 금지 | `coverage_ratios` 좌표계 검증 |
| S-DoT 위치 식별자 부재 | `load_sdot` 안내 예외 |
| 동 2개면 β₃ 추정 불가 | `fit_interaction` 예외 |

---

## 현재 상태

- ✅ 전력 · ASOS 결합, 기저수요, R, 전환온도, 통계검정, 피크 임계
- ⏸ **Ablation** — S-DoT 설치위치 매핑 확보 후 활성화
  (서울시 IoT 허브 신청: http://iothub.eseoul.go.kr/publicData/insertForm.do)
- ⏸ **상호작용 모델** — 분석 동 3개 이상으로 확장 후 활성화

---

## 재현된 예비 결과 (2022-06-28 ~ 08-31)

| 지역 | 평균 R | T* | β | 야간 R | 주간 R |
|---|---|---|---|---|---|
| 진관동 | 33.1% | 18.0℃ | 2.77 %p/℃ | 31.2% | 34.7% |
| 구로동 | 27.6% | 19.0℃ | 2.76 %p/℃ | 17.8% | 35.8% |

일평균 R 차이(구로동 − 진관동) = −5.37 %p (95% CI [−8.65, −2.08], n=45일, p=0.0026)

**해석**: 냉방 민감도 β 는 사실상 동일했고, 차이는 야간 수요 패턴에서 나타났다.
미기후보다 **건물 용도·재실 패턴**이 지배적일 가능성이 크다.
→ 비교지역을 주거 우세 동으로 조정하고 생활인구를 통제변수로 추가할 것.
