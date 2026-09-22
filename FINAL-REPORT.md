# Sol Advisor full-v2 optimization report

Document basis: `SA-FULL-V2-20260920-R1`


> Fresh-review closure revision: P2 corrected-candidate admission now checks observed reviewer
> thread/context against the complete persisted rejection ancestry. Live packet, review,
> inspection and acceptance consumers also verify retained ancestry, including dependency stages.
> Same-candidate evidence continuation, exact replay and P1 historical interpretation remain.
> Usage examples now select a stage explicitly and distinguish P2 behavioral admission from
> hard isolation. Current exact-candidate verification, independent source review and bounded
> native trial results live in `.agent-artifacts/20260922-fresh-closure-e38c03/archive/report.md`.
> The user stopped full execution during this revision. Root finishes the repair and deterministic
> verification solo; the native trial is partial and no new independent source verdict is claimed.
> That external report is finalized after source freeze; older evidence below does not approve
> this revision. No production installation or end-to-end performance improvement is claimed.

> Prior flow-alignment revision (2026-09-22): **SOURCE REVIEWED FOR ITS EXACT CANDIDATE**.
> Its external receipt is `.agent-artifacts/20260922-flow-alignment/archive/sol-review-4.md`.
> Later freshness repairs require new review; this prior ship does not approve subsequent bytes.
> New tasks use `SA-FULL-V2-P2`: stage-scoped cumulative assembly and real prior acceptance,
> pre-review/pre-ship checks, registered isolated Python probes, and explicit Root-observed
> behavioral review. The current full discovery passed **186/186 on Python 3.14** and
> **19/19 current integration tests on Python 3.12**. Three independent source reviews
> returned fix-first; their six findings now have real regression coverage. Formal verifier and fresh review receipts are
> retained externally in `.agent-artifacts/20260922-flow-alignment/archive/`.
> This revision preserves the earlier red logs and does not claim production installation,
> a real multi-Terra end-to-end trial, hard native reviewer isolation, or cost/speed improvement.
> The following historical report does not sign these new bytes.

## Flow-alignment changes and evidence

- Stages own separate work selections and check scopes. The final stage reviews the cumulative
  result; exact accepted upstream selections cannot be rebound. CLI `final-accept` loads retained
  review/dependency contexts and advances the stage only after valid evidence and Root authority.
- P freezes required pre-review checks. Required late E is bound by V, not written back into P.
  Missing/failing required checks reject ship; optional evidence may be supplied without making
  it mandatory. Final candidate identity verification remains after V.
- Registered probe source, actual sandbox executable/profile/argv, evidence and original packet
  stay bound. macOS child reads are restricted to selected manifest-bound regular files, registered
  probe source and Python/system runtime resources; writes are restricted to a private run directory and network is denied.
- Behavioral review is explicitly contracted. Root captures before dispatch and after response,
  retains every old task input/log, and permits only appended check records. Observed thread ID is
  the fallback context identity; retries cannot rebind windows. This cannot detect write-restore.
- Real-run integration tests cover three stages, two peer first-stage deliveries, an ordered later
  edit, late checks, a new sandboxed probe, immutable P, V, CLI A, and meaningful refusal paths.
  Their runtime IDs are explicitly synthetic; they are tool-integration evidence, not native
  Agent compliance. All four actual runner source dependencies are candidate-bound for P2.
- The second fresh review found unreachable final-check contracts and recursive probe read
  grants exposing ignored baseline files. P2 now requires a final identity check per stage
  at candidate/pre-ship scope, and probe directory selectors expand only to bound regular
  candidate files. Real sandbox tests deny fake private files and Git metadata while
  permitting the declared candidate file.
- The third fresh review found the pure public acceptance validator accepted another stage
  final check even though the live runner refused it. The same applicability rule now holds
  at both entry points, with an actual accepted-stage fixture proving the valid neighbor and
  a recomputed cross-stage final evidence counterexample.
- Four leftover Root-rerun instructions were corrected without changing non-full responsibilities.
- The first fresh source review found cumulative-selection mismatch at stage three, intermediate
  acceptance receipt recovery after CAS, and an unconditional nonempty pre-review evidence rule.
  All three were reproduced and corrected; prior red evidence and review remain immutable.
- P2 design review accepts either the contracted hard mode or an explicit design observation
  window before a product candidate exists. A design reviewer context cannot perform final review.
