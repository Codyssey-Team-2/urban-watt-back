"""
Urban-MicroGrid | 피처 생성 (수식 구현부)

문서의 계산식이 그대로 함수 하나씩에 대응한다.
    ①  MCI   = ISR − VCR
    ②  ΔT    = T_sdot − T_asos
    ③  B     = median{ P : 쾌적일, 같은 시각·요일유형 }
    ④  CSL   = max(0, P − B)
    ⑤  R     = CSL / B × 100
"""
import numpy as np
import pandas as pd

from . import config as C


# ══════════════════════════════════════════════════════════
#  ① 공간 — 피복률과 미기후 지수
# ══════════════════════════════════════════════════════════
def coverage_ratios(gdf_landcover, impervious_codes, vegetation_codes,
                    water_codes):
    """
    ISR = Σ A_불투수 / A_전체 × 100
    VCR = Σ A_식생   / A_전체 × 100
    WSR = Σ A_수면   / A_전체 × 100

    ※ gdf_landcover 는 반드시 CRS_WORK(투영좌표계)로 변환된 상태여야 한다.
       경위도(EPSG:4326)에서 면적을 계산하면 값이 왜곡된다.
    """
    if gdf_landcover.crs is not None and gdf_landcover.crs.to_string() != C.CRS_WORK:
        raise ValueError(f"좌표계가 {C.CRS_WORK} 가 아닙니다. 면적 계산 전 변환하세요.")

    g = gdf_landcover.copy()
    g["area"] = g.geometry.area
    total = g["area"].sum()

    def share(codes):
        return g.loc[g["code"].isin(codes), "area"].sum() / total * 100

    return {
        "ISR": share(impervious_codes),
        "VCR": share(vegetation_codes),
        "WSR": share(water_codes),
    }


def microclimate_index(isr, vcr):
    """
    MCI = ISR − VCR         범위 −100 ~ +100
    양수일수록 불투수 우세(열 축적), 음수일수록 식생 우세.
    """
    return isr - vcr


def microclimate_index_normalized(mci):
    """0~100 척도로 표출할 때 사용."""
    return (mci + 100) / 2


# ══════════════════════════════════════════════════════════
#  ② 미기후 — 기온 편차와 야간 열섬 강도
# ══════════════════════════════════════════════════════════
def delta_t(df, col_sdot="T_sdot", col_asos="T_asos"):
    """ΔT(d,t) = T_sdot(d,t) − T_asos(t)"""
    out = df.copy()
    out["dT"] = out[col_sdot] - out[col_asos]
    return out


def night_uhi(df, dong_col="dong"):
    """
    UHI_night(d) = mean{ ΔT(d,t) : 야간, 분석기간 }
    야간 구간은 config.NIGHT_HOURS 로 고정한다.
    """
    d = df[df["ts"].dt.hour.isin(C.NIGHT_HOURS)]
    return d.groupby(dong_col)["dT"].mean().rename("UHI_night")


# ══════════════════════════════════════════════════════════
#  ③ 달력 변수
# ══════════════════════════════════════════════════════════
def add_calendar(df):
    """시간·요일·휴일 파생. 미기후 효과와 혼동되지 않도록 반드시 통제한다."""
    d = df.copy()
    hol = pd.to_datetime(C.HOLIDAYS)
    d["date"] = d["ts"].dt.normalize()
    d["h"] = d["ts"].dt.hour
    d["dow"] = d["ts"].dt.dayofweek
    d["daytype"] = np.where(
        d["date"].isin(hol) | (d["dow"] == 6), "일·휴일",
        np.where(d["dow"] == 5, "토", "평일"))
    return d


def add_daily_temp(df):
    """일평균·일최고 기온 — 쾌적일 판정과 폭염일 판정에 사용."""
    d = df.copy()
    agg = d.groupby("date")["T_asos"].agg(T_daily="mean", T_max="max")
    return d.merge(agg, on="date", how="left")


# ══════════════════════════════════════════════════════════
#  ④ 기저수요와 냉방 민감 추가수요
# ══════════════════════════════════════════════════════════
def comfort_days(df):
    """
    쾌적일 = 냉난방 영향이 작은 날
             COMFORT_TEMP_MIN ≤ 일평균기온 ≤ COMFORT_TEMP_MAX
    """
    return df[(df["T_daily"] >= C.COMFORT_TEMP_MIN) &
              (df["T_daily"] <= C.COMFORT_TEMP_MAX)]


def baseline_demand(df):
    """
    B(d, h, w) = median{ P(d,t) : t ∈ 쾌적일, hour=h, daytype=w }

    평균이 아니라 중앙값을 쓴다. 표본이 적고 이상치에 취약하기 때문이다.
    """
    cd = comfort_days(df)
    n_days = cd["date"].nunique()
    if n_days < 7:
        print(f"  ⚠ 쾌적일이 {n_days}일뿐입니다. 기저수요 추정이 불안정할 수 있습니다.")

    B = (cd.groupby(["dong", "h", "daytype"])["kwh"]
           .median().rename("B").reset_index())
    print(f"  [기저수요] 쾌적일 {n_days}일 기준, {len(B)}개 (동×시각×요일유형) 조합")
    return B


def cooling_sensitive_load(df, B):
    """
    CSL(d,t) = max(0, P(d,t) − B(d,h,w))          [kWh]
    R(d,t)   = CSL(d,t) / B(d,h,w) × 100          [%]   ← 비교는 항상 R 로

    R 은 동별 규모 차이를 제거한다.
    절대 kWh 로 두 동을 비교하면 '동네 크기 차이'를 보게 된다.
    """
    d = df.merge(B, on=["dong", "h", "daytype"], how="left")
    missing = d["B"].isna().sum()
    if missing:
        print(f"  ⚠ 기저수요 매칭 실패 {missing}행 — 해당 조합의 쾌적일 표본이 없습니다.")
    d["CSL"] = (d["kwh"] - d["B"]).clip(lower=0)
    d["R"] = d["CSL"] / d["B"] * 100
    return d
