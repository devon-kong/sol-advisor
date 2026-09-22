# Full-route protocol

This reference applies only after Root explicitly declares the `full` route. It adds no
behavior to `solo`, `delegate`, or `audit`; those routes retain [SKILL.md](../SKILL.md).
It is an offline coordination protocol, not a service, generic event system, semantic
merger, production installer, or authorization for credentials, business networking,
publication, push, or destructive cleanup.

## Participants and decision separation

Root writes the immutable task contract, owns mutable-state CAS, identity binding, decision,
release, exception investigation, and final acceptance. It schedules one or more peer Terra
stage deliveries; Terra independently delivers, self-tests, and self-reviews owned work and
is never a lead, integrator, or default technical rerunner. P2/P3 deterministic tools publish
their own records. Fresh Sol is read-only: it starts with high-value contract
counterexamples, then completes technical validation. Root does not perform a duplicate full
technical rerun or diff review by default.

Root loads the orchestration procedure once and sends each Terra its complete work
contract, exact role-core identity, and any specifically needed risk reference. A worker
does not reload Root's SKILL, operations, or artifact procedure as a startup checklist.
It reads the product code and related consumers needed for its owned result, completes
ordinary implementation/test/self-review corrections locally, and returns a compact
evidence index. Do not shorten acceptance, ownership, interface or permission constraints
to save prompt tokens; remove repeated procedural loading instead.

Keep these facts distinct:

- `DR` is design-only: `design-approved|fix-first|rethink|null`; it has no candidate,
  packet, V, or A authority.
- A stage is task contract/state progress. A selected attempt or green delivery never
  establishes candidate provenance or final acceptance.
- `V.status` is `valid|unavailable|invalid`. Only valid V has the verdict triad
  `ship|fix-first|rethink`. Operational `review_status` is separate.

## Immutable/mutable boundary

New full tasks use `SA-FULL-V2-P2`. Keep active `SA-FULL-V2-P1` tasks and old
attestations on their original interpretation; an explicit migration starts a new
contract and does not carry forward an old verdict. The staged protocol is a versioned
extension of the existing file-based tools, not a new scheduling service.

Before dispatch, Root derives the stages, dependencies, owners, preserved behavior,
critical risks, check order, permissions and stop conditions from the user's goal and
repository facts. Use the available native `update_plan` tool for phase progress; if it
is unavailable, show a concise text plan without claiming a native update. Users do not
need to author the tool's JSON records. Keep future work at the appropriate level of
detail; an actual interface or acceptance change requires a new contract, while an
ordinary progress update does not.

A stage becomes complete only after its current candidate has a valid Sol verdict and
Root acceptance. Ready deliveries are not accepted stages. The next dependent stage must
retain the exact accepted upstream inputs; final review covers the cumulative product and
the complete user goal. It can share the final stage's Sol context rather than adding a
second same-scope reviewer. A change to an accepted dependency makes downstream evidence
stale; do not silently reuse it or mark every historical stage invalid without analysis.

Checks have different purposes. Cheap pre-review checks establish that the candidate is
worth reviewing; required pre-ship checks must be complete before ship. Sol starts with
independent critical challenges, then finishes the remaining review and any required late
checks in the same context. An early rejection reports related findings together and names
unreviewed scope. The next fresh review must cover that remaining scope as well as the fix.
Tool commands that record or run these checks do not make Root a second technical reviewer.

`task-contract.json` is canonical immutable with `contract_digest`, goal, authority,
preserved/excluded behavior, stages/dependencies, ownership/interfaces, checks, exact
no-secret environment policy, coverage, and rejection policy. It contains no artifact IDs,
attempts, progress, or future child IDs; a material change creates a new digest.

`state.json` is only mutable progress:

~~~text
{version, contract_digest, stage_status, work_status, selected_attempts,
 current_ids:{assembly_index,candidate_binding,review_packet,verdict,acceptance},
 applicable_rejection_roots, last_operation_receipt}
~~~

One lock and expected-version CAS guard it. State is not an identity or input for CB/E/P/V/A
unless that artifact schema explicitly names a progress fact.

## Immutable artifact chain

