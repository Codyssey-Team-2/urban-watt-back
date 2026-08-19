"""
Urban-MicroGrid | 프론트엔드 응답 직렬화

설계 원칙
────────────────────────────────────────────────────────────
프론트엔드는 계산하지 않는다.
등급·라벨·색상·설명문까지 전부 백엔드가 만들어 내려보낸다.

    ❌  프론트가 MCI 38.4 를 받아서 "이건 낮음이네" 판단
    ✅  백엔드가 {"value": 38.4, "grade": "낮음", "color": "#4A90D9",
                "label": "나무·풀밭이 많은 편"} 을 통째로 내려줌

이렇게 해야 등급 기준이 바뀔 때 프론트를 안 고쳐도 되고,
발표 시연에서 화면 문구가 흔들리지 않는다.
"""
import json

from . import config as C

# pandas 는 시계열 빌더(build_forecast / build_alerts)에서만 쓴다.
# 원자료 없이 실측 스냅샷만 서빙하는 API 모드에서는 과학 스택이 없어도
# 이 모듈이 임포트되어야 하므로 최상단에서 불러오지 않는다.


# ══════════════════════════════════════════════════════════
#  등급 기준 (여기만 고치면 전 화면에 반영된다)
# ══════════════════════════════════════════════════════════
HEAT_GRADES = [
    (0,  30, "매우 낮음", "#2E7D32", "나무와 흙이 대부분이라 열이 잘 빠집니다"),
    (30, 45, "낮음",      "#66BB6A", "나무·풀밭이 많은 편입니다"),
    (45, 55, "보통",      "#FBC02D", "포장면과 녹지가 비슷합니다"),
    (55, 70, "높음",      "#EF6C00", "포장면이 많아 열이 갇히기 쉽습니다"),
    (70, 101, "매우 높음", "#C62828", "대부분이 콘크리트·아스팔트입니다"),
]

RISK_GRADES = [
    (0.00, 0.85, "안전",  "#2E7D32", "평소 수준입니다"),
    (0.85, 0.95, "주의",  "#FBC02D", "평소보다 높습니다"),
    (0.95, 1.00, "경계",  "#EF6C00", "위험선에 근접했습니다"),
    (1.00, 9.99, "위험",  "#C62828", "위험선을 넘었습니다"),
]


def _grade(value, table):
    for lo, hi, name, color, desc in table:
        if lo <= value < hi:
            return {"grade": name, "color": color, "message": desc}
    return {"grade": "-", "color": "#9E9E9E", "message": "판정 불가"}


# ══════════════════════════════════════════════════════════
#  단위 · 언어 변환
# ══════════════════════════════════════════════════════════
def as_ten_places(ratio_pct):
    """
    83.0 %  →  "10곳 중 8곳"
    퍼센트보다 훨씬 직관적이라 카드 UI 부제목에 쓴다.
    """
    if ratio_pct is None:
        return None
    n = round(ratio_pct / 10)
    return f"10곳 중 {n}곳"


def as_soccer_field(area_m2):
    """면적을 축구장 환산 (1면 ≈ 7,140 ㎡)."""
    if area_m2 is None:
        return None
    return round(area_m2 / 7140, 1)


def heat_index(isr, vcr):
    """
    도시열 지수 = (MCI + 100) / 2,  0~100
    MCI 는 −100~+100 이라 일반인에게 직관적이지 않다.
    화면에는 항상 0~100 척도로만 노출한다.
    """
    if isr is None or vcr is None:
        return None
    return round(((isr - vcr) + 100) / 2, 1)


def as_extra_usage_sentence(r_pct):
    """33.1 % → '평소보다 약 1/3 더 쓰고 있습니다'"""
    if r_pct is None:
        return None
    if r_pct < 10:
        return "평소와 비슷합니다"
    frac = round(100 / r_pct)
    return f"평소보다 약 {frac}분의 1 더 쓰고 있습니다"


def as_ac_sentence(beta):
    """2.77 %p/℃ → '기온이 1도 오르면 전기 사용이 2.8% 늘어납니다'"""
    if beta is None:
        return None
    return f"기온이 1℃ 오르면 전기 사용이 {beta:.1f}% 늘어납니다"


def as_switch_on_sentence(t_star):
    """18.0 ℃ → '기온이 18도를 넘으면 냉방이 시작됩니다'"""
    if t_star is None:
        return None
    return f"기온이 {t_star:.0f}℃를 넘으면 냉방이 시작됩니다"


