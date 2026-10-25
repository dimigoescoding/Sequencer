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
3. Upload an `.xlsx` workbook with `FOU data`, `IAC data`, `WTG data`, and `Programme` sheets. Any other sheet is ignored. Constraints and settings are not read from the file.
4. The page confirms that the upload is stored and lists the FOU, IAC, WTG, and programme counts. The new version is kept even when it has errors, together with the original file. Versions are not edited in place. Upload a corrected workbook to create the next version.
5. Read the error and warning lists. Activate a version only when it has no critical errors.
6. Open the FOU, IAC, WTG, and Programme tabs. Each table scrolls vertically through its rows.

Critical errors include a missing sheet or mandatory column, a missing or duplicate id, an invalid Include value, a non-positive weight on an included FOU row, or a coordinate that is not a number. A formula with no value stored in the file is an error. Sequencer does not calculate formulas. A value already stored by Excel is read and reported as a warning. An excluded FOU row, such as an OSS, may leave weight, spider, shallow, and jacking blank.

Warnings do not block optimisation. A cable end that is not a FOU or WTG id is a warning. The cable is kept and no location is invented.

## Correcting validation errors

Fix the workbook in Excel and upload it again. Do not expect the previous version to change. Activate the new version when its error count is zero, and point the scenario at that version if it is not selected automatically.

## Creating scenarios

A project can hold several scenarios on the same dataset. Example names such as "Delivery Priority" are not built in.

1. Open Scenarios and create one.
2. Select a valid dataset version.
3. Rename, duplicate, or delete a scenario from its page. Duplicating copies vessel settings and constraints so you can change one copy without changing the other.
4. Previous runs stay on the scenario until you delete the scenario.

## Settings

FOU per trip applies only to foundations. WTG per trip applies only to turbines. IAC has no trip limit. Both capacities accept 1 to 20. The number of trips for a package is its included count divided by that capacity, rounded up. The final trip may be shorter.

Solver time is on the same settings page. Choose 1 to 600 seconds. The stored default is 20. One limit covers the whole programme. The generate page waits until the run finishes. A run that stops at that limit is feasible unless OR-Tools proves it optimal.

Changing the dataset does not replace these values or the constraints you added.

## Constraints

Open the scenario, then Constraints. The Package column is a dropdown: FOU, IAC, or WTG. The rule is applied only to that package. Full sequence versus within trip stays a separate choice on ordering rules. Edit a row to change the package, hard or soft, and the severity. Activate or deactivate a row, or delete it. Add constraint offers the supported rule list. The explanation is shown as text. Sequencer does not read it as a new rule.

A soft severity is a number from 1 to 100. Changing a row to hard clears its severity.

Rules you can add include:

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

Submit the form to run OR-Tools once for the whole programme. FOU, IAC, and WTG are activities in that one model. A cable is the activity that joins its two location ids. Package settings and constraints choose which activities they bind. Sequencer does not insert a buffer or force FOU, then IAC, then WTG. Programme P50 dates are stored per slot and are not turned into windows unless you add a constraint. A loading bar stays on the page until the solver finishes. If the model is infeasible, no partial sequence is stored. If any hard check fails, the whole run is invalid. Status values:

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
