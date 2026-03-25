"""
Shared pytest configuration for st_engine tests.
"""

# Gevent monkey-patching MUST happen before any other imports.
# Locust calls ``monkey.patch_all()`` at import time.  If standard-library
# modules (threading, ssl, …) are imported first, the late monkey-patch
# corrupts Python's import lock and causes
# ``RuntimeError: cannot release un-acquired lock`` during test collection.
from gevent import monkey  # noqa: E402

monkey.patch_all()

import os  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# Ensure tests run in test mode
os.environ.setdefault("TESTING", "1")

# Make the st_engine package importable when tests run from repository root
ST_ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ST_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ST_ENGINE_ROOT))
