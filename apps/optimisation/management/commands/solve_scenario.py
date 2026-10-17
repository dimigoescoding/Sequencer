"""Solve one scenario from the command line and optionally write its workbook."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.exports.services.workbook import build_run_workbook
from apps.optimisation.services.runner import SolveBlocked, execute
from apps.scenarios.models import Scenario


class Command(BaseCommand):
    help = "Run optimisation for one scenario owned by the named user."

    def add_arguments(self, parser):
        parser.add_argument("--project", required=True)
        parser.add_argument("--scenario", required=True)
        parser.add_argument("--username", default="")
        parser.add_argument("--export", default="")

    def handle(self, *args, **options):
        scenarios = Scenario.objects.select_related("project", "project__owner").filter(
            project__name=options["project"],
            name=options["scenario"],
        )
        if options["username"]:
            scenarios = scenarios.filter(project__owner__username=options["username"])
        scenario = scenarios.first()
        if scenario is None:
            raise CommandError("Scenario was not found for that project.")
        if scenarios.count() > 1 and not options["username"]:
            raise CommandError("More than one matching scenario. Pass --username.")
        try:
            run = execute(scenario)
        except SolveBlocked as exc:
            raise CommandError(
                "Blocked before the solver:\n- " + "\n- ".join(exc.conflicts)
            ) from exc
        self.stdout.write(
            f"Run {run.pk} status={run.status} solver={run.solver_status} validation={run.validation_status}"
        )
        if options["export"]:
            path = Path(options["export"])
            path.write_bytes(build_run_workbook(run))
            self.stdout.write(f"Exported {path}")