- A native Sol stage canary proposed a new probe, inspected its real evidence plus late checks in
  the same context, and returned ship. The P2 tool admitted `V-native` with an observed
  behavioral window. See `archive/native-canary/admitted-context.json`; peer deliveries remain
  synthetic and this does not prove native multi-Terra operation or whole-product acceptance.
  This native canary predates the subsequent contract/read-policy tightening; its exact
  candidate is retained and is not an attestation for the final source bytes.
- One formal run failed an unchanged residual-process cleanup test; its original assertion
  detail was not retained by the strict runner. A single diagnostic, 30 repeated cases, a
  full 183-test diagnostic and formal retry passed. The cause remains unproven; the red
  run is preserved separately and is not erased by later green results.

The initial implementer returned partial results with 166 mostly existing tests. Root rejected
that as insufficient integration evidence, built actual full-chain counterexamples, and repaired
runner/packet/provenance consumers together. Red runs and subsequent green records remain under
`archive/`; the initial green counts are not recounted as current acceptance.

> Correction status (2026-09-22): **SOLO_CORRECTION_TESTED / NOT ACCEPTED**.
> `e7dae270…` is historical `fix-first`, not approval for later bytes. Its later c7b5 candidate
> `sha256:c7b50ba0bd3af3383eda144a155d058176ea310f88f29eb052826ac36c48a7b1` had formal E
> `E-formal-verify-candidate-c7b5` with **135/135 pass**, then a fresh Sol technical
> `fix-first`; formal V admission was `unavailable`. Its later c23e candidate had formal E
> `E-formal-verify-candidate-c23e` with **143/143 pass**, then a fresh Sol technical `fix-first`;
> formal V admission was again `unavailable`. After the later 74e8 `fix-first` finding, Root
> stopped using the full route to repair Sol Advisor itself and corrected the development source
> solo. The current worktree has **162/162 local offline tests** and a strict verifier pass.
> The exact whole-worktree candidate is stored at
> `.agent-artifacts/20260920-full-v2-01a0be24/archive/metrics/20260922-final-evidence-candidate.json`.
> The earlier `6a2ca363…` snapshot is retained and superseded after the measured loading change.
> This is candidate-bound offline evidence only: no new formal E or formal V has been created. Historic 106-test and
> final-review statements below do not sign current bytes. SA-FINAL-PATH-CONFINEMENT-001,
> SA-FINAL-SCOPED-CHECK-001, SA-FINAL-REVIEW-ADMISSION-001, and
> SA-FINAL-HARNESS-IDENTITY-001 still require an exact candidate freeze and a fresh independent Sol
> review. The behavioral write-then-restore boundary and performance benefit remain unproven.
> This host cannot supply the Root-controlled native reviewer lifecycle required for behavioral
> admission; broad-host behavioral V/DR publication is fail-closed. Only observed hard-read-only
> tagged V/DR can be newly signed, and final native review remains unproven.

Baseline: `d5b999bbc68766712895cb83aabcdcc5efcac923`, plugin `0.7.3`

Source version after work: unreleased `0.8.0`

Snapshot outcome: **development candidate locally tested; exact-candidate independent acceptance and
lower-cost/lower-wall-clock benefit are not demonstrated**

The whole-worktree candidate manifest is under the task-owned `.agent-artifacts` archive, excluded
from its own inventory. Retained c7b5/c23e candidate/E/review artifacts are historical and cannot
sign the repaired worktree. No new formal E, formal V, or final Sol receipt exists for these bytes.

The final solo correction tightened the five-output run transaction and shared P/CR/A provenance
guard, added adversarial replay/consumer tests, and replaced synthetic review-packet E fixtures
with actual `run-check.py` runs. The prior final-accept test's unreachable assertions were moved to
the real scoped-chain acceptance/replay/drift tests; its synthetic-E refusal remains explicit.
Root subsequently measured procedural-loading overhead, changed full-only worker loading, and
verified the new core in fresh native fixture sessions. These workers never repaired plugin source.

## Executive result

The source now implements the full-v2 organization and evidence model: Root owns planning and
acceptance; peer Terra workers independently implement, self-test, self-review and correct their own
lanes; deterministic tools receive and assemble selected deliveries; fresh Sol validates the real
combined candidate without editing it. No lead, integrator, permanent tester or generic agent layer
was added. `solo`, `delegate` and `audit` retain their separate behavior.

