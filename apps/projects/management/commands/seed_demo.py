"""Create a local demonstration project. Refuses to run when DEBUG is off."""

from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from openpyxl import Workbook

from apps.constraints.models import Constraint
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-local-only"
DEMO_PROJECT = "Demo Foundation Project"
DEMO_SCENARIO = "Demonstration"


class Command(BaseCommand):
    help = "Load a synthetic local demonstration project. Not for production."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo is for local development only and will not run when DEBUG is off."
            )
        user = get_user_model().objects.filter(username=DEMO_USERNAME).first()
        if user is None:
            user = get_user_model().objects.create_user(
                username=DEMO_USERNAME,
                email="demo@example.com",
                password=DEMO_PASSWORD,
            )
        else:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
        Project.objects.filter(owner=user, name=DEMO_PROJECT).delete()
        project = Project.objects.create(
            owner=user,
            name=DEMO_PROJECT,
            description="Synthetic foundation campaign for local demonstration. It is not a real wind farm.",
            package_type=Project.PackageType.FOUNDATION,
        )
        version = create_dataset_version(
            project=project,
            user=user,
            filename="synthetic_foundations.xlsx",
            content=_workbook(),
        )
        if version.error_count:
            details = "; ".join(
                version.issues.filter(severity="error").values_list("message", flat=True)[:8]
            )
            raise CommandError(f"Demo workbook failed validation: {details}")
        activate_dataset(version)
        scenario = Scenario.objects.create(
            project=project,
            name=DEMO_SCENARIO,
            description="Synthetic hard and soft constraints entered as ordinary records. Sequencer did not recommend them.",
            dataset_version=version,
        )
        VesselSettings.objects.create(
            scenario=scenario,
            max_foundations_per_trip=4,
            allow_partial_final_trip=True,
            base_maximum_trip_payload_t="5000",
            solver_time_limit_seconds=20,
            harbour_easting_m="0",
            harbour_northing_m="0",
        )
        for order, payload in enumerate(_constraints(), start=1):
            Constraint.objects.create(scenario=scenario, display_order=order, **payload)
        self.stdout.write(
            self.style.SUCCESS(f"Demo user '{DEMO_USERNAME}' / project '{DEMO_PROJECT}' is ready.")
        )
        self.stdout.write("Local password: demo-local-only")


def _workbook() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Foundation_Input"
    headers = [
        "Foundation_ID",
        "Include",
        "Weight_t",
        "Delivery_Sequence",
        "Length_m",
        "Delivery_Batch",
        "Easting_m",
        "Northing_m",
        "Punch_Through",
        "Difficulty_Value",
        "Eccentricity_Limit_m",
        "Fixed_Trip",
        "Fixed_Position",
        "Earliest_Sequence",
        "Latest_Sequence",
        "Notes",
    ]
    worksheet.append(headers)
    for number in range(1, 13):
        worksheet.append(
            [
                f"F{number:02d}",
                "No" if number == 12 else "Yes",
                800 + number * 25,
                number,
                20 + number,
                1 if number <= 6 else 2,
                1000 + number * 150,
                2000 + (number % 3) * 80,
                "Yes" if number in {3, 8} else "No",
                number * 8,
                None,
                1 if number == 1 else None,
                1 if number == 2 else None,
                8 if number == 11 else None,
                6 if number == 4 else None,
                f"Synthetic foundation F{number:02d}",
            ]
        )
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _constraints() -> list[dict]:
    return [
        _hard("Payload limit", "maximum_trip_payload", {"maximum_payload_t": "5000"}),
        _hard(
            "Punch-through positions",
            "allowed_positions",
            {
                "attribute": "Punch_Through",
                "operator": "equals",
                "value": "Yes",
                "allowed_positions": [3, 4],
            },
        ),
        _hard(
            "Punch-through count",
            "maximum_matching_per_trip",
            {
                "attribute": "Punch_Through",
                "operator": "equals",
                "value": "Yes",
                "maximum_count": 2,
            },
        ),
        _hard("F01 on trip 1", "fixed_trip", {"foundation_id": "F01", "trip_number": 1}),
        _hard(
            "F02 in position 1",
            "fixed_vessel_position",
            {"foundation_id": "F02", "position_number": 1},
        ),
        _hard(
            "F11 not before sequence 8",
            "earliest_sequence",
            {"foundation_id": "F11", "earliest_sequence": 8},
        ),
        _hard(
            "F04 not after sequence 6",
            "latest_sequence",
            {"foundation_id": "F04", "latest_sequence": 6},
        ),
        _hard(
            "F01 before F06",
            "precedence",
            {
                "predecessor_foundation_id": "F01",
                "successor_foundation_id": "F06",
                "minimum_gap": 1,
            },
        ),
        _soft("Delivery alignment", "delivery_sequence_alignment", {"tolerance_positions": 2}, 50),
        _soft(
            "Easier foundations earlier",
            "difficulty_progression",
            {
                "attribute": "Difficulty_Value",
                "applicable_start_trip": 1,
                "applicable_end_trip": 3,
                "direction": "ascending",
            },
            60,
        ),
        _soft(
            "Shorter trips",
            "minimise_within_trip_distance",
            {"include_harbour_legs": True, "harbour_easting_m": "0", "harbour_northing_m": "0"},
            25,
        ),
        {
            "name": "Inactive same-trip example",
            "constraint_type": "same_trip",
            "description": "Stored inactive so it does not affect the solve until a user activates it.",
            "active": False,
            "enforcement": "soft",
            "severity": 10,
            "scope": "",
            "parameters_json": {"foundation_ids": ["F05", "F06"]},
        },
    ]


def _hard(name: str, constraint_type: str, parameters: dict) -> dict:
    return {
        "name": name,
        "constraint_type": constraint_type,
        "description": "Synthetic hard constraint for the local demo.",
        "active": True,
        "enforcement": "hard",
        "severity": None,
        "scope": "",
        "parameters_json": parameters,
    }


def _soft(name: str, constraint_type: str, parameters: dict, severity: int) -> dict:
    return {
        "name": name,
        "constraint_type": constraint_type,
        "description": "Synthetic soft preference for the local demo.",
        "active": True,
        "enforcement": "soft",
        "severity": severity,
        "scope": parameters.get("scope", ""),
        "parameters_json": parameters,
    }
