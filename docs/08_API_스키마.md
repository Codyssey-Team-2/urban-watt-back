# Urban-MicroGrid API 스키마

FastAPI Pydantic 모델을 기준으로 정리한 프론트엔드 연동 계약이다.

- Base URL: `http://localhost:8000`
- API prefix: `/api`
- 법정동코드: 진관동 `1138011400`, 구로동 `1153010100`
- 시간: KST 기준 ISO 8601, UTC offset 없음
- 전력량: `kWh`
- 비율·퍼센트: `%`, 냉방 민감도: `%p/℃`
- 미확보 값은 임의 수치로 채우지 않고 `null`, `pending`, `note`로 표현한다.

## 엔드포인트

| Method | Path | 200 response |
|---|---|---|
| GET | `/api/meta` | `Meta` |
| GET | `/api/dongs` | `DongList` |
| GET | `/api/dongs/geojson` | `DongGeoJSON` |
| GET | `/api/dong/{code}` | `DongSummary` |
| GET | `/api/dong/{code}/forecast?date=YYYY-MM-DD` | `Forecast` |
| GET | `/api/compare?codes=A,B` | `Compare` |
| GET | `/api/model-performance` | `ModelPerformance` |
| GET | `/api/briefing?codes=A,B&date=YYYY-MM-DD&refresh=false` | `Briefing` |

## 공통 타입

### `Graded`

| 필드 | 타입 | Nullable | 설명 |
|---|---|---:|---|
| `grade` | string | O | 백엔드가 판정한 등급 |
| `color` | string | O | HEX 색상 |
| `message` | string | O | 화면 표시 문구 |

프론트엔드는 등급·색상·문구를 재계산하지 않는다.

## `DongSummary`

`GET /api/dong/{code}`

| 필드 | 타입 | 설명 |
|---|---|---|
| `code` | string | 10자리 법정동코드 |
| `name` | string | 법정동명 |
| `microclimate` | `Microclimate` | 미기후·토지피복 |
| `demand` | `Demand` | 정규화 수요 R |
| `cooling` | `Cooling` | 전환온도·냉방 민감도 |
| `peak` | `Peak` | 동별 피크 임계 |

### `Microclimate`

| 필드 | 타입 | Nullable | 설명 |
|---|---|---:|---|
| `status` | `ready \| pending` | X | 자료 상태 |
| `heat_index` | number | O | 0~100 도시열 지수 |
| `grade`, `color`, `message` | string | O | 판정 결과 |
| `components` | `CoverComponents` | X | 피복 구성 |
| `area_km2` | number | O | 산출 면적 |
| `basis` | `MicroclimateBasis` | O | 산출 기준·출처 |
| `note` | string | O | 예비값 또는 pending 사유 |
| `caveat` | string | O | 해석 단서 |

`CoverComponents`의 `paved`, `green`, `water`는 필수이고 `bare`, `wetland`는 nullable이다.
각 구성요소는 `{ percent: number|null, text: string|null, label: string }`다.

`MicroclimateBasis`:

```ts
interface MicroclimateBasis {
  tag: string
  method: string
  source: string
  clipped_to_dong: boolean
  note: string
  caveat: string
}
```

### `Demand`, `Cooling`, `Peak`

```ts
interface Demand {
  extra_usage_percent: number | null
  extra_usage_text: string | null
  night_percent: number | null
  day_percent: number | null
  pattern: string | null
}

interface Cooling {
  switch_on_temp: number | null
  switch_on_text: string | null
  sensitivity: number | null
  sensitivity_text: string | null
}

interface Peak {
  threshold_kwh: number | null
  threshold_text: string | null
  risk_days: number | null
  total_days: number | null
  risk_days_text: string | null
}
```

## `Forecast`

`GET /api/dong/{code}/forecast?date=YYYY-MM-DD`

```ts
interface Forecast {
  code: string
  name: string
  date: string
  threshold_kwh: number | null
  weather: DayWeather | null
  points: ForecastPoint[]
}

interface ForecastPoint {
  time: string
  hour: number
  usage_kwh: number
  baseline_kwh: number | null
  extra_percent: number | null
  temperature: number | null
  humidity: number | null
  wind: number | null
  risk_ratio: number
  grade: string | null
  color: string | null
  message: string | null
}

interface DayWeather {
  t_max: number | null
  t_min: number | null
  humidity: number | null
  wind: number | null
  heatwave: boolean | null
}
```