Historical offline verification passed all 106 then-discovered tests. Fresh native sessions explicitly loaded the
workspace 0.8.0 sources and exercised a single-Terra path, two peer Terras plus mechanical assembly,
combined Sol review, critical rejection and responsible-Terra correction, fresh complete re-review,
interruption/resume idempotence and real capacity refusal. The host did not enforce reviewer
read-only isolation (`danger-full-access`, permission profile `disabled`), so the historical review boundary was
behavioral and candidate bytes were checked before and after review. That historical evidence is not admitted for
the corrected bytes; new contracts default to hard-read-only and permit behavioral fallback only when explicitly
contracted and attested. This limitation is not hidden.

The performance goal has a mixed result. Candidate creation gains a safe opt-in scoped mode on the
large fixture (`0.340×` the baseline whole-worktree median in the current-source rerun) while preserving old manifest behavior;
small fixtures regress and therefore keep whole-worktree mode as the default. In the bounded native
Terra comparison, 0.8.0 achieved 14/15 hidden passes versus 13/15 for 0.7.3, but it also produced one
public-interface regression. Median per-agent elapsed time was 245 seconds versus 192 seconds, and
summed parallel-batch wall time was 1837 versus 1351 seconds. These runs explicitly loaded workspace
source and are not installed steady-state measurements, but they do not support a claim that the new
protocol is faster or cheaper overall. A later controlled three-pair dispatch experiment supports
a narrower improvement: sending only the worker core and complete work contract reduced median
elapsed time from 54.8 to 35.7 seconds and uncached input from 24,991 to 6,474 tokens, with 6/6
hidden checks passing. This result justified the full-only loading change, not an end-to-end claim.

## Source and document inventory

Core protocol and tools:

- `plugins/sol-advisor/scripts/full_protocol.py`
- `plugins/sol-advisor/scripts/workflow.py`
- `plugins/sol-advisor/scripts/run-check.py`
- `plugins/sol-advisor/scripts/review-packet.py`
- `plugins/sol-advisor/scripts/candidate.py`
- `plugins/sol-advisor/scripts/install-agents.sh`
- `plugins/sol-advisor/scripts/verify.sh`

Roles and orchestration:

- `plugins/sol-advisor/skills/orchestration/SKILL.md`
- `plugins/sol-advisor/skills/orchestration/references/full-workflow.md`
- `plugins/sol-advisor/skills/orchestration/references/role-contracts.md`
- `plugins/sol-advisor/skills/orchestration/references/convergence.md`
- `plugins/sol-advisor/skills/orchestration/references/operations.md`
- `plugins/sol-advisor/skills/orchestration/references/artifacts.md`
- `plugins/sol-advisor/agents/sol-advisor-terra-implementer.toml`
- `plugins/sol-advisor/agents/sol-advisor-sol-reviewer.toml`

Tests and graders:

- `plugins/sol-advisor/tests/test_full_protocol.py`
- `plugins/sol-advisor/tests/test_workflow.py`
- `plugins/sol-advisor/tests/test_run_check.py`
- `plugins/sol-advisor/tests/test_review_packet.py`
- `plugins/sol-advisor/tests/test_candidate.py`
- `plugins/sol-advisor/tests/test_behavioral_fixtures.py`
- `plugins/sol-advisor/tests/behavioral-evals/full-v2/cases.json`
- `plugins/sol-advisor/tests/behavioral-evals/full-v2/grader.py`

Metadata and user documentation:

- `plugins/sol-advisor/.codex-plugin/plugin.json`
- `plugins/sol-advisor/skills/orchestration/agents/openai.yaml`
- `.agents/plugins/marketplace.json` (inspected; local-source schema remains compatible)
- `README.md`
- `docs/full-v2/USAGE.md`
- `docs/full-v2/INSTALL-GRAY-ROLLBACK.md`
- `docs/full-v2/REQUIREMENTS-MAP.md`
- `metrics.json`

## Implemented behavior

1. Full-only contracts separate immutable task and artifact identity from mutable progress state.
2. Root records phase dependencies, risks, permissions and acceptance, and updates the actual plan
   when that capability exists.
