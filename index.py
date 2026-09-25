"""Vercel entrypoint: exposes the FastAPI ``app`` (locally, use ``uvicorn soundkraft.app:app``)."""

from soundkraft.app import app

__all__ = ["app"]
