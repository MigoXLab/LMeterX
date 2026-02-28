"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import threading
import time
from typing import Dict, List, Optional, Tuple

import psutil

from utils.logger import logger
from utils.vm_push import ENGINE_ID, build_metric_line, push_metrics

# Default collection interval in seconds.
_COLLECT_INTERVAL: float = float(os.environ.get("RESOURCE_COLLECT_INTERVAL", "2"))

# cgroup v2 paths (Docker / K8s modern runtimes)
_CGROUP_V2_CPU_STAT = "/sys/fs/cgroup/cpu.stat"
_CGROUP_V2_CPU_MAX = "/sys/fs/cgroup/cpu.max"
_CGROUP_V2_MEMORY_CURRENT = "/sys/fs/cgroup/memory.current"
_CGROUP_V2_MEMORY_MAX = "/sys/fs/cgroup/memory.max"

# cgroup v1 paths (older Docker runtimes)
_CGROUP_V1_CPU_USAGE = "/sys/fs/cgroup/cpu/cpuacct.usage"
_CGROUP_V1_MEMORY_USAGE = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
_CGROUP_V1_MEMORY_LIMIT = "/sys/fs/cgroup/memory/memory.limit_in_bytes"


def _read_file(path: str) -> Optional[str]:
    """Read a single-line file safely, return None on failure."""
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except OSError:
        return None


def _detect_cgroup_version() -> int:
    """Detect cgroup version (2, 1, or 0 = host/no cgroup)."""
    if os.path.isfile(_CGROUP_V2_CPU_STAT):
        return 2
    if os.path.isfile(_CGROUP_V1_CPU_USAGE):
        return 1
    return 0


