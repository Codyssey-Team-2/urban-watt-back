"""
Urban-MicroGrid | 데이터 로더

원자료의 형식 차이를 여기서 모두 흡수하고,
바깥으로는 항상 [ts, dong, value] 형태의 깔끔한 시계열만 내보낸다.
"""
import pandas as pd
import numpy as np

from . import config as C


# ══════════════════════════════════════════════════════════
#  공통 유틸
# ══════════════════════════════════════════════════════════
def hm_to_timestamp(ymd, hm):
    """
    전력 자료의 시각 표기 변환.

    원자료는 0100 ~ 2400 형식이며 '0100 = 01:00시'로 표기된다.
    라벨 시각 h 를 구간 [h-1, h) 로 해석하여 정시 timestamp 로 바꾼다.
        0100 → 00:00,  1400 → 13:00,  2400 → 23:00
    이 규칙을 고정해야 ASOS 와 한 시간 어긋나는 사고를 막을 수 있다.
    """
    h = (hm // 100).astype(int)
    return pd.to_datetime(ymd.astype(str)) + pd.to_timedelta(h - 1, unit="h")


def _to_hourly(df, ymd_col, hm_col, val_col, dong_name):
    """중복 제거 → 정시 변환 → (ts) 유일성 보장."""
    d = df[[ymd_col, hm_col, val_col]].copy()
    d.columns = ["ymd", "hm", "kwh"]

    n0 = len(d)
    d = d.drop_duplicates()                       # 완전중복행 제거
    n1 = len(d)

    d["hm"] = d["hm"].astype(int)
    d = d[d["hm"].between(100, 2400)]
    d["ts"] = hm_to_timestamp(d["ymd"], d["hm"])

    # 같은 ts 에 값이 여러 개면 평균 (원칙적으로 없어야 함)
    d = d.groupby("ts", as_index=False)["kwh"].mean()
    d["dong"] = dong_name

    print(f"  [{dong_name}] 원본 {n0:,}행 → 중복제거 {n1:,}행 → 시간축 {len(d):,}행")
    return d[["ts", "dong", "kwh"]]


# ══════════════════════════════════════════════════════════
#  전력
# ══════════════════════════════════════════════════════════
def load_power_csv(path, sigungu, bjdong, dong_name):
    """
    서울 열린데이터광장 법정동별시간별전력사용량 CSV.

    주의 1) 파일에 서울 전체 자치구가 들어있으므로 반드시 코드로 필터링.
    주의 2) 스프레드시트를 거친 파일은 1,048,575행에서 잘려 있을 수 있다.
    """
    df = pd.read_csv(path, dtype={"SIGUNGU_CD": str, "BJDONG_CD": str})

    if len(df) == 1_048_575:
        print("  ⚠ 경고: 행 수가 스프레드시트 최대치와 일치합니다. "
              "파일이 절단되었을 가능성이 높습니다.")

    sel = df[(df.SIGUNGU_CD == sigungu) & (df.BJDONG_CD == bjdong)]
    if sel.empty:
        raise ValueError(f"{dong_name}({sigungu}-{bjdong}) 데이터가 없습니다. "
                         f"법정동코드를 확인하세요.")
    return _to_hourly(sel, "USE_YM", "USE_HM", "FDRCT_VLD_KWH", dong_name)


def load_power_xlsx(path, dong_name):
    """이미 한 개 동으로 필터링된 엑셀 (컬럼: 날짜 / 시간 / 전력사용량)."""
    x = pd.read_excel(path)
    x.columns = ["ymd", "hm", "kwh"]
    return _to_hourly(x, "ymd", "hm", "kwh", dong_name)


# ══════════════════════════════════════════════════════════
#  기상
# ══════════════════════════════════════════════════════════
def load_asos(path):
    """기상청 ASOS 서울(108) 시간자료. 인코딩은 cp949."""
    a = pd.read_csv(path, encoding="cp949")
    rename = {"기온(°C)": "T_asos", "습도(%)": "RH", "일사(MJ/m2)": "SR"}
    keep = ["일시"] + [c for c in rename if c in a.columns]
    a = a[keep].rename(columns=rename)
    a["ts"] = pd.to_datetime(a["일시"])
    cols = ["ts"] + [v for v in rename.values() if v in a.columns]
    print(f"  [ASOS] {len(a):,}행 | {a.ts.min()} ~ {a.ts.max()}")
    return a[cols]


# ══════════════════════════════════════════════════════════
#  S-DoT  (설치위치 매핑 확보 후 사용)
# ══════════════════════════════════════════════════════════
def load_sdot(sdot_dir, location_map, asos=None):
    """
    S-DoT 주간 CSV 를 모두 읽어 [ts, dong, T_sdot] 로 집계한다.

    환경정보 파일에는 위치 식별자가 없다.
    반드시 location_map (시리얼 → 법정동코드) 을 별도로 확보해야 한다.
        서울시 IoT 허브 신청: http://iothub.eseoul.go.kr/publicData/insertForm.do
    """
    if sdot_dir is None or location_map is None:
        raise NotImplementedError(
            "S-DoT 설치위치 매핑이 아직 없습니다. "
            "config.PATH_SDOT_DIR / PATH_SDOT_LOCATION 를 설정하세요.")

    from pathlib import Path
    frames = []
    for f in sorted(Path(sdot_dir).glob("*.csv")):
        d = pd.read_csv(f, encoding="cp949")
        d = d.rename(columns={"시리얼": "serial", "기온(℃)": "T_sdot",
                              "등록일자": "reg"})
        d["ts"] = pd.to_datetime(d["reg"]).dt.floor("h")
        frames.append(d[["serial", "ts", "T_sdot"]])
    s = pd.concat(frames, ignore_index=True)

    s = s.merge(location_map, on="serial", how="inner")   # → dong 부여
    s = clean_sdot(s, asos)
    out = s.groupby(["dong", "ts"], as_index=False)["T_sdot"].mean()
    return out


def clean_sdot(s, asos=None):
    """S-DoT 이상값 제거 — 규칙을 코드에 고정해 재현 가능하게 만든다."""
    n0 = len(s)

    lo, hi = C.SDOT_TEMP_RANGE
    s = s[s.T_sdot.between(lo, hi)]                       # ① 물리 범위 이탈

    s = s.sort_values(["serial", "ts"])                   # ② 동일값 고착
    same = s.groupby("serial")["T_sdot"].diff().eq(0)
    run = same.groupby((~same).cumsum()).cumsum()
    s = s[run < C.SDOT_STUCK_HOURS]

    if asos is not None:                                  # ③ ASOS 대비 과대편차
        s = s.merge(asos[["ts", "T_asos"]], on="ts", how="left")
        s = s[(s.T_sdot - s.T_asos).abs() <= C.SDOT_DELTA_T_LIMIT]

    print(f"  [S-DoT] 이상값 제거 {n0:,} → {len(s):,}행 "
          f"({(1 - len(s)/n0) * 100:.1f}% 제거)")
    return s
