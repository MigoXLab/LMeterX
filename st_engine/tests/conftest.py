import os
import sys
from unittest.mock import MagicMock

# Mock gevent monkey patching before any other imports to prevent deadlocks/hangs
# with pytest-cov / coverage tracking.
try:
    import gevent.monkey

    gevent.monkey.patch_all = MagicMock()
except ImportError:
    pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
