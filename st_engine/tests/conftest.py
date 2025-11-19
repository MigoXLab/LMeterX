"""
Shared pytest configuration for st_engine tests.
"""

import os
import sys
from pathlib import Path

# Ensure tests run in test mode
os.environ.setdefault("TESTING", "1")

# Make the st_engine package importable when tests run from repository root
ST_ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ST_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ST_ENGINE_ROOT))
