"""Stop the one running solver from the server's other thread.

Gunicorn keeps two threads. The generate request holds one thread inside
CP-SAT. Cancel uses the other thread and asks that solver to stop.
"""

from __future__ import annotations

import threading

_guard = threading.Lock()
_solver = None
_token = ""
_cancelled_token = ""


def begin(token: str) -> bool:
    """Register this run. A cancel that already named this token stops it."""
    global _solver, _token
    with _guard:
        _token = token or ""
        _solver = None
        return not token or token != _cancelled_token


def bind(solver) -> None:
    global _solver
    with _guard:
        _solver = solver
        stop = bool(_token) and _token == _cancelled_token
    if stop:
        solver.StopSearch()


def release(solver) -> None:
    global _solver
    with _guard:
        if _solver is solver:
            _solver = None


def cancel(token: str) -> None:
    global _cancelled_token
    if not token:
        return
    with _guard:
        _cancelled_token = token
        solver = _solver if _token == token else None
    if solver is not None:
        solver.StopSearch()


def was_cancelled() -> bool:
    with _guard:
        return bool(_token) and _token == _cancelled_token


def finish(token: str) -> None:
    global _token, _solver, _cancelled_token
    with _guard:
        if _token == token:
            _token = ""
            _solver = None
        if _cancelled_token == token:
            _cancelled_token = ""
