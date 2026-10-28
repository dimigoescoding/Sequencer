"""Controlled constraint form. Values are literals, never formulas or code."""

from __future__ import annotations

from django import forms

from apps.constraints.library import CONSTRAINT_TYPES
from apps.constraints.services.matching import OPERATORS, ORDERING_ATTRIBUTES
from apps.constraints.services.parameters import validate_parameters
from apps.optimisation.services.types import FoundationInput, VesselConfig
from apps.ui import apply_bootstrap

PACKAGE_CHOICES = [("FOU", "FOU"), ("IAC", "IAC"), ("WTG", "WTG")]


class ConstraintForm(forms.Form):
    package = forms.ChoiceField(
        choices=PACKAGE_CHOICES,
        initial="FOU",
        required=False,
        label="Package",
        help_text="FOU, IAC, or WTG. The rule is applied only to that package inside the one programme.",
    )
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
        if self.constraint_type == "loop_id_sequence":
            self.fields["package"].choices = [("IAC", "IAC")]
            self.fields["package"].initial = "IAC"
            self.fields["package"].required = True
            self.fields["package"].help_text = "Loop ID is read from the IAC sheet."
        if self.constraint_type == "package_buffer":
            self.fields["package"].choices = [("IAC", "IAC"), ("WTG", "WTG")]
            self.fields["package"].initial = "IAC"
            self.fields["package"].required = True
            self.fields["package"].help_text = "IAC waits for FOU. WTG waits for IAC."
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
        if kind in {"fixed_trip", "fixed_vessel_position", "precedence", "latest_sequence"}:
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
            "latest_sequence",
            "attribute_ordering",
            "difficulty_progression",
            "matching_installed_first",
            "avoid_matching_in_first_trips",
        }:
            choices = (
                numeric_choices
                if kind in {"attribute_ordering", "difficulty_progression"}
                else column_choices
            )
            self.fields["attribute"] = forms.ChoiceField(
                choices=choices, required=kind != "latest_sequence"
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
        if kind == "latest_sequence":
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
        if kind == "earliest_sequence":
            self.fields["selector"] = forms.ChoiceField(
                label="Applies to",
                choices=[
                    ("foundation", "One location"),
                    ("attribute", "Locations with an attribute"),
                ],
                initial="attribute",
                help_text="Only the selected choice is saved.",
            )
            self.fields["foundation_id"] = forms.ChoiceField(
                choices=[("", "Select a location")] + foundation_choices,
                required=False,
                label="Location",
            )
            self.fields["attribute"] = forms.ChoiceField(
                choices=[("", "Select an attribute")] + column_choices,
                required=False,
                label="Attribute",
            )
            self.fields["operator"] = forms.ChoiceField(
                choices=[("", "Select an operator")] + [(item, item) for item in OPERATORS],
                required=False,
            )
            self.fields["value"] = forms.CharField(
                required=False,
                help_text=(
                    "Literal comparison value. For a Yes/No column such as Shallow location, "
                    "enter YES."
                ),
            )
            self.fields["value_to"] = forms.CharField(
                required=False,
                label="Upper value",
                help_text="Used only when the operator is between.",
            )
            self.fields["earliest_trip"] = forms.IntegerField(
                min_value=1,
                label="Earliest trip",
                help_text=(
                    "The first trip these locations may be installed. "
                    "Enter 2 to keep them out of the first trip."
                ),
            )
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
        if kind == "avoid_matching_in_first_trips":
            self.fields["trip_count"] = forms.IntegerField(
                min_value=1,
                initial=1,
                help_text="Matching locations are kept out of this many trips at the start of the sequence.",
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
        if kind == "package_buffer":
            self.fields["mode"] = forms.ChoiceField(
                choices=[("minimum", "Minimum days"), ("maximize", "Maximize")],
                label="Buffer",
                help_text=(
                    "Minimum keeps at least this many days between the previous package's end "
                    "and this package's start. Maximize makes the smallest location gap as large "
                    "as the programme dates allow, and does not take a day limit."
                ),
            )
            self.fields["minimum_days"] = forms.IntegerField(
                required=False,
                min_value=0,
                label="Minimum days",
                help_text="Whole days of 24 hours. Used only when the buffer is a minimum.",
            )

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        if cleaned.get("enforcement") == "soft" and cleaned.get("severity") is None:
            self.add_error("severity", "Soft constraints require a severity from 1 to 100.")
        if cleaned.get("enforcement") == "hard":
            cleaned["severity"] = None
        cleaned["package"] = cleaned.get("package") or "FOU"
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
        cleaned["package"] = cleaned.get("package") or "FOU"
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
        if kind == "earliest_sequence":
            if cleaned.get("selector") == "attribute":
                parameters = self._rule(cleaned)
            else:
                if not cleaned.get("foundation_id"):
                    raise forms.ValidationError("Select a location.")
                parameters = {"foundation_id": cleaned["foundation_id"]}
            parameters["earliest_trip"] = cleaned["earliest_trip"]
            return parameters
        if kind == "latest_sequence":
            parameters = {}
            if cleaned.get("selector") == "attribute":
                parameters.update(self._rule(cleaned))
            else:
                if not cleaned.get("foundation_id"):
                    raise forms.ValidationError("Select a foundation.")
                parameters["foundation_id"] = cleaned["foundation_id"]
            if cleaned.get("bound_kind") == "trip":
                parameters["latest_trip"] = cleaned["bound_value"]
            else:
                parameters["latest_sequence"] = cleaned["bound_value"]
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
            return {"include_harbour_legs": False}
        if kind == "loop_id_sequence":
            return {"attribute": "Loop ID"}
        if kind == "package_buffer":
            if cleaned.get("mode") == "maximize":
                return {"mode": "maximize"}
            if cleaned.get("minimum_days") is None:
                raise forms.ValidationError("Enter the minimum number of days.")
            return {"mode": "minimum", "minimum_days": cleaned["minimum_days"]}
        if kind in {"matching_installed_first", "avoid_matching_in_first_trips"}:
            parameters = self._rule(cleaned)
            if kind == "avoid_matching_in_first_trips":
                parameters["trip_count"] = cleaned["trip_count"]
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


class ConstraintLevelForm(forms.Form):
    """Change package, hard or soft, and the severity, without rewriting the rule parameters."""

    package = forms.ChoiceField(choices=PACKAGE_CHOICES, label="Package")
    enforcement = forms.ChoiceField(
        label="Type",
        choices=[("hard", "Hard"), ("soft", "Soft")],
    )
    severity = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        help_text="Required for a soft constraint, from 1 to 100. A hard constraint does not use a severity.",
    )

    def __init__(
        self, *args, package_choices: list[tuple[str, str]] | None = None, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        if package_choices is not None:
            self.fields["package"].choices = package_choices
            self.fields["package"].help_text = "IAC waits for FOU. WTG waits for IAC."
        apply_bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        if cleaned.get("enforcement") == "soft" and cleaned.get("severity") is None:
            self.add_error("severity", "Soft constraints require a severity from 1 to 100.")
        if cleaned.get("enforcement") == "hard":
            cleaned["severity"] = None
        return cleaned


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
        "trip_count",
        "mode",
        "minimum_days",
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
    if constraint_type == "earliest_sequence":
        initial["selector"] = "attribute" if parameters.get("attribute") else "foundation"
        if parameters.get("earliest_trip") not in (None, ""):
            initial["earliest_trip"] = parameters["earliest_trip"]
    if constraint_type == "latest_sequence":
        initial["selector"] = "attribute" if parameters.get("attribute") else "foundation"
        if parameters.get("latest_trip"):
            initial["bound_kind"] = "trip"
            initial["bound_value"] = parameters["latest_trip"]
        else:
            initial["bound_kind"] = "sequence"
            initial["bound_value"] = parameters.get("latest_sequence")
    if constraint_type not in CONSTRAINT_TYPES:
        return initial
    return initial
