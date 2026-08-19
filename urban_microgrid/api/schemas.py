"""
Urban-MicroGrid | 응답 스키마

docs/02_지표언어_API계약.md 의 계약을 파이썬 타입으로 고정한다.
계약과 어긋난 응답은 여기서 터진다 — 발표 시연 중 프론트가 깨지는 것보다
서버가 개발 단계에서 터지는 편이 낫다.

계약 규칙 (Part III)
    · 퍼센트 소수 1자리 · kWh 반올림 · 온도 소수 1자리
    · 값이 없으면 null + status="pending" + note
    · 시각은 ISO 8601 문자열, KST 고정 (타임존 오프셋 없음)
    · 등급·색상·문구는 백엔드가 만들어 내려보낸다
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── 공통 ────────────────────────────────────────────────
class Graded(BaseModel):
    """등급 3종 세트. 프론트는 이 값을 그대로 쓴다(판정 로직 없음)."""
    grade: Optional[str] = None
    color: Optional[str] = None
    message: Optional[str] = None


# ── ① 동 상세 ───────────────────────────────────────────
class CoverComponent(BaseModel):
    percent: Optional[float] = None
    text: Optional[str] = None          # "10곳 중 4곳"
    label: str                          # "콘크리트·아스팔트"


class CoverComponents(BaseModel):
    paved: CoverComponent
    green: CoverComponent
    water: CoverComponent
    # 나지·습지는 불투수에도 식생에도 넣지 않는다 → 세 비율 합이 100% 가 아니다
    bare: Optional[CoverComponent] = None
    wetland: Optional[CoverComponent] = None


class MicroclimateBasis(BaseModel):
    """이 피복률이 '어떤 기준의 값인가'. 화면에 단서로 그대로 띄운다."""
    tag: str                            # "프로젝트 예비값"
    method: str
    source: str
    clipped_to_dong: bool               # False = 법정동 경계로 자르기 전
    note: str
    caveat: str


class Microclimate(Graded):
    status: Literal["ready", "pending"]
    heat_index: Optional[float] = None  # 0~100 (MCI 를 화면 척도로 변환)
    components: CoverComponents
    area_km2: Optional[float] = None
    basis: Optional[MicroclimateBasis] = None
    note: Optional[str] = None          # pending 사유 또는 예비값 표기
    caveat: Optional[str] = None        # 합이 100% 가 아닌 이유


class Demand(BaseModel):
    extra_usage_percent: Optional[float] = None   # 정규화 지표 R
    extra_usage_text: Optional[str] = None
    night_percent: Optional[float] = None
    day_percent: Optional[float] = None
    pattern: Optional[str] = None                 # 야간형 / 주간형


class Cooling(BaseModel):
    switch_on_temp: Optional[float] = None        # 전환온도 T*
    switch_on_text: Optional[str] = None
    sensitivity: Optional[float] = None           # 냉방민감도 β
    sensitivity_text: Optional[str] = None


class Peak(BaseModel):
    threshold_kwh: Optional[float] = None         # 동별 백분위 임계 θ
    threshold_text: Optional[str] = None
    risk_days: Optional[int] = None
    total_days: Optional[int] = None
    risk_days_text: Optional[str] = None


class DongSummary(BaseModel):
    code: str = Field(..., min_length=10, max_length=10, description="법정동코드")
    name: str
    microclimate: Microclimate
    demand: Demand
    cooling: Cooling
    peak: Peak


# ── ② 시계열 ────────────────────────────────────────────
class ForecastPoint(Graded):
    time: str                          # "2022-07-10T13:00:00"
    hour: int
    usage_kwh: float
    baseline_kwh: Optional[float] = None
    extra_percent: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    wind: Optional[float] = None
    risk_ratio: float


class DayWeather(BaseModel):
    """헤더의 기상 칩. 값이 없는 항목은 프론트가 칩을 숨긴다."""
    t_max: Optional[float] = None
    t_min: Optional[float] = None
    humidity: Optional[float] = None
    wind: Optional[float] = None
    heatwave: Optional[bool] = None      # 일 최고기온 ≥ 33℃


class Forecast(BaseModel):
    code: str
    name: str
    date: str
    threshold_kwh: Optional[float] = None
    weather: Optional[DayWeather] = None
    points: list[ForecastPoint]


# ── ④ 비교표 ────────────────────────────────────────────
class CompareRow(BaseModel):
    label: str
    unit: str
    values: dict[str, Optional[float]]


class Compare(BaseModel):
    dongs: list[str]
    rows: list[CompareRow]


# ── 모델 성능 ──────────────────────────────────────────────
class ModelMetric(BaseModel):
    key: Literal["a", "b", "c"]
    label: str
    mape: Optional[float] = None
    rmse: Optional[float] = None
    mae: Optional[float] = None


class ModelPerformance(BaseModel):
    status: Literal["ready", "pending"]
    metric: str
    models: list[ModelMetric]
    improvement_percent: Optional[float] = None
    improvement_basis: str
    note: str
    caveat: str


# ── ⑤ 지도 마커 ─────────────────────────────────────────
class DongMarker(BaseModel):
    code: str
    name: str
    lat: float
    lng: float
    heat_index: Optional[float] = None
    grade: Optional[str] = None
    color: str                          # 미확보 동은 회색(#9E9E9E)
    risk_days: Optional[int] = None


class DongList(BaseModel):
    dongs: list[DongMarker]
    latlng_source: str                  # "provisional" | "shp"


# ── ⑥ 지도 폴리곤 (GeoJSON) ─────────────────────────────
class FeatureProperties(BaseModel):
    """지도 라이브러리에 그대로 넘기는 속성. 프론트는 색을 계산하지 않는다."""
    code: str
    name: Optional[str] = None
    status: str
    heat_index: Optional[float] = None
    grade: Optional[str] = None
    color: str
    message: Optional[str] = None
    extra_usage_percent: Optional[float] = None
    risk_days: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    tooltip: Optional[str] = None
    fill_color: str
    fill_opacity: float
    stroke_color: str
    stroke_width: float
    stroke_opacity: float


class DongFeature(BaseModel):
    type: Literal["Feature"]
    geometry: dict[str, Any]            # EPSG:4326, [경도, 위도]
    properties: FeatureProperties


class DongGeoJSON(BaseModel):
    type: Literal["FeatureCollection"]
    status: Literal["ready", "pending"]
    bbox: Optional[list[float]] = None  # [서, 남, 동, 북] — 지도 범위 맞추기
    features: list[DongFeature]
    source: Optional[str] = None
    note: Optional[str] = None


# ── ⑦ AI 브리핑 ─────────────────────────────────────────
class BriefingPrompt(BaseModel):
    """실제로 모델에 넘어간 프롬프트. 프롬프트 튜닝을 코드 수정 없이 하기 위해 노출한다."""
    system: str
    user: str


class Briefing(BaseModel):
    codes: list[str]
    date: Optional[str] = None
    status: Literal["ready", "needs_review"]
    text: str
    provider: str
    model: str
    usage: Optional[dict[str, Any]] = None
    # 사실표에 없는 숫자 — 비어 있지 않으면 화면에 경고를 띄운다
    unverified_numbers: list[str] = Field(default_factory=list)
    note: Optional[str] = None
    facts: dict[str, Any]
    prompt: BriefingPrompt


# ── ⑧ 메타 (데모 정직성 패널) ────────────────────────────
class Meta(BaseModel):
    service: str
    version: str
    mode: Literal["live", "snapshot"]
    mode_text: str
    period: dict[str, str]
    llm: dict[str, Any]
    dongs: list[dict[str, Any]]
    pending: list[str]                  # 아직 못 만드는 것 + 사유
    caveats: list[str]                  # 발표에서 함께 읽어야 하는 단서
