# Urban-MicroGrid | 지표 언어 변환 & API 계약

**Watt the hell (2조)** | 구로구 구로동 ↔ 은평구 진관동

> 아이디어톤 발표에는 수식을 넣지 않는다. 대신 **"어떤 데이터가 어떤 화면 문구로 바뀌는가"**를 보여준다.
> 이 문서는 그 변환 규칙과, 프론트엔드가 받을 JSON 계약을 정의한다.

---

## 핵심 설계 원칙

```
❌  프론트가 MCI = 38.4 를 받아서 "이건 낮음이네" 판단
✅  백엔드가 { value: 38.4, grade: "낮음", color: "#66BB6A",
             message: "나무·풀밭이 많은 편입니다" } 를 통째로 전달
```

**프론트엔드는 계산하지 않는다.** 등급·색상·설명문까지 백엔드가 만들어 내려보낸다.

이렇게 하는 이유:
1. 등급 기준이 바뀌어도 프론트를 안 고친다
2. 발표 시연 중 화면 문구가 흔들리지 않는다
3. 같은 지표가 지도·카드·비교표에서 다르게 표기되는 사고를 막는다

---

# Part I. 지표 언어 변환표

## 1. 공간 지표 — 퍼센트를 버린다

| 내부 지표 | 화면 표기 | 변환 규칙 |
|---|---|---|
| 불투수피복률 78.8% (구로동) | **콘크리트·아스팔트 · "10곳 중 8곳"** | `round(pct/10)` |
| 식생피복률 57.4% (진관동) | **나무·풀밭 · "10곳 중 6곳"** | 〃 |
| 수면비율 0.9% | **하천·물** | 〃 |
| MCI +63.0 (구로동) | **도시열 지수 81.5** | `(MCI+100)/2` → 0~100 |
| MCI −26.2 (진관동) | **도시열 지수 36.9** | 〃 |

> 나지·습지는 불투수에도 식생에도 넣지 않는다(분류 기준: `docs/06`).
> 그래서 **ISR + VCR + WSR 의 합은 100%가 아니다.** 서버가 `caveat` 로 이 단서를 함께 보낸다.

**왜 바꾸나**: "불투수피복률"은 아무도 모른다. "10곳 중 4곳이 콘크리트"는 누구나 안다.
MCI는 −100~+100이라 음수가 나와서 직관적이지 않다. **화면에는 0~100만 노출**한다.

### 도시열 지수 등급

| 범위 | 등급 | 색상 | 문구 |
|---|---|---|---|
| 0–30 | 매우 낮음 | `#2E7D32` | 나무와 흙이 대부분이라 열이 잘 빠집니다 |
| 30–45 | 낮음 | `#66BB6A` | 나무·풀밭이 많은 편입니다 |
| 45–55 | 보통 | `#FBC02D` | 포장면과 녹지가 비슷합니다 |
| 55–70 | 높음 | `#EF6C00` | 포장면이 많아 열이 갇히기 쉽습니다 |
| 70–100 | 매우 높음 | `#C62828` | 대부분이 콘크리트·아스팔트입니다 |

---

## 2. 전력 지표 — 분수로 말한다

| 내부 지표 | 화면 표기 |
|---|---|
| R = 33.1% | **"평소보다 약 3분의 1 더 쓰고 있습니다"** |
| β = 2.77 %p/℃ | **"기온이 1℃ 오르면 전기 사용이 2.8% 늘어납니다"** |
| T\* = 18.0℃ | **"기온이 18℃를 넘으면 냉방이 시작됩니다"** |
| θ = 35,945 kWh | **"위험선"** (숫자는 툴팁에만) |
| 초과 12일 / 49일 | **"여름 49일 중 12일이 위험일"** |

**"기저수요 대비 증가율"** 대신 **"평소보다 얼마나 더"**.
**"전환온도"** 대신 **"냉방이 켜지는 온도"**.
**"임계치"** 대신 **"위험선"**.

### 위험 등급 (실측 ÷ 위험선)

| 비율 | 등급 | 색상 | 문구 |
|---|---|---|---|
| < 0.85 | 안전 | `#2E7D32` | 평소 수준입니다 |
| 0.85–0.95 | 주의 | `#FBC02D` | 평소보다 높습니다 |
| 0.95–1.00 | 경계 | `#EF6C00` | 위험선에 근접했습니다 |
| ≥ 1.00 | 위험 | `#C62828` | 위험선을 넘었습니다 |

---

## 3. 발표에서 쓸 문장 (실측값 기준)

