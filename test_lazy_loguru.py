from loguru import logger
import sys

logger.remove()
logger.add(sys.stdout, level="DEBUG")

req_id = "1234"
payload_data = {"key": "value"}

logger.opt(lazy=True).debug(
    "[{req_id}] Request Payload: {payload}",
    req_id=lambda: req_id,
    payload=lambda: (lambda s: s[:500] + "... (truncated)" if len(s) > 500 else s)(repr(payload_data))
)
