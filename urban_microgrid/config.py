"""
Urban-MicroGrid | 설정
모든 경로·상수·수식 파라미터를 한 곳에 모은다.
값을 바꿀 때는 코드가 아니라 이 파일만 수정한다.
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ────────────────────────── .env ──────────────────────────
# 루트 .env 에 GEMINI_API_KEY 등을 넣어두면 여기서 읽어 os.environ 에 얹는다.
# .env 는 git 제외 대상이다(.gitignore) — 절대 커밋하지 않는다.
# python-dotenv 가 없어도 API 는 그냥 뜬다(환경변수를 직접 export 했다면 그걸로 충분).
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

# ────────────────────────── 경로 ──────────────────────────
# 원자료 위치는 실행 환경마다 다르다.
#   1) 환경변수 UMG_DATA_DIR / UMG_OUT_DIR 이 있으면 그것
#   2) 없으면 샌드박스 업로드 경로
#   3) 그것도 없으면 저장소의 data/ · out/
_SANDBOX_IN = Path("/mnt/user-data/uploads")
_SANDBOX_OUT = Path("/mnt/user-data/outputs")


def _resolve(env_key, sandbox, fallback):
    v = os.environ.get(env_key)
    if v:
        return Path(v)
    return sandbox if sandbox.exists() else fallback


DATA_DIR = _resolve("UMG_DATA_DIR", _SANDBOX_IN, REPO_ROOT / "data")
OUT_DIR = _resolve("UMG_OUT_DIR", _SANDBOX_OUT, REPO_ROOT / "out")

PATH_POWER_CSV = DATA_DIR / "은평구_진관동_시간대별_전력사용량.csv"
PATH_POWER_XLSX = DATA_DIR / "구로구_구로동_시간대별_전력사용량_22_06_28___22_10_14.xlsx"
PATH_ASOS = DATA_DIR / "SURFACE_ASOS_108_HR_2022_2022_2023.csv"
PATH_SDOT_DIR = None          # S-DoT 주간 CSV 폴더 (설치위치 매핑 확보 후 사용)
PATH_SDOT_LOCATION = None     # 시리얼 ↔ 법정동 매핑 파일

# ─────────────────────── 대상 법정동 ───────────────────────
# 법정동코드 = 시군구코드(5) + 법정동코드(5)
# 주의: 은평구 진관동은 11400. 10800은 다른 동이다.
DONGS = {
    "진관동": {"sigungu": "11380", "bjdong": "11400"},
    # "답십리동": {"sigungu": "11230", "bjdong": "10500"},   # 후보
    # "대림동":   {"sigungu": "11560", "bjdong": "11000"},   # 후보
}

# ─────────────────────── 좌표계 (GIS) ───────────────────────
CRS_WORK = "EPSG:5179"    # 면적·버퍼·교차 등 모든 공간 연산
CRS_DISPLAY = "EPSG:4326"  # 지도 표출 전용
BUFFER_RADII_M = [50, 100, 200]
BUFFER_DEFAULT_M = 100

# ─────────────────────── 수식 파라미터 ───────────────────────
# 기저수요 산출용 '쾌적일' 정의: 냉난방 영향이 작은 일평균기온 구간
COMFORT_TEMP_MIN = 15.0
COMFORT_TEMP_MAX = 20.0

# 전환온도 T* 그리드 탐색 범위
TSTAR_GRID_MIN = 18.0
TSTAR_GRID_MAX = 29.0
TSTAR_GRID_STEP = 0.5

# 피크 임계치: 동별 과거 분포의 상위 백분위 (절대 kWh 아님)
PEAK_QUANTILE = 0.95

# 폭염일 판정 (일 최고기온)
HEATWAVE_TMAX = 33.0

# 야간 구간 (도시열섬이 가장 뚜렷한 시간대)
NIGHT_HOURS = list(range(20, 24)) + list(range(0, 7))

# 분석 기간 (시계열 3종의 교집합)
PERIOD_START = "2022-06-28"
PERIOD_END = "2022-10-14"
SUMMER_START = "2022-06-28"
SUMMER_END = "2022-08-31"

# 공휴일 (분석 기간 내)
HOLIDAYS = [
    "2022-08-15",  # 광복절
    "2022-09-09", "2022-09-10", "2022-09-11", "2022-09-12",  # 추석 연휴
    "2022-10-03",  # 개천절
    "2022-10-10",  # 한글날 대체
]

# S-DoT 이상치 제거 규칙
SDOT_DELTA_T_LIMIT = 10.0   # |S-DoT − ASOS| 가 이 값을 넘으면 제거 [℃]
SDOT_TEMP_RANGE = (-30.0, 55.0)
SDOT_STUCK_HOURS = 6        # 동일값이 이 시간 이상 연속되면 고착으로 간주


# ══════════════════════════════════════════════════════════
#  API (백엔드 서비스) 설정
# ══════════════════════════════════════════════════════════
# 동 식별은 항상 10자리 법정동코드. 이름으로 조회하지 않는다.
# 주의: 은평구 진관동은 11400. 10800 은 다른 동이다.
DONG_META = {
    "1138011400": {
        "name": "진관동", "sigungu": "11380", "bjdong": "11400",
        "source": "csv",                      # 전력 원자료 형식
        "lat": 37.637, "lng": 126.933,
    },
    "1153010100": {
        "name": "구로동", "sigungu": "11530", "bjdong": "10100",
        "source": "xlsx",
        "lat": 37.495, "lng": 126.887,
    },
}
DONG_CODE_BY_NAME = {v["name"]: k for k, v in DONG_META.items()}

# 좌표 출처. 법정동 경계 SHP 의 representative_point 를 확보하면 "shp" 로 바꾼다.
DONG_LATLNG_SOURCE = "provisional"

# ─── 토지피복 (미기후) 산출값 ───────────────────────────────
# 출처: docs/06_토지피복_불투수식생_산출결과.md
#   세분류 토지피복지도 2022(EGIS) 10개 도엽 · EPSG:5186 · 5m 격자 래스터화
#   전력소비시설(L3 111·112·121·131·141·162·163)을 핵심영역으로 100m 버퍼
#
# 넣지 말아야 할 값 (전부 실제로 혼동된 적이 있다):
#   · 도엽 전체값 (진관동 도엽 ISR 5.37 / VCR 87.59) — 북한산이 지배한다
#   · 창신동 예비값 (83.0 / 13.1) — 애초에 다른 동이다
#   · docs/02 예시응답의 35.0 / 58.2 — 계약 설명용 예시값이다
#
# ★ 나지·습지는 불투수에도 식생에도 넣지 않는다.
#   따라서 ISR + VCR + WSR 의 합은 100% 가 되지 않는다. 화면에도 이 단서를 함께 보낸다.
MICROCLIMATE_PRELIM = {
    "1138011400": {"ISR": 31.2, "VCR": 57.4, "WSR": 0.9,
                   "bare": 8.9, "wetland": 1.6, "area_km2": 10.56},
    "1153010100": {"ISR": 78.8, "VCR": 15.9, "WSR": 0.9,
                   "bare": 4.3, "wetland": 0.2, "area_km2": 30.02},
}

# 위 값이 '어떤 기준의 값인지'를 응답에 함께 실어 보낸다.
# 법정동 경계 클리핑 전이라는 사실을 프론트가 숨길 수 없게 하기 위한 것.
MICROCLIMATE_BASIS = {
    "tag": "프로젝트 예비값",
    "method": "생활권 100m 버퍼 · 5m 격자 래스터화",
    "source": "세분류 토지피복지도 2022 (EGIS, 10개 도엽)",
    "clipped_to_dong": False,
    "note": "[프로젝트 예비값] 생활권 100m 버퍼 기준 · 도엽 병합 범위(법정동 경계 클리핑 전)",
    "caveat": "나지·습지는 불투수·식생 어디에도 포함하지 않으므로 세 비율의 합은 100%가 아닙니다",
}

# ─── 서버 ────────────────────────────────────────────────
API_TITLE = "Urban-MicroGrid API"
API_VERSION = "0.1.0"
API_PREFIX = "/api"
# 데모용. 실배포 시 프론트 도메인만 남긴다.
API_CORS_ORIGINS = ["*"]

# 모델 성능 카드 계약. 성능 수치는 실제 Ablation 실행 결과로만
# 채우며, 현재는 S-DoT 설치위치 매핑이 없어 pending 상태다.
MODEL_VARIANTS = [
    {"key": "a", "label": "달력·부하 패턴"},
    {"key": "b", "label": "+ 서울 대표 기상"},
    {"key": "c", "label": "+ 미기후·도시공간"},
]
MODEL_PERFORMANCE_NOTE = (
    "S-DoT 설치위치 매핑이 없어 기상만 모델과 미기후 모델의 "
    "Ablation 성능을 아직 측정할 수 없습니다."
)

# 실측 스냅샷 (원자료가 없을 때 API 가 이 값을 서빙한다)
SNAPSHOT_DIR = REPO_ROOT / "docs" / "api_sample"

FORECAST_DEMO_DATE = "2022-07-10"   # 시연 기준일 (가장 더웠던 날)

# ─── 법정동 경계 폴리곤 (지도 표출) ─────────────────────────
# GeoJSON 하나만 있으면 된다. 없으면 /api/dongs/geojson 이 pending 으로 답한다.
# SHP 을 받았다면 아래로 변환한다 (geopandas 필요):
#     python -m urban_microgrid.landcover 법정동경계.shp data/dong_boundaries.geojson
BOUNDARY_GEOJSON_CANDIDATES = [
    DATA_DIR / "dong_boundaries.geojson",
    DATA_DIR / "법정동경계.geojson",
    SNAPSHOT_DIR / "dong_boundaries.geojson",
]
# 경계 파일마다 코드 컬럼 이름이 다르다(EMD_CD · ADM_CD · adm_cd · BJCD …).
# 이름을 맞추려 들지 말고 '값이 우리 법정동코드와 같은 속성'을 찾는다.
BOUNDARY_CODE_HINTS = ["EMD_CD", "ADM_CD", "adm_cd", "BJDONG_CD", "code"]
BOUNDARY_SIMPLIFY_DEG = 0.00005     # 좌표 단순화 (원본은 수 MB → 지도가 멈춘다)

# ─── 지도 스타일 ────────────────────────────────────────────
# 폴리곤 채움색·투명도까지 백엔드가 정한다. 프론트는 그리기만 한다.
MAP_STYLE = {
    "fill_opacity": 0.32,
    "stroke_width": 4,
    "stroke_opacity": 0.95,
    # 등급별 테두리색 (채움은 등급 색을 그대로 쓴다)
    "stroke_darken": {
        "#2E7D32": "#1B5E20", "#66BB6A": "#2E9E6B", "#FBC02D": "#F9A825",
        "#EF6C00": "#E65100", "#C62828": "#D2543A", "#9E9E9E": "#757575",
    },
}

# 스냅샷 파일명. 시계열 스냅샷은 동 정보를 파일 안에 갖고 있지 않으므로
# 어느 동의 시계열인지 여기서 명시한다.
SNAPSHOT_DONG_PATTERN = "dong_{code}.json"
SNAPSHOT_FORECAST = {
    "1138011400": "forecast_jingwan.json",
}

# ══════════════════════════════════════════════════════════
#  AI 브리핑 (LLM)
# ══════════════════════════════════════════════════════════
# 목업 우측 레일의 "AI 브리핑" 패널.
# 백엔드가 실측값으로 사실표(fact sheet)를 만들어 프롬프트에 넣고,
# 모델은 '문장으로 옮기는 일'만 한다. 숫자를 만들어낼 여지를 남기지 않는다.
LLM_PROVIDER = os.environ.get("UMG_LLM_PROVIDER", "gemini")
LLM_MODEL = os.environ.get("UMG_LLM_MODEL", "gemini-3.6-flash")
LLM_API_KEY_ENVS = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]   # 앞에서부터 찾는다
LLM_MAX_OUTPUT_TOKENS = 800
LLM_TEMPERATURE = 0.2        # 시연 중 문장이 흔들리지 않게 낮게 잡는다
LLM_THINKING_LEVEL = "MINIMAL"  # 브리핑은 분석이 아니라 문장화 — 출력 토큰을 보존한다
LLM_TIMEOUT_S = 60          # Gemini 3.x 첫 호출은 20초를 넘길 수 있다
LLM_CACHE = True             # 같은 요청은 다시 호출하지 않는다 (비용·변동 방지)

# 브리핑 문장 규칙. 이 프로젝트의 표현 원칙을 그대로 모델에 건다.
BRIEFING_RULES = [
    "제공된 사실표에 있는 숫자만 쓴다. 없는 수치는 절대 만들어내지 않는다.",
    "인과 표현을 쓰지 않는다. 'A 때문에 B' 금지, 'A 와 같은 방향으로 B 가 관측됨' 형태로 쓴다.",
    "'입증'·'증명'·'확인됨' 같은 단정 표현을 쓰지 않는다. 관측된 사실만 서술한다.",
    "예상과 다른 결과를 숨기거나 완화하지 않는다. 그대로 쓴다.",
    "2개 동 사례라는 한계를 마지막 문장에 반드시 병기한다.",
    "3문장 이내, 각 문장은 40자 안팎. 발표 슬라이드 옆에 놓일 문구다.",
    "전문용어를 피한다. '전환온도'→'냉방이 켜지는 온도', '임계치'→'위험선'.",
]

# 대응표본 t-검정 실측 결과 [프로젝트 예비값] — docs/03 · CLAUDE.md
# 여름(2022-06-28~08-31) 일평균 R 차이, 구로동 − 진관동
PAIRED_TEST_RESULT = {
    "comparison": "구로동 − 진관동",
    "metric": "일평균 추가 사용률 R",
    "diff_pp": -5.37,
    "ci95": [-8.65, -2.08],
    "p_value": 0.0026,
    "cohen_d": -0.48,
    "n_days": 45,
}