The normal full chain is `material + D + delivery E -> I -> schema-2 manifest + CB ->
pre-review candidate E -> P -> challenge request + challenge E + CR + pre-ship E -> V -> root authority + A`.
Artifacts are canonical, hashed, create-no-replace, re-read after publication, and reject
nonregular paths, symlinks, invalid data, or different existing bytes. Identical bytes are
idempotent.

- `D` binds contract/work/baseline/ready identity, material bytes, its one passing delivery-E
  ID, and exclusive path/runtime resources; missing/substituted delivery evidence, drift,
  overlap, interface mismatch, or post-ready write rejects.
- `I` has common baseline, selected D/material attempts, and deterministic isolated output;
  duplicate/stale attempts, aliases, undeclared output, and semantic merging reject.
- `CB` is the sole protocol candidate reference. It retains the unchanged external schema-2
  manifest path/hash/candidate ID and manifest-derived inventory policy, and proves its
  explicit inputs match retained I/D/material plus the complete delivery-evidence set.
- `E` is scope-correct: delivery names material, candidate names CB, challenge names
  `{packet_id, cb_id}`. Contract, check, subject, harness, environment, and runtime bind.
- `P` freezes contract, CB, I, D, passing pre-review candidate E, coverage, and rejection
  roots and the exact stage/review scope. Only required pre-review checks gate P;
  required pre-ship E is appended to V in the same review context. Optional checks do not
  become mandatory, and final identity verification remains after V.
- Challenge requests are canonical/non-secret and use a predeclared check or a P2
  probe registered under the contract's optional explicit probe policy. P3 resumes
  the same observed Sol context; challenge E binds request ID/digest, CR binds request/P/CB/E,
  and V's only CR link is `challenge_receipt_id`. A failed challenge can support
  `fix-first`/`rethink`, but only passing candidate and challenge evidence can support `ship`.
- `A` binds contract/stage/CB/P/V/final candidate E/root authority and exact dependency A
  provenance. It does not bind state, operation receipts, reports, challenge requests, or
  future identity. Its final candidate E must be later than V and no later than Root's trusted
  observation time.

P1's stdlib-only `scripts/full_protocol.py` canonicalizes/hashes and validates these shapes
and relationships. It does not execute commands, acquire locks, write state, choose a
semantic verdict, spawn a role, or replace schema-2 `candidate.py`. P2/P3 consume this seam
rather than inventing a second contract.

P2's `scripts/workflow.py` is the mechanical storage consumer. `receive` validates one
material/D/delivery-E/bundle plus a separately observed native-runtime receipt before it
publishes an immutable attempt. P2 `assemble --stage` requires exactly the current stage's
work items and carries exact accepted upstream selections forward. Prior A/V/E provenance
and current candidate bytes are checked; a progress marker cannot authorize a stage.
Each stage has non-overlapping owned paths; dependency-ordered later edits use exact before
hashes, replayed in stage order. The original clean Git baseline remains common. It copies that
baseline into an isolated output, applies canonical add/modify/delete bundles by exact
before/after hashes, and publishes I/output identity/schema-2 manifest/CB without semantic
merging. Every mutation uses an immutable intent, expected-version state CAS and immutable
receipt; a repeated operation with changed bytes or selection conflicts.

P3's `scripts/run-check.py` executes only a contract-declared or explicitly registered
probe argv/cwd/timeout under the
exact non-secret environment, in a new 0700 run directory and process group. It preserves
bounded stdout/stderr, exit/timeout/cleanup facts, candidate identity before and after, and
publishes E only with a complete immutable run record and receipt. Nonzero is `fail`;
never-started, timeout, uncertain cleanup, log failure, or candidate drift cannot become
`pass`.

`scripts/review-packet.py` requires those persisted run facts before it freezes a P. It
publishes a canonical authorized challenge request, accepts only the matching challenge E,
and binds request/P/CB/E in CR. Root supplies the observed native reviewer runtime receipt;
the tool requires the exact Sol/high identity and the contracted observed isolation mode, publishes V, and applies the P1
record-review transition. DR remains design-only and cannot carry P/V/A authority. The Sol
thread returns data only; these Root-side tools perform all artifact/state writes.

## Dependencies, recovery, and roots

For stage `S`, `Dep*(S)` is sorted transitive strict-dependency closure. An A map must equal
that closure exactly; each prior A uses the same contract, correct dependency stage, accepted
status, and recursively valid provenance. Missing, extra, stale, wrong-stage, or
cross-contract A rejects.