# ══════════════════════════════════════════════════════════
#  응답 빌더
# ══════════════════════════════════════════════════════════
def build_dong_summary(dong, code, isr=None, vcr=None, wsr=None,
                       bare=None, wetland=None, area_km2=None, basis=None,
                       r_mean=None, r_night=None, r_day=None,
                       t_star=None, beta=None, theta=None,
                       risk_days=None, total_days=None):
    """
    GET /api/dong/{code} — 동 상세 카드 1개.

    basis 는 '이 피복률이 어떤 기준의 값인가'를 담은 dict 다(config.MICROCLIMATE_BASIS).
    법정동 경계 클리핑 전 예비값이라는 사실이 화면까지 그대로 따라가야 하므로
    ready 상태에서도 note 를 비우지 않는다.
    """
    hi = heat_index(isr, vcr)
    pending = hi is None
    basis = basis or {}

    return {
        "code": code,
        "name": dong,
        "microclimate": {
            "status": "pending" if pending else "ready",
            "heat_index": hi,
            **({} if pending else _grade(hi, HEAT_GRADES)),
            "components": {
                "paved": {"percent": isr, "text": as_ten_places(isr),
                          "label": "콘크리트·아스팔트"},
                "green": {"percent": vcr, "text": as_ten_places(vcr),
                          "label": "나무·풀밭"},
                "water": {"percent": wsr, "text": as_ten_places(wsr),
                          "label": "하천·물"},
                # 나지·습지는 불투수에도 식생에도 넣지 않는다.
                # 화면에서 "왜 합이 100%가 아닌가"에 답할 수 있게 함께 내려보낸다.
                "bare": {"percent": bare, "text": as_ten_places(bare),
                         "label": "흙·빈 땅"},
                "wetland": {"percent": wetland, "text": as_ten_places(wetland),
                            "label": "갈대밭·습지"},
            },
            "area_km2": area_km2,
            "basis": None if pending else (basis or None),
            "note": (basis.get("note") if not pending
                     else "토지피복 도엽 확보 후 산출됩니다"),
            "caveat": None if pending else basis.get("caveat"),
        },
        "demand": {
            "extra_usage_percent": r_mean,
            "extra_usage_text": as_extra_usage_sentence(r_mean),
            "night_percent": r_night,
            "day_percent": r_day,
            "pattern": ("야간형" if (r_night or 0) > (r_day or 0) else "주간형"),
        },
        "cooling": {
            "switch_on_temp": t_star,
            "switch_on_text": as_switch_on_sentence(t_star),
            "sensitivity": beta,
            "sensitivity_text": as_ac_sentence(beta),
        },
        "peak": {
            "threshold_kwh": round(theta, 1) if theta is not None else None,
            "threshold_text": f"{theta:,.0f} kWh" if theta else None,
            "risk_days": risk_days,
            "total_days": total_days,
            "risk_days_text": (f"여름 {total_days}일 중 {risk_days}일이 위험일"
                               if risk_days is not None else None),
        },
    }


def build_forecast(df_dong, theta):
    """
    GET /api/dong/{code}/forecast — 24시간 시계열.
    프론트는 이 배열을 그대로 차트에 꽂으면 된다.
    """
    import pandas as pd

    points = []
    for _, r in df_dong.iterrows():
        actual = float(r["kwh"])
        ratio = actual / theta if theta else 0
        g = _grade(ratio, RISK_GRADES)
        points.append({
            "time": r["ts"].strftime("%Y-%m-%dT%H:00:00"),
            "hour": int(r["h"]),
            "usage_kwh": round(actual, 1),
            "baseline_kwh": round(float(r["B"]), 1) if pd.notna(r["B"]) else None,
            "extra_percent": round(float(r["R"]), 1) if pd.notna(r["R"]) else None,
            "temperature": float(r["T_asos"]) if pd.notna(r["T_asos"]) else None,
            "risk_ratio": round(ratio, 3),
            **g,
        })
    return {"threshold_kwh": round(theta, 1) if theta else None, "points": points}


def build_alerts(df, theta_map, top_n=20):
    """GET /api/alerts — 경보 목록 (위험도 높은 순)."""
    import pandas as pd

    rows = []
    for dong, d in df.groupby("dong"):
        th = theta_map.get(dong)
        if not th:
            continue
        over = d[d["kwh"] > th]
        for _, r in over.iterrows():
            ratio = float(r["kwh"]) / th
            rows.append({
                "dong": dong,
                "time": r["ts"].strftime("%Y-%m-%dT%H:00:00"),
                "usage_kwh": round(float(r["kwh"]), 1),
                "threshold_kwh": round(th, 1),
                "over_percent": round((ratio - 1) * 100, 1),
                "temperature": float(r["T_asos"]) if pd.notna(r["T_asos"]) else None,
                **_grade(ratio, RISK_GRADES),
            })
    rows.sort(key=lambda x: -x["over_percent"])
    return {"count": len(rows), "alerts": rows[:top_n]}


def build_compare(summaries):
    """GET /api/compare — 두 동 나란히 비교."""
    keys = [
        ("도시열 지수", lambda s: s["microclimate"]["heat_index"], ""),
        ("콘크리트·아스팔트", lambda s: s["microclimate"]["components"]["paved"]["percent"], "%"),
        ("나무·풀밭", lambda s: s["microclimate"]["components"]["green"]["percent"], "%"),
        ("하천·물", lambda s: s["microclimate"]["components"]["water"]["percent"], "%"),
        ("평소 대비 추가 사용", lambda s: s["demand"]["extra_usage_percent"], "%"),
        ("야간 추가 사용", lambda s: s["demand"]["night_percent"], "%"),
        ("주간 추가 사용", lambda s: s["demand"]["day_percent"], "%"),
        ("냉방 시작 온도", lambda s: s["cooling"]["switch_on_temp"], "℃"),
        ("1℃당 증가율", lambda s: s["cooling"]["sensitivity"], "%"),
    ]
    rows = []
    for label, fn, unit in keys:
        rows.append({
            "label": label, "unit": unit,
            "values": {s["name"]: fn(s) for s in summaries},
        })
    return {"dongs": [s["name"] for s in summaries], "rows": rows}


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path
