---
name: orchestration
description: "Codex-native risk-gated selective routing: default solo delivery, targeted native delegation or audit, and exceptional full review. For root startup, load only skill guidance, then declare the route before other task tools; never batch loading with task discovery."
---

# Sol Advisor Orchestration

Act as the architect. Own the user's intent, acceptance basis, architecture, route choice,
decomposition, implementation or delegation, root verification, correction decisions,
and final acceptance. Selective routing has four exact modes: `solo`, `delegate`, `audit`,
and `full`. Solo is the default. One auxiliary agent is the default maximum; full is an
explicit broad or high-risk exception.

Read [references/role-contracts.md](references/role-contracts.md) before the first
delegation or review. Use [references/operations.md](references/operations.md) for exact
spawn, preflight, runtime evidence, candidate binding, isolation, and maintainer
procedures. For high-risk, cross-module, long-running, resumed, or correction-loop work,
read [references/convergence.md](references/convergence.md) and use only the artifacts the
task needs.

Before creating task artifacts, read [references/artifacts.md](references/artifacts.md).
Use one task directory under workspace-root `.agent-artifacts/` for generated material;
put correction rounds and auxiliary lanes beneath it, rather than creating more project
siblings. Keep disposable work separate
from retained acceptance inputs before binding a candidate. Routine work needs no artifact
directory unless it actually produces files, and no mandatory archive or manifest.

## Declare the route before task tools

Before declaring a route, the root may read this skill and the references directly linked
from it, read-only. All other repository or memory inspection, tests, task tools, and
task-scoped commands require the declaration first.
After guidance-only loading, declare the route before inspecting any task files.
Do not batch skill/reference loading with repository discovery or other task tools before
the declaration.

Before the first task tool call, emit one machine-auditable declaration:

~~~text
SELECTIVE ROUTE
mode: solo | delegate | audit | full
risk: <concise, task-specific rationale>
~~~

No other task tool call may precede this declaration. Choose `solo` unless a stated risk
justifies another mode. A later declaration may only escalate the route when newly
observed risk justifies it; never silently downgrade. Record the evidence for an
escalation. Details and the task-scoped preflight matrix are in operations.md.

## Preflight and verify only the active auxiliary stage

Solo checks no auxiliary. Immediately before spawning Luna or Terra, non-mutatingly
preflight only that selected implementer. Immediately before spawning the Reviewer at
the review stage, preflight only the Reviewer. In `full`, do not preflight the Reviewer
at route start: delivery or mechanical admission may prevent that stage from being reached.

After each actual spawn, accept its result only after verifying the exact returned
native thread's role, model, and effort. Public metadata is authoritative; if it omits
a model or effort, use the local inspector only for that omitted field. The Reviewer
also needs observed sandbox and permission handling. Missing, conflicting, unavailable,
or unobservable evidence stops only the affected lane; never silently substitute a role,
model, effort, or reviewer.

## Route delivery without duplication

- `solo`: root plans, implements, tests, and self-reviews; spawn no auxiliary.
- `delegate`: select Luna / Max for bounded, fully specified work, or Terra / High for
  judgment-heavy, high-risk, context-heavy, or wide-blast-radius work. The selected
  implementer executes the complete spec; root verifies; do not request a fresh review.
- `audit`: root implements and verifies; a fresh read-only Sol / High reviewer reviews
  the accumulated diff; spawn no implementer.
- `full`: only for an explicit broad or high-risk exception. Root owns plan, identity,
  decision, release, and final acceptance; it schedules one or more peer Terra stage
  deliveries under the immutable task contract, then fresh Sol performs technical
  validation. Root investigates exceptions and binds identity, but does not perform a
  default technical rerun or duplicate diff review.

For `full` only, read [full-workflow.md](references/full-workflow.md) before writing the
task contract or worker prompt. It defines the immutable/mutable boundary, Terra peer
delivery, Sol challenge lifecycle, design/stage/final separation, recovery, and acceptance
provenance; it does not alter the three non-full routes.
Root loads these orchestration references once. For full workers, send the complete owned
work contract, exact development role-core path/identity when applicable, and only the
specific risk references needed by that work. Do not make each Terra repeat Root's
SKILL/operations/artifact initialization; workers still inspect actual code and consumers.

Auxiliary work must substitute for root work, not duplicate it. A Luna result may
justify escalation to Terra / High only when it reveals newly observed complexity,
risk, wide blast radius, or misclassification. A corrected Luna attempt is reserved
for a specification error and is not a prerequisite for Terra. Any route change must
be declared and evidenced; do not silently downgrade.

## Establish one acceptance basis

Before implementation, translate the user goal and repository contracts into one
traceable acceptance basis: observable outcome, preserved behavior, material quality
targets, allowed scope, excluded scope, evidence needed, and unverified assumptions.
This is an interpretation of the goal, not permission to replace it, lower its standard,
or widen authority. Explore first when a material assumption is cheaply testable.

Keep this basis in the task prompt for routine work. Use the compact artifact in the
convergence reference only when multiple handoffs, risk, or task length makes continuity
valuable. For cross-module delivery, prove an early path through real module boundaries;
replace only genuine external boundaries such as the network. Choose evidence for the
claim: integration is not automatically stronger than a targeted concurrency or recovery
test.

## Keep root responsibilities with the root

Keep these responsibilities with the root:

- Resolve requirements, material ambiguity, and conflicts in the acceptance basis.
- Choose architecture, interfaces, decomposition, and selective route.
- Write the complete worker specification for any selected implementer.
- For `solo`, `delegate`, and `audit`, inspect the actual diff and rerun the
  route-appropriate verification.