3. Each Terra delivery binds owned bytes, delivery metadata, passing evidence, runtime identity and
   the owned bundle. Progress is not a delivery.
4. Mechanical assembly selects exact attempts from a clean common Git baseline, records before and
   after byte identities, preserves attribution and rejects overlap or drift. It never performs a
   semantic merge.
5. Task mutation uses create-no-replace artifacts, operation intents and receipts, one lock,
   expected-version CAS and fail-closed recovery without replaying uncertain side effects.
6. Checks use literal argv, exact non-sensitive environment, bounded logs and timeout process-group
   cleanup. Nonzero, never-started, timed-out, uncertain-cleanup, log-failure and candidate-drift
   states cannot become pass.
7. Review packets keep candidate E, P, challenge request, challenge E, CR, V and Root authority A
   separate. Relationships are recomputed from complete records; old verdicts cannot sign new bytes.
8. Sol review is critical-first and then complete-scope in one context. A critical early return must
   declare remaining scope; a fresh review of a corrected candidate must dispose of that scope.
9. Candidate whole-worktree behavior remains the default. Explicit `scoped-literal-v1` binds exact
   paths and HEAD and rejects unbound dirty or untracked paths.
10. The installer migrates only exact historical 0.7.3 Terra/Reviewer bytes. Modified, symlink and
    nonregular targets reject; check-only does not write; explicit `--target-dir` works without
    `HOME` or `CODEX_HOME`.
11. Formal verification discovers the actual test set and mandatory mechanisms rather than a fixed
    31/5 count or an obsolete sentence. Forbidden-pattern guards cannot silently skip when `rg` is
    unavailable.

## Verification evidence

### Offline and isolated installation

- Baseline full discovery: 36/36.
- Historical c7b5 formal E: `E-formal-verify-candidate-c7b5`, 135/135 pass; its fresh Sol technical
  review returned `fix-first`, while formal V admission was unavailable.
- Historical c23e formal E: `E-formal-verify-candidate-c23e`, 143/143 pass; its fresh Sol technical
  review returned `fix-first`, while formal V admission was unavailable.
- Current solo-corrected worktree: 162/162 local offline tests; dynamic and nonempty strict discovery
  executed required mechanisms with no skips or expected failures. This is candidate-bound offline
  evidence, not formal E, native review, or acceptance.
- `sh plugins/sol-advisor/scripts/verify.sh`: strict candidate-source pass.
- Python compile, shell syntax, JSON/TOML parsing, Markdown links and `git diff --check`: pass in the
  final pre-candidate rerun.
- Isolated companion-role install, exact 0.7.3 migration, role checks, user-customization refusal,
  symlink/nonregular refusal and check-only no-write: pass.
- c7b5 red/green and formal-E record:
  `.agent-artifacts/20260920-full-v2-01a0be24/work/final-fix/c7b5-argv-truncation-red-green.md`,
  `.agent-artifacts/20260920-full-v2-01a0be24/work/final-verification-task-correction-3/evidence/E-formal-verify-candidate-c7b5.json`,
  and `.agent-artifacts/20260920-full-v2-01a0be24/archive/native/final-correction-3-sol-review.md`.
- c23e final-provenance/CLI red-green and formal-E record:
  `.agent-artifacts/20260920-full-v2-01a0be24/work/final-fix/c23e-final-provenance-red-green.md`,
  `.agent-artifacts/20260920-full-v2-01a0be24/work/final-verification-task-correction-4/evidence/E-formal-verify-candidate-c23e.json`,
  and `.agent-artifacts/20260920-full-v2-01a0be24/archive/native/final-correction-4-sol-review.md`.
- Verifier red/green evidence:
  `.agent-artifacts/20260922-verifier-docs-terra-01/work/red/test_verify_test_suite-before-runner.log`,
  `.agent-artifacts/20260922-verifier-docs-terra-01/archive/logs/test_verify_test_suite-green.log`,
  `.agent-artifacts/20260922-verifier-docs-terra-01/archive/logs/full-unittest.log`, and
  `.agent-artifacts/20260922-verifier-docs-terra-01/archive/logs/official-verify.log`.

### Historical native development-source behavior

These retained sessions do not establish corrected-source native-route regression or hard native
V/A: this host lacks the Root-controlled lifecycle required for behavioral reviewer admission.

