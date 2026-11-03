"""Switch the one Render web service between Free and the 2 GB plan.

The live tier comes from the instance that is serving this process. The
switch writes the web service plan in render.yaml and pushes that file.
A Blueprint sync applies the plan. A service auto-deploy does not. A run
that finishes on the 2 GB instance writes the free plan back.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.db import connection

from apps.optimisation.models import RenderPlanState
from apps.optimisation.services.memory_cap import exceeds_free_instance

PAID_PLAN = "1c-2g"
FREE_PLAN = "free"
_PLAN_UNCHANGED = (
    "Render deployed the commit and left the service on the Free plan. "
    "The Blueprint sync did not change the plan."
)
_GITHUB = "https://api.github.com"
_WEB_PLAN = re.compile(
    r"(?m)^([ \t]*# sequencer-web-plan\n[ \t]*plan:[ \t]*)(\S+)[ \t]*$"
)


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
    if (
        tier == "free"
        and state.desired == PAID_PLAN
        and _deployed_web_plan() == PAID_PLAN
    ):
        _save(FREE_PLAN, _PLAN_UNCHANGED)
        state = _state()
    return {
        "tier": tier,
        "switching": state.desired == PAID_PLAN and tier == "free",
        "returning": state.desired == FREE_PLAN and tier == "paid",
        "configured": _configured() or tier == "local",
        "error": state.error,
    }


def request_paid_plan() -> None:
    """Ask the Blueprint to deploy this service on 1c-2g."""
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


def _deployed_web_plan() -> str | None:
    path = Path(__file__).resolve().parents[3] / "render.yaml"
    try:
        text = path.read_text()
    except OSError:
        return None
    match = _WEB_PLAN.search(text)
    if match is None:
        return None
    return match.group(2)


def set_web_plan(text: str, plan: str) -> str:
    """Return render.yaml with the web service plan set. The database plan stays."""

    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{plan}"

    updated, count = _WEB_PLAN.subn(replace, text, count=1)
    if count != 1:
        raise RenderPlanError("The web service plan line was not found in render.yaml.")
    return updated


def _switch(plan: str) -> None:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RenderPlanError("Set GITHUB_TOKEN on the Render service, then try again.")
    if plan not in {FREE_PLAN, PAID_PLAN}:
        raise RenderPlanError("The plan change was not recognised.")
    repo = os.environ.get("GITHUB_REPOSITORY", "dimigoescoding/Sequencer").strip()
    branch = os.environ.get("GITHUB_BRANCH", "main").strip() or "main"
    for attempt in range(2):
        payload = _github(
            "GET",
            f"{_file_url(repo)}?ref={urllib.parse.quote(branch)}",
            token,
        )
        try:
            text = base64.b64decode(payload["content"]).decode()
            sha = payload["sha"]
        except (KeyError, ValueError) as exc:
            raise RenderPlanError("GitHub did not return render.yaml.") from exc
        updated = set_web_plan(text, plan)
        if updated == text:
            return
        body = {
            "message": _commit_message(plan),
            "content": base64.b64encode(updated.encode()).decode(),
            "sha": sha,
            "branch": branch,
        }
        try:
            _github("PUT", _file_url(repo), token, body)
            return
        except RenderPlanError as exc:
            if "(409)" not in str(exc) or attempt == 1:
                raise


def _commit_message(plan: str) -> str:
    if plan == PAID_PLAN:
        return "Move the sequencer web service to 1c-2g for one run."
    return "Return the sequencer web service to the free plan."


def _file_url(repo: str) -> str:
    return f"{_GITHUB}/repos/{repo}/contents/render.yaml"


def _github(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "sequencer",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise RenderPlanError(
                "GitHub refused the plan change. Use a token that can write render.yaml in this repository."
            ) from exc
        detail = exc.read().decode(errors="replace").strip().replace("\n", " ")[:180]
        raise RenderPlanError(f"GitHub did not update render.yaml ({exc.code}). {detail}") from exc
    except urllib.error.URLError as exc:
        raise RenderPlanError("GitHub could not be reached.") from exc
    if not raw:
        return {}
    return json.loads(raw)


def _configured() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN", "").strip())


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