> "구로동 생활권은 **10곳 중 8곳이 콘크리트·아스팔트**라 도시열 지수 81.5점, '매우 높음'입니다.
> 진관동은 **10곳 중 6곳이 나무·풀밭**이라 36.9점, '낮음'입니다. **44점 차이**입니다."
>
> "그런데 여름에 **평소보다 3분의 1을 더 쓰고 있고**, 특히 **밤 시간대가 31%**로 구로동의 두 배 가까이 됩니다."
>
> "가장 더웠던 2022년 7월 10일, **오후 1시에 위험선을 넘었습니다.**"

수식 한 줄 없이 전달됩니다.

---

# Part II. API 계약

## 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| `GET` | `/api/dongs` | 동 목록 (미니맵 핀) |
| `GET` | `/api/dongs/geojson` | **지도 폴리곤 (FeatureCollection)** |
| `GET` | `/api/dong/{code}` | 동 상세 카드 |
| `GET` | `/api/dong/{code}/forecast?date=` | 24시간 시계열 |
| `GET` | `/api/compare?codes=A,B` | 두 동 비교표 |
| `GET` | `/api/meta` | 서비스 모드 · 미확보 항목 · 발표 단서 |

법정동코드: 구로동 `1153010100` · 진관동 `1138011400`

---

## ① `GET /api/dong/1138011400` — 동 상세

실제 데이터로 생성한 응답입니다.

```json
{
  "code": "1138011400",
  "name": "진관동",
  "microclimate": {
    "status": "ready",
    "heat_index": 36.9,
    "grade": "낮음",
    "color": "#66BB6A",
    "message": "나무·풀밭이 많은 편입니다",
    "components": {
      "paved":   { "percent": 31.2, "text": "10곳 중 3곳", "label": "콘크리트·아스팔트" },
      "green":   { "percent": 57.4, "text": "10곳 중 6곳", "label": "나무·풀밭" },
      "water":   { "percent": 0.9,  "text": "10곳 중 0곳", "label": "하천·물" },
      "bare":    { "percent": 8.9,  "text": "10곳 중 1곳", "label": "흙·빈 땅" },
      "wetland": { "percent": 1.6,  "text": "10곳 중 0곳", "label": "갈대밭·습지" }
    },
    "area_km2": 10.56,
    "basis": {
      "tag": "프로젝트 예비값",
      "method": "생활권 100m 버퍼 · 5m 격자 래스터화",
      "source": "세분류 토지피복지도 2022 (EGIS, 10개 도엽)",
      "clipped_to_dong": false,
      "note": "[프로젝트 예비값] 생활권 100m 버퍼 기준 · 도엽 병합 범위(법정동 경계 클리핑 전)",
      "caveat": "나지·습지는 불투수·식생 어디에도 포함하지 않으므로 세 비율의 합은 100%가 아닙니다"
    },
    "note": "[프로젝트 예비값] 생활권 100m 버퍼 기준 · 도엽 병합 범위(법정동 경계 클리핑 전)",
    "caveat": "나지·습지는 불투수·식생 어디에도 포함하지 않으므로 세 비율의 합은 100%가 아닙니다"
  },
  "demand": {
    "extra_usage_percent": 33.1,
    "extra_usage_text": "평소보다 약 3분의 1 더 쓰고 있습니다",
    "night_percent": 31.2,
    "day_percent": 34.7,
    "pattern": "주간형"
  },
  "cooling": {
    "switch_on_temp": 18.0,
    "switch_on_text": "기온이 18℃를 넘으면 냉방이 시작됩니다",
    "sensitivity": 2.77,
    "sensitivity_text": "기온이 1℃ 오르면 전기 사용이 2.8% 늘어납니다"
  },
  "peak": {
    "threshold_kwh": 35944.97,
    "threshold_text": "35,945 kWh",
    "risk_days": 12,
    "total_days": 49,
    "risk_days_text": "여름 49일 중 12일이 위험일"
  }
}
```

### `basis` · `note` · `caveat` — 값의 출처를 화면까지 끌고 간다 ★

`microclimate` 값은 **법정동 경계로 자르기 전** 생활권 100m 버퍼 값입니다(`docs/06`).
`status: "ready"` 여도 `note` 를 비우지 않는 이유가 여기 있습니다.

프론트는 **카드 하단에 `note`, 도넛 차트 옆에 `caveat` 를 그대로 출력**합니다.
값이 확정되면 `basis.clipped_to_dong` 이 `true` 가 되고 문구가 자동으로 바뀝니다.

