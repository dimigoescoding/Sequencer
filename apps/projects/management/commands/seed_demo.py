"""Create a local demonstration project. Refuses to run when DEBUG is off."""

from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from openpyxl import Workbook

from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from apps.scenarios.services.sync import sync_scenario_from_dataset

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
            description="Constraints and settings loaded from the synthetic workbook.",
            dataset_version=version,
        )
        VesselSettings.objects.create(scenario=scenario, solver_time_limit_seconds=20)
        sync_scenario_from_dataset(scenario)
        self.stdout.write(
            self.style.SUCCESS(f"Demo user '{DEMO_USERNAME}' / project '{DEMO_PROJECT}' is ready.")
        )
        self.stdout.write("Local password: demo-local-only")


def _workbook() -> bytes:
    workbook = Workbook()
    information = workbook.active
    information.title = "Information"
    information.append(
        [
            "WTG ID",
            "Structure",
            "Easting",
            "Northing",
            "Aver. Weight[t]",
            "Spider location",
            "Shallow location",
            "String",
            "Jacking difficulty",
            "Location",
        ]
    )
    rows = [
        ("S1", 0, 0, 500, "YES", "NO", "Easy", 1),
        ("S2", 100, 0, 520, "YES", "NO", "Easy", 2),
        ("A1", 0, 100, 480, "NO", "YES", "Easy", 3),
        ("A2", 100, 100, 490, "NO", "NO", "Difficult", 4),
        ("B1", 0, 200, 470, "NO", "YES", "Easy", 5),
        ("B2", 100, 200, 460, "NO", "NO", "Easy", 6),
        ("C1", 0, 300, 450, "NO", "NO", "Easy", 7),
        ("C2", 100, 300, 440, "NO", "NO", "Difficult", 8),
    ]
    for wtg, easting, northing, weight, spider, shallow, difficulty, location in rows:
        information.append(
            [wtg, "WTG", easting, northing, weight, spider, shallow, "S1", difficulty, location]
        )
    constraints = workbook.create_sheet("Constraints")
    constraints.append(["Package", "Name", "Explanation", "Type", "Severity", "Status"])
    constraints.append(
        [
            "FOU",
            "Spider locations FOU",
            "Spider locations should be installed first, but in no particular order.",
            "Hard",
            "NA",
            "Active",
        ]
    )
    constraints.append(
        [
            "FOU",
            "Shallow locations",
            "Only one shallow location per trip allowed",
            "Hard",
            "NA",
            "Active",
        ]
    )
    constraints.append(
        [
            "FOU",
            "Infield sailing optimization FOU",
            "Optimizes the infield sailing time within the trip from the given coordinates.",
            "Soft",
            0.5,
            "Active",
        ]
    )
    constraints.append(
        [
            "FOU",
            "Jacking difficulty",
            "Avoid difficult locations in the first 3 trips",
            "Soft",
            0.5,
            "Not active",
        ]
    )
    settings = workbook.create_sheet("Settings")
    settings.append(["Setting", "Number"])
    settings.append(["MP per trip", 4])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
