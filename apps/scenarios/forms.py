from django import forms

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


class VesselSettingsForm(forms.ModelForm):
    class Meta:
        model = VesselSettings
        exclude = ["scenario"]
        help_texts = {
            "max_foundations_per_trip": "Used to derive trip number and vessel position from the sequence.",
            "allow_partial_final_trip": "When off, the included count must fill every trip.",
            "base_maximum_trip_payload_t": "Optional reference only. Add a payload constraint to enforce a limit. No default is assumed.",
            "solver_time_limit_seconds": "Stops the solver after this many seconds (1–30). A feasible result is not labelled optimal unless OR-Tools proves it.",
            "transit_speed_knots": "Recorded for audit. MVP 1 does not calculate transit time.",
            "harbour_easting_m": "Leave blank unless a distance constraint should use harbour legs. No default harbour is assumed.",
            "harbour_northing_m": "Leave blank unless a distance constraint should use harbour legs.",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["max_foundations_per_trip"].min_value = 1
        self.fields["max_foundations_per_trip"].max_value = 20
        self.fields["solver_time_limit_seconds"].min_value = 1
        self.fields["solver_time_limit_seconds"].max_value = 30
        apply_bootstrap(self)

    def clean_max_foundations_per_trip(self):
        value = self.cleaned_data["max_foundations_per_trip"]
        if value < 1 or value > 20:
            raise forms.ValidationError("MVP 1 accepts 1 to 20 foundations per trip.")
        return value

    def clean_solver_time_limit_seconds(self):
        value = self.cleaned_data["solver_time_limit_seconds"]
        if value < 1 or value > 30:
            raise forms.ValidationError("Use a solver time limit from 1 to 30 seconds.")
        return value
