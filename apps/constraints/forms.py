"""Controlled constraint form. Values are literals, never formulas or code."""

from __future__ import annotations

from django import forms

from apps.constraints.library import CONSTRAINT_TYPES
from apps.constraints.services.matching import OPERATORS, ORDERING_ATTRIBUTES
from apps.constraints.services.parameters import validate_parameters
from apps.optimisation.services.types import FoundationInput, VesselConfig
from apps.ui import apply_bootstrap


class ConstraintForm(forms.Form):
    name = forms.CharField(max_length=200)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    enforcement = forms.ChoiceField(
        choices=[("hard", "Hard — must be satisfied"), ("soft", "Soft — preference with severity")]
    )
    severity = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        help_text="Required for a soft constraint. Ignored and stored blank for a hard constraint.",
    )
    active = forms.BooleanField(required=False, initial=True)

    def __init__(
        self,
        *,
        constraint_type: str,
        foundation_ids: list[str],
        columns: list[str],
        foundations: list[FoundationInput],
        vessel: VesselConfig,
        columns_present: set[str],
        initial_parameters: dict | None = None,
        **kwargs,
    ) -> None:
        self.constraint_type = constraint_type
        self.foundations = foundations
        self.vessel = vessel
        self.columns_present = columns_present
        parameters = initial_parameters or {}
        initial = dict(kwargs.get("initial") or {})
        initial.update(_initial_parameters(constraint_type, parameters))
        kwargs["initial"] = initial
        super().__init__(**kwargs)
        self._add_type_fields(foundation_ids, columns, vessel.max_foundations_per_trip)
        apply_bootstrap(self)

    def _add_type_fields(
        self, foundation_ids: list[str], columns: list[str], capacity: int
    ) -> None:
        foundation_choices = [(item, item) for item in foundation_ids]
        column_choices = [(item, item) for item in columns]
        numeric_choices = [(item, item) for item in columns if item in ORDERING_ATTRIBUTES]
        position_choices = [(str(number), str(number)) for number in range(1, capacity + 1)]
        kind = self.constraint_type
        if kind == "maximum_trip_payload":
            self.fields["maximum_payload_t"] = forms.DecimalField(
                min_value=0.001,
                decimal_places=3,
                help_text="Tonnes. This value is required. The scenario base payload is not applied for you.",
            )
        if kind in {"fixed_trip", "fixed_vessel_position", "precedence"} or kind in {
            "earliest_sequence",
            "latest_sequence",
        }:
            self.fields["foundation_id"] = forms.ChoiceField(
                choices=foundation_choices,
                required=kind in {"fixed_trip", "fixed_vessel_position"},
                label="Foundation",
            )
        if kind == "precedence":
            self.fields["predecessor_foundation_id"] = forms.ChoiceField(
                choices=foundation_choices, label="Predecessor"
            )
            self.fields["successor_foundation_id"] = forms.ChoiceField(
                choices=foundation_choices, label="Successor"
            )
            self.fields["minimum_gap"] = forms.IntegerField(min_value=1, initial=1)
            self.fields["maximum_gap"] = forms.IntegerField(required=False, min_value=1)
        if kind in {"fixed_trip", "fixed_vessel_position"}:
            self.fields["trip_number"] = forms.IntegerField(
                required=kind == "fixed_trip",
                min_value=1,
                help_text="Leave blank on a fixed position when the position applies in whichever trip contains the foundation.",
            )
        if kind == "fixed_vessel_position":
            self.fields["position_number"] = forms.IntegerField(min_value=1, max_value=capacity)
        if kind in {
            "allowed_positions",
            "excluded_positions",
            "maximum_matching_per_trip",
            "minimum_matching_per_trip",
            "earliest_sequence",
            "latest_sequence",
            "attribute_ordering",
            "difficulty_progression",
        }:
            choices = (
                numeric_choices
                if kind in {"attribute_ordering", "difficulty_progression"}
                else column_choices
            )
            self.fields["attribute"] = forms.ChoiceField(
                choices=choices, required=kind not in {"earliest_sequence", "latest_sequence"}
            )
            if kind != "attribute_ordering" and kind != "difficulty_progression":
                self.fields["operator"] = forms.ChoiceField(
                    choices=[(item, item) for item in OPERATORS], required=False
                )
                self.fields["value"] = forms.CharField(
                    required=False,
                    help_text="Literal comparison value. For in_list and not_in_list, separate values with commas. Do not enter a formula.",
                )
                self.fields["value_to"] = forms.CharField(
                    required=False,
                    label="Upper value",
                    help_text="Used only when the operator is between.",
                )
        if kind in {"earliest_sequence", "latest_sequence"}:
            self.fields["selector"] = forms.ChoiceField(
                choices=[
                    ("foundation", "One foundation"),
                    ("attribute", "Foundations matching an attribute rule"),
                ],
                initial="foundation",
            )
            self.fields["bound_kind"] = forms.ChoiceField(
                choices=[("sequence", "Sequence position"), ("trip", "Trip number")],
                initial="sequence",
            )
            self.fields["bound_value"] = forms.IntegerField(min_value=1)
        if kind == "allowed_positions":
            self.fields["allowed_positions"] = forms.MultipleChoiceField(choices=position_choices)
        if kind == "excluded_positions":
            self.fields["excluded_positions"] = forms.MultipleChoiceField(choices=position_choices)
        if kind == "maximum_matching_per_trip":
            self.fields["maximum_count"] = forms.IntegerField(min_value=0)
        if kind == "minimum_matching_per_trip":
            self.fields["minimum_count"] = forms.IntegerField(min_value=1)
            self.fields["applicable_trips"] = forms.CharField(
                required=False,
                help_text="Optional trip numbers, separated by commas. Leave blank to apply the rule to every trip.",
            )
        if kind in {"same_trip", "separate_trip"}:
            self.fields["foundation_ids"] = forms.MultipleChoiceField(
                choices=foundation_choices, label="Foundations"
            )
        if kind in {"attribute_ordering", "difficulty_progression"}:
            self.fields["direction"] = forms.ChoiceField(
                choices=[("ascending", "Ascending"), ("descending", "Descending")]
            )
        if kind == "attribute_ordering":
            self.fields["scope"] = forms.ChoiceField(
                choices=[("full_sequence", "Full sequence"), ("within_trip", "Within each trip")]
            )
        if kind == "delivery_sequence_alignment":
            self.fields["tolerance_positions"] = forms.IntegerField(min_value=0, initial=0)
        if kind == "difficulty_progression":
            self.fields["applicable_start_trip"] = forms.IntegerField(min_value=1, initial=1)
            self.fields["applicable_end_trip"] = forms.IntegerField(min_value=1, initial=1)
        if kind == "minimise_within_trip_distance":
            self.fields["include_harbour_legs"] = forms.BooleanField(required=False)
            self.fields["harbour_easting_m"] = forms.DecimalField(
                required=False, decimal_places=3, max_digits=16
            )
            self.fields["harbour_northing_m"] = forms.DecimalField(
                required=False, decimal_places=3, max_digits=16
            )

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        if cleaned.get("enforcement") == "soft" and cleaned.get("severity") is None:
            self.add_error("severity", "Soft constraints require a severity from 1 to 100.")
        if cleaned.get("enforcement") == "hard":
            cleaned["severity"] = None
        if self.errors:
            return cleaned
        try:
            parameters = self.build_parameters(cleaned)
        except forms.ValidationError as exc:
            self.add_error(None, exc)
            return cleaned
        for message in validate_parameters(
            self.constraint_type,
            parameters,
            foundations=self.foundations,
            vessel=self.vessel,
            columns_present=self.columns_present,
        ):
            self.add_error(None, message)
        cleaned["parameters"] = parameters
        cleaned["scope"] = str(parameters.get("scope") or "")
        return cleaned

    def build_parameters(self, cleaned: dict) -> dict:
        kind = self.constraint_type
        if kind == "maximum_trip_payload":
            return {"maximum_payload_t": format(cleaned["maximum_payload_t"], "f")}
        if kind == "fixed_trip":
            return {
                "foundation_id": cleaned["foundation_id"],
                "trip_number": cleaned["trip_number"],
            }
        if kind == "fixed_vessel_position":
            parameters = {
                "foundation_id": cleaned["foundation_id"],
                "position_number": cleaned["position_number"],
            }
            if cleaned.get("trip_number"):
                parameters["trip_number"] = cleaned["trip_number"]
            return parameters
        if kind in {
            "allowed_positions",
            "excluded_positions",
            "maximum_matching_per_trip",
            "minimum_matching_per_trip",
        }:
            parameters = self._rule(cleaned)
            if kind == "allowed_positions":
                parameters["allowed_positions"] = [
                    int(item) for item in cleaned["allowed_positions"]
                ]
            elif kind == "excluded_positions":
                parameters["excluded_positions"] = [
                    int(item) for item in cleaned["excluded_positions"]
                ]
            elif kind == "maximum_matching_per_trip":
                parameters["maximum_count"] = cleaned["maximum_count"]
            else:
                parameters["minimum_count"] = cleaned["minimum_count"]
                trips = _split_ints(cleaned.get("applicable_trips") or "")
                if trips:
                    parameters["applicable_trips"] = trips
            return parameters
        if kind in {"earliest_sequence", "latest_sequence"}:
            parameters: dict = {}
            if cleaned.get("selector") == "attribute":
                parameters.update(self._rule(cleaned))
            else:
                if not cleaned.get("foundation_id"):
                    raise forms.ValidationError("Select a foundation.")
                parameters["foundation_id"] = cleaned["foundation_id"]
            sequence_key = "earliest_sequence" if kind == "earliest_sequence" else "latest_sequence"
            trip_key = "earliest_trip" if kind == "earliest_sequence" else "latest_trip"
            if cleaned.get("bound_kind") == "trip":
                parameters[trip_key] = cleaned["bound_value"]
            else:
                parameters[sequence_key] = cleaned["bound_value"]
            return parameters
        if kind == "precedence":
            parameters = {
                "predecessor_foundation_id": cleaned["predecessor_foundation_id"],
                "successor_foundation_id": cleaned["successor_foundation_id"],
                "minimum_gap": cleaned["minimum_gap"],
            }
            if cleaned.get("maximum_gap"):
                parameters["maximum_gap"] = cleaned["maximum_gap"]
            return parameters
        if kind in {"same_trip", "separate_trip"}:
            return {"foundation_ids": list(cleaned["foundation_ids"])}
        if kind == "attribute_ordering":
            return {
                "attribute": cleaned["attribute"],
                "direction": cleaned["direction"],
                "scope": cleaned["scope"],
            }
        if kind == "delivery_sequence_alignment":
            return {"tolerance_positions": cleaned["tolerance_positions"]}
        if kind == "difficulty_progression":
            return {
                "attribute": cleaned["attribute"],
                "applicable_start_trip": cleaned["applicable_start_trip"],
                "applicable_end_trip": cleaned["applicable_end_trip"],
                "direction": cleaned["direction"],
            }
        if kind == "minimise_within_trip_distance":
            parameters = {"include_harbour_legs": bool(cleaned.get("include_harbour_legs"))}
            if cleaned.get("harbour_easting_m") is not None:
                parameters["harbour_easting_m"] = format(cleaned["harbour_easting_m"], "f")
            if cleaned.get("harbour_northing_m") is not None:
                parameters["harbour_northing_m"] = format(cleaned["harbour_northing_m"], "f")
            return parameters
        raise forms.ValidationError("This constraint type is not supported.")

    def _rule(self, cleaned: dict) -> dict:
        operator = cleaned.get("operator")
        if not operator:
            raise forms.ValidationError("Select an operator.")
        parameters = {"attribute": cleaned.get("attribute"), "operator": operator}
        if operator in {"is_blank", "is_not_blank"}:
            return parameters
        if operator == "between":
            if not cleaned.get("value") or not cleaned.get("value_to"):
                raise forms.ValidationError("Between requires two numeric bounds.")
            parameters["value"] = cleaned["value"].strip()
            parameters["value_to"] = cleaned["value_to"].strip()
            return parameters
        if operator in {"in_list", "not_in_list"}:
            values = [
                part.strip() for part in (cleaned.get("value") or "").split(",") if part.strip()
            ]
            if not values:
                raise forms.ValidationError("Enter at least one literal list value.")
            parameters["value"] = values
            return parameters
        if not (cleaned.get("value") or "").strip():
            raise forms.ValidationError("Enter a literal comparison value.")
        parameters["value"] = cleaned["value"].strip()
        return parameters