- A historical Terra design proposal and fresh Sol design challenge ended `design-approved` for v9; the later
  implementation reviews used different native contexts, and design approval was never treated as
  product approval.
- Single Terra implementation plus fresh Sol: candidate
  `sha256:8601a308ce0ddf4e050c3ad3a1c2ab35b7aaaaae073fc3890f570fef842a01a8`,
  `valid/ship`.
- Two independent Terra deliveries, no lead/integrator, exact mechanical combination and fresh Sol:
  candidate `sha256:e8014cf4e1a1a6cb6e994cc4aad34a37a37d5bbb59ba01ab36b5a18797b1b1b9`,
  `valid/ship`.
- Critical authority-lifecycle failure: first fresh Sol returned `valid/fix-first` and declared the
  unreviewed scope; the responsible Terra corrected it; a different fresh Sol completed both the
  fix and previous remaining scope and returned `valid/ship` for candidate 2.
- Interruption: the interrupted attempt produced no delivery; the same thread resumed and wrote the
  result once; a second continuation made no write and preserved inode, mtime and hash.
- Capacity: with all three child slots occupied, a fourth spawn returned
  `agent thread limit reached`; no retry or model substitution occurred.
- Detailed evidence:
  `.agent-artifacts/20260920-full-v2-01a0be24/archive/native/native-behavior-metrics-v3.json`.

### Paired bounded comparison

Five non-12306 cases used frozen task directories, the same Terra/high role, three repeats per
version and hidden checks unavailable to implementers. Original C4 and C5 calibration failures are
retained but excluded because their hidden schemas were not fully stated; explicit-schema fixtures
were rerun.

| Case | 0.7.3 hidden | 0.8.0 hidden | Median seconds 0.7.3 → 0.8.0 |
|---|---:|---:|---:|
| Normal greeting | 3/3 | 3/3 | 191 → 180 |
| Cross-consumer quantity | 3/3 | 3/3 | 166 → 241 |
| Authority lifecycle | 3/3 | 2/3 | 191 → 359 |
| Evidence admission | 1/3 | 3/3 | 259 → 424 |
| Operation recovery | 3/3 | 3/3 | 231 → 258 |

Aggregate quality is 13/15 versus 14/15. The 0.8.0 lifecycle failure changed an existing
synchronous API to async and rewrote its visible tests; the hidden compatibility check caught the
unawaited coroutine. The failure is preserved and not corrected or recounted. The C4 improvement
shows better evidence-boundary reasoning, but the small sample does not prove uniform quality gain.

The per-agent median is 192 versus 245 seconds; cumulative model time is 3221 versus 4321 seconds;
summed three-way parallel batch wall time is 1351 versus 1837 seconds. C3 0.8.0 repeat 3 includes a
root prompt-path correction and keeps its raw 516-second time.

The previous claim that token receipts were unavailable was incorrect. A later exact-session
extraction found native `token_count` records for all 30 paired runs and six invalid-fixture
attempts, with cumulative totals matching the sum of unique per-call receipts. Across the paired
runs, baseline/development used 430,586/550,172 uncached input tokens, 8,499,712/11,285,760 cached
input tokens, and 78,591/98,732 output tokens. Model calls rose from 183 to 215. Price remains
unknown. Invalid-fixture attempts are separately retained and included in all-attempt resource
totals; their unequal cohort sizes are not used for a savings comparison.

Observed shell commands rose from 130 to 168, including orchestration-reading commands rising
from 31 to 52, while test-command occurrences fell from 69 to 61. One directly inspected small
fixture repeated the long reference reads after truncated output and a guessed template path.
This identifies a procedural-loading overhead mechanism; it does not attribute all time variation
to the protocol. Raw allowlisted attribution is `benchmark-attribution-v2.json` in the metrics archive.

### Measured full-worker loading correction

A preregistered one-task experiment ran three fresh native Terra/high sessions per condition on
byte-identical cross-consumer fixtures. Both conditions retained the same acceptance, ownership,
offline constraints, tests, self-review, final report limit and hidden grader. The variable was
loading five Root/role references versus loading the exact Terra core plus the supplied contract.
All six hidden checks passed; source reads and role/model/effort were observed, not self-reported.

