"""Compatibility entry point for Uvicorn deployments."""

import logging

from taskflow.config import Settings
from taskflow.main import create_app

settings = Settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
app = create_app(settings)
