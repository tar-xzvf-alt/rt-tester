# Configuration audit

Status: diagnosis, live checks, source verification and report completed.

## Request

Determine why project configs do not always work; test profiles compatible with
the current stand. Preserve user changes and original experiment artifacts.

## Confirmed starting observations

- `text.conf` expects non-RT 6.18.37; the last live kernel was 6.18.18-rt.
  A real preflight run failed before GPIO startup with an opaque traceback.
- Most historical profiles use the old SSH/exporter address 10.42.0.211.
- The user's RT userspace profile changes SSH to 10.64.128.112 but leaves its
  exporter address at 10.42.0.211.
- Profiles use fixed kernel/source paths and central monitoring by default.
- Runtime endpoint/path handling requires separate regression checks.
- After changing harness mode, the board stopped answering even through Wi-Fi;
  gateway and USB devices remain available. Investigate UART independently.

## Scope

Inventory originals versus adapted status. Test RT GPIO, general/template/local
profiles and cyclictest when reachable and compatible. Verify central monitoring
with existing credentials only. Mark non-RT and supervised topology blockers
explicitly. Fix confirmed narrow runner/config issues and verify both language
versions plus automated checks. No commits or new RPM release requested.

## Implemented fixes

- Standalone profiles derive exporter host instead of duplicating a stale IP.
- Source GPIO runner resolves DB paths before changing receiver working directory.
- Kernel mismatch reports actual and expected values instead of an opaque shell failure.
- All three measurement runners use a bounded SSH connection attempt.
- User's existing host edit and `text.conf` remain intact.

## Executed checks

- UART showed the board waiting in boot menu; selected the previously used RT kernel.
- Seven regression tests reproduced issues before changes and passed afterward.
- Nine GPIO adaptations passed (RT idle/stress pairs, generic standalone, three
  templates, and the user's text profile with explicitly corrected kernel).
- Two cyclictest runs completed with four threads and zero histogram overflow.
- Local and central monitoring received matching session data.
- Both cyclictest bundles published and remote scope/histogram totals match local
  cycle counts. A 60-second test-harness timeout was too short for the first
  publication; repeat completed and importer confirmed unchanged/idempotent data.
- Non-RT profiles and supervised multi-node profiles remain untested on the
  current RT/single-board stand.

## Final verification

- Full automated suite: 50 tests passed; documentation checks and diff check passed.
- Standards review's stderr/stdout finding reproduced, fixed in all three runners,
  and confirmed resolved. Spec review reported no findings.
- Nine GPIO profiles: 110500 requests and responses, zero timeouts.
- Eleven adapted profiles executed; two additional publication checks passed.
- Effective overrides, logs, SQLite/bundles, remote catalog verification and
  checksums saved under `/home/taranev/rt-experiments/config-audit-20261008/`.
- Test workloads/monitoring/tunnel cleaned up; node_exporter state restored;
   target remains RT at 1.5 GHz. No new commit or package build was made.

## Subsequent repository maintenance

- Source fixes, tests and bilingual documentation were committed as `558b598`.
- Runner finalization improvements were committed separately as `1bfa272`.
- Local `configs/stands/text.conf` was moved out of the source tree to
  `/home/taranev/rt-experiments/visionfive2-gpio-local-20261007/text.conf`.
- Empty, unused SQLite runtime sidecars were removed; primary databases retained.
