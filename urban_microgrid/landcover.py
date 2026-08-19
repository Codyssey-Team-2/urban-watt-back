"""
Urban-MicroGrid | 토지피복 처리

두 가지 경로를 제공한다.

  1) 순수 파이썬 (의존성 없음)  — SHP/DBF 직접 파싱, 도엽 전체 피복률 계산
     geopandas 설치 전에도 즉시 검증 가능. 클리핑·버퍼는 불가.

  2) geopandas 경로            — 법정동 경계 클리핑 + 핵심시설 버퍼까지 전체 파이프라인
     실제 프로젝트 지표(ISR/VCR)는 이쪽으로 산출한다.

세분류 토지피복지도 규격
  L1_CODE 대분류(3자리) / L2_CODE 중분류 / L3_CODE 세분류
  좌표계는 .prj 기준 EPSG:5186 (Korea 2000 중부원점, FE 200000 / FN 600000)
"""
import struct
from collections import defaultdict
from pathlib import Path

from . import config as C

# ══════════════════════════════════════════════════════════
#  분류 코드 정의  (문서 3장 "공간 분석 범위 기준"의 코드화)
# ══════════════════════════════════════════════════════════
L1_IMPERVIOUS = {"100"}              # 시가화건조지역
L1_VEGETATION = {"200", "300", "400"}  # 농업 + 산림 + 초지
L1_WATER = {"700"}                   # 수역
L1_WETLAND = {"500"}                 # 습지 — 불투수·식생 어느 쪽도 아님
L1_BARE = {"600"}                    # 나지  — 어느 쪽도 아님

# 전력소비가 실제 발생하는 시설 = 버퍼의 중심이 되는 핵심영역
L3_POWER_CONSUMING = {
    "111",  # 단독주거시설
    "112",  # 공동주거시설
    "121",  # 공업시설
    "131",  # 상업·업무시설
    "141",  # 문화·체육·휴양시설
    "162",  # 교육·행정시설
    "163",  # 기타 공공시설
}
# 도로(154)는 핵심영역 선정에서 제외하되 분석범위 안에서는 포함한다.


# ══════════════════════════════════════════════════════════
#  1) 순수 파이썬 리더
# ══════════════════════════════════════════════════════════
def read_dbf(path):
    """DBF 를 dict 리스트로. 인코딩은 cp949."""
    b = Path(path).read_bytes()
    nrec, = struct.unpack("<i", b[4:8])
    hlen, = struct.unpack("<h", b[8:10])
    rlen, = struct.unpack("<h", b[10:12])
    nf = (hlen - 33) // 32
    fields = []
    for i in range(nf):
        o = 32 + i * 32
        name = b[o:o + 11].split(b"\x00")[0].decode("cp949", "ignore")
        fields.append((name, b[o + 16]))
    out = []
    for r in range(nrec):
        p = hlen + r * rlen + 1          # 첫 바이트는 삭제 플래그
        row = {}
        for name, ln in fields:
            row[name] = b[p:p + ln].decode("cp949", "ignore").strip()
            p += ln
        out.append(row)
    return out


def _ring_area(ring):
    """부호 있는 면적(shoelace). 외곽은 +, 홀(hole)은 − 로 나와 자동 차감된다."""
    s = 0.0
    for i in range(len(ring) - 1):
        s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return s / 2


def read_shp_polygons(path):
    """
    SHP 를 [(rings, area)] 로. rings 는 링 좌표 리스트.
    레코드 순서는 DBF 행 순서와 1:1 대응한다.
    """
    d = Path(path).read_bytes()
    pos, out = 100, []
    while pos < len(d):
        _, clen = struct.unpack(">ii", d[pos:pos + 8])
        pos += 8
        rec = d[pos:pos + clen * 2]
        pos += clen * 2
        stype, = struct.unpack("<i", rec[0:4])
        if stype != 5:                    # Polygon 아님
            out.append(([], 0.0))
            continue
        nparts, npoints = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + nparts * 4]))
        po = 44 + nparts * 4
        pts = [struct.unpack("<2d", rec[po + i * 16:po + i * 16 + 16])
               for i in range(npoints)]
        rings, total = [], 0.0
        for i, s in enumerate(parts):
            e = parts[i + 1] if i + 1 < nparts else npoints
            ring = pts[s:e]
            rings.append(ring)
            total += _ring_area(ring)
        out.append((rings, abs(total)))
    return out


def coverage_from_sheet(shp_path, dbf_path=None):
    """
    도엽 하나의 피복률을 계산한다 (클리핑 없음).

    ⚠️ 이 값은 '도엽 전체' 기준이며 법정동 지표가 아니다.
       진관동 도엽은 북한산이 74% 를 차지해 ISR 이 5% 대로 나온다.
       실제 프로젝트 지표는 coverage_for_dong() 을 써야 한다.
    """
    shp_path = Path(shp_path)
    dbf_path = Path(dbf_path) if dbf_path else shp_path.with_suffix(".dbf")

    recs = read_dbf(dbf_path)
    geoms = read_shp_polygons(shp_path)
    if len(recs) != len(geoms):
        raise ValueError(f"DBF({len(recs)}) 와 SHP({len(geoms)}) 레코드 수 불일치")

    total = sum(a for _, a in geoms)
    by_l1, by_l3 = defaultdict(float), defaultdict(float)
    for r, (_, a) in zip(recs, geoms):
        by_l1[(r["L1_CODE"], r["L1_NAME"])] += a
        by_l3[(r["L3_CODE"], r["L3_NAME"])] += a

    def share(codes):
        return sum(a for r, (_, a) in zip(recs, geoms)
                   if r["L1_CODE"] in codes) / total * 100

    isr, vcr, wsr = share(L1_IMPERVIOUS), share(L1_VEGETATION), share(L1_WATER)
    return {
        "total_area_m2": total,
        "n_polygons": len(geoms),
        "ISR": round(isr, 2),
        "VCR": round(vcr, 2),
        "WSR": round(wsr, 2),
        "wetland_pct": round(share(L1_WETLAND), 2),
        "bare_pct": round(share(L1_BARE), 2),
        "MCI": round(isr - vcr, 2),
        "by_l1": {f"{c} {n}": round(a / total * 100, 2)
                  for (c, n), a in sorted(by_l1.items())},
        "by_l3_top": {f"{c} {n}": round(a / total * 100, 2)
                      for (c, n), a in sorted(by_l3.items(),
                                              key=lambda x: -x[1])[:10]},
        "scope": "sheet_full",
        "warning": "도엽 전체 기준. 법정동 클리핑 전 값이므로 프로젝트 지표로 쓰지 말 것.",
    }


