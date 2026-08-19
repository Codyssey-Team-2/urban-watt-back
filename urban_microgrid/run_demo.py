"""
Urban-MicroGrid | 데모 파이프라인

실행:  python -m urban_microgrid.run_demo
"""
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from . import config as C
from . import io_loaders as io
from . import features as F
from . import models as M
from . import evaluate as E


def section(title):
    print("\n" + "=" * 66)
    print(f"  {title}")
    print("=" * 66)


def main():
    section("STEP 1. 데이터 적재")
    frames = []
    for name, cd in C.DONGS.items():
        frames.append(io.load_power_csv(C.PATH_POWER_CSV,
                                        cd["sigungu"], cd["bjdong"], name))
    frames.append(io.load_power_xlsx(C.PATH_POWER_XLSX, "구로동"))
    power = pd.concat(frames, ignore_index=True)
    asos = io.load_asos(C.PATH_ASOS)

    section("STEP 2. 결합 및 달력 변수")
    df = power.merge(asos, on="ts", how="left")
    df = F.add_calendar(df)
    df = F.add_daily_temp(df)
    df = df[(df.date >= C.PERIOD_START) & (df.date <= C.PERIOD_END)]
    print(f"  결합 결과 {df.shape[0]:,}행 | 기온 결측 {df.T_asos.isna().sum()}행")
    print(f"  분석 기간 {df.ts.min()} ~ {df.ts.max()}")

    section("STEP 3. 기저수요 B 와 정규화 지표 R")
    B = F.baseline_demand(df)
    df = F.cooling_sensitive_load(df, B)

    summer = df[(df.date >= C.SUMMER_START) & (df.date <= C.SUMMER_END)]
    print()
    print(summer.groupby("dong").agg(
        평균kwh=("kwh", "mean"), 기저평균=("B", "mean"),
        평균R=("R", "mean"), 최대R=("R", "max")).round(1).to_string())

    section("STEP 4. 전환온도 T* 와 냉방민감도 β")
    cp = M.fit_changepoint_by_dong(summer)
    print(cp.round(2).to_string(index=False))
    if cp.at_boundary.any():
        print("  ⚠ T* 가 탐색 격자 경계에 있습니다. 기간이 짧아 식별이 약합니다.")

    section("STEP 5. 시간대별 R 프로파일")
    summer = summer.copy()
    summer["구간"] = np.where(summer.h.isin(C.NIGHT_HOURS), "야간", "주간")
    print(summer.pivot_table(index="dong", columns="구간",
                             values="R", aggfunc="mean").round(1).to_string())

    section("STEP 6. 통계 검정")
    dongs = sorted(summer.dong.unique())
    if len(dongs) >= 2:
        res = E.paired_test(summer, dongs[0], dongs[1], value_col="R")
        print("  " + E.format_finding(res))
        print(f"  Cohen's d = {res['cohen_d']:.2f}")

    section("STEP 7. 피크 임계치")
    theta = E.peak_threshold(summer)
    for dong, th in theta.items():
        d = summer[summer.dong == dong]
        print(f"  {dong}: θ={th:,.0f} kWh | 초과 {int((d.kwh > th).sum())}시간 "
              f"/ {d[d.kwh > th].date.nunique()}일")

    section("STEP 8. Ablation (기상만 vs 기상+미기후)")
    if "dT" in df.columns:
        tr, te = M.time_split(df)
        yb, pb, _ = M.fit_predict(tr, te, use_microclimate=False)
        ym, pm, _ = M.fit_predict(tr, te, use_microclimate=True)
        print(E.ablation_report(yb, pb, ym, pm).to_string(index=False))
    else:
        print("  ⏭  건너뜀 — S-DoT 설치위치 매핑이 없어 미기후 변수(dT)를 만들 수 없습니다.")
        print("     서울시 IoT 허브에서 시리얼↔위치 매핑을 확보하면 이 단계가 활성화됩니다.")

    section("완료")
    out = C.OUT_DIR / "urban_microgrid_panel.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"  분석 패널 저장: {out}")


if __name__ == "__main__":
    main()
