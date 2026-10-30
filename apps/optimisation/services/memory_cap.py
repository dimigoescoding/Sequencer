"""Stop a solver that would exhaust a free Render instance.

The cap is a virtual-memory limit around the solver call. It is applied only
when this process is inside an instance of about 512 MB. A larger instance,
including the 2 GB plan, has no cap. Switching the web service to that plan
removes the limit once the new instance is running.

Measured on ``sequencer input v5.xlsx`` (50 FOU, 55 IAC, 50 WTG, 20 seconds):

- FOU with sailing distance peaked at 343 MB resident and 601 MB virtual.
- FOU, IAC, and WTG together with sailing distance peaked at 626 MB resident
  and 879 MB virtual, and passed 512 MB resident.

A 700 MB virtual cap stops that joint run with ``MemoryError`` at about
400 MB resident. The FOU sailing-distance run still finishes.
"""

from __future__ import annotations

import ctypes
import gc
import resource
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Above this, the instance is not the free 512 MB web service.
_FREE_INSTANCE_CEILING = 600 * 1024 * 1024
_SOLVER_ADDRESS_CAP = 700 * 1024 * 1024


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
