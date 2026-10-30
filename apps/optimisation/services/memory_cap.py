"""Stop a solver that would exhaust a free Render instance.

The cap is a virtual-memory limit around the solver call. It is applied only
when this process is inside an instance of about 512 MB. A larger instance,
including the 2 GB plan, has no cap. Switching the web service to that plan
removes the limit once the new instance is running.

Measured on ``sequencer input v5.xlsx`` (50 FOU, 55 IAC, 50 WTG, 20 seconds):

- FOU with sailing distance peaked at 343 MB resident and 601 MB virtual.
- FOU, IAC, and WTG together with sailing distance peaked at 626 MB resident
  and 879 MB virtual, and passed 512 MB resident.

A 700 MB virtual cap stopped that joint run at about 400 MB resident.
The cap is 1000 MB virtual. The FOU sailing-distance run still finishes.
"""

from __future__ import annotations

import ctypes
import gc
import resource
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Above this, the instance is not the free 512 MB web service.
_FREE_INSTANCE_CEILING = 600 * 1024 * 1024
_SOLVER_ADDRESS_CAP = 1000 * 1024 * 1024


def instance_limit_bytes() -> int | None:
    """Memory limit of this process, from its cgroup or from MemTotal."""
    return _instance_limit_bytes()


def exceeds_free_instance() -> bool:
    """True when this process has more memory than the 512 MB Render service."""
    limit = _instance_limit_bytes()
    return limit is not None and limit > _FREE_INSTANCE_CEILING


def address_cap_bytes() -> int | None:
    """Virtual-memory cap for the solver, or None when this instance is larger."""
    limit = _instance_limit_bytes()
    if limit is None or limit > _FREE_INSTANCE_CEILING:
        return None
    return _SOLVER_ADDRESS_CAP


@contextmanager
def solver_address_cap() -> Iterator[None]:
    """Apply the free-instance cap for one solver call, then restore it."""
    cap = address_cap_bytes()
    if cap is None:
        yield
        return
    previous = resource.getrlimit(resource.RLIMIT_AS)
    hard = previous[1]
    soft_cap = hard if 0 <= hard < cap else cap
    try:
        resource.setrlimit(resource.RLIMIT_AS, (soft_cap, hard))
    except (ValueError, OSError):
        yield
        return
    try:
        yield
    finally:
        try:
            resource.setrlimit(resource.RLIMIT_AS, previous)
        except (ValueError, OSError):
            pass


def release_solver_heap() -> None:
    """Return solver allocations to the operating system after a cap stop."""
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


class MemoryProbe:
    """Peak real memory and address space while a solver call is running."""

    def __init__(self) -> None:
        self.peak_rss_bytes: int | None = None
        self.peak_address_bytes: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        self.sample()

    def sample(self) -> None:
        reading = _proc_memory_bytes()
        if reading is None:
            return
        rss, address = reading
        self.peak_rss_bytes = rss if self.peak_rss_bytes is None else max(self.peak_rss_bytes, rss)
        self.peak_address_bytes = (
            address if self.peak_address_bytes is None else max(self.peak_address_bytes, address)
        )

    def _loop(self) -> None:
        while not self._stop.wait(0.05):
            self.sample()


def _proc_memory_bytes() -> tuple[int, int] | None:
    try:
        lines = Path("/proc/self/status").read_text().splitlines()
    except OSError:
        return None
    rss_kb = address_kb = None
    for line in lines:
        if line.startswith("VmRSS:"):
            rss_kb = int(line.split()[1])
        elif line.startswith("VmSize:"):
            address_kb = int(line.split()[1])
    if rss_kb is None or address_kb is None:
        return None
    return rss_kb * 1024, address_kb * 1024


def _instance_limit_bytes() -> int | None:
    cgroup = _cgroup_limit_bytes()
    if cgroup is not None:
        return cgroup
    return _memtotal_bytes()


def _cgroup_limit_bytes() -> int | None:
    """Smallest cgroup memory limit that applies to this process."""
    paths = [Path("/sys/fs/cgroup/memory.max")]
    try:
        for line in Path("/proc/self/cgroup").read_text().splitlines():
            if not line.startswith("0::"):
                continue
            current = Path("/sys/fs/cgroup")
            paths.append(current / "memory.max")
            for part in line.split(":", 2)[-1].lstrip("/").split("/"):
                if not part:
                    continue
                current = current / part
                paths.append(current / "memory.max")
    except OSError:
        pass
    limits = []
    for path in paths:
        try:
            text = path.read_text().strip()
        except OSError:
            continue
        if text.isdigit():
            limits.append(int(text))
    if not limits:
        return None
    return min(limits)


def _memtotal_bytes() -> int | None:
    try:
        lines = Path("/proc/meminfo").read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    return None
