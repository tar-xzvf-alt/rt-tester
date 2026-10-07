# Agent Notes

## Agent skills

### Issue tracker

For planning work or managing tasks, read `docs/agents/issue-tracker.md`.
Plans and tasks are stored locally under `.scratch/`.

### Triage labels

For incoming issue classification, read `docs/agents/triage-labels.md`.

### Domain docs

Before domain or architecture work, read `docs/agents/domain.md`.

## Documentation

English uses `README.md` and `docs/`; Russian mirrors reader documentation in
`docs/ru/`. Update matching instructions, commands, and limitations together.
See `docs/README.md` for the document organization and maintenance rules.

## Verification

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`
for automated checks. Measurement runners require real hardware and may alter
local/remote state even with `--dry-run`; use isolated function-level checks for
documentation profiles.
