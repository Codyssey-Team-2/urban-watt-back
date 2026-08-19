"""
Urban-MicroGrid | 평가

    ⑨  RMSE / MAE / MAPE, 미기후 개선율
    ⑩  피크 임계치와 경보 성능
    ⑪  두 지역 차이의 통계 검정
"""
import numpy as np
import pandas as pd

from . import config as C


# ══════════════════════════════════════════════════════════
#  ⑨ 예측 정확도
# ══════════════════════════════════════════════════════════
def rmse(y, yhat):
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(yhat)) ** 2)))


def mae(y, yhat):
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(yhat))))


def mape(y, yhat):
    y, yhat = np.asarray(y), np.asarray(yhat)
    m = y != 0
    return float(np.mean(np.abs(y[m] - yhat[m]) / y[m]) * 100)


def improvement_rate(rmse_base, rmse_micro):
    """
    개선율 = (RMSE_기상만 − RMSE_기상+미기후) / RMSE_기상만 × 100  [%]

    발표자료의 '미기후 융합 효과'는 반드시 이 값으로 제시한다.
    측정하지 않은 수치를 넣지 않는다.
    """
    return (rmse_base - rmse_micro) / rmse_base * 100


def ablation_report(y_base, p_base, y_micro, p_micro):
    """기상만 vs 기상+미기후 비교표."""
    rows = [
        {"모델": "기상만", "RMSE": rmse(y_base, p_base),
         "MAE": mae(y_base, p_base), "MAPE(%)": mape(y_base, p_base)},
        {"모델": "기상+미기후", "RMSE": rmse(y_micro, p_micro),
         "MAE": mae(y_micro, p_micro), "MAPE(%)": mape(y_micro, p_micro)},
    ]
    out = pd.DataFrame(rows)
    out["개선율(%)"] = [np.nan, improvement_rate(rows[0]["RMSE"], rows[1]["RMSE"])]
    return out.round(2)


# ══════════════════════════════════════════════════════════
#  ⑩ 피크 임계치와 경보
# ══════════════════════════════════════════════════════════
def peak_threshold(df, dong_col="dong", value_col="kwh"):
    """
    θ(d) = quantile(P(d, 과거 여름), PEAK_QUANTILE)

    절대 kWh 로 임계를 잡으면 큰 동은 항상 위험, 작은 동은 항상 안전이 된다.
    반드시 동별 상대 기준을 쓴다.
    """
    return (df.groupby(dong_col)[value_col]
              .quantile(C.PEAK_QUANTILE).rename("theta"))


def alarm_metrics(df, theta, pred_col="pred", value_col="kwh",
                  dong_col="dong"):
    """
    경보 발령 = 예측치 > θ(d)
    실제 초과 = 실측치 > θ(d)

    Precision = TP/(TP+FP),  Recall = TP/(TP+FN),  F1 = 2PR/(P+R)
    """
    d = df.merge(theta, on=dong_col, how="left")
    pred_pos = d[pred_col] > d["theta"]
    true_pos = d[value_col] > d["theta"]

    tp = int((pred_pos & true_pos).sum())
    fp = int((pred_pos & ~true_pos).sum())
    fn = int((~pred_pos & true_pos).sum())

    prec = tp / (tp + fp) if tp + fp else np.nan
    rec = tp / (tp + fn) if tp + fn else np.nan
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else np.nan
    return {"TP": tp, "FP": fp, "FN": fn,
            "Precision": prec, "Recall": rec, "F1": f1}


def lead_time(df, theta, pred_col="pred", value_col="kwh",
              dong_col="dong", ts_col="ts"):
    """
    리드타임 = 실제 임계 초과 시각 − 최초 경보 시각   [시간]
    발표에서 'RMSE 몇 % 개선'보다 훨씬 잘 전달되는 지표다.
    """
    d = df.merge(theta, on=dong_col, how="left").sort_values(ts_col)
    d["date"] = d[ts_col].dt.normalize()
    outs = []
    for (dong, date), g in d.groupby([dong_col, "date"]):
        actual = g.loc[g[value_col] > g["theta"], ts_col]
        alarm = g.loc[g[pred_col] > g["theta"], ts_col]
        if len(actual) and len(alarm):
            outs.append((actual.min() - alarm.min()).total_seconds() / 3600)
    return float(np.mean(outs)) if outs else np.nan


# ══════════════════════════════════════════════════════════
#  ⑪ 통계 검정
# ══════════════════════════════════════════════════════════
def paired_test(df, dong_a, dong_b, value_col="R", by="date"):
    """
    두 지역의 일평균 지표 차이에 대한 대응표본 검정.

    반환: 평균차, 95% 신뢰구간, t, p, Cohen's d, 표본수

    '1.5℃ 차이가 의미 있나요'라는 질문에 대한 정량적 답이다.
    숫자 하나만 제시하는 것과 신뢰구간·표본수를 붙이는 것은 신뢰도가 다르다.
    """
    from scipy import stats

    piv = (df.pivot_table(index=by, columns="dong", values=value_col,
                          aggfunc="mean").dropna())
    if dong_a not in piv or dong_b not in piv:
        raise ValueError("두 지역 모두의 값이 필요합니다.")

    diff = piv[dong_a] - piv[dong_b]
    n = len(diff)
    se = diff.std(ddof=1) / np.sqrt(n)
    t, p = stats.ttest_rel(piv[dong_a], piv[dong_b])
    return {
        "비교": f"{dong_a} − {dong_b}",
        "평균차": float(diff.mean()),
        "CI95_low": float(diff.mean() - 1.96 * se),
        "CI95_high": float(diff.mean() + 1.96 * se),
        "t": float(t), "p": float(p),
        "cohen_d": float(diff.mean() / diff.std(ddof=1)),
        "n": int(n),
    }


def format_finding(res, unit="%p"):
    """발표·문서에 그대로 붙일 수 있는 문장으로 변환."""
    sig = "유의함" if res["p"] < 0.05 else "유의하지 않음"
    return (f"{res['비교']} = {res['평균차']:.2f}{unit} "
            f"(95% CI [{res['CI95_low']:.2f}, {res['CI95_high']:.2f}], "
            f"n={res['n']}일, p={res['p']:.4f}, {sig})")
