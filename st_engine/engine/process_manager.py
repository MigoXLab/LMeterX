"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import psutil

from engine.process_monitor import ProcessMonitor
from utils.logger import logger


@dataclass
class LocustProcessGroup:
    """Represents a group of Locust processes for a single task."""

    task_id: str
    master_pid: Optional[int] = None
    worker_pids: Optional[List[int]] = None
    port: Optional[int] = None
    start_time: float = 0.0
    status: str = "unknown"  # created, running, stopping, stopped, failed

    def __post_init__(self):
        """Normalize optional fields for worker list and timestamps."""
        if self.worker_pids is None:
            self.worker_pids = []
        if self.start_time == 0.0:
            self.start_time = time.time()


class MultiprocessManager:
    """Enhanced multiprocess manager for Locust testing."""

    def __init__(self):
        """Initialize process tracking structures and monitoring helpers."""
        self._process_groups: Dict[str, LocustProcessGroup] = {}
        self._port_usage: Dict[int, str] = {}  # port -> task_id mapping
        self._lock = threading.RLock()
        self._base_port = 5557  # Locust default master port
        self._cleanup_timeout = 30.0  # seconds
        self._monitor = ProcessMonitor()
        self._monitor.start_monitoring()

    def __del__(self):
        """Cleanup on destruction."""
        try:
            self._monitor.stop_monitoring()
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.debug("Monitor cleanup skipped: %s", exc)

    def cleanup_all_locust_processes(self) -> int:
        """
        Cleanup all existing Locust processes system-wide.
        Returns:
            Number of processes terminated.
        """
        terminated_count = 0

        try:
            locust_processes = list(self._iter_external_locust_processes())

            if locust_processes:
                # Terminate processes gracefully first
                for process in locust_processes:
                    try:
                        process.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                # Wait for graceful termination
                time.sleep(3.0)

                # Force kill remaining processes
                for process in locust_processes:
                    try:
                        if process.is_running():
                            process.kill()
                        terminated_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        terminated_count += 1
                        continue

        except Exception as e:
            logger.error(f"Error during Locust process cleanup: {e}")

        # Clear internal state
        with self._lock:
            self._process_groups.clear()
            self._port_usage.clear()

        return terminated_count

    def allocate_port(self, task_id: str) -> int:
        """Allocate a unique port for a task's master process."""
        with self._lock:
            # Try to find an unused port
            for port in range(self._base_port, self._base_port + 100):
                if port not in self._port_usage and not self._is_port_in_use(port):
                    self._port_usage[port] = task_id
                    return port

            raise RuntimeError("No available ports for Locust master process")

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use."""
        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                return result == 0
        except Exception:
            return False

    def register_process_group(
        self, task_id: str, master_pid: int, worker_pids: List[int], port: int
    ) -> None:
        """Register a new Locust process group."""
        with self._lock:
            process_group = LocustProcessGroup(
                task_id=task_id,
                master_pid=master_pid,
                worker_pids=worker_pids.copy(),
                port=port,
                status="running",
            )

            self._process_groups[task_id] = process_group

            # Register with process monitor
            all_pids = [master_pid] + worker_pids
            self._monitor.register_process_group(f"locust_task_{task_id}", all_pids)

    def terminate_process_group(self, task_id: str, timeout: float = 15.0) -> bool:
        """
        Terminate all processes in a group with enhanced cleanup.

        Args:
            task_id: Task identifier
            timeout: Maximum time to wait for graceful termination

        Returns:
            True if all processes were terminated successfully
        """
        with self._lock:
            if task_id not in self._process_groups:
                logger.warning(f"No process group found for task {task_id}")
                return True

            process_group = self._process_groups[task_id]
            process_group.status = "stopping"

            all_pids = []
            if process_group.master_pid:
                all_pids.append(process_group.master_pid)
            if process_group.worker_pids:
                all_pids.extend(process_group.worker_pids)

            success = True
            terminated_pids = []

            # Step 1: Graceful termination (SIGTERM)
            for pid in all_pids:
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    terminated_pids.append(pid)
                    continue

            # Step 2: Wait for graceful termination
            start_time = time.time()
            while time.time() - start_time < timeout:
                remaining_pids = []
                for pid in all_pids:
                    if pid in terminated_pids:
                        continue
                    try:
                        process = psutil.Process(pid)
                        if process.is_running():
                            remaining_pids.append(pid)
                        else:
                            terminated_pids.append(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        terminated_pids.append(pid)

                if not remaining_pids:
                    break

                time.sleep(0.5)

            # Step 3: Force termination (SIGKILL) for remaining processes
            remaining_pids = [pid for pid in all_pids if pid not in terminated_pids]
            if remaining_pids:
                logger.warning(
                    f"Force killing remaining processes for task {task_id}: {remaining_pids}"
                )
                for pid in remaining_pids:
                    try:
                        process = psutil.Process(pid)
                        process.kill()
                        process.wait(timeout=5.0)
                        terminated_pids.append(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        terminated_pids.append(pid)
                    except psutil.TimeoutExpired:
                        logger.error(
                            f"Failed to kill process {pid} - may require manual intervention"
                        )
                        success = False

            # Step 4: Cleanup
            if process_group.port and process_group.port in self._port_usage:
                del self._port_usage[process_group.port]

            process_group.status = "stopped" if success else "failed"

            # Unregister from process monitor
            self._monitor.unregister_process_group(f"locust_task_{task_id}")
            return success

    def cleanup_task(self, task_id: str) -> None:
        """Clean up all resources for a task."""
        with self._lock:
            if task_id in self._process_groups:
                process_group = self._process_groups[task_id]

                # Release port
                if process_group.port and process_group.port in self._port_usage:
                    del self._port_usage[process_group.port]

                # Remove from tracking
                del self._process_groups[task_id]

    def get_process_group_status(self, task_id: str) -> Optional[LocustProcessGroup]:
        """Get status of a process group."""
        with self._lock:
            return self._process_groups.get(task_id)

    def get_all_process_groups(self) -> Dict[str, LocustProcessGroup]:
        """Get all process groups."""
        with self._lock:
            return self._process_groups.copy()

    def force_cleanup_orphaned_processes(self) -> int:
        """
        Force cleanup of orphaned Locust processes that are not tracked.
        This is a safety measure for edge cases.

        Returns:
            Number of orphaned processes cleaned up.
        """
        orphaned_count = 0

        try:
            tracked_pids = set()
            active_task_ids = set()

            with self._lock:
                for task_id, group in self._process_groups.items():
                    # Only consider processes from stopped/failed tasks as potential orphans
                    if group.status in ["stopped", "failed"]:
                        continue

                    active_task_ids.add(task_id)
                    if group.master_pid:
                        tracked_pids.add(group.master_pid)
                    if group.worker_pids:
                        tracked_pids.update(group.worker_pids)

            # Find potentially orphaned Locust processes
            orphaned_candidates = []
            for proc in self._iter_external_locust_processes():
                try:
                    pid = proc.pid
                    if pid in tracked_pids:
                        continue

                    cmdline = proc.info.get("cmdline", [])
                    if cmdline is None:
                        cmdline = []
                    cmdline_str = (
                        " ".join(cmdline)
                        if isinstance(cmdline, (list, tuple))
                        else str(cmdline)
                    )
                    create_time = proc.info.get("create_time", 0)

                    process_age = time.time() - create_time
                    if process_age < 300:
                        continue

                    is_associated_with_active_task = any(
                        task_id in cmdline_str for task_id in active_task_ids
                    )
                    if not is_associated_with_active_task:
                        orphaned_candidates.append(pid)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Terminate orphaned processes
            for pid in orphaned_candidates:
                try:
                    process = psutil.Process(pid)
                    if process.is_running():
                        logger.warning(
                            f"Terminating orphaned Locust process {pid} (age > 5min, not tracked)"
                        )
                        process.terminate()

                        try:
                            process.wait(timeout=5.0)
                        except psutil.TimeoutExpired:
                            process.kill()

                        orphaned_count += 1

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            logger.error(f"Error during orphaned process cleanup: {e}")

        return orphaned_count

    def _is_locust_process(self, process: psutil.Process) -> bool:
        """Check if a process is a Locust process."""
        try:
            cmdline = process.cmdline()
            name = process.name()

            # Ensure cmdline is not None and is iterable
            if cmdline is None:
                cmdline = []

            return (
                isinstance(cmdline, (list, tuple))
                and any("locust" in str(arg).lower() for arg in cmdline)
            ) or (
                name.lower() in ["python", "python3"]
                and isinstance(cmdline, (list, tuple))
                and any(
                    "/locust" in str(arg) or "locustfile" in str(arg) for arg in cmdline
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _iter_external_locust_processes(self):
        """
        Yield Locust processes excluding the current process and internal monitors.
        Centralizes filtering logic to keep cleanup routines cohesive.
        """
        attrs = ["pid", "name", "cmdline", "create_time"]
        for proc in psutil.process_iter(attrs):
            try:
                if not self._is_locust_process(proc):
                    continue
                if proc.pid == os.getpid():
                    continue
                cmdline = proc.info.get("cmdline", [])
                if cmdline is None:
                    cmdline = []
                cmdline_str = (
                    " ".join(cmdline)
                    if isinstance(cmdline, (list, tuple))
                    else str(cmdline)
                )
                if "ProcessMonitor" in cmdline_str or "process_monitor" in cmdline_str:
                    continue
                yield proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _count_remaining_locust_processes(self) -> int:
        """Count remaining Locust processes."""
        try:
            return sum(1 for _ in self._iter_external_locust_processes())
        except Exception:
            return 0


# Global multiprocess manager instance
_multiprocess_manager = MultiprocessManager()


def get_multiprocess_manager() -> MultiprocessManager:
    """Get the global multiprocess manager instance."""
    return _multiprocess_manager


def cleanup_all_locust_processes() -> int:
    """Cleanup all existing Locust processes system-wide."""
    return _multiprocess_manager.cleanup_all_locust_processes()


def register_locust_process_group(
    task_id: str, master_pid: int, worker_pids: List[int], port: int
) -> None:
    """Register a new Locust process group."""
    _multiprocess_manager.register_process_group(task_id, master_pid, worker_pids, port)


def terminate_locust_process_group(task_id: str, timeout: float = 15.0) -> bool:
    """Terminate all processes in a group."""
    return _multiprocess_manager.terminate_process_group(task_id, timeout)


def cleanup_task_resources(task_id: str) -> None:
    """Clean up all resources for a task."""
    _multiprocess_manager.cleanup_task(task_id)


def get_task_process_status(task_id: str) -> Optional[LocustProcessGroup]:
    """Get status of a task's process group."""
    return _multiprocess_manager.get_process_group_status(task_id)


def allocate_master_port(task_id: str) -> int:
    """Allocate a unique port for a task's master process."""
    return _multiprocess_manager.allocate_port(task_id)


def force_cleanup_orphaned_processes() -> int:
    """Force cleanup of orphaned Locust processes."""
    return _multiprocess_manager.force_cleanup_orphaned_processes()
