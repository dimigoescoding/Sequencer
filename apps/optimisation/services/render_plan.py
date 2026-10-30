"""Switch the one Render web service between Free and the 2 GB plan.

The live tier comes from the instance that is serving this process. Asking
Render for 1c-2g does not add memory until that deploy is up. A run that
finishes on the 2 GB instance asks Render to return to Free.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request

from django.db import connection

from apps.optimisation.models import RenderPlanState
from apps.optimisation.services.memory_cap import exceeds_free_instance

PAID_PLAN = "1c-2g"
FREE_PLAN = "free"
_API = "https://api.render.com/v1"


class RenderPlanError(Exception):
    """Render did not accept the plan change."""


def live_tier() -> str:
    """free, paid, or local. Local means this process is not the Render service."""
    if not _on_render():
        return "local"
    if exceeds_free_instance():
        return "paid"
    return "free"


def plan_status() -> dict:
    tier = live_tier()
    state = _state()
    return {
        "tier": tier,
        "switching": state.desired == PAID_PLAN and tier == "free",
        "returning": state.desired == FREE_PLAN and tier == "paid",
        "configured": _configured() or tier == "local",
        "error": state.error,
    }


def request_paid_plan() -> None:
    """Ask Render to deploy this service on 1c-2g."""
    if not _on_render():
        raise RenderPlanError("Memory upgrade is available on the Render service.")
    if live_tier() == "paid":
        _save(PAID_PLAN, "")
        return
    _save(PAID_PLAN, "")
    try:
        _switch(PAID_PLAN)
    except RenderPlanError as exc:
        _save(FREE_PLAN, str(exc))
        raise


def schedule_return_to_free() -> None:
    """After a stored run on the paid instance, deploy Free again."""
    try:
        if live_tier() != "paid":
            return
        _save(FREE_PLAN, "")
    except Exception:
        return
    threading.Thread(target=_return_worker, daemon=True).start()


def _return_worker() -> None:
    try:
        _switch(FREE_PLAN)
    except RenderPlanError as exc:
        _save(FREE_PLAN, str(exc))
    finally:
        connection.close()


def _switch(plan: str) -> None:
    key = os.environ.get("RENDER_API_KEY", "").strip()
    service_id = os.environ.get("RENDER_SERVICE_ID", "").strip()
    if not key:
        raise RenderPlanError("Set RENDER_API_KEY on the Render service, then try again.")
    if not service_id:
        raise RenderPlanError("RENDER_SERVICE_ID is not set on this service.")
    _send(
        "PATCH",
        f"{_API}/services/{service_id}",
        key,
        {"serviceDetails": {"plan": plan}},
    )
    try:
        _send(
            "POST",
            f"{_API}/services/{service_id}/deploys",
            key,
            {"deployMode": "deploy_only"},
        )
    except RenderPlanError as exc:
        if "(400)" not in str(exc):
            raise
        _send("POST", f"{_API}/services/{service_id}/deploys", key, {})


def _send(method: str, url: str, key: str, body: dict) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip().replace("\n", " ")[:180]
        raise RenderPlanError(f"Render did not change the plan ({exc.code}). {detail}") from exc
    except urllib.error.URLError as exc:
        raise RenderPlanError("Render could not be reached.") from exc


def _configured() -> bool:
    return bool(os.environ.get("RENDER_API_KEY", "").strip()) and bool(
        os.environ.get("RENDER_SERVICE_ID", "").strip()
    )


def _on_render() -> bool:
    return os.environ.get("RENDER", "").lower() == "true" or bool(
        os.environ.get("RENDER_SERVICE_ID", "").strip()
    )


def _state() -> RenderPlanState:
    row, _created = RenderPlanState.objects.get_or_create(pk=1, defaults={"desired": FREE_PLAN})
    return row


def _save(desired: str, error: str) -> None:
    row = _state()
    row.desired = desired
    row.error = error
    row.save(update_fields=["desired", "error"])
