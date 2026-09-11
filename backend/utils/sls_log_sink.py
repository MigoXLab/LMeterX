"""Backend adapter for the shared Alibaba Cloud SLS Loguru sink."""

try:
    from common.sls_log_sink import SLSLogSink as _SharedSLSLogSink
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from common.sls_log_sink import SLSLogSink as _SharedSLSLogSink

from utils.sls_settings import get_sls_settings


class SLSLogSink(_SharedSLSLogSink):
    def __init__(self, service_name: str):
        """Initialize the SLS sink from backend settings."""
        settings = get_sls_settings()
        super().__init__(
            service_name=service_name,
            enabled=settings.SLS_ENABLED,
            endpoint=settings.SLS_ENDPOINT,
            project=settings.SLS_PROJECT,
            logstore=settings.SLS_LOGSTORE,
            access_key_id=settings.SLS_ACCESS_KEY_ID,
            access_key_secret=settings.SLS_ACCESS_KEY_SECRET,
            topic=settings.SLS_TOPIC,
            source=settings.SLS_SOURCE,
            batch_size=settings.SLS_BATCH_SIZE,
            flush_interval=settings.SLS_FLUSH_INTERVAL,
            queue_size=settings.SLS_QUEUE_SIZE,
        )