- For `solo`, `delegate`, and `audit`, independently derive at least one check for each
  material risk instead of only replaying implementer evidence. In `full`, Root instead
  verifies identity/provenance and investigates a concrete exception; Sol owns technical
  validation.
- Separate inspected, confirmed-affected, and authorized-to-change surfaces.
- Decide whether newly observed risk warrants escalation.
- Judge the reviewer verdict when the route includes review and accept the deliverable.

Every worker prompt must contain OBJECTIVE AND ACCEPTANCE, FILES AND OWNERSHIP,
INTERFACES, CONSTRAINTS, VERIFICATION, and the structured implementation return in
[the role contracts](references/role-contracts.md). State the exact owned files,
preserve concurrent edits, and never silently widen scope.

Treat worker reports as claims. In `solo`, `delegate`, and `audit`, confirm the complete
diff, changed-file scope, requested checks, and artifact/runtime evidence as Root. In
`full`, confirm structured delivery identity/provenance and only investigate a concrete
exception; do not duplicate peer Terra or Sol technical work.

## Keep verification evidence stable

Every mode needs stable evidence. A worker stops writes to files handed to the root when
it returns, and does not resume those writes until the root releases that file set. In
`solo`, the root tests after its own edit. If independent writers exist, verify against a
stable dependency-complete copy or record a relevant pre/post digest around the check.
An edit invalidates only the evidence that depends on changed bytes; retain earlier,
reproducible failures and unaffected evidence with their scope. Formatting-only corrections
need the affected structural checks, but do not by themselves force unrelated business
reruns.

For a multi-file change, the acceptance basis must name the required files and scenarios.
The plan may be inline; it does not require a separate artifact. Reject a plan with missing
inputs, and compare the executed cases with that plan. Exit zero or a zero-skip report
alone is not behavioral proof.

## Close findings by cause and evidence

Every mode, including `solo`, handles a discovered defect with the same sequence: preserve
or reproduce the failure, inspect causally related consumers, correct confirmed defects
within authority, then verify the rejected path and an adjacent valid path. This sequence
does not create an automatic extra agent, reviewer, manifest, table, or repository-wide
sweep. Use a compact table only when multiple consumers make it useful; local prose is
enough otherwise.

Apply the same handling to findings from implementation, root verification, and review:

- Implementation behavior violates acceptance: identify the supported cause, inspect
  causally related surfaces, correct within authority, and verify.
- Test or evidence is insufficient: improve the proof; do not change production behavior
  without evidence of an implementation defect.
- Architecture or acceptance terms cannot all hold: the root resolves the design or scope;
  do not send the unchanged specification back for another local patch.
- Environment or tool capability is missing: restore the condition or block only the
  affected stage.
- Candidate, role, isolation, or review evidence is invalid: reject that verdict, preserve
  any independently reproducible finding, stabilize the conditions, and review again.
- A suggestion is outside accepted scope: record it separately; it is not a required fix.

On the first defect, inspect the causally related surface. For a rule shared across entry
points, enumerate its actual consumers and record affected, excluded, unverified, or
out-of-authority status. For validation, recovery, and fail-closed changes, check an
adjacent valid path as well as the rejected path. A shared label alone does not establish
a shared cause or authorize a common abstraction.

When new evidence falsifies a prior closure claim, do not repeat the same correction loop.
Before the next attempt, state what the prior reasoning missed, what method now changes,
and what new evidence the attempt should produce. If the mechanism is already shown
infeasible, rethink immediately rather than waiting for a repeat count. Rejecting a
finding requires counterevidence or an explicit acceptance-basis citation; changing
reviewers never clears an unresolved valid finding. Correction budgets are user-defined;
on an authorized resume, preserve prior failures and the cumulative closure record.

## Review only when the route includes it

For `audit`, after Root verification, spawn a new native Sol / High reviewer. For `full`,
after structured Terra deliveries and identity binding, spawn a new native Sol / High
technical reviewer. The reviewer must remain behaviorally read-only, inspect the actual
accumulated diff, and return `REVIEW_STATUS: valid|unavailable|invalid`; only valid carries
exactly one of ship, fix-first, or rethink. A reviewer never implements its own fixes. For
every high-risk or repeated-omission principal material
risk, it must offer a fresh behavior challenge or actual-code equivalence reasoning; a
hash or log alone is not approval. `solo` and `delegate` do not receive a fresh reviewer.

- ship: report completion with the verification evidence.
- fix-first applies only to `audit` and `full`:
  - audit: the root implements the required correction, re-verifies, and obtains a new
    fresh reviewer.
  - full: the relevant peer Terra stage handles the required correction; Root binds the
    new delivery/candidate identity, and a new fresh Sol technical review follows.
  - solo and delegate: no fresh reviewer is added unless a newly observed,
    risk-evidenced route escalation is declared; never silently add one.
- rethink: revise the architecture and do not report completion.

Any implementation correction invalidates the prior verdict. Apply the observed sandbox
and permission profile rules in the operations reference; never claim enforced
read-only isolation when it was not observed.

For `audit`, acceptance requires the frozen acceptance basis, resolved blocking findings,
Root verification against the same candidate, and a valid fresh `ship`. For `full`, it
requires the frozen basis, structured peer delivery/candidate identity, resolved blocking
findings, and fresh Sol technical `REVIEW_STATUS: valid` with `ship`; Root then makes the
final acceptance decision without a default technical rerun. For `solo` and `delegate`,
apply the same acceptance basis and Root evidence without adding a reviewer. A time or
retry limit may produce an honest partial or blocked result; it never turns unmet acceptance
into completion.
