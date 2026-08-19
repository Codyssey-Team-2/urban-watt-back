"""
Urban-MicroGrid | FastAPI 백엔드

    urban_microgrid/api/
    ├── schemas.py   docs/02_지표언어_API계약.md 를 타입으로 고정
    ├── store.py     데이터 원천 (원자료 → 파이프라인 / 실측 스냅샷)
    ├── routes.py    엔드포인트
    └── main.py      앱 조립

실행:  uvicorn urban_microgrid.api.main:app --reload
"""
from .main import app, create_app  # noqa: F401
