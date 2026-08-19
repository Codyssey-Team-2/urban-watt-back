"""
Urban-MicroGrid | 엔드포인트

    GET /api/dongs                      지도 마커
    GET /api/dongs/geojson              지도 폴리곤 (FeatureCollection)
    GET /api/dong/{code}                동 상세 카드
    GET /api/dong/{code}/forecast       24시간 시계열 + 그날의 기상 요약
    GET /api/compare?codes=A,B          비교표
    GET /api/briefing?codes=A,B         AI 브리핑 (LLM)
    GET /api/meta                       모드·미확보 항목·단서 (시연 정직성 패널)

동 식별은 항상 10자리 법정동코드다. 이름으로 조회하지 않는다.
"""
from fastapi import APIRouter, Depends, Query

from .. import config as C
from . import schemas as sc
from .store import DataStore, get_store

router = APIRouter(prefix=C.API_PREFIX, tags=["urban-microgrid"])

_ALL_CODES = ",".join(C.DONG_META)


@router.get("/meta", response_model=sc.Meta,
            summary="서비스 상태 · 미확보 항목")
def get_meta(store: DataStore = Depends(get_store)):
    """
    지금 이 서버가 무엇으로 답하고 있는지(live / snapshot)와
    아직 못 만드는 항목을 그대로 내려보낸다.
    시연 중 "이 부분은 데이터 확보 중"을 화면이 스스로 말하게 하기 위한 것.
    """
    return store.meta()


@router.get("/dongs", response_model=sc.DongList, summary="지도 마커")
def get_dongs(store: DataStore = Depends(get_store)):
    """미니맵·핀 표시용. 폴리곤이 필요하면 `/api/dongs/geojson` 을 쓴다."""
    return store.markers()


@router.get("/dongs/geojson", response_model=sc.DongGeoJSON,
            summary="지도 폴리곤 (GeoJSON)")
def get_dongs_geojson(store: DataStore = Depends(get_store)):
    """
    법정동 경계 폴리곤. 표준 FeatureCollection 이라 지도 라이브러리에
    그대로 넣으면 된다(Leaflet `L.geoJSON` · Mapbox `addSource` · deck.gl `GeoJsonLayer`).

    채움색·투명도·테두리까지 `properties` 에 들어 있다. 프론트는 색을 고르지 않는다.
    좌표는 EPSG:4326, 순서는 [경도, 위도].
    """
    return store.geojson()


@router.get("/compare", response_model=sc.Compare, summary="비교표")
def get_compare(
    codes: str = Query(_ALL_CODES, description="쉼표로 구분한 법정동코드"),
    store: DataStore = Depends(get_store),
):
    """행 단위로 내려보내 프론트가 표를 그대로 그릴 수 있게 한다."""
    wanted, seen = [], set()
    for c in codes.split(","):
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            wanted.append(c)
    return store.compare(wanted)


@router.get("/briefing", response_model=sc.Briefing, summary="AI 브리핑")
def get_briefing(
    codes: str = Query(_ALL_CODES, description="쉼표로 구분한 법정동코드"),
    date: str | None = Query(None, description="YYYY-MM-DD (기상 요약용, 선택)"),
    refresh: bool = Query(False, description="캐시를 무시하고 다시 생성"),
    store: DataStore = Depends(get_store),
):
    """
    실측값으로 만든 사실표를 프롬프트에 넣어 모델에 넘긴다.
    모델은 분석하지 않는다 — 이미 끝난 분석을 문장으로 옮길 뿐이다.

    응답에는 실제로 넘어간 `prompt` 와 `facts` 가 함께 들어 있어
    코드를 열지 않고도 프롬프트를 검토할 수 있다.
    `unverified_numbers` 가 비어 있지 않으면 사실표에 없는 숫자가 섞인 것이다.
    """
    wanted = [c.strip() for c in codes.split(",") if c.strip()]
    return store.briefing(wanted, date, refresh=refresh)


@router.get("/dong/{code}", response_model=sc.DongSummary, summary="동 상세")
def get_dong(code: str, store: DataStore = Depends(get_store)):
    return store.summary(code)


@router.get("/dong/{code}/forecast", response_model=sc.Forecast,
            summary="24시간 시계열")
def get_forecast(
    code: str,
    date: str | None = Query(None, description="YYYY-MM-DD (기본: 시연 기준일)"),
    store: DataStore = Depends(get_store),
):
    """
    `usage_kwh` 실선 · `baseline_kwh` 점선 · `threshold_kwh` 가로 기준선.
    각 포인트의 `color` 를 그대로 쓰면 되고, 프론트에 판정 로직은 없다.
    """
    return store.forecast(code, date)
