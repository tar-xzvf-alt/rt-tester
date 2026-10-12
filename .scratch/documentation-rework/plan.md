# Documentation rework plan

Status: finished documentation approved; updated package built and verified.

## Agreed goals

- Primary audience: experiment engineers preparing stands, collecting measurements,
  validating data, and interpreting results.
- Secondary audience: developers maintaining and extending rt-tester.
- Present the project through one fully reproducible experiment:
  what is measured → experimental setup → execution → integrity checks →
  interpretation of results.
- English is the primary documentation language.
- Provide an alternative Russian documentation set. Explain established terms
  such as GPIO, PREEMPT_RT, and latency at first use in the Russian reading path.
- Track this work with a local Markdown plan.
- Reference experiment mode: standalone GPIO with a userspace handler.
- Explain Prometheus/Grafana delivery and visualization as a separate scenario.
- Keep existing documentation paths for English; mirror the documentation under
  `docs/ru/` for Russian, with language-switch links.
- Add a compact `development/` section with architecture, development/testing,
  and change-guide documents in both languages.
- Keep default local task labels: `needs-triage`, `needs-info`,
  `ready-for-agent`, `ready-for-human`, and `wontfix`.
- Reference setup: VisionFive 2, Arduino Mega 2560, and ALT Linux.
- Use installed RPM packages for the standard execution path; describe source
  builds as an additional path and in developer documentation.
- Cover both local Prometheus/Grafana and central remote-write deployment.
- Reference example includes expected runner output, artifact locations,
  integrity checks, one real result graph, a statistics table, and limitations.
- An idle-versus-stress comparison is not required for the reference example.
- Plotting is a separate source-checkout step with explicitly documented Python
  dependencies; measurement execution remains the RPM-based standard path.
- Include portable reference profile examples for collection without
  observability, local observability, and central remote-write observability.
- Verify both language versions, local links, CLI/config examples, statistical
  definitions, and analysis against an existing real database during preparation.
- Track physical reference-stand and server walkthroughs separately and explicitly
  label each validation step as executed or not yet executed.
- Create `AGENTS.md` in rt-tester with short pointers to local tracker, task labels,
  and single-context domain-document rules under `docs/agents/`.
- Prepare a new RPM containing the updated documentation only after the user
  reviews the finished documentation and explicitly confirms satisfaction.

## Proposed implementation scope

- Rewrite the project entry and documentation index for experiment engineers,
  with a secondary developer entry path.
- Make the current documentation English and provide equivalent Russian documents
  under `docs/ru/`, with language-switch links and equivalent commands/constraints.
- Add a complete standalone userspace GPIO tutorial for the agreed reference
  setup, covering prerequisites, wiring, profile adaptation, smoke, collection,
  integrity checks, analysis, and interpretation.
- Explain GPIO, PREEMPT_RT, latency, and other reader-critical terminology at
  first use; define whole-group and retained-tail statistics precisely.
- Include diagrams and a real historical analysis example with provenance and
  clearly stated metadata limits.
- Add local and central observability walkthroughs, including verification of
  scraping, remote-write delivery, and dashboard data. Explain the distinction
  between live metric delivery and publication of the primary SQLite artifact.
- Add architecture, development/testing, and change-guide documents.
- Correct documented limitations of merge and preview execution.
- Keep English/Russian operational content equivalent and verify both versions
  together when commands, configuration examples, or constraints change.
- Add local engineering-workflow pointers and apply existing documentation
  structure conventions to new material.

## Completion criteria for preparation

- English and Russian entry points lead to equivalent engineer and developer paths.
- The reference tutorial identifies required hardware/software, editable profile
  values, measurement parameters, artifacts, expected outputs, integrity checks,
  and interpretation limits.
- Local and central observability examples avoid dependence on the author's
  private addresses, credentials, or home-directory layout.
- Every included real result distinguishes historical evidence from newly
  executed measurements and exposes known metadata limits.
- Relevant automated tests pass, examples are checked against the current code,
  and offline analysis of real sample data is verified.
- A validation record distinguishes automated/static/offline checks from pending
  hardware and server walkthroughs.

## Packaging stage — after documentation approval

Prerequisite: the user explicitly approves the finished documentation. Agreement
on the plan alone does not authorize this stage.

- Update package version/release and changelog as appropriate for the final diff.
- Verify that RPM packaging includes the English/Russian documentation tree,
  required visual assets, and the new reference configuration examples.
- Build the updated RPM with the project's packaging workflow and run package
  checks.
- Inspect the built package contents and verify packaged documentation links and
  examples against installed paths.
- Report the resulting package version, artifact paths, and verification results.

## Implementation results

- English reader documentation was rewritten at the existing paths.
- All 27 reader documents under `docs/` have Russian mirrors and language switches.
- Added the standalone walkthrough, local/central observability instructions,
  three portable profiles, statistics reference, SVG diagrams, and six bilingual
  developer documents.
- Added local agent-workflow notes and task tracking rules.
- Automated suite: 43 tests passed. Focused documentation/profile checks passed
  again after review corrections; `git diff --check` passed.
- Executed the documented historical analysis-copy and plot command. Original
  historical DB SHA256 stayed unchanged. Verified all 25 SVG bins against SQL.
- Executed the tutorial integrity-check code on synthetic no-loss data; this is
  explicitly not evidence of a hardware run.
- Standards review found incorrect relative-path guidance and a timestamp
  definition; both were corrected in English and Russian. Spec review identified
  the same path issue, also corrected.
- New RPM `0.4.2-alt1` built in x86_64, aarch64 and riscv64 hasher; 43 tests passed
  in each. Binary contents and packaged links verified; payloads match across
  builds. Hardware/server walkthroughs and host installation were not performed.
- Release artifacts and report:
  `/home/taranev/RPM/rt-tester-tools-0.4.2-alt1-20261007-104343/`.
- Existing unrelated untracked SQLite sidecars were left intact. Source snapshot
  preparation did not change Git history or index.

## Audit evidence

- Baseline reviewed: commit 5f05a38.
- Existing automated suite passed: 38 unittest tests, including local Markdown
  link checks. This does not establish hardware reproducibility.
- Key documentation gaps: developer architecture map, independently usable PC
  installation path, statistical field definitions, merge limitations, and
  visible example results.
- Hardware, remote infrastructure, RPM installation, and external link
  availability have not been verified as part of the audit.
- Historical standalone userspace VisionFive 2 session `186819` has versioned
  source data in `tests/old_databases/28032026.db` and an existing plot in
  `tests/results_starfive/186819_visionfive_6.18_300_75_stress_off.png`.
  Its full kernel/handler/firmware versions are not pinned; it may illustrate
  analysis but must not be presented as output of the current reference profile.
- No neutral standalone local-observability example profile was found. Existing
  runner support can generate local Prometheus/Grafana configuration, but current
  standalone profiles configure the project central server.
