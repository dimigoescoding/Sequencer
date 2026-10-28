from django import forms
from django.db.models import Q

from apps.scenarios.models import Scenario, VesselSettings
from apps.ui import apply_bootstrap


class ScenarioForm(forms.ModelForm):
    class Meta:
        model = Scenario
        fields = ["name", "description", "dataset_version"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, project, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["dataset_version"].queryset = project.dataset_versions.filter(error_count=0)
        self.fields["dataset_version"].required = False
        self.fields[
            "dataset_version"
        ].help_text = "Optimisation uses this version even if you later activate another dataset."
        apply_bootstrap(self)


class ScenarioDatasetForm(forms.ModelForm):
    class Meta:
        model = Scenario
        fields = ["dataset_version"]

    def __init__(self, project, scenario, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        current_id = scenario.dataset_version_id or 0
        self.fields["dataset_version"].queryset = project.dataset_versions.filter(
            Q(error_count=0) | Q(pk=current_id)
        )
        self.fields["dataset_version"].required = False
        self.fields["dataset_version"].label = "Dataset"
        self.fields["dataset_version"].help_text = (
            "Optimisation uses this version even if another dataset is active on the project."
        )
        self.fields["dataset_version"].label_from_instance = _dataset_label
        apply_bootstrap(self)


def _dataset_label(version) -> str:
    active = " · active" if version.is_active else ""
    return f"Version {version.version_number} · {version.included_count} included{active}"


class VesselSettingsForm(forms.ModelForm):
    class Meta:
        model = VesselSettings
        exclude = ["scenario"]
        help_texts = {
            "max_foundations_per_trip": "Used to derive trip number and vessel position from the sequence.",
            "allow_partial_final_trip": "When off, the included count must fill every trip.",
            "base_maximum_trip_payload_t": "Optional reference only. Add a payload constraint to enforce a limit. No default is assumed.",
            "solver_time_limit_seconds": "Stops the solver after this many seconds (1–600). A feasible result is not labelled optimal unless OR-Tools proves it.",
            "transit_speed_knots": "Recorded for audit. MVP 1 does not calculate transit time.",
            "harbour_easting_m": "Stored with the scenario. Harbour transit is not part of the sailing-distance objective.",
            "harbour_northing_m": "Stored with the scenario. Harbour transit is not part of the sailing-distance objective.",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["max_foundations_per_trip"].label = "FOU per trip"
        self.fields["wtg_per_trip"].label = "WTG per trip"
        self.fields["max_foundations_per_trip"].min_value = 1
        self.fields["max_foundations_per_trip"].max_value = 20
        self.fields["wtg_per_trip"].min_value = 1
        self.fields["wtg_per_trip"].max_value = 20
        self.fields["solver_time_limit_seconds"].min_value = 1
        self.fields["solver_time_limit_seconds"].max_value = 600
        apply_bootstrap(self)

    def clean_max_foundations_per_trip(self):
        return _trip_capacity(self.cleaned_data["max_foundations_per_trip"], "FOU per trip")

    def clean_wtg_per_trip(self):
        return _trip_capacity(self.cleaned_data["wtg_per_trip"], "WTG per trip")

    def clean_solver_time_limit_seconds(self):
        return _solver_time(self.cleaned_data["solver_time_limit_seconds"])


class ProgrammeSettingsForm(forms.ModelForm):
    """FOU per trip, WTG per trip, and the shared solver time limit."""

    class Meta:
        model = VesselSettings
        fields = ["max_foundations_per_trip", "wtg_per_trip", "solver_time_limit_seconds"]
        labels = {
            "max_foundations_per_trip": "FOU per trip",
            "wtg_per_trip": "WTG per trip",
            "solver_time_limit_seconds": "Solver time (seconds)",
        }
        help_texts = {
            "max_foundations_per_trip": "Used only for FOU. Trip number and vessel position for foundations come from this capacity.",
            "wtg_per_trip": "Used only for WTG. IAC is ordered without a trip limit.",
            "solver_time_limit_seconds": "How long the one programme solve may run, from 1 to 600 seconds. The page waits until the run finishes.",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["max_foundations_per_trip"].min_value = 1
        self.fields["max_foundations_per_trip"].max_value = 20
        self.fields["wtg_per_trip"].min_value = 1
        self.fields["wtg_per_trip"].max_value = 20
        self.fields["solver_time_limit_seconds"].min_value = 1
        self.fields["solver_time_limit_seconds"].max_value = 600
        apply_bootstrap(self)

    def clean_max_foundations_per_trip(self):
        return _trip_capacity(self.cleaned_data["max_foundations_per_trip"], "FOU per trip")

    def clean_wtg_per_trip(self):
        return _trip_capacity(self.cleaned_data["wtg_per_trip"], "WTG per trip")

    def clean_solver_time_limit_seconds(self):
        return _solver_time(self.cleaned_data["solver_time_limit_seconds"])


def _trip_capacity(value: int, label: str) -> int:
    if value < 1 or value > 20:
        raise forms.ValidationError(f"{label} must be a whole number from 1 to 20.")
    return value


def _solver_time(value: int) -> int:
    if value < 1 or value > 600:
        raise forms.ValidationError("Use a solver time limit from 1 to 600 seconds.")
    return value
