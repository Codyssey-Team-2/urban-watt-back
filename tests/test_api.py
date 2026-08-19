"""
Urban-MicroGrid | API 계약 회귀 테스트

docs/02_지표언어_API계약.md 의 Part III 규칙을 그대로 검사한다.
발표 전에 한 번 돌려서 초록이면 프론트가 깨질 일이 없다.

    python tests/test_api.py        (pytest 없이도 실행됨)
    pytest tests/test_api.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient   # noqa: E402

from urban_microgrid import config as C     # noqa: E402
from urban_microgrid.api.main import app    # noqa: E402

client = TestClient(app)
JINGWAN = "1138011400"
GURO = "1153010100"


def _get(url, status=200):
    r = client.get(url)
    assert r.status_code == status, f"{url} → {r.status_code} (기대 {status})"
    return r.json()


# ── 계약 규칙 ────────────────────────────────────────────
def test_meta_declares_mode():
    m = _get("/api/meta")
    assert m["mode"] in ("live", "snapshot")
    # 미확보 항목과 단서는 항상 응답에 실린다 (시연 정직성)
    assert m["pending"] and m["caveats"]


def test_dong_summary_shape():
    for code in (JINGWAN, GURO):
        d = _get(f"/api/dong/{code}")
        assert d["code"] == code and len(d["code"]) == 10
        mc = d["microclimate"]
        assert mc["status"] in ("ready", "pending")
        # 규칙 3: 값이 없으면 null + status + note 를 함께 보낸다
        if mc["status"] == "pending":
            assert mc["heat_index"] is None and mc["note"]
        else:
            assert mc["heat_index"] is not None and mc["color"].startswith("#")
        # 계약 3종은 항상 있어야 하고, 나지·습지는 추가 항목이다
        assert {"paved", "green", "water"} <= set(mc["components"])


def test_rounding_rules():
    """규칙 2: 퍼센트 소수 1자리 · kWh 반올림 · 온도 소수 1자리."""
    for code in (JINGWAN, GURO):
        d = _get(f"/api/dong/{code}")
        for v in (d["demand"]["extra_usage_percent"],
                  d["demand"]["night_percent"],
                  d["demand"]["day_percent"]):
            assert v is None or round(v, 1) == v, f"{code} 퍼센트 자릿수: {v}"
        th = d["peak"]["threshold_kwh"]
        assert th is None or round(th, 1) == th, f"{code} θ 자릿수: {th}"


def test_frontend_never_computes():
    """규칙 1·5: 등급·색상·문구는 전부 백엔드가 만들어 보낸다."""
    f = _get(f"/api/dong/{JINGWAN}/forecast")
    assert f["points"], "시계열이 비어 있습니다"
    for p in f["points"]:
        assert p["grade"] and p["color"].startswith("#") and p["message"]
        assert p["time"].endswith(":00:00") and "T" in p["time"]   # 규칙 4
        assert p["risk_ratio"] >= 0


def test_forecast_threshold_matches_summary():
    """시계열의 위험선과 상세 카드의 위험선이 갈라지면 화면이 거짓말을 한다."""
    f = _get(f"/api/dong/{JINGWAN}/forecast")
    d = _get(f"/api/dong/{JINGWAN}")
    assert f["threshold_kwh"] == d["peak"]["threshold_kwh"]


def test_alerts_sorted_desc():
    a = _get("/api/alerts?limit=5")
    over = [x["over_percent"] for x in a["alerts"]]
    assert over == sorted(over, reverse=True)
    assert a["count"] >= len(a["alerts"])      # count 는 전체 초과 건수
    for x in a["alerts"]:
        assert x["usage_kwh"] > x["threshold_kwh"]


def test_compare_is_row_oriented():
    c = _get(f"/api/compare?codes={GURO},{JINGWAN}")
    assert c["dongs"] == ["구로동", "진관동"]        # 요청 순서를 지킨다
    for row in c["rows"]:
        assert set(row["values"]) == set(c["dongs"])


def test_markers_always_have_color():
    """미확보 동도 색이 있어야 지도가 깨지지 않는다."""
    for m in _get("/api/dongs")["dongs"]:
        assert m["color"].startswith("#")
        assert m["code"] in C.DONG_META


# ── 실패 경로 ────────────────────────────────────────────
def test_unknown_code_is_404_not_500():
    e = _get("/api/dong/9999999999", status=404)
    assert e["status"] == "not_found" and e["note"]


def test_missing_data_is_503_with_note():
    """미확보 자료는 에러가 아니라 '아직 없음'으로 답한다."""
    if C.SNAPSHOT_FORECAST.get(GURO) or _get("/api/meta")["mode"] == "live":
        return
    e = _get(f"/api/dong/{GURO}/forecast", status=503)
    assert e["status"] == "pending" and e["note"]


# ── 데이터 함정 방어 ─────────────────────────────────────
def test_jingwan_code_is_11400():
    """10800 은 다른 동이다. 코드가 바뀌면 값이 6천↔41만 으로 튄다."""
    assert C.DONG_META[JINGWAN]["bjdong"] == "11400"
    assert _get(f"/api/dong/{JINGWAN}")["name"] == "진관동"


def test_no_unmeasured_microclimate():
    """
    도엽 전체값(ISR 5.37)이나 창신동 예비값(83.0/13.1)이 실수로
    구로동·진관동 값으로 들어가지 않았는지 확인한다.
    """
    banned = {5.37, 87.59, 83.0, 13.1}
    for code in C.DONG_META:
        mc = _get(f"/api/dong/{code}")["microclimate"]
        isr = mc["components"]["paved"]["percent"]
        vcr = mc["components"]["green"]["percent"]
        assert isr not in banned and vcr not in banned, f"{code} 에 예비값이 들어갔습니다"


def test_microclimate_matches_config():
    """
    산출 결과(docs/06)가 화면까지 그대로 도달하는지.
    도시열 지수는 (ISR − VCR + 100) / 2 여야 한다.
    """
    for code, mc in C.MICROCLIMATE_PRELIM.items():
        got = _get(f"/api/dong/{code}")["microclimate"]
        assert got["status"] == "ready"
        comp = got["components"]
        assert comp["paved"]["percent"] == mc["ISR"]
        assert comp["green"]["percent"] == mc["VCR"]
        assert comp["water"]["percent"] == mc["WSR"]
        assert comp["bare"]["percent"] == mc["bare"]
        assert comp["wetland"]["percent"] == mc["wetland"]
        expected = round((mc["ISR"] - mc["VCR"] + 100) / 2, 1)
        assert got["heat_index"] == expected, f"{code}: {got['heat_index']} ≠ {expected}"
        assert got["grade"] and got["color"].startswith("#")


def test_prelim_tag_reaches_the_screen():
    """
    법정동 경계 클리핑 전 값이라는 단서가 응답에서 빠지면 안 된다.
    이 테스트가 '예비값'을 '확정값'처럼 보이게 하는 회귀를 막는다.
    """
    if C.MICROCLIMATE_BASIS.get("clipped_to_dong"):
        return
    for code in C.MICROCLIMATE_PRELIM:
        mc = _get(f"/api/dong/{code}")["microclimate"]
        assert mc["basis"] and mc["basis"]["tag"] == "프로젝트 예비값"
        assert mc["basis"]["clipped_to_dong"] is False
        assert mc["note"] and mc["caveat"]
    meta = _get("/api/meta")
    assert any("클리핑" in x for x in meta["pending"] + meta["caveats"])


def test_cover_percentages_do_not_sum_to_100():
    """
    나지·습지를 어느 쪽에도 넣지 않았으므로 합은 100% 가 아니다.
    합을 100 으로 맞추려고 누군가 값을 손대면 여기서 걸린다.
    """
    for code in C.MICROCLIMATE_PRELIM:
        comp = _get(f"/api/dong/{code}")["microclimate"]["components"]
        three = sum(comp[k]["percent"] for k in ("paved", "green", "water"))
        assert three < 99.9, f"{code}: ISR+VCR+WSR = {three} — 분류 기준이 바뀌었습니다"


def test_live_pipeline_if_raw_data_present():
    """원자료가 있으면 live 모드로 떠야 한다 (스냅샷에 눌러앉지 않게)."""
    try:
        import pandas  # noqa: F401
    except ImportError:
        print("  ⏭  pandas 미설치 — live 모드 검사 건너뜀")
        return
    if not all(p.exists() for p in (C.PATH_POWER_CSV, C.PATH_POWER_XLSX, C.PATH_ASOS)):
        print("  ⏭  원자료 없음 — live 모드 검사 건너뜀")
        return
    assert _get("/api/meta")["mode"] == "live"
    f = _get(f"/api/dong/{GURO}/forecast?date={C.FORECAST_DEMO_DATE}")
    assert len(f["points"]) == 24


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ✅ {name}")
        except AssertionError as e:
            fails += 1
            print(f"  ❌ {name}: {e}")
    print("\n" + ("모두 통과" if not fails else f"{fails}건 실패"))
    sys.exit(1 if fails else 0)
