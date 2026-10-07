# Issue tracker: Local Markdown

Plans, specifications, and tasks live under `.scratch/<feature>/`.

- `plan.md`: decisions and progress during design.
- `spec.md`: the agreed scope and completion criteria.
- `issues/NN-<slug>.md`: one file per implementation task.
- Each task records `Status:` and `Blocked by:` near its start.
- Add discussion under `## Comments` in the relevant task.

When a workflow asks to publish or fetch an issue, write or read the local file.
Use the status labels in `triage-labels.md` for incoming issue classification.
Implementation tasks use `pending`, `in-progress`, or `completed` for progress;
dependencies must be completed before a dependent task starts.
