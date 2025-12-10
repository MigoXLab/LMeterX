"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import psutil

from utils.logger import logger


@dataclass
class ProcessInfo:
    """Process information for monitoring."""

    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_mb: float
    create_time: float
    parent_pid: Optional[int] = None
    children: List[int] = field(default_factory=list)

    def __post_init__(self):
        """Ensure children list is always initialized."""
        if self.children is None:
            self.children = []


class ProcessMonitor:
    """Enhanced process monitor for multiprocess management."""

    def __init__(self):
        """Initialize monitoring state and threading primitives."""
        self._monitored_processes: Dict[int, ProcessInfo] = {}
        self._process_groups: Dict[str, Set[int]] = {}
        self._lock = threading.RLock()
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_interval = 5.0  # seconds
        self._cleanup_interval = 30.0  # seconds
        self._last_cleanup = time.time()

    def start_monitoring(self):
        """Start process monitoring."""
        with self._lock:
            if self._monitoring:
                return

            self._monitoring = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, name="ProcessMonitor", daemon=True
            )
            self._monitor_thread.start()
            logger.info("Process monitoring started")

    def stop_monitoring(self):
        """Stop process monitoring."""
        with self._lock:
            if not self._monitoring:
                return

            self._monitoring = False
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=5.0)
            logger.info("Process monitoring stopped")

    def register_process_group(self, group_name: str, pids: List[int]):
        """Register a group of processes for monitoring."""
        with self._lock:
            self._process_groups[group_name] = set(pids)
            for pid in pids:
                self._add_process_to_monitoring(pid)
            logger.info(
                f"Registered process group '{group_name}' with {len(pids)} processes"
            )

    def unregister_process_group(self, group_name: str):
        """Unregister a process group."""
        with self._lock:
            if group_name in self._process_groups:
                pids = self._process_groups[group_name]
                for pid in list(pids):
                    self._remove_process_from_monitoring(pid)
                del self._process_groups[group_name]
                logger.info(f"Unregistered process group '{group_name}'")

    def add_process(self, pid: int, group_name: Optional[str] = None):
        """Add a process to monitoring."""
        with self._lock:
            self._add_process_to_monitoring(pid)
            if group_name:
                if group_name not in self._process_groups:
                    self._process_groups[group_name] = set()
                self._process_groups[group_name].add(pid)

    def remove_process(self, pid: int):
        """Remove a process from monitoring."""
        with self._lock:
            self._remove_process_from_monitoring(pid)
            # Remove from all groups
            for group_name, pids in self._process_groups.items():
                pids.discard(pid)

    def _add_process_to_monitoring(self, pid: int):
        """Add process to monitoring (internal method)."""
        try:
            if pid in self._monitored_processes:
                return

            process = psutil.Process(pid)
            process_info = ProcessInfo(
                pid=pid,
                name=process.name(),
                status=process.status(),
                cpu_percent=process.cpu_percent(),
                memory_mb=process.memory_info().rss / 1024 / 1024,
                create_time=process.create_time(),
                parent_pid=process.ppid(),
                children=[child.pid for child in process.children()],
            )

            self._monitored_processes[pid] = process_info
            logger.debug(f"Added process {pid} ({process_info.name}) to monitoring")

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"Failed to add process {pid} to monitoring: {e}")

    def _remove_process_from_monitoring(self, pid: int):
        """Remove process from monitoring (internal method)."""
        if pid in self._monitored_processes:
            del self._monitored_processes[pid]
            logger.debug(f"Removed process {pid} from monitoring")

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._monitoring:
            try:
                self._update_process_info()
                self._cleanup_dead_processes()
                time.sleep(self._monitor_interval)
            except Exception as e:
                logger.error(f"Error in process monitoring loop: {e}")
                time.sleep(self._monitor_interval)

    def _update_process_info(self):
        """Update information for monitored processes."""
        with self._lock:
            for pid in list(self._monitored_processes.keys()):
                try:
                    process = psutil.Process(pid)
                    process_info = self._monitored_processes[pid]

                    process_info.status = process.status()
                    process_info.cpu_percent = process.cpu_percent()
                    process_info.memory_mb = process.memory_info().rss / 1024 / 1024
                    process_info.children = [child.pid for child in process.children()]

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process no longer exists, mark for cleanup
                    process_info = self._monitored_processes[pid]
                    process_info.status = "zombie"

    def _cleanup_dead_processes(self):
        """Clean up dead processes."""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return

        with self._lock:
            dead_processes = []
            for pid, process_info in self._monitored_processes.items():
                if process_info.status in ["zombie", "dead"]:
                    dead_processes.append(pid)

            for pid in dead_processes:
                self._remove_process_from_monitoring(pid)
                # Remove from all groups
                for group_name, pids in self._process_groups.items():
                    pids.discard(pid)

            if dead_processes:
                logger.info(f"Cleaned up {len(dead_processes)} dead processes")

            self._last_cleanup = current_time

    def get_process_status(self, pid: int) -> Optional[ProcessInfo]:
        """Get status of a specific process."""
        with self._lock:
            return self._monitored_processes.get(pid)

    def get_group_status(self, group_name: str) -> Dict[str, ProcessInfo]:
        """Get status of all processes in a group."""
        with self._lock:
            if group_name not in self._process_groups:
                return {}

            group_status = {}
            for pid in self._process_groups[group_name]:
                if pid in self._monitored_processes:
                    group_status[str(pid)] = self._monitored_processes[pid]

            return group_status

    def get_all_processes_status(self) -> Dict[str, ProcessInfo]:
        """Get status of all monitored processes."""
        with self._lock:
            return {str(pid): info for pid, info in self._monitored_processes.items()}

    def terminate_process_group(self, group_name: str, timeout: float = 10.0) -> bool:
        """Terminate all processes in a group."""
        with self._lock:
            if group_name not in self._process_groups:
                return False

            pids = list(self._process_groups[group_name])
            success = True

            for pid in pids:
                if not self._terminate_process(pid, timeout):
                    success = False

            return success

    def _terminate_process(self, pid: int, timeout: float) -> bool:
        """Terminate a single process."""
        try:
            process = psutil.Process(pid)

            # Try graceful termination first
            process.terminate()

            try:
                process.wait(timeout=timeout)
                logger.info(f"Process {pid} terminated gracefully")
                return True
            except psutil.TimeoutExpired:
                # Force kill if graceful termination fails
                process.kill()
                process.wait()
                logger.warning(f"Process {pid} was force killed")
                return True

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"Failed to terminate process {pid}: {e}")
            return False

    def get_system_resources(self) -> Dict[str, float]:
        """Get system resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available / 1024 / 1024,
                "disk_percent": disk.percent,
                "disk_free_mb": disk.free / 1024 / 1024,
            }
        except Exception as e:
            logger.error(f"Failed to get system resources: {e}")
            return {}


# Global process monitor instance
_process_monitor = ProcessMonitor()


def get_process_monitor() -> ProcessMonitor:
    """Get the global process monitor instance."""
    return _process_monitor


def start_process_monitoring():
    """Start process monitoring."""
    _process_monitor.start_monitoring()


def stop_process_monitoring():
    """Stop process monitoring."""
    _process_monitor.stop_monitoring()


def register_locust_processes(pids: List[int], task_id: str):
    """Register Locust processes for monitoring."""
    group_name = f"locust_task_{task_id}"
    _process_monitor.register_process_group(group_name, pids)


def unregister_locust_processes(task_id: str):
    """Unregister Locust processes from monitoring."""
    group_name = f"locust_task_{task_id}"
    _process_monitor.unregister_process_group(group_name)


def get_locust_process_status(task_id: str) -> Dict[str, ProcessInfo]:
    """Get status of Locust processes for a task."""
    group_name = f"locust_task_{task_id}"
    return _process_monitor.get_group_status(group_name)


def terminate_locust_processes(task_id: str, timeout: float = 10.0) -> bool:
    """Terminate all Locust processes for a task."""
    group_name = f"locust_task_{task_id}"
    return _process_monitor.terminate_process_group(group_name, timeout)