`usage_kwh`는 실측 총전력, `baseline_kwh`는 기저수요, `threshold_kwh`는 동별
백분위 위험선이다. S-DoT 온도와 B/C 모델 예측선은 현재 스키마에 없다.

## `DongList`

`GET /api/dongs`

```ts
interface DongList {
  dongs: DongMarker[]
  latlng_source: string
}

interface DongMarker {
  code: string
  name: string
  lat: number
  lng: number
  heat_index: number | null
  grade: string | null
  color: string
  risk_days: number | null
}
```

## `DongGeoJSON`

`GET /api/dongs/geojson`

```ts
interface DongGeoJSON {
  type: 'FeatureCollection'
  status: 'ready' | 'pending'
  bbox: number[] | null
  features: DongFeature[]
  source: string | null
  note: string | null
}
```

`DongFeature` 형식은 GeoJSON `Feature`며 `geometry`는 EPSG:4326 좌표다.
`properties`는 다음 필드를 갖는다.

```ts
interface FeatureProperties {
  code: string
  name: string | null
  status: string
  heat_index: number | null
  grade: string | null
  color: string
  message: string | null
  extra_usage_percent: number | null
  risk_days: number | null
  lat: number | null
  lng: number | null
  tooltip: string | null
  fill_color: string
  fill_opacity: number
  stroke_color: string
  stroke_width: number
  stroke_opacity: number
}
```

## `Compare`

`GET /api/compare?codes=1153010100,1138011400`

```ts
interface Compare {
  dongs: string[]
  rows: Array<{
    label: string
    unit: string
    values: Record<string, number | null>
  }>
}
```

`dongs`는 요청 순서를 유지하며 `values`의 key는 동 이름이다. 비교는 절대 kWh가
아닌 정규화 지표 R을 사용한다.

## `ModelPerformance`

`GET /api/model-performance`

```ts
interface ModelPerformance {
  status: 'ready' | 'pending'
  metric: string
  models: Array<{
    key: 'a' | 'b' | 'c'
    label: string
    mape: number | null
    rmse: number | null
    mae: number | null
  }>
  improvement_percent: number | null
  improvement_basis: string
  note: string
  caveat: string
}
```

현재는 S-DoT 설치위치 매핑과 Ablation이 완료되지 않아 `status: "pending"`이고
성능 수치는 모두 `null`이다.

## `Briefing`

`GET /api/briefing?codes=A,B&date=YYYY-MM-DD&refresh=false`

```ts
interface Briefing {
  codes: string[]
  date: string | null
  status: 'ready' | 'needs_review'
  text: string
  provider: string
  model: string
  usage: Record<string, unknown> | null
  unverified_numbers: string[]
  note: string | null
  facts: Record<string, unknown>
  prompt: { system: string; user: string }
}
```

`unverified_numbers`가 비어 있지 않으면 화면에 경고를 표시한다. API key가 없거나
모델 호출이 불가능하면 503 `pending` 응답이 온다.

## `Meta`

`GET /api/meta`

```ts
interface Meta {
  service: string
  version: string
  mode: 'live' | 'snapshot'
  mode_text: string
  period: Record<string, string>
  llm: Record<string, unknown>
  dongs: Array<Record<string, unknown>>
  pending: string[]
  caveats: string[]
}
```

## 오류·pending 응답

### 404 — 분석 대상이 아닌 법정동코드

```json
{
  "status": "not_found",
  "detail": "법정동코드 9999999999 는 분석 대상이 아닙니다.",
  "note": "분석 대상: 진관동(1138011400), 구로동(1153010100)"
}
```

### 503 — 요청은 유효하지만 자료 미확보

```ts
interface PendingError {
  status: 'pending'
  detail: string
  note: string | null
}
```

### 422 — 쿼리·경로 검증 실패

FastAPI 표준 `HTTPValidationError` 형식을 사용한다.

## 프론트엔드 처리 규칙

1. 초기 로드 시 `/api/meta`로 모드·기간·대상 동을 확인한다.
2. `status === "pending"` 또는 HTTP 503이면 스켈레톤과 `note`를 표시한다.
3. `null`을 0으로 변환하지 않는다.
4. `grade`, `color`, `message`, `tooltip`, 지도 스타일은 응답값을 그대로 쓴다.
5. 절대 kWh로 동을 비교하거나 프론트에서 별도 위험 임계를 계산하지 않는다.
6. 실제 스웨거/OpenAPI 원문은 서버 실행 후 `/openapi.json`, `/docs`에서 확인한다.
