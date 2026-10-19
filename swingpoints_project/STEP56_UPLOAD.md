# Uploading the Step 5–6 update

Baseline: the supplied `Financial-Technical-Analysis-main(3).zip`.
This update adds trade entries and profit/loss to that unified version.

## Changes-only ZIP

`Step56_Changes_Only.zip` contains only files whose contents differ from the
baseline: implementation, integration, tests, documentation and refreshed default
results. Its paths start with `README.md` or `swingpoints_project/`, matching the
repository root. It is an update package and cannot run by itself.

1. Unzip the changes-only archive on your computer.
2. On GitHub, select the branch you want to update and open the repository root,
   one level above `swingpoints_project`.
3. Choose **Add file → Upload files** and drag the extracted `README.md` and
   `swingpoints_project` folder into the upload area.
4. Check that paths begin with `swingpoints_project/` exactly once, then commit.
   A suitable message is `Add Steps 5–6 trade entries and profit/loss`.

Files already at the same path are updated. Unchanged files stay in place. The
package needs no deletions. For a pull request, use `STEP56_PR_DESCRIPTION.md`.

## Full project ZIP

The full archive contains the complete runnable project, the original datasets,
default results in `output/`, plus additional comparisons:

- `examples/step56_next_open/`: the report's next-Open execution option.
- `examples/step56_methods/`: all four swing methods with identical trade settings.

These two new comparison folders are omitted from the changes-only archive to
keep the browser upload small. Recreate them from `swingpoints_project` with:

```bash
python app.py data/data.csv --entry-timing next_open --output examples/step56_next_open
python run_methods.py data/data.csv --output examples/step56_methods
```

See `STEP56_ZH.md` for installation and GUI instructions, `STEP56.md` for the
precise execution rules, and `STEP56_RESULTS.md` for measured test-data results.
