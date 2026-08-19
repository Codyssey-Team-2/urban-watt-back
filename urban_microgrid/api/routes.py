"""
Urban-MicroGrid | 엔드포인트

    GET /api/dongs                      지도 마커
    GET /api/dong/{code}                동 상세 카드
    GET /api/dong/{code}/forecast       24시간 시계열
    GET /api/alerts                     경보 목록
    GET /api/compare?codes=A,B          비교표
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
    return store.markers()


@router.get("/alerts", response_model=sc.Alerts, summary="경보 목록")
def get_alerts(
    limit: int = Query(C.ALERTS_TOP_N, ge=1, le=1000, description="반환 개수"),
    dong: str | None = Query(None, description="동 이름으로 필터 (선택)"),
    store: DataStore = Depends(get_store),
):
    """`over_percent` 내림차순. `count` 는 전체 초과 건수(반환 개수가 아니다)."""
    return store.alerts(limit=limit, dong=dong)


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