class ResourceCollector:
    """Collect CPU, Memory and Network metrics and push to VictoriaMetrics."""

    def __init__(self, interval: float = _COLLECT_INTERVAL):
        """Initialize ResourceCollector with the given collection interval."""
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cgroup_version = _detect_cgroup_version()
        self._prev_cpu_ns: Optional[int] = None
        self._prev_cpu_time: Optional[float] = None
        self._prev_net: Optional[Tuple[int, int]] = None
        self._prev_net_time: Optional[float] = None
        self._cpu_limit_cores: Optional[float] = None
        self._memory_limit_bytes: Optional[int] = None

        # Pre-compute limits
        self._init_limits()
        logger.info(
            f"ResourceCollector initialized: cgroup_v{self._cgroup_version}, "
            f"cpu_limit={self._cpu_limit_cores}, "
            f"mem_limit={self._memory_limit_bytes}, "
            f"engine_id={ENGINE_ID}, interval={self._interval}s"
        )

    def _init_limits(self):
        """Pre-read container resource limits."""
        if self._cgroup_version == 2:
            # cpu.max format: "quota period" or "max period"
            raw = _read_file(_CGROUP_V2_CPU_MAX)
            if raw and raw != "max":
                parts = raw.split()
                if len(parts) == 2 and parts[0] != "max":
                    quota = int(parts[0])
                    period = int(parts[1])
                    self._cpu_limit_cores = quota / period

            raw = _read_file(_CGROUP_V2_MEMORY_MAX)
            if raw and raw != "max":
                try:
                    self._memory_limit_bytes = int(raw)
                except ValueError:
                    pass

        elif self._cgroup_version == 1:
            # cgroup v1 CPU period/quota
            period_raw = _read_file("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
            quota_raw = _read_file("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
            if period_raw and quota_raw:
                try:
                    period = int(period_raw)
                    quota = int(quota_raw)
                    if quota > 0:
                        self._cpu_limit_cores = quota / period
                except ValueError:
                    pass

            raw = _read_file(_CGROUP_V1_MEMORY_LIMIT)
            if raw:
                try:
                    val = int(raw)
                    # cgroup v1 sets 9223372036854771712 for "no limit"
                    if val < 2**62:
                        self._memory_limit_bytes = val
                except ValueError:
                    pass

        # Fallback to host
        if self._cpu_limit_cores is None:
            self._cpu_limit_cores = float(psutil.cpu_count(logical=True) or 1)
        if self._memory_limit_bytes is None:
            self._memory_limit_bytes = psutil.virtual_memory().total

    def start(self):
        """Start the collection daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._collect_loop,
            name="ResourceCollector",
            daemon=True,
        )
        self._thread.start()
        logger.info("ResourceCollector started.")

    def stop(self):
        """Stop the collection daemon thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("ResourceCollector stopped.")

    def _collect_loop(self):
        """Main collection loop."""
        while self._running:
            try:
                snapshot = self._collect_snapshot()
                self._push_snapshot(snapshot)
            except Exception as e:
                logger.debug(f"ResourceCollector error: {e}")
            time.sleep(self._interval)

    def _collect_snapshot(self) -> Dict[str, float]:
        """Collect a single snapshot of system resources."""
        now = time.time()
        result: Dict[str, float] = {}

        # --- CPU ---
        cpu_percent = self._get_cpu_percent(now)
        result["cpu_percent"] = round(cpu_percent, 2)
        result["cpu_limit_cores"] = self._cpu_limit_cores or 1.0

        # --- Memory ---
        mem_used, mem_total = self._get_memory()
        result["memory_used_bytes"] = mem_used
        result["memory_total_bytes"] = mem_total
        result["memory_percent"] = round(
            (mem_used / mem_total * 100) if mem_total > 0 else 0, 2
        )

        # --- Network ---
        net_sent_bps, net_recv_bps, net_sent_total, net_recv_total = self._get_network(
            now
        )
        result["network_sent_bytes_per_sec"] = round(net_sent_bps, 2)
        result["network_recv_bytes_per_sec"] = round(net_recv_bps, 2)
        result["network_sent_bytes_total"] = net_sent_total
        result["network_recv_bytes_total"] = net_recv_total

        return result

    def _get_cpu_percent(self, now: float) -> float:
        """Get container-aware CPU usage percentage.

        Returns a value between 0 and 100 representing the percentage of
        allocated CPU that is being used.
        """
        if self._cgroup_version == 2:
            raw = _read_file(_CGROUP_V2_CPU_STAT)
            if raw:
                for line in raw.split("\n"):
                    if line.startswith("usage_usec"):
                        usage_us = int(line.split()[1])
                        return self._calc_cpu_percent(usage_us * 1000, now)
        elif self._cgroup_version == 1:
            raw = _read_file(_CGROUP_V1_CPU_USAGE)
            if raw:
                usage_ns = int(raw)
                return self._calc_cpu_percent(usage_ns, now)

        # Fallback: psutil host-level
        return psutil.cpu_percent(interval=0)

    def _calc_cpu_percent(self, current_ns: int, now: float) -> float:
        """Calculate CPU percentage from cumulative nanosecond counters."""
        if self._prev_cpu_ns is None or self._prev_cpu_time is None:
            self._prev_cpu_ns = current_ns
            self._prev_cpu_time = now
            return 0.0

        delta_ns = current_ns - self._prev_cpu_ns
        delta_time = now - self._prev_cpu_time

        self._prev_cpu_ns = current_ns
        self._prev_cpu_time = now

        if delta_time <= 0:
            return 0.0

        # Convert to cores used
        cores_used = delta_ns / (delta_time * 1e9)
        limit = self._cpu_limit_cores or 1.0
        return min((cores_used / limit) * 100, 100.0)

    def _get_memory(self) -> Tuple[int, int]:
        """Get container-aware memory usage and limit in bytes."""
        if self._cgroup_version == 2:
            raw = _read_file(_CGROUP_V2_MEMORY_CURRENT)
            if raw:
                used = int(raw)
                total = self._memory_limit_bytes or psutil.virtual_memory().total
                return used, total
        elif self._cgroup_version == 1:
            raw = _read_file(_CGROUP_V1_MEMORY_USAGE)
            if raw:
                used = int(raw)
                total = self._memory_limit_bytes or psutil.virtual_memory().total
                return used, total

        # Fallback
        mem = psutil.virtual_memory()
        return mem.used, mem.total

    def _get_network(self, now: float) -> Tuple[float, float, int, int]:
        """Get network bandwidth (bytes/sec) and total bytes."""
        counters = psutil.net_io_counters()
        sent_total = counters.bytes_sent
        recv_total = counters.bytes_recv

        if self._prev_net is None or self._prev_net_time is None:
            self._prev_net = (sent_total, recv_total)
            self._prev_net_time = now
            return 0.0, 0.0, sent_total, recv_total

        delta_time = now - self._prev_net_time
        if delta_time <= 0:
            return 0.0, 0.0, sent_total, recv_total

        sent_bps = (sent_total - self._prev_net[0]) / delta_time
        recv_bps = (recv_total - self._prev_net[1]) / delta_time

        self._prev_net = (sent_total, recv_total)
        self._prev_net_time = now

        return max(sent_bps, 0), max(recv_bps, 0), sent_total, recv_total

    def _push_snapshot(self, snapshot: Dict[str, float]):
        """Push the snapshot to VictoriaMetrics."""
        timestamp_ms = int(time.time() * 1000)
        labels = {"engine_id": ENGINE_ID}

        # Metric definitions: (vm_metric_name, snapshot_key)
        metric_defs: List[Tuple[str, str]] = [
            ("engine_cpu_percent", "cpu_percent"),
            ("engine_cpu_limit_cores", "cpu_limit_cores"),
            ("engine_memory_used_bytes", "memory_used_bytes"),
            ("engine_memory_total_bytes", "memory_total_bytes"),
            ("engine_memory_percent", "memory_percent"),
            ("engine_network_sent_bytes_per_sec", "network_sent_bytes_per_sec"),
            ("engine_network_recv_bytes_per_sec", "network_recv_bytes_per_sec"),
            ("engine_network_sent_bytes_total", "network_sent_bytes_total"),
            ("engine_network_recv_bytes_total", "network_recv_bytes_total"),
        ]

        lines: List[str] = []
        for metric_name, key in metric_defs:
            val = snapshot.get(key, 0)
            lines.append(
                build_metric_line(metric_name, float(val), labels, timestamp_ms)
            )

        push_metrics(lines)


# Module-level singleton (created lazily)
_collector: Optional[ResourceCollector] = None


def get_resource_collector() -> ResourceCollector:
    """Get or create the global ResourceCollector singleton."""
    global _collector
    if _collector is None:
        _collector = ResourceCollector()
    return _collector


def start_resource_collector():
    """Start the global resource collector."""
    get_resource_collector().start()


def stop_resource_collector():
    """Stop the global resource collector."""
    if _collector is not None:
        _collector.stop()
