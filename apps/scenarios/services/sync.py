"""Copy workbook constraints and settings onto a scenario.

The dataset version stays unchanged. Activate and deactivate, and edited
setting values, live on the scenario. Choosing a different dataset version
loads that version's rows again.
"""

from __future__ import annotations

from decimal import Decimal

from apps.constraints.models import Constraint
from apps.datasets.services.catalogue import setting_key
from apps.scenarios.models import Scenario


def sync_scenario_from_dataset(scenario: Scenario) -> None:
    dataset = scenario.dataset_version
    if dataset is None:
        return
    scenario.constraints.all().delete()
    Constraint.objects.bulk_create(
        [
            Constraint(
                scenario=scenario,
                name=item.name,
                constraint_type=item.constraint_type,
                description=item.explanation,
                active=item.active,
                enforcement=item.enforcement,
                severity=item.severity,
                scope=item.package,
                parameters_json=item.parameters_json,
                display_order=item.display_order,
            )
            for item in dataset.constraint_rows.all()
        ]
    )
    values = {item.name: item.value for item in dataset.setting_rows.all()}
    settings = scenario.vessel_settings
    settings.workbook_values = values
    for name, raw in values.items():
        if setting_key(name) == "mp_per_trip":
            settings.max_foundations_per_trip = int(Decimal(raw))
    settings.save()
