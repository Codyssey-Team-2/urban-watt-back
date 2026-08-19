"""Repository-root ASGI entry point.

Run from the repository root with:
    uvicorn main:app --reload
"""

from urban_microgrid.api.main import app

__all__ = ["app"]