### 미확보 데이터 처리 규칙 ★

값이 아직 없는 지표는 **null 을 그냥 내려보내면 프론트가 깨집니다.** 그래서 `status` 로 명시합니다.

```json
"microclimate": {
  "status": "pending",
  "heat_index": null,
  "components": { "paved": { "percent": null, "text": null, ... } },
  "note": "토지피복 도엽 확보 후 산출됩니다"
}
```

프론트는 `status === "pending"` 이면 **스켈레톤 + note 문구**를 띄웁니다.
발표 시연에서 "이 부분은 데이터 확보 중"이라고 화면이 스스로 말해주므로 오히려 정직해 보입니다.

---

## ② `GET /api/dong/{code}/forecast` — 24시간 시계열

```json
{
  "code": "1138011400",
  "name": "진관동",
  "date": "2022-07-10",
  "threshold_kwh": 35945.0,
  "weather": {
    "t_max": 35.4, "t_min": 25.6,
    "humidity": 68.0, "wind": 1.2,
    "heatwave": true
  },
  "points": [
    {
      "time": "2022-07-10T12:00:00",
      "hour": 12,
      "usage_kwh": 35196.6,
      "baseline_kwh": 22098.0,
      "extra_percent": 59.3,
      "temperature": 31.8,
      "risk_ratio": 0.979,
      "grade": "경계",
      "color": "#EF6C00",
      "message": "위험선에 근접했습니다"
    },
    {
      "time": "2022-07-10T13:00:00",
      "hour": 13,
      "usage_kwh": 36176.7,
      "baseline_kwh": 22385.9,
      "extra_percent": 61.6,
      "temperature": 32.3,
      "risk_ratio": 1.006,
      "grade": "위험",
      "color": "#C62828",
      "message": "위험선을 넘었습니다"
    }
  ]
}
```

**프론트 렌더링**
- `usage_kwh` → 실선
- `baseline_kwh` → 점선 (평소 수준)
- `threshold_kwh` → 가로 기준선
- `color` → 각 포인트 색상. 판정 로직 불필요

시연 포인트: **12시 "경계" → 13시 "위험"** 으로 넘어가는 순간이 화면에서 색으로 보입니다.

`weather` 는 그날의 기상 요약입니다(헤더의 `폭염 35.4℃` 칩).
`humidity` · `wind` 는 원자료가 있을 때만 채워지고, 없으면 `null` 입니다 — **프론트는 해당 칩을 숨깁니다.**
`heatwave` 는 일 최고기온 ≥ 33℃ 판정을 백엔드가 내린 결과입니다.

---

## ③ `GET /api/dongs/geojson` — 지도 폴리곤

표준 GeoJSON `FeatureCollection` 입니다. 지도 라이브러리에 **그대로** 넣으면 됩니다.
(Leaflet `L.geoJSON(data)` · Mapbox `map.addSource({type:"geojson",data})` · deck.gl `GeoJsonLayer`)

```json
{
  "type": "FeatureCollection",
  "status": "ready",
  "bbox": [126.87, 37.49, 126.96, 37.66],
  "source": "data/dong_boundaries.geojson",
  "note": null,
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[[126.92, 37.62], ...]] },
      "properties": {
        "code": "1138011400",
        "name": "진관동",
        "status": "ready",
        "heat_index": 36.9,
        "grade": "낮음",
        "color": "#66BB6A",
        "message": "나무·풀밭이 많은 편입니다",
        "extra_usage_percent": 33.1,
        "risk_days": 12,
        "lat": 37.637, "lng": 126.933,
        "tooltip": "진관동 · 도시열 36.9 · 낮음",
        "fill_color": "#66BB6A",
        "fill_opacity": 0.32,
        "stroke_color": "#2E9E6B",
        "stroke_width": 4,
        "stroke_opacity": 0.95
      }
    }
  ]
}
```

**프론트 렌더링**
- `fill_color` / `fill_opacity` / `stroke_*` 를 그대로 쓴다. **색을 계산하지 않는다**
- `bbox` 로 지도 범위를 맞춘다 `[서, 남, 동, 북]`
- `tooltip` 은 말풍선에 그대로 찍는다
- 좌표계는 **EPSG:4326**, 좌표 순서는 `[경도, 위도]`

지도 폴리곤 색과 우측 카드 색은 **같은 등급표(`serialize.HEAT_GRADES`)에서 나옵니다.**
둘이 어긋나는 사고는 `tests/test_api.py::test_map_color_matches_card_color` 가 막습니다.

### 경계 파일이 없을 때

