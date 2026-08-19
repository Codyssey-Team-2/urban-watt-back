"""
Urban-MicroGrid | 모델

    ⑥  전환온도 T* 와 냉방민감도 β   (구간 선형 회귀 + 그리드 서치)
    ⑦  상호작용 모델                (동 3개 이상일 때만 가능)
    ⑧  예측 모델 + Ablation         (기상만 vs 기상+미기후)
"""
import numpy as np
import pandas as pd

from . import config as C


# ══════════════════════════════════════════════════════════
#  ⑥ 전환온도와 냉방 민감도
# ══════════════════════════════════════════════════════════
def _design_matrix(d, tstar, temp_col):
    """
    R = α + β·max(0, T − T*) + γ·(시각 더미) + δ·(요일유형 더미) + ε
    """
    x = np.maximum(0.0, d[temp_col].values - tstar)
    H = pd.get_dummies(d["h"].astype(str), drop_first=True).values.astype(float)
    D = pd.get_dummies(d["daytype"], drop_first=True).values.astype(float)
    return np.column_stack([np.ones(len(d)), x, H, D])


def fit_changepoint(d, temp_col="T_asos"):
    """
    T* 를 격자 탐색해 잔차제곱합(RSS)이 최소가 되는 값을 고른다.

        T*_d = argmin_T*  RSS(T*)
        β_d  = 해당 T* 에서의 기울기  [%p / ℃]

    반환: dict(T_star, beta, rss, r2, n, at_boundary)
    """
    grid = np.arange(C.TSTAR_GRID_MIN, C.TSTAR_GRID_MAX + 1e-9, C.TSTAR_GRID_STEP)
    y = d["R"].values
    best = None

    for ts in grid:
        X = _design_matrix(d, ts, temp_col)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        rss = float(((y - X @ coef) ** 2).sum())
        if best is None or rss < best["rss"]:
            best = {"T_star": float(ts), "beta": float(coef[1]), "rss": rss}

    tss = float(((y - y.mean()) ** 2).sum())
    best["r2"] = 1 - best["rss"] / tss if tss > 0 else np.nan
    best["n"] = len(d)
    # 격자 경계에 붙으면 T* 가 제대로 식별되지 않은 것 → 해석 주의
    best["at_boundary"] = best["T_star"] in (C.TSTAR_GRID_MIN, C.TSTAR_GRID_MAX)
    return best


def fit_changepoint_by_dong(df, temp_col="T_asos"):
    """동별로 T*, β 를 추정해 표로 반환."""
    rows = []
    for dong, d in df.groupby("dong"):
        r = fit_changepoint(d, temp_col)
        r["dong"] = dong
        rows.append(r)
    out = pd.DataFrame(rows)[["dong", "T_star", "beta", "r2", "n", "at_boundary"]]
    return out.sort_values("dong").reset_index(drop=True)


# ══════════════════════════════════════════════════════════
#  ⑦ 상호작용 모델 — 미기후 가설의 본체
# ══════════════════════════════════════════════════════════
def fit_interaction(df, mci_map, temp_col="T_asos"):
    """
    R = β0 + β1·T + β2·MCI + β3·(MCI × T) + 통제변수 + ε

    β3 > 0 이고 유의하면
        "미기후 지수가 높을수록 기온에 대한 반응 기울기가 가파르다"
    가 성립한다. 이것이 프로젝트의 가설 그 자체다.

    ※ 동이 2개면 MCI 가 값을 2개만 가져 동 더미와 완전공선이 되어
      β2, β3 를 추정할 수 없다. 동을 3개 이상으로 늘려야 한다.
    """
    n_dong = df["dong"].nunique()
    if n_dong < 3:
        raise ValueError(
            f"동이 {n_dong}개입니다. MCI 가 동 더미와 완전공선이라 β2·β3 를 "
            f"추정할 수 없습니다. 최소 3개, 권장 20개 이상으로 확장하세요.")

    import statsmodels.formula.api as smf
    d = df.copy()
    d["MCI"] = d["dong"].map(mci_map)
    d["T"] = d[temp_col]
    model = smf.ols("R ~ T + MCI + T:MCI + C(h) + C(daytype)", data=d).fit()
    return model


# ══════════════════════════════════════════════════════════
#  ⑧ 예측 모델과 Ablation
# ══════════════════════════════════════════════════════════
FEATURES_WEATHER = ["T_asos", "RH", "h", "dow", "is_holiday", "T_daily"]
FEATURES_MICRO = ["dT", "ISR", "VCR", "MCI"]


def prepare_xy(df, use_microclimate: bool, target="kwh"):
    """모델 입력 행렬 구성. use_microclimate 로 Ablation 을 제어한다."""
    d = df.copy()
    d["is_holiday"] = d["daytype"].ne("평일").astype(int)
    cols = [c for c in FEATURES_WEATHER if c in d.columns]
    if use_microclimate:
        cols += [c for c in FEATURES_MICRO if c in d.columns]
    d = d.dropna(subset=cols + [target])
    return d[cols], d[target], cols


def time_split(df, test_ratio=0.25):
    """
    시간 순서 기반 분할. 랜덤 K-fold 는 데이터 누수이므로 절대 쓰지 않는다.
    (같은 날의 13시로 14시를 맞히게 되어 성능이 가짜로 좋아진다)
    """
    d = df.sort_values("ts")
    cut = int(len(d) * (1 - test_ratio))
    return d.iloc[:cut], d.iloc[cut:]


def fit_predict(train, test, use_microclimate: bool, target="kwh"):
    """GradientBoosting 기반 수요 예측. 반환: (실측, 예측, 사용피처)"""
    from sklearn.ensemble import GradientBoostingRegressor

    Xtr, ytr, cols = prepare_xy(train, use_microclimate, target)
    Xte, yte, _ = prepare_xy(test, use_microclimate, target)

    m = GradientBoostingRegressor(random_state=0)
    m.fit(Xtr, ytr)
    return yte.values, m.predict(Xte), cols