Each mutating command publishes an intent before artifacts and a receipt after outcome. Same
operation ID plus same request returns its receipt; a changed request conflicts. Preserve
partial, mismatched, drifted, or uninspectable facts as `ambiguous`/`unknown`; never replay.
Assemble considers exactly I, output identity, schema-2 manifest, and CB: none permits a
failure receipt/new op; complete+old-state permits one CAS then receipt; exact state without
receipt permits receipt only; partial/mismatch is ambiguous.

A valid `fix-first` adds V to canonical roots and sets `needs-fix`; `rethink` sets
`needs-decision`; valid `ship` removes only its complete closure and sets
`reviewed-awaiting-final-accept`. Unavailable/invalid keeps current valid V and roots,
sets verdict null and `blocked-unavailable`. No review result directly accepts a stage.

## Environment, correction, and readiness

The child begins with an empty inherited environment in a new 0700 directory. Only ordered,
unique, present non-sensitive entries pass by exact name/value. Sensitive/unclassified needs
are `runtime/environment-unavailable`, never passed, logged, hashed, or cached. Reuse needs
exact scope plus harness/input/runtime/platform/executable/interpreter identity and bounded
logs.

`fix-first` invalidates the candidate/verdict. Terra corrects only released ownership, Root
binds/verifies the changed candidate, and a fresh Sol review follows. For corrected P2 candidates,
review admission checks both observed thread and context against the complete rejection
ancestry. Reuse of either identity, or missing identity needed to prove independence,
refuses the new review. Live consumers bind that ancestry to persisted verdict records,
including accepted dependency stages. Same-candidate evidence continuation and exact
operation replay remain valid; P1 historical interpretation is unchanged. Design approval, stage
progress, or a packet is not readiness. Missing native identity/continuation/isolation,
lock/fsync, environment enforcement, installer, cleanup, or performance evidence remains
explicitly unverified.

## Corrected reviewer admission

Historical `SA-REVIEW-ATTESTATION-1` keeps its original meaning and cannot newly admit a
broad host. New P2 contracts use `SA-REVIEW-ATTESTATION-2`, choosing hard-read-only or
explicit `hard-or-behavioral` before review. Hard-required tasks never fall back.

For behavioral mode, Root begins the observation before dispatching the fresh Sol and
ends it after the response. The tools bind the actual role/model/effort, observed sandbox,
permission profile, exact dispatched prompt digest and candidate. An observed thread ID
is the context fallback when the host supplies no separate context ID. Root supplies the
native observation; a reviewer-authored window or role claim is not a substitute.
The prompt digest binds initial read-only instructions; subsequent requested evidence may
continue that context without widening authority. Scope or permission changes require a
new contract/window.

Before a product candidate exists, `begin-design-window` binds the immutable design input
and `record-design-review --behavioral-window-id` closes that interval. P2 admits DR under
the same explicit hard/behavioral policy but refuses implementation review from that design
reviewer context. Design approval is never a V or Root acceptance.

The window protects every pre-existing task input, including old E and logs. New immutable
run/challenge/probe records may be appended without changing P or C; existing records may
not change or disappear. Each evidence consumer also verifies persisted run provenance.
This is behavioral read-only observation, not a hard sandbox and not proof against a
write that was restored before the final observation. Missing/drifted/rebound observations
refuse admission. Never hide that limitation or weaken a hard-isolation requirement.

New Python probes use the runner's interpreter and macOS sandbox-exec. They can read only
manifest-bound regular candidate files selected by the contract, their registered source,
plus interpreter/system resources and ancestor directory metadata. A directory selector is
expanded to literal files, never a recursive grant; ignored files, Git metadata, and
conventional credential paths are excluded; writes are restricted to a private run directory and networking is denied.
Sandbox executable/profile, source, exact launched argv and output are retained. A missing
sandbox or unsupported interpreter refuses this probe lane. This child sandbox says
nothing about the native reviewer's permissions. No probe policy means no dynamic probes.

P2 contract admission requires an applicable final identity check for every stage. All
`final_candidate_verify: true` checks must use candidate scope and pre-ship phase; the
runner still executes them only after V. Invalid placement or missing coverage fails early.
