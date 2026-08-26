"""Backend adapter for shared Alibaba Cloud SLS settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

try:
    from common.sls_settings import SLSSettings as _SharedSLSSettings
except ModuleNotFoundError:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from common.sls_settings import SLSSettings as _SharedSLSSettings


BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = BACKEND_DIR / ".env"


class SLSSettings(_SharedSLSSettings):
    def __init__(self) -> None:
        """Load SLS settings from process environment and the backend env file."""
        super().__init__(ENV_FILE_PATH)


@lru_cache()
def get_sls_settings() -> SLSSettings:
    """Return cached SLS settings."""
    return SLSSettings()