| Metric, median | Full reference loading | Worker core + contract |
|---|---:|---:|
| Elapsed seconds | 54.801 | 35.697 |
| Uncached input tokens | 24,991 | 6,474 |
| Cached input tokens | 450,048 | 185,088 |
| Output tokens | 3,255 | 1,865 |
| Model calls | 10 | 5 |

Root promoted the narrower loading rule into full-only dispatch guidance and the Terra core.
Actual product investigation, acceptance constraints, self-tests and ordinary corrections remain
required. A separate fresh session explicitly loaded the modified core; it is confirmation, not
an additional paired sample. `dispatch-eval-v1-results.json` contains every paired sample and the
independent hidden results. This one-task experiment does not establish full-route or cross-task
cost reduction and does not erase the earlier regression samples.

Detailed samples, runtimes and raw hidden logs are under
`.agent-artifacts/20260920-full-v2-01a0be24/archive/metrics/`.

### Current native non-full regression

Three fresh fixture Roots explicitly loaded the current development Skill. The observed native
trace shows solo made its own changes and checks with zero auxiliaries; delegate used one
Luna/max, then Root reran tests and independent interface checks with no Sol; audit made its own
changes and checks, then a fresh Sol/high returned `valid/ship` for the exact fixture candidate,
with no implementer. All three independent hidden checks passed. The audit candidate matched
before and after review; the Sol made no observed file edits. Its runtime remained
`danger-full-access/disabled`, so this is behavioral read-only audit evidence, not hard full V/A.

`native-route-regression-v2-results.json` retains source hashes, actual native identities,
declarations, command/change/spawn traces, candidate receipts and hidden outputs. The initial v1
collector incorrectly treated native Text-block messages as strings; its false missing-declaration
results remain retained. These are bounded one-feature route regressions, not broad application
coverage or installed-product acceptance.

### Candidate performance

- Current source `de977ba3…` was remeasured because the earlier benchmark used a different script hash.
- Large fixture: baseline whole median `133.8 ms`, new whole `133.9 ms`, scoped `45.5 ms`.
- Large scoped/baseline ratio: `0.340`.
- Small scoped/baseline ratio: `1.287`; scoped therefore remains opt-in.
- Each mode has one first-observed and three warm runs on unchanged retained fixtures. No OS cache
  flush was performed; true cold-storage performance remains unmeasured.
- Old whole and legacy manifest interpretation is unchanged; unsafe or uncertain scope falls back.

## Compatibility, installation and rollback

- `solo`, `delegate` and `audit` were not converted into full.
- Old schema-2 whole and legacy manifests retain their field sets and interpretation.
- Luna was not redesigned. Terra/Sol pins remain Terra/high and Sol/high.
- Exact legacy fixtures remain; new 0.7.3 fixtures were added instead of rewriting history.
- No production plugin, global configuration, credential, business system or remote repository was
  changed. No commit, push or publication occurred.
- Isolated install, upgrade, gray rollout triggers and rollback steps are in
  `docs/full-v2/INSTALL-GRAY-ROLLBACK.md`.

## Remaining limitations and release judgment

1. The host exposed no hard read-only sandbox for Sol. Reviewers complied behaviorally and candidate
   bytes stayed stable, but this is not equivalent to enforced isolation.
2. The five-case comparison is bounded Terra behavior under explicit workspace-source loading. The
   two-Terra full route was observed once on 0.8.0, not in three paired end-to-end baseline/new runs.
3. Native token use is measured for the listed cohorts; monetary cost and full-route total usage
   remain unknown. Cached tokens and elapsed time must not be converted into an invented price.
4. The historical five-case comparison regressed in elapsed/model work. The later one-task loading
   experiment improves both, but does not establish an overall full-route performance gain.
5. The tracked report cannot include the final candidate ID or verdict without changing the bytes it
   describes. The external final-review receipt is authoritative for that last binding.
6. Candidate warm measurements are current; controlled cold-storage latency remains unmeasured.

Recommended release status: **eligible for isolated/gray evaluation only after the exact final
candidate receives a fresh Sol `REVIEW_STATUS: valid`, `VERDICT: ship`; local loading and scoped
candidate improvements are measured, but full-route cost/speed and production readiness remain unproven.**

## Repository state

All work remains uncommitted on the isolated `codex/full-v2-optimization` worktree. Historical red
evidence and calibration failures are retained. The user's original checkout, production install,
global configuration and remote repository were not modified.
