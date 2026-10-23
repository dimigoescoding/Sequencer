# User guide

Sequencer stores the constraints you enter. It does not suggest a methodology, fill in missing engineering values, or loosen a hard rule that cannot be met.

## Creating a project

1. Log in.
2. Open Projects and choose New project.
3. Enter a name and, if you want, a description. The package is Foundation.
4. Open the project. From there you can archive it, restore it from Archived Projects, rename it, or duplicate it. Duplication copies the dataset, scenarios, and constraints. It does not copy optimisation runs.

## Uploading Excel

1. Open Foundation Data.
2. Download the template if you need the column headings.
3. Upload an `.xlsx` workbook with `Information`, `Constraints`, and `Settings` sheets.
4. The page confirms that the upload is stored and lists the foundation, constraint, and setting counts. The new version is kept even when it has errors, together with the original file. Versions are not edited in place. Upload a corrected workbook to create the next version.
5. Read the error and warning lists. Activate a version only when it has no critical errors.

Critical errors include a missing sheet or mandatory column, a missing or duplicate WTG ID, an invalid Yes/No value, a non-positive weight, a coordinate that is not a number, or a soft constraint without a severity. A formula with no value stored in the file is an error. Sequencer does not calculate formulas. A value already stored by Excel is read and reported as a warning.

Warnings do not block optimisation. An unknown constraint name is stored and shown, and it is not turned into a rule from its explanation.

## Correcting validation errors

Fix the workbook in Excel and upload it again. Do not expect the previous version to change. Activate the new version when its error count is zero, and point the scenario at that version if it is not selected automatically.

## Creating scenarios

A project can hold several scenarios on the same dataset. Example names such as "Delivery Priority" are not built in.

1. Open Scenarios and create one.
2. Select a valid dataset version.
3. Rename, duplicate, or delete a scenario from its page. Duplicating copies vessel settings and constraints so you can change one copy without changing the other.
4. Previous runs stay on the scenario until you delete the scenario.

## Settings

Each scenario shows the settings from the workbook. `MP per trip` is the only setting in the supplied file. You can change its value. The number of trips is the included location count divided by `MP per trip`, rounded up. The final trip may be shorter than that capacity.

Solver time is on the same settings page. Choose 1 to 600 seconds. The stored default is 20. The generate page waits until the run finishes. A run that stops at that limit is feasible unless OR-Tools proves it optimal.

## Constraints

Open the scenario, then Constraints. The rows start from the Constraints sheet: package, name, explanation, rule, hard or soft, severity, and status. Edit a row to change hard or soft and the severity. Activate or deactivate a row, or delete it from the scenario. Add constraint offers the supported rule list. The explanation is shown as text. Sequencer does not read it as a new rule.

A soft severity of 0.5 in the workbook is half of the internal 1–100 scale, so the solver starts at 50. You can replace that number with any severity from 1 to 100. Changing a row to hard clears its severity.

Named rules in this workbook:

- Spider locations are installed first, in any order among themselves.
- At most one shallow location is placed on a trip.
- Infield sailing minimises the straight-line distance from each foundation to the next across the full sequence. The total includes the sail inside a trip and the sail from the end of one trip to the start of the next. Harbour transit is not included. On a larger set, the search re-solves stretches of the sequence that cross trip boundaries. The validation table shows the within-trip distance, the trip-to-trip distance, and the total in nautical miles.
- Jacking difficulty, when active, prefers to keep difficult locations out of the first three trips.

Earliest trip is a constraint you can add. It applies to one location, or to every location matching an attribute. The number is the first trip those locations may be installed. Enter 2 to keep them out of the first trip. For a Yes/No column such as Shallow location, use equals and YES.

## Hard versus soft constraints

Hard constraints are part of the CP-SAT model. If they cannot all be met, the run is `INFEASIBLE` and there is no sequence. Sequencer will not drop or soften them for you.

Soft constraints add a penalty. The result can violate them. The validation tab marks that as a soft trade-off and shows the penalty. Severity 100 is stronger than severity 50 for the same constraint type on the same data.

## Generating a sequence

Open Generate Sequence. Direct conflicts are listed first, for example one foundation fixed to two trips, a position above vessel capacity, a hard group that is also a hard separation, or a fixed group that already exceeds a hard payload limit. The solver does not start until those messages are clear.

Submit the form to run OR-Tools. Status values:

- `OPTIMAL` — proven best scaled objective.
- `FEASIBLE` — a valid sequence was found before the time limit. It is not claimed to be optimal.
- `INFEASIBLE` — no sequence exists. Nothing was invented.
- `UNKNOWN` or `ERROR` — no sequence was stored as a solution.
- `INVALID` — a sequence came back but failed an independent hard check. It is not an approved result.

## Reading the results

The run summary shows the project, scenario, dataset version, time, solver status, runtime, objective, validation status, foundation and trip counts, and the number of hard constraints, soft constraints, and soft trade-offs.

Installation Sequence lists order, trip, vessel position, weight, delivery deviation, and the constraints that governed each foundation. Search by foundation ID, sort columns, and page through long results.

Trip Summary lists count, order, payload, punch-through count, difficulty, and checks. Route distance appears when coordinates exist and a distance constraint is active. The unit is nautical miles. One nautical mile is 1,852 metres.

Visual plots the stored sequence on equal-scale easting and northing axes. Play, step, speed, and the slider move through the installation order. Each trip has its own colour, and completed trips fade. A line is drawn only between consecutive foundations in the same trip. Harbour transit and the join from one trip to the next are not drawn. The caption shows that within-trip distance in nautical miles. If a sequenced foundation has no easting or northing, the plot stays blank and those foundation IDs are named. A run with no stored sequence has nothing to plot.

Validation lists each check with target, actual result, status, affected foundations, and an explanation. Badges are Passed, Failed, Warning, Information, and Soft trade-off. The run passes only when every hard check passes.

## Exporting Excel

On a completed run, choose Export. The workbook has:

1. Optimized_Sequence
2. Trip_Summary
3. Validation
4. Foundation_Input
5. Vessel_Settings
6. Constraint_Configuration
7. Run_Summary

It includes the project, scenario, run id, solver status, validation status, and the exact constraint parameters used for that run. There is no map sheet. Generating the file again does not require the original upload to still be on disk, because the result rows are in the database.
