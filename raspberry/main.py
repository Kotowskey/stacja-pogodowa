"""Punkt wejścia: uruchamia serwer Uvicorn z aplikacją FastAPI.

Uruchomienie:
    python -m raspberry.main
    # albo:
    uvicorn raspberry.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging

import uvicorn

from .api import create_app
from .config import load_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


config = load_config()
app = create_app(config)


def main() -> None:
    uvicorn.run(
        app,
        host=config.web.host,
        port=config.web.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
