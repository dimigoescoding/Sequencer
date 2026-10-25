"""Keep scenario constraints and trip settings when the dataset changes.

Constraints, FOU per trip, and WTG per trip are edited in the app. Uploading
another workbook does not delete them or copy values out of the file.
"""

from __future__ import annotations

from apps.scenarios.models import Scenario


def sync_scenario_from_dataset(scenario: Scenario) -> None:
    return
