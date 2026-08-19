"""
Urban-MicroGrid | 데이터 원천

API 는 두 가지 모드로 뜬다.

    live      원자료(전력·ASOS)가 있으면 파이프라인을 그대로 돌려 응답을 만든다.
              run_demo 와 같은 함수를 쓰므로 숫자가 갈라질 수 없다.

    snapshot  원자료가 없으면 docs/api_sample/ 의 실측 산출물을 서빙한다.
              발표 노트북에 원자료를 올리지 않아도 시연이 되게 하기 위한 경로다.
              스냅샷 값도 파이프라인이 만든 실측치이므로 조작이 아니다.

두 모드 모두 응답 조립은 serialize.build_* 하나만 쓴다.
등급·색상·문구가 모드마다 달라지는 사고를 구조적으로 막는다.
"""
import json
from functools import lru_cache

from .. import briefing as B
from .. import config as C
from .. import llm
from .. import serialize as S


# ── 예외 (routes 에서 HTTP 코드로 번역된다) ──────────────
class DongNotFound(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(f"법정동코드 {code} 는 분석 대상이 아닙니다.")


class DataUnavailable(Exception):
    """요청은 유효하나 아직 해당 데이터가 없다 (미확보 자료 대기)."""

    def __init__(self, message, note=None):
        self.note = note
        super().__init__(message)


def _round(v, nd=1):
    return None if v is None else round(float(v), nd)


class DataStore:
    """앱 기동 시 1회 적재하고 이후에는 메모리에서 서빙한다."""

    def __init__(self):
        self.mode = "snapshot"
        self.reason = ""
        self.summaries = {}      # {code: dong summary dict}
        self.theta = {}          # {동이름: θ}
        self._panel = None       # live 모드 전용 (pandas DataFrame)
        self._forecast = {}      # snapshot 모드 전용 {code: {date: payload}}
        self._shapes = {}        # {법정동코드: GeoJSON geometry}
        self._boundary_src = None
        self._briefings = {}     # {(코드들, 날짜): 브리핑} — 시연 중 문장 고정

    # ══════════════════════════════════════════════════
    #  적재
    # ══════════════════════════════════════════════════
    def load(self):
        self._load_boundaries()
        ok, why = self._live_possible()
        if ok:
            try:
                self._load_live()
                self.mode, self.reason = "live", "원자료로 파이프라인을 실행했습니다"
                return self
            except Exception as e:      # 원자료가 깨졌어도 시연은 계속되어야 한다
                why = f"파이프라인 실행 실패({type(e).__name__}: {e})"
        self._load_snapshot()
        self.mode, self.reason = "snapshot", f"{why} → 실측 스냅샷을 서빙합니다"
        return self

    @staticmethod
    def _live_possible():
        missing = [p.name for p in (C.PATH_POWER_CSV, C.PATH_POWER_XLSX, C.PATH_ASOS)
                   if not p.exists()]
        if missing:
            return False, f"원자료 없음({', '.join(missing)})"
        try:
            import pandas  # noqa: F401
        except ImportError:
            return False, "pandas 미설치"
        return True, ""

    # ── live ──────────────────────────────────────────
    def _load_live(self):
        import pandas as pd

        from .. import io_loaders as io
        from .. import features as F
        from .. import models as M
        from .. import evaluate as E

        frames = []
        for meta in C.DONG_META.values():
            if meta["source"] == "csv":
                frames.append(io.load_power_csv(C.PATH_POWER_CSV, meta["sigungu"],
                                                meta["bjdong"], meta["name"]))
            else:
                frames.append(io.load_power_xlsx(C.PATH_POWER_XLSX, meta["name"]))

        df = pd.concat(frames, ignore_index=True).merge(
            io.load_asos(C.PATH_ASOS), on="ts", how="left")
        df = F.add_daily_temp(F.add_calendar(df))
        df = df[(df.date >= C.PERIOD_START) & (df.date <= C.PERIOD_END)]

        # 기저수요 B → 정규화 지표 R. 비교는 항상 R 로 한다(절대 kWh 금지).
        df = F.cooling_sensitive_load(df, F.baseline_demand(df))
        self._panel = df.sort_values("ts")

        summer = df[(df.date >= C.SUMMER_START) & (df.date <= C.SUMMER_END)]
        # θ 는 동별 백분위. 절대 kWh 임계는 큰 동을 항상 위험으로 만든다.
        theta = E.peak_threshold(summer)
        self.theta = {k: float(v) for k, v in theta.items()}
        cp = M.fit_changepoint_by_dong(summer).set_index("dong")

        night = summer.h.isin(C.NIGHT_HOURS)
        for code, meta in C.DONG_META.items():
            name = meta["name"]
            d = summer[summer.dong == name]
            if d.empty:
                continue
            th = self.theta.get(name)
            self.summaries[code] = self._summary(
                code, name,
                r_mean=_round(d.R.mean()),
                r_night=_round(d[night.loc[d.index]].R.mean()),
                r_day=_round(d[~night.loc[d.index]].R.mean()),
                t_star=_round(cp.at[name, "T_star"]) if name in cp.index else None,
                beta=_round(cp.at[name, "beta"], 2) if name in cp.index else None,
                theta=th,
                risk_days=int(d[d.kwh > th].date.nunique()) if th else None,
                total_days=int(d.date.nunique()),
            )

    # ── snapshot ──────────────────────────────────────
    def _load_snapshot(self):
        for code, meta in C.DONG_META.items():
            path = C.SNAPSHOT_DIR / C.SNAPSHOT_DONG_PATTERN.format(code=code)
            if not path.exists():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            # 스냅샷의 숫자만 가져오고, 응답 조립은 live 와 같은 빌더로 한다.
            self.summaries[code] = self._summary(
                code, meta["name"],
                r_mean=raw["demand"]["extra_usage_percent"],
                r_night=raw["demand"]["night_percent"],
                r_day=raw["demand"]["day_percent"],
                t_star=raw["cooling"]["switch_on_temp"],
                beta=raw["cooling"]["sensitivity"],
                theta=raw["peak"]["threshold_kwh"],
                risk_days=raw["peak"]["risk_days"],
                total_days=raw["peak"]["total_days"],
            )
            if raw["peak"]["threshold_kwh"]:
                self.theta[meta["name"]] = float(raw["peak"]["threshold_kwh"])

        for code, fname in C.SNAPSHOT_FORECAST.items():
            path = C.SNAPSHOT_DIR / fname
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            points = payload.get("points", [])
            if not points:
                continue
            self._forecast[code] = {points[0]["time"][:10]: payload}

    # ── 경계 폴리곤 ───────────────────────────────────
    def _load_boundaries(self):
        """
        법정동 경계 GeoJSON 을 찾아 대상 동의 도형만 추린다.

        경계 파일마다 코드 컬럼 이름이 다르므로(EMD_CD · ADM_CD · adm_cd …)
        이름을 맞추려 들지 않고 '값이 우리 법정동코드와 같은 속성'을 찾는다.
        파일이 없으면 조용히 넘어가고, 엔드포인트가 pending 으로 답한다.
        """
        for path in C.BOUNDARY_GEOJSON_CANDIDATES:
            if not path.exists():
                continue
            try:
                fc = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for feat in fc.get("features", []):
                code = self._match_code(feat.get("properties") or {})
                if code and feat.get("geometry"):
                    self._shapes[code] = feat["geometry"]
            if self._shapes:
                self._boundary_src = str(path)
                return

    @staticmethod
    def _match_code(props):
        # 힌트 컬럼을 먼저 보고, 없으면 전체 속성값을 훑는다
        ordered = [props.get(k) for k in C.BOUNDARY_CODE_HINTS if k in props]
        for v in ordered + list(props.values()):
            code = str(v).strip() if v is not None else ""
            if code in C.DONG_META:
                return code
        return None

    # ── 공통 조립 ─────────────────────────────────────
    @staticmethod
    def _summary(code, name, **kw):
        """
        미기후 블록은 항상 config.MICROCLIMATE_PRELIM 에서만 온다.
        값이 없으면 status="pending" + note 가 내려가고, 프론트는 스켈레톤을 띄운다.
        값이 있으면 MICROCLIMATE_BASIS(예비값 태그·산출기준·단서)를 함께 실어
        "법정동 경계 클리핑 전"이라는 사실이 화면까지 따라가게 한다.
        """
        mc = C.MICROCLIMATE_PRELIM.get(code, {})
        return S.build_dong_summary(
            name, code,
            isr=mc.get("ISR"), vcr=mc.get("VCR"), wsr=mc.get("WSR"),
            bare=mc.get("bare"), wetland=mc.get("wetland"),
            area_km2=mc.get("area_km2"),
            basis=C.MICROCLIMATE_BASIS if mc else None, **kw)

    # ══════════════════════════════════════════════════
    #  조회
    # ══════════════════════════════════════════════════
    def summary(self, code):
        if code not in C.DONG_META:
            raise DongNotFound(code)
        if code not in self.summaries:
            raise DataUnavailable(
                f"{C.DONG_META[code]['name']}의 전력 시계열이 아직 없습니다.",
                note="OA-22835 에서 해당 동을 추출하면 활성화됩니다")
        return self.summaries[code]

    def markers(self):
        out = []
        for code, meta in C.DONG_META.items():
            s = self.summaries.get(code)
            mc = (s or {}).get("microclimate", {})
            out.append({
                "code": code, "name": meta["name"],
                "lat": meta["lat"], "lng": meta["lng"],
                "heat_index": mc.get("heat_index"),
                "grade": mc.get("grade"),
                # 미확보 동은 회색. 프론트가 색을 고르지 않는다.
                "color": mc.get("color") or "#9E9E9E",
                "risk_days": (s or {}).get("peak", {}).get("risk_days"),
            })
        return {"dongs": out, "latlng_source": C.DONG_LATLNG_SOURCE}

    def forecast(self, code, date=None):
        summary = self.summary(code)
        name = C.DONG_META[code]["name"]
        theta = self.theta.get(name)
        date = date or C.FORECAST_DEMO_DATE

        if self.mode == "snapshot":
            avail = self._forecast.get(code, {})
            if not avail:
                raise DataUnavailable(
                    f"{name}의 시계열 스냅샷이 없습니다.",
                    note="원자료를 넣고 live 모드로 띄우면 전 기간이 열립니다")
            if date not in avail:
                raise DataUnavailable(
                    f"스냅샷에는 {', '.join(sorted(avail))} 만 있습니다 (요청: {date}).",
                    note="원자료를 넣고 live 모드로 띄우면 전 기간이 열립니다")
            payload = dict(avail[date])
        else:
            d = self._panel[(self._panel.dong == name) &
                            (self._panel.date == date)]
            if d.empty:
                raise DataUnavailable(
                    f"{date} 는 분석 기간({C.PERIOD_START} ~ {C.PERIOD_END}) 밖이거나 "
                    f"{name}의 관측이 없습니다.")
            payload = S.build_forecast(d, theta)

        payload.update(code=code, name=name, date=date)
        payload.setdefault("threshold_kwh", summary["peak"]["threshold_kwh"])
        payload["weather"] = S.build_weather(payload.get("points", []))
        return payload

    def geojson(self):
        if not self._shapes:
            raise DataUnavailable(
                "법정동 경계 폴리곤이 아직 없습니다.",
                note="법정동 경계 GeoJSON 을 data/dong_boundaries.geojson 에 넣으면 "
                     "지도에 폴리곤이 그려집니다 (SHP 은 landcover 로 변환)")
        missing = [C.DONG_META[c]["name"] for c in C.DONG_META
                   if c not in self._shapes]
        out = S.build_geojson(self._shapes, self.summaries, C.DONG_META)
        out["source"] = self._boundary_src
        if missing:
            out["note"] = f"경계를 찾지 못한 동: {', '.join(missing)}"
        return out

    def briefing(self, codes, date=None, refresh=False):
        """
        AI 브리핑. 사실표를 만들어 프롬프트로 조립하고 모델에 넘긴다.

        같은 요청은 캐시에서 돌려준다. 시연 도중 새로고침할 때마다
        문구가 흔들리면 안 되고, 호출 비용도 계속 나가면 안 된다.
        """
        key = (tuple(codes), date)
        if C.LLM_CACHE and not refresh and key in self._briefings:
            return self._briefings[key]

        summaries = [self.summary(c) for c in codes]
        weather = None
        try:
            weather = self.forecast(codes[0], date).get("weather")
        except DataUnavailable:
            pass                      # 기상 요약은 있으면 좋고 없어도 된다

        facts = B.build_facts(summaries, weather)
        prompt = B.build_prompt(facts)

        try:
            result = llm.generate(prompt["system"], prompt["user"])
        except llm.LLMUnavailable as e:
            raise DataUnavailable(
                f"AI 브리핑을 만들 수 없습니다: {e}",
                note="키를 설정하면 자동으로 활성화됩니다. 그때까지 화면은 "
                     "스켈레톤을 띄우면 됩니다")
        except llm.LLMFailed as e:
            raise DataUnavailable(f"모델 호출에 실패했습니다: {e}",
                                  note="잠시 후 다시 시도하거나 키·쿼터를 확인하세요")

        # 사실표에 없는 숫자가 섞였는지 검사한다. 숨기지 않고 그대로 실어 보낸다.
        unverified = B.verify(result["text"], facts)
        out = {
            "codes": list(codes),
            "date": date,
            "status": "needs_review" if unverified else "ready",
            "text": result["text"],
            "provider": result["provider"],
            "model": result["model"],
            "usage": result.get("usage"),
            "unverified_numbers": unverified,
            "note": ("사실표에 없는 숫자가 있습니다. 발표 전 확인하세요"
                     if unverified else None),
            "facts": facts,
            "prompt": prompt,
        }
        if C.LLM_CACHE:
            self._briefings[key] = out
        return out

    def compare(self, codes):
        return S.build_compare([self.summary(c) for c in codes])

    def model_performance(self):
        """목업 수치 대신 실측 Ablation 결과만 내리는 카드 계약."""
        return {
            "status": "pending",
            "metric": "MAPE",
            "models": [{**model, "mape": None, "rmse": None, "mae": None}
                       for model in C.MODEL_VARIANTS],
            "improvement_percent": None,
            "improvement_basis": "B(기상만) 대비 C(미기후·도시공간)",
            "note": C.MODEL_PERFORMANCE_NOTE,
            "caveat": "측정 전이므로 개선율을 표시하지 않습니다.",
        }

    def meta(self):
        pending, caveats = [], []
        if not C.MICROCLIMATE_PRELIM:
            pending.append("미기후(ISR/VCR) — 법정동 경계 SHP 확보 후 산출")
        elif not C.MICROCLIMATE_BASIS.get("clipped_to_dong"):
            pending.append("미기후 확정값 — 현재는 생활권 100m 버퍼 예비값"
                           "(법정동 경계 클리핑 전)")
            caveats.append(C.MICROCLIMATE_BASIS["note"])
            caveats.append(C.MICROCLIMATE_BASIS["caveat"])
        if self.mode == "snapshot":
            pending.append("전 기간 시계열 — 원자료 투입 후 live 모드에서 열림")
        if not self._shapes:
            pending.append("지도 폴리곤 — 법정동 경계 GeoJSON 대기")
        llm_status, llm_note = llm.status()
        if llm_status != "ready":
            pending.append(f"AI 브리핑 — {llm_note}")
        pending.append("ΔT·야간 열섬·Ablation — S-DoT 설치위치 매핑 대기")
        if C.DONG_LATLNG_SOURCE == "provisional":
            caveats.append("지도 좌표는 임시값입니다. 경계 SHP 의 대표점으로 교체 예정")
        caveats += [
            "2개 동 사례입니다. 일반화는 향후 과제입니다",
            "냉방 민감도 β 는 두 동이 사실상 동일했고 차이는 야간 수요에서 나타났습니다",
            "모든 수치는 프로젝트 예비값이며 공식 통계가 아닙니다",
        ]
        return {
            "service": C.API_TITLE,
            "version": C.API_VERSION,
            "mode": self.mode,
            "mode_text": self.reason,
            "period": {"start": C.PERIOD_START, "end": C.PERIOD_END,
                       "summer_start": C.SUMMER_START, "summer_end": C.SUMMER_END},
            "dongs": [{"code": c, "name": m["name"],
                       "loaded": c in self.summaries}
                      for c, m in C.DONG_META.items()],
            "llm": {"provider": C.LLM_PROVIDER, "model": C.LLM_MODEL,
                    "status": llm_status},
            "pending": pending,
            "caveats": caveats,
        }


@lru_cache(maxsize=1)
def get_store():
    """앱 전체에서 하나만 쓴다 (기동 시 1회 적재)."""
    return DataStore().load()