def _split_ints(value: str) -> list[int]:
    if not value.strip():
        return []
    numbers = []
    for part in value.split(","):
        part = part.strip()
        if not part.isdigit():
            raise forms.ValidationError(
                "Applicable trips must be positive integers separated by commas."
            )
        numbers.append(int(part))
    return numbers


def _initial_parameters(constraint_type: str, parameters: dict) -> dict:
    initial = {}
    if not parameters:
        return initial
    for key in (
        "maximum_payload_t",
        "foundation_id",
        "trip_number",
        "position_number",
        "attribute",
        "operator",
        "minimum_gap",
        "maximum_gap",
        "maximum_count",
        "minimum_count",
        "direction",
        "scope",
        "tolerance_positions",
        "applicable_start_trip",
        "applicable_end_trip",
        "include_harbour_legs",
        "harbour_easting_m",
        "harbour_northing_m",
        "predecessor_foundation_id",
        "successor_foundation_id",
    ):
        if parameters.get(key) not in (None, ""):
            initial[key] = parameters[key]
    if isinstance(parameters.get("value"), list):
        initial["value"] = ", ".join(str(item) for item in parameters["value"])
    elif parameters.get("value") not in (None, ""):
        initial["value"] = parameters["value"]
    if parameters.get("value_to") not in (None, ""):
        initial["value_to"] = parameters["value_to"]
    if parameters.get("allowed_positions"):
        initial["allowed_positions"] = [str(item) for item in parameters["allowed_positions"]]
    if parameters.get("excluded_positions"):
        initial["excluded_positions"] = [str(item) for item in parameters["excluded_positions"]]
    if parameters.get("foundation_ids"):
        initial["foundation_ids"] = [str(item) for item in parameters["foundation_ids"]]
    if parameters.get("applicable_trips"):
        initial["applicable_trips"] = ", ".join(
            str(item) for item in parameters["applicable_trips"]
        )
    if constraint_type in {"earliest_sequence", "latest_sequence"}:
        initial["selector"] = "attribute" if parameters.get("attribute") else "foundation"
        sequence_key = (
            "earliest_sequence" if constraint_type == "earliest_sequence" else "latest_sequence"
        )
        trip_key = "earliest_trip" if constraint_type == "earliest_sequence" else "latest_trip"
        if parameters.get(trip_key):
            initial["bound_kind"] = "trip"
            initial["bound_value"] = parameters[trip_key]
        else:
            initial["bound_kind"] = "sequence"
            initial["bound_value"] = parameters.get(sequence_key)
    if constraint_type not in CONSTRAINT_TYPES:
        return initial
    return initial
