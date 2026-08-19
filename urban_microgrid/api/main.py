"""
Urban-MicroGrid | FastAPI 앱

실행
    uvicorn urban_microgrid.api.main:app --reload --port 8000
    python -m urban_microgrid.api.main            (동일)

문서
    http://localhost:8000/docs      Swagger UI
    http://localhost:8000/api/meta  지금 무엇으로 답하고 있는지
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .. import config as C
from .routes import router
from .store import DataUnavailable, DongNotFound, get_store

DESCRIPTION = """
법정동 단위 전력수요·피크 위험 예측 API — **Watt the hell (2조)**

계약: `docs/02_지표언어_API계약.md`

* 등급·색상·문구까지 백엔드가 만들어 보낸다. 프론트는 계산하지 않는다.
* 값이 없으면 `null` + `status: "pending"` + `note` 를 함께 보낸다.
* 모든 수치는 **프로젝트 예비값**이며 공식 통계가 아니다. 2개 동 사례다.
"""

# 404 응답에 붙일 안내. 조회는 이름이 아니라 코드로만 한다.
TARGETS = ", ".join(f"{m['name']}({c})" for c, m in C.DONG_META.items())


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store()      # 기동 시 1회 적재 — 첫 요청이 느려지지 않게
    print(f"[urban-microgrid] mode={store.mode} · {store.reason}")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=C.API_TITLE, version=C.API_VERSION,
                  description=DESCRIPTION, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=C.API_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # 미확보 자료는 500 이 아니라 "아직 없음"으로 답한다.
    # 프론트는 note 를 그대로 스켈레톤에 띄우면 된다.
    @app.exception_handler(DongNotFound)
    def _not_found(request: Request, exc: DongNotFound):
        return JSONResponse(status_code=404, content={
            "status": "not_found",
            "detail": str(exc),
            "note": f"분석 대상: {TARGETS}",
        })

    @app.exception_handler(DataUnavailable)
    def _unavailable(request: Request, exc: DataUnavailable):
        return JSONResponse(status_code=503, content={
            "status": "pending",
            "detail": str(exc),
            "note": exc.note,
        })

    @app.get("/", include_in_schema=False)
    def _root():
        return RedirectResponse("/docs")

    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("urban_microgrid.api.main:app", host="127.0.0.1", port=8000,
                reload=True)
