# Runner finalization: architecture step 1

Status: completed
Baseline: 558b598

## Scope agreed with the user

Implement architecture-review step 1 after committing existing profile,
diagnostics and documentation changes. Do not commit test-session data.
Confirmed test seams: GPIO/stand `run_measurement`, cyclictest `execute`,
supervised `run_receiver`. Use mocked SSH and short local child processes;
do not execute hardware runners.

## Required behavior

- Attempt all mandatory stop actions even if diagnostics or another action fails.
- Preserve the original measurement/startup exception, including interrupts and
  SystemExit. Report secondary failures separately to stderr.
- With no original error, propagate a finalization error rather than reporting
  successful completion. Retain any already finalized cyclictest bundle.
- Reap and close the piped receiver on callback, read, write or interrupt failure;
  use bounded TERM/wait/KILL/wait and close pipes independently.
- Bound remote finalization commands so one unavailable target does not block
  other stop attempts indefinitely.
- Separate broad pre-run recovery of a dedicated stand from normal stopping of
  configured PIDs/modules and newly started process groups, including runtime
  descendants that remain in the supervisor process group.
- Preserve keep-target(s), dry-run, retained observability and tuning policies.
- Package any shared support module and update English/Russian architecture
  and testing documentation together.

## Limitations and verification

No concurrent-run coordination, machine-event protocol/readiness deadline,
collector-state redesign, transport framework or rollback of clock/tuning changes.
Remote unavailability means termination cannot be confirmed. A runtime deliberately
detaching from its process group requires separate lifecycle handling.
Run focused tests, the full AGENTS.md unittest command and diff checks; review the
working changes against the baseline for Standards and Spec.

## Verification result

69 automated tests passed (19 cleanup tests), source CLI help and diff checks
passed. Standards and Spec review findings were fixed and rechecked; no remaining
findings. Hardware/remote runs and package build/install were not executed.