# ══════════════════════════════════════════════════════════
#  2) geopandas 경로 — 실제 프로젝트 지표
# ══════════════════════════════════════════════════════════
def load_landcover(paths):
    """도엽 여러 장을 읽어 하나로 병합하고 작업 좌표계로 변환."""
    import geopandas as gpd
    import pandas as pd

    frames = [gpd.read_file(p, encoding="cp949") for p in paths]
    gdf = pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=frames[0].crs)
    return gdf.to_crs(C.CRS_WORK)


def coverage_for_dong(landcover, boundaries, dong_code,
                      buffer_m=None, code_field="EMD_CD"):
    """
    문서 3장 기준을 그대로 구현한 프로젝트 지표 산출.

        ① 법정동 경계로 클리핑
        ② 전력소비시설(L3_POWER_CONSUMING)만 추출 → 핵심영역
        ③ 핵심영역 buffer_m 로 분석범위 생성
        ④ 분석범위 안에서만 피복률 재계산

    이렇게 해야 진관동의 북한산이 지표를 왜곡하지 않는다.
    """
    import geopandas as gpd

    buffer_m = buffer_m or C.BUFFER_DEFAULT_M
    for g in (landcover, boundaries):
        if g.crs is None or g.crs.to_string() != C.CRS_WORK:
            raise ValueError(f"좌표계를 {C.CRS_WORK} 로 맞추고 호출하세요.")

    dong = boundaries[boundaries[code_field].astype(str) == str(dong_code)]
    if dong.empty:
        raise ValueError(f"법정동코드 {dong_code} 를 경계 자료에서 찾지 못했습니다.")

    clipped = gpd.overlay(landcover, dong[["geometry"]], how="intersection")

    core = clipped[clipped["L3_CODE"].isin(L3_POWER_CONSUMING)]
    if core.empty:
        raise ValueError("핵심영역(전력소비시설)이 비었습니다. L3_CODE 값을 확인하세요.")

    zone = core.buffer(buffer_m).union_all()
    scope = gpd.clip(clipped, zone)

    scope = scope.copy()
    scope["area"] = scope.geometry.area
    total = scope["area"].sum()

    def share(codes):
        return scope.loc[scope["L1_CODE"].isin(codes), "area"].sum() / total * 100

    isr, vcr, wsr = share(L1_IMPERVIOUS), share(L1_VEGETATION), share(L1_WATER)
    return {
        "dong_code": str(dong_code),
        "buffer_m": buffer_m,
        "scope_area_m2": float(total),
        "ISR": round(isr, 2),
        "VCR": round(vcr, 2),
        "WSR": round(wsr, 2),
        "MCI": round(isr - vcr, 2),
        "heat_index": round(((isr - vcr) + 100) / 2, 1),
        "scope": "dong_buffer",
    }


def buffer_sensitivity(landcover, boundaries, dong_code, code_field="EMD_CD"):
    """
    50 / 100 / 200 m 각각의 지표를 산출한다.
    세 값을 모델에 넣어 성능이 가장 좋은 반경을 채택하면,
    100m 가 '임의값'이 아니라 '민감도 분석 결과'가 된다.
    """
    return {r: coverage_for_dong(landcover, boundaries, dong_code, r, code_field)
            for r in C.BUFFER_RADII_M}


def export_boundary_geojson(boundaries, dong_codes, out_path,
                            code_field="EMD_CD", simplify_deg=0.00005):
    """
    프론트엔드용 경계 GeoJSON.

      · 표출 좌표계(EPSG:4326)로 변환 — GeoJSON 좌표 순서는 [경도, 위도]
      · simplify + 좌표 6자리 절삭으로 용량을 크게 줄인다
        (원본 그대로 내보내면 수 MB 가 되어 모바일에서 지도가 멈춘다)
    """
    b = boundaries[boundaries[code_field].astype(str).isin(
        [str(c) for c in dong_codes])].copy()
    b = b.to_crs(C.CRS_DISPLAY)
    b["geometry"] = b.geometry.simplify(simplify_deg, preserve_topology=True)
    b["lat"] = b.geometry.representative_point().y   # centroid 가 동 밖으로 나갈 수 있음
    b["lng"] = b.geometry.representative_point().x
    b.to_file(out_path, driver="GeoJSON", COORDINATE_PRECISION=6)
    return {
        "path": str(out_path),
        "bbox": [round(v, 6) for v in b.total_bounds],
        "centers": b[[code_field, "lat", "lng"]].to_dict("records"),
    }
