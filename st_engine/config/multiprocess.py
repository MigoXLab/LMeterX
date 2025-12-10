"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
from functools import cached_property
from typing import Any, Dict, Optional


class MultiprocessingConfig:
    """Multiprocessing configuration manager with caching for performance."""

    class _ConfigReader:
        """Internal helper to read environment variables once."""

        def __init__(self) -> None:
            self.enable_multiprocess = os.environ.get(
                "ENABLE_MULTIPROCESS", "auto"
            ).lower()
            self.cpu_cores = os.environ.get("LOCUST_CPU_CORES", "").strip()
            self.processes = os.environ.get("LOCUST_PROCESSES", "").strip()
            self.multiprocess_threshold = int(
                os.environ.get("MULTIPROCESS_THRESHOLD", "1000")
            )
            self.min_users_per_process = int(
                os.environ.get("MIN_USERS_PER_PROCESS", "500")
            )
            self.force_single_process = (
                os.environ.get("FORCE_SINGLE_PROCESS", "false").lower() == "true"
            )
            self.manager_timeout = int(os.environ.get("MANAGER_TIMEOUT", "30"))
            self.fallback_queue_type = os.environ.get(
                "FALLBACK_QUEUE_TYPE", "gevent"
            ).lower()

        def as_dict(self) -> Dict[str, Any]:
            return {
                "enable_multiprocess": self.enable_multiprocess,
                "cpu_cores": self.cpu_cores,
                "processes": self.processes,
                "multiprocess_threshold": self.multiprocess_threshold,
                "min_users_per_process": self.min_users_per_process,
                "force_single_process": self.force_single_process,
                "manager_timeout": self.manager_timeout,
                "fallback_queue_type": self.fallback_queue_type,
            }

    def __init__(self) -> None:
        self._config_reader = self._ConfigReader()

    @cached_property
    def config(self) -> Dict[str, Any]:
        """Cached configuration dictionary."""
        return self._config_reader.as_dict()

    @cached_property
    def cpu_count(self) -> int:
        """Detect and cache CPU core count."""
        return self._get_detected_cpu_count()

    @cached_property
    def is_docker(self) -> bool:
        """Detect and cache if running in Docker."""
        return (
            os.path.exists("/.dockerenv")
            or os.environ.get("DOCKER_CONTAINER") == "true"
        )

    def _get_detected_cpu_count(self) -> int:
        """Detect optimal CPU count for multiprocessing."""
        # Priority 1: LOCUST_CPU_CORES
        cpu_cores = self.config["cpu_cores"]
        if cpu_cores and cpu_cores.replace(".", "").isdigit():
            return max(1, int(float(cpu_cores)))

        # Priority 2: Legacy LOCUST_PROCESSES
        legacy_processes = self.config["processes"]
        if legacy_processes and legacy_processes.isdigit():
            return max(1, int(legacy_processes))

        # Priority 3: System detection
        try:
            import multiprocessing

            system_cpu_count = multiprocessing.cpu_count()

            if self.is_docker:
                return min(system_cpu_count, 4)  # Conservative limit in containers

            return system_cpu_count
        except (ImportError, NotImplementedError):
            return 1

    def should_enable_multiprocess(
        self, concurrent_users: int, cpu_count: Optional[int] = None
    ) -> bool:
        """Decide if multiprocessing should be enabled."""
        if cpu_count is None:
            cpu_count = self.cpu_count

        cfg = self.config

        # Global override
        if cfg["force_single_process"]:
            return False

        # Explicitly disabled
        if cfg["enable_multiprocess"] in ("false", "0", "no"):
            return False

        # Hardware constraint
        if cpu_count <= 1:
            return False

        # Load constraint
        if concurrent_users <= cfg["multiprocess_threshold"]:
            return False

        # Explicitly enabled or auto (default)
        return cfg["enable_multiprocess"] in ("true", "1", "yes", "auto")

    def should_use_manager(self) -> bool:
        """Decide if multiprocessing.Manager should be used."""
        cfg = self.config

        if cfg["force_single_process"]:
            return False

        if cfg["enable_multiprocess"] in ("false", "0", "no"):
            return False

        # Conservative in Docker unless explicitly enabled
        if self.is_docker:
            return cfg["enable_multiprocess"] in ("true", "1", "yes")

        # Single process mode
        if os.environ.get("LOCUST_PROCESSES", "1") == "1":
            return False

        # Resource check
        if not self._check_system_resources():
            return False

        return True

    def _check_system_resources(self) -> bool:
        """Check if system resources are sufficient for multiprocessing."""
        # File descriptor limit
        try:
            import resource

            soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            if soft < 1000:
                return False
        except Exception:
            pass

        # Memory check
        try:
            import psutil

            memory = psutil.virtual_memory()
            if memory.available < 500 * 1024 * 1024:  # 500MB
                return False
        except ImportError:
            pass

        return True

    def get_process_count(
        self, concurrent_users: int, cpu_count: Optional[int] = None
    ) -> int:
        """Calculate optimal number of worker processes."""
        if cpu_count is None:
            cpu_count = self.cpu_count

        if not self.should_enable_multiprocess(concurrent_users, cpu_count):
            return 1

        cfg = self.config
        min_users = cfg["min_users_per_process"]

        # Cap by CPU (max 8 for stability)
        max_by_cpu = min(cpu_count, 8)

        # Cap by user load
        max_by_users = max(1, concurrent_users // min_users)

        process_count = min(max_by_cpu, max_by_users)

        # Ensure minimum users per process is respected
        if process_count > 1:
            users_per_process = concurrent_users // process_count
            if users_per_process < min_users:
                process_count = max(1, concurrent_users // min_users)

        return process_count


# === Singleton instance ===
_config = MultiprocessingConfig()


# === Public API ===
def get_cpu_count() -> int:
    """Get detected CPU core count."""
    return _config.cpu_count


def get_multiprocessing_config() -> Dict[str, Any]:
    """Get full multiprocessing configuration."""
    return _config.config.copy()


def should_enable_multiprocess(
    concurrent_users: int, cpu_count: Optional[int] = None
) -> bool:
    """Determine if multiprocessing should be enabled."""
    return _config.should_enable_multiprocess(concurrent_users, cpu_count)


def should_use_multiprocessing_manager() -> bool:
    """Determine if multiprocessing.Manager should be used."""
    return _config.should_use_manager()


def get_process_count(concurrent_users: int, cpu_count: Optional[int] = None) -> int:
    """Get optimal number of processes for load testing."""
    return _config.get_process_count(concurrent_users, cpu_count)


def get_fallback_queue_type() -> str:
    """Get queue type to fallback to if multiprocessing fails."""
    return _config.config["fallback_queue_type"]


__all__ = [
    "get_cpu_count",
    "get_multiprocessing_config",
    "should_enable_multiprocess",
    "should_use_multiprocessing_manager",
    "get_process_count",
    "get_fallback_queue_type",
]
