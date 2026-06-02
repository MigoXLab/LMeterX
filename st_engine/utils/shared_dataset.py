"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Memory-efficient shared dataset reader using mmap.

Serializes the dataset to a temporary file, then mmap's it.
After fork (Locust --processes N), all child processes share the same
physical memory pages (copy-on-write semantics, but data is never modified).
Each process maintains its own read index for round-robin access.
"""

import mmap
import os
import queue
import struct
import tempfile
from typing import Any, Dict, List

import orjson

from utils.logger import logger

# 4 bytes for length prefix per item
_LENGTH_PREFIX_SIZE = 4
_LENGTH_STRUCT = struct.Struct("<I")


class SharedDatasetReader:
    """Read-only round-robin dataset backed by mmap.

    Usage:
        reader = SharedDatasetReader.from_items(items_list)
        item = reader.next()  # round-robin access

    After os.fork(), each child process inherits the mmap mapping
    but maintains its own _index counter, achieving zero-copy sharing.
    """

    def __init__(self, mm: mmap.mmap, offsets: List[int], total_items: int):
        """Initialize with mmap object, item offsets, and total count."""
        self._mm = mm
        self._offsets = offsets
        self._total = total_items
        self._index = 0

    @classmethod
    def from_items(
        cls, items: List[Dict[str, Any]], task_logger=None
    ) -> "SharedDatasetReader":
        """Create a SharedDatasetReader from a list of dict items.

        Serializes items using orjson (fast, compact), writes to a temp file,
        then mmap's it for shared read access across forked processes.
        """
        effective_logger = task_logger or logger

        if not items:
            raise ValueError("Cannot create SharedDatasetReader from empty items")

        tmp_fd, tmp_path = tempfile.mkstemp(prefix="lmeterx_dataset_", suffix=".mmap")
        try:
            offsets: List[int] = []
            current_offset = 0

            with os.fdopen(tmp_fd, "wb") as f:
                for item in items:
                    blob = orjson.dumps(item)
                    length_bytes = _LENGTH_STRUCT.pack(len(blob))
                    offsets.append(current_offset)
                    f.write(length_bytes)
                    f.write(blob)
                    current_offset += _LENGTH_PREFIX_SIZE + len(blob)

            fd = os.open(tmp_path, os.O_RDONLY)
            try:
                mm = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
            finally:
                os.close(fd)

            effective_logger.info(
                f"SharedDatasetReader created: {len(items)} items, "
                f"{current_offset / 1024:.1f} KB mmap'd"
            )

            return cls(mm, offsets, len(items))
        finally:
            # Unlink immediately - the mmap file descriptor keeps the data alive.
            # After fork, children inherit the mmap mapping, not the path reference.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def next(self) -> Dict[str, Any]:
        """Get next item in round-robin order."""
        if self._total == 0:
            raise IndexError("Cannot get next item from empty dataset")
        idx = self._index % self._total
        self._index += 1
        return self._read_item(idx)

    def _read_item(self, idx: int) -> Dict[str, Any]:
        """Deserialize item at given index from mmap."""
        offset = self._offsets[idx]
        length = _LENGTH_STRUCT.unpack_from(self._mm, offset)[0]
        data = self._mm[
            offset + _LENGTH_PREFIX_SIZE : offset + _LENGTH_PREFIX_SIZE + length
        ]
        return orjson.loads(data)

    def __len__(self) -> int:
        """Return total number of items in the dataset."""
        return self._total

    @property
    def empty(self) -> bool:
        """Check if the dataset is empty."""
        return self._total == 0

    def close(self) -> None:
        """Release mmap resources."""
        try:
            self._mm.close()
        except Exception as e:
            logger.debug(f"Ignored error closing mmap: {e}")


class DatasetQueueAdapter:
    """Adapter that makes SharedDatasetReader behave like a queue.Queue.

    Provides get_nowait()/put_nowait()/empty()/qsize() interface for backward
    compatibility with existing code that uses queue.Queue for datasets.
    """

    def __init__(self, reader: SharedDatasetReader):
        """Initialize adapter with a SharedDatasetReader instance."""
        self._reader = reader

    def get_nowait(self) -> Dict[str, Any]:
        """Get next item (round-robin). Raises queue.Empty if dataset is empty."""
        try:
            return self._reader.next()
        except IndexError:
            raise queue.Empty()

    def put_nowait(self, item) -> None:
        """No-op: data is read-only in shared memory."""
        pass

    def put(self, item) -> None:
        """No-op: data is read-only in shared memory."""
        pass

    def empty(self) -> bool:
        """Always False if dataset has items (infinite round-robin)."""
        return self._reader.empty

    def qsize(self) -> int:
        """Return the size of the underlying dataset."""
        return len(self._reader)

    def close(self) -> None:
        """Release underlying mmap resources."""
        self._reader.close()
