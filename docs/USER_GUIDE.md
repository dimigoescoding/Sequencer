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
3. Upload an `.xlsx` workbook. The sheet must be named `Foundation_Input`.
4. The new version is stored even when it has errors, together with the original file. Versions are not edited in place. Upload a corrected workbook to create the next version.
5. Read the error and warning lists. Activate a version only when it has no critical errors.

Critical errors include a missing sheet or mandatory column, a missing or duplicate `Foundation_ID`, an invalid Yes/No value, a non-positive weight, a non-integer sequence value, and an earliest sequence after the latest sequence. Formulas are errors. The application does not calculate them.

Warnings include missing coordinates, difficulty, delivery batch, or notes. Warnings do not block optimisation. They do disable constraint types that need the missing data. The constraint chooser states the reason.

`Fixed_Trip`, `Fixed_Position`, `Earliest_Sequence`, and `Latest_Sequence` in the workbook are data columns. Add a constraint if you want the solver to enforce them. A fixed position above the scenario's foundations-per-trip limit is reported when you generate a sequence.

## Correcting validation errors

Fix the workbook in Excel and upload it again. Do not expect the previous version to change. Activate the new version when its error count is zero, and point the scenario at that version if it is not selected automatically.

## Creating scenarios

A project can hold several scenarios on the same dataset. Example names such as "Delivery Priority" are not built in.

1. Open Scenarios and create one.
2. Select a valid dataset version.
3. Rename, duplicate, or delete a scenario from its page. Duplicating copies vessel settings and constraints so you can change one copy without changing the other.
4. Previous runs stay on the scenario until you delete the scenario.

## Vessel settings

Each scenario has its own settings.

- Maximum foundations per trip defaults to 4.
- The final trip may be partial. Turn that off only when every trip, including the last, must be full.
- Solver time limit defaults to 20 seconds. The allowed range is 1–30. The page waits for that solve, and the server runs one solve at a time.
- Payload, transit speed, and harbour coordinates stay empty until you enter them. Empty does not mean zero, and it does not enable payload or harbour-leg checks.

The number of trips is the included foundation count divided by the maximum per trip, rounded up.

## Adding constraints

Open the scenario, then Constraints, then Add constraint. Pick a type. Types that need missing columns are listed with an explanation and cannot be saved.

The form is a structured builder:

- Choose enforcement: hard (must be satisfied) or soft (preference).
- For a soft constraint, set severity from 1 to 100. A higher severity pulls harder against other soft constraints of the same kind. It does not override a hard constraint.
- For attribute rules, choose the column, an operator, and the comparison value. You cannot type a formula.

Examples of what the builder can express:

- If `Punch_Through` equals Yes, allowed positions are 3 and 4, enforced as hard.
- If `Difficulty_Value` is greater than 75, prefer later in the sequence, enforced as soft with a severity you choose.
- If `Delivery_Batch` equals a batch you name, the matching foundations are allowed only from a trip you name, enforced as hard through an earliest-sequence rule.

Actions on a saved constraint: edit, duplicate, activate, deactivate, delete, and move up or down. Deleting asks for confirmation. Display order is for reading the list. It does not change hard feasibility.

A soft payload limit shows a warning because the result may exceed the limit. The excess is reported as a trade-off.

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

Trip Summary lists count, order, payload, punch-through count, difficulty, and checks. Route distance appears when coordinates exist and a distance constraint is active. The unit is metres.

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
