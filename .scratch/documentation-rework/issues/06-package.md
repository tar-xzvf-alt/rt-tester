# Prepare updated rt-tester-tools RPM

Status: completed
Blocked by: none (05 completed; finished documentation approved by user)

Start only after the user explicitly states that the finished documentation is
satisfactory. Approval of the design/implementation plan is not this approval.

Update version/release and changelog, build the RPM, run package checks, inspect
English/Russian documents, SVG assets and example profiles in package contents,
and report the resulting version and artifact paths.

## Result

Version: `0.4.2-alt1`, `BuildArch: noarch`.
All three hasher builds passed: x86_64, aarch64 and riscv64; 43 tests in each.
All 113 payload files match across architectures. Checked 27 reader pages per
language, 344 local links, two SVGs, three profiles and seven CLI wrappers per RPM.

Release directory:
`/home/taranev/RPM/rt-tester-tools-0.4.2-alt1-20261007-104343/`.
Canonical binary: `RPMS/rt-tester-tools-0.4.2-alt1.noarch.rpm`.
Source: `SRPMS/rt-tester-tools-0.4.2-alt1.src.rpm`.
See `BUILD-REPORT.md`, `SHA256SUMS`, `logs/` and `verification/package-checks.json`.

Local unsigned build used the project's existing changelog/packager/GPG check
exceptions. Other checks and `%check` stayed enabled. Hardware/server tests and
host installation were not performed. Git history/index were not changed.