`503` + `{"status": "pending", "note": "..."}` 로 답합니다. 프론트는 폴리곤 레이어를 건너뛰고
`/api/dongs` 의 핀만 찍으면 됩니다. 지도가 빈 화면이 되지 않습니다.

경계 SHP 을 받으면 한 줄로 변환합니다.

```bash
python -m urban_microgrid.landcover 법정동경계.shp
```

`data/dong_boundaries.geojson` 이 생기고, 서버를 재시작하면 폴리곤이 나갑니다.
코드 컬럼 이름(`EMD_CD` · `ADM_CD` · `adm_cd` …)은 자동으로 찾습니다.

---

## ④ `GET /api/compare` — 비교표

행 단위로 내려보내 **표를 그대로 그릴 수 있게** 합니다.

```json
{
  "dongs": ["구로동", "진관동"],
  "rows": [
    { "label": "도시열 지수",      "unit": "",  "values": { "구로동": 81.5, "진관동": 36.9 } },
    { "label": "콘크리트·아스팔트", "unit": "%", "values": { "구로동": 78.8, "진관동": 31.2 } },
    { "label": "나무·풀밭",        "unit": "%", "values": { "구로동": 15.9, "진관동": 57.4 } },
    { "label": "하천·물",           "unit": "%", "values": { "구로동": 0.9,  "진관동": 0.9  } },
    { "label": "평소 대비 추가 사용", "unit": "%", "values": { "구로동": 27.6, "진관동": 33.1 } },
    { "label": "야간 추가 사용",     "unit": "%", "values": { "구로동": 17.8, "진관동": 31.2 } },
    { "label": "주간 추가 사용",     "unit": "%", "values": { "구로동": 35.8, "진관동": 34.7 } },
    { "label": "냉방 시작 온도",     "unit": "℃", "values": { "구로동": 19.0, "진관동": 18.0 } },
    { "label": "1℃당 증가율",       "unit": "%", "values": { "구로동": 2.76, "진관동": 2.77 } }
  ]
}
```

---

## ⑤ `GET /api/dongs` — 지도 마커

```json
{
  "dongs": [
    { "code": "1138011400", "name": "진관동", "lat": 37.637, "lng": 126.933,
      "heat_index": 36.9, "grade": "낮음", "color": "#66BB6A", "risk_days": 12 },
    { "code": "1153010100", "name": "구로동", "lat": 37.495, "lng": 126.887,
      "heat_index": 81.5, "grade": "매우 높음", "color": "#C62828", "risk_days": 12 }
  ]
}
```

좌표는 법정동 경계 SHP의 중심점(centroid)에서 뽑습니다. **표출용이므로 EPSG:4326으로 변환** 후 내려보냅니다.

---

# Part III. 규칙 요약 (프론트·백엔드 합의사항)

| # | 규칙 |
|---|---|
| 1 | 프론트는 등급·색상을 계산하지 않는다. 백엔드가 준 값을 그대로 쓴다 |
| 2 | 모든 퍼센트는 소수 1자리, kWh는 정수, 온도는 소수 1자리 |
| 3 | 값이 없으면 `null` + `status: "pending"` + `note` 를 함께 보낸다 |
| 4 | 시각은 ISO 8601 (`2022-07-10T13:00:00`), 시간대는 KST 고정 |
| 5 | 색상은 hex 문자열. 등급 기준이 바뀌면 백엔드만 수정 |
| 6 | 동 식별은 항상 10자리 법정동코드. 이름으로 조회하지 않는다 |

---

# Part IV. 구현 위치

| 기능 | 파일 · 함수 |
|---|---|
| 등급 기준표 | `serialize.HEAT_GRADES`, `RISK_GRADES` |
| "10곳 중 N곳" 변환 | `serialize.as_ten_places` |
| 도시열 지수 (0–100) | `serialize.heat_index` |
| "평소보다 N분의 1" 문장 | `serialize.as_extra_usage_sentence` |
| 냉방 문장 2종 | `serialize.as_ac_sentence`, `as_switch_on_sentence` |
| 동 상세 응답 | `serialize.build_dong_summary` |
| 시계열 응답 | `serialize.build_forecast` |
| 지도 폴리곤 | `serialize.build_geojson`, `map_style` |
| 그날의 기상 요약 | `serialize.build_weather` |
| 비교표 응답 | `serialize.build_compare` |

등급 문구를 바꾸고 싶으면 `HEAT_GRADES` / `RISK_GRADES` 두 리스트만 수정하면 전 화면에 반영됩니다.
