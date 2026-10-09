# Native operations

This reference owns role pins, spawn mechanics, companion installation, selected-role
preflight, runtime evidence, candidate binding, reviewer isolation, and maintainer
verification. Route selection and root responsibilities belong to [SKILL.md](../SKILL.md);
worker and reviewer prompts belong to [role-contracts.md](role-contracts.md).

For a declared `full` route, use [full-workflow.md](full-workflow.md) before task-contract
publication. Root plans and later binds/verifies the candidate, Sol implementer independently delivers
owned work, and policy-selected Sol performs critical-then-complete read-only review. Root does not
add a default duplicate technical rerun. No protocol rule authorizes role substitution,
install, credentials, business networking, publication, or push.

## Role pins and spawn mechanics

The installed TOMLs are the source of truth:

| Role type | Model | Effort | Use |
|---|---|---|---|
| sol_advisor_luna_implementer | gpt-6-luna | xhigh | Bounded implementation |
| sol_advisor_sol_implementer | gpt-6.1-sol | high | Judgment-heavy or high-risk implementation |
| sol_advisor_sol_reviewer | gpt-6.1-sol | high | Fresh or budget-authorised continuing review; requests read-only sandbox |

Use the selected exact role with a fresh context for a new identity. For an authorised
sequential continuation, resume the last native Reviewer via followup_task rather than spawn:

~~~text
agent_type: sol_advisor_luna_implementer
fork_turns: none
~~~

~~~text
agent_type: sol_advisor_sol_implementer
fork_turns: none
~~~

~~~text
agent_type: sol_advisor_sol_reviewer
fork_turns: none
~~~

Do not attach model or reasoning overrides. Missing, conflicting, unavailable, or
unobservable role/model/effort evidence stops the active auxiliary stage; never
substitute another role.

## Install, update, and selected-role preflight

Plugin installation does not register user-owned TOMLs. At installation or update time,
run the repository-relative installer and its all-role exactness check:

~~~sh
sh plugins/sol-advisor/scripts/install-agents.sh
sh plugins/sol-advisor/scripts/install-agents.sh --check
~~~

When operating from an installed skill, resolve the same script relative to this
reference's parent skill:

~~~sh
skill_dir=<directory-containing-this-SKILL.md>
installer="$skill_dir/../../scripts/install-agents.sh"
sh "$installer" --check
~~~

The installer is fail-closed and post-install checks exactness. It migrates only
byte-exact historical Luna and old-name implementer templates; modified, unsafe, nonregular, symlinked,
or conflicting destinations remain refusals, with all mutation preflighted.

For task-scoped preflight, non-mutatingly check only the role about to be spawned:

| Stage | Companion check |
|---|---|
| Before Luna | `--check-role luna` |
| Before Sol implementer | `--check-role implementer` |
| Before Reviewer | `--check-role reviewer` |

`--check-role` is repeatable for compatibility, but route stages use one active role.
The legacy `sol` value remains an alias for `reviewer`. A selected check reads and
validates only its selected template and destination; all-role `--check` validates all
three. Unknown or missing role arguments fail before destination mutation. Cache a
successful selected check only for the current task.

## Runtime routing evidence

After every actual spawn, inspect the exact returned native thread before accepting its
result. Verify the selected role, model, and effort; for a Reviewer, also verify
observed sandbox and permission handling. Do not validate an unspawned auxiliary. A
failure stops only that stage.

Public spawn/details metadata is authoritative. Prefer the UUID supplied by public details when present.
An initial public receipt need not contain a UUID when authoritative records
can recover identity. If it is omitted, read only public metadata and local allowlisted
session fields to recover one unambiguous native UUID tied to this spawn: match the root
parent UUID and the exact returned canonical path, and match the public call ID when it is
available. An absent, ambiguous, multiple, or conflicting mapping pauses only the active
lane. Never pass a canonical path as a UUID, and never guess a thread, model, or role.

Pass only that provided or uniquely recovered UUID to the helper resolved relative to the
installed skill:

~~~sh
skill_dir=<directory-containing-this-SKILL.md>
runtime_inspector="$skill_dir/../../scripts/inspect-agent-runtime.sh"
sh "$runtime_inspector" <native-subagent-thread-id>
~~~

The helper emits allowlisted routing fields and refuses invalid IDs, zero/multiple
matches, missing fields, or conflicting values. Public and local evidence must agree; a
conflict refuses the active lane. This is not a role fallback, a resolver CLI, a helper
adapter, or a general runtime tool.

## Reviewer isolation

The Reviewer TOML requests `sandbox_mode = read-only`. Capture the observed sandbox
policy and permission profile:

- Observed read-only: isolation is enforced.
- Broader host policy: continue only when hard isolation is not required, the prompt
  forbids edits, and the root captures exact before/after repository and artifact state.
- Unobservable isolation, required hard isolation, or any mutation: stop the review and
  do not claim read-only isolation.

A Reviewer always returns `REVIEW_STATUS: valid|unavailable|invalid`. A valid status has
exactly one `ship|fix-first|rethink` verdict; unavailable/invalid has `VERDICT: null`.
A fix invalidates the prior valid verdict; re-verify and obtain the next fresh Reviewer
or the last-Reviewer continuation under the sequential policy. Historical pools still
require fresh correction rounds, as defined in SKILL.md. For `full`, P3 performs the same-observed-context challenge handshake
and record publication described in full-workflow.md.

## Mechanical full-task storage

For a full task, `scripts/workflow.py` owns only deterministic task storage. Initialize or
validate a task directory before receiving attempts. Each `receive` call names one operation
ID, expected state version, material, D, passing delivery E, canonical bundle and observed
runtime receipt. Each `assemble` call names an exact work-key-to-D selection and a clean
common-baseline repository. Inputs are validated before the intent is published; published
records are create-no-replace and byte-identical retries are idempotent.

The state file has one task lock and expected-version CAS. Assembly copies the baseline and
applies only declared byte changes; path overlap, aliases, changed ready bytes, dirty or
different baselines, missing attempts and changed same-operation requests reject. Complete
artifacts with old state may receive one CAS; state-after with no receipt writes only the
receipt; no outputs records failure/new-operation; partial or drifted output remains
ambiguous and is never replayed. These commands do not choose a delivery semantically or
grant review/acceptance authority.

Run predeclared checks and explicitly registered P2 probes through `scripts/run-check.py`, not shell interpolation or a summary
wrapper. A check record is reusable only when its immutable E, run record, operation receipt,
bounded log hashes, command/harness, exact environment/runtime identity and candidate binding
remain applicable. A zero exit without these facts is not evidence. A timeout targets the
authorized process group; uncertain residual cleanup remains incomplete.

Build P and record challenges/reviews through `scripts/review-packet.py`. Candidate E without
complete `run-check` provenance is rejected before P. Challenge E uses its canonical request
ID/digest and does not recursively become a new review packet. The reviewer runtime receipt
is redacted to supported native identity fields and must prove the Sol/high role and the contract-selected isolation mode;
self-reported role text cannot substitute it. Candidate verification runs again before V is
recorded, so an old response cannot sign changed bytes.

## Stable evidence and verification plans

For every route, a handed-off worker stops writes to its handed-off files until the root
releases them. The root tests after its own `solo` edit. With independent writers, use a
stable dependency-complete copy or record a relevant pre/post digest around the check.
Edits invalidate only evidence that depends on changed bytes; a candidate-bound review is
still unusable when its selected input changes. Formatting-only corrections need affected
structural checks, not unrelated business reruns.

For a multi-file verification plan, name required files and behavioral scenarios before
execution. The plan may be inline; no separate artifact is required. Reject missing inputs
and compare actual executed cases with the plan. An exit status of zero or zero skips is
insufficient without those cases and their expected results.

## Stable candidate binding

Select one external temporary task directory using [artifacts.md](artifacts.md) before
snapshot. Keep manifests and required inputs at their original paths until closure.

For `audit`, bind Root verification, the reviewer return, and final acceptance to the same
candidate. For `full`, bind structured peer delivery identity, the Sol technical return, and
final acceptance to the same candidate; Root uses this identity check and investigates a
concrete exception, not a default technical rerun. Use the shipped tool for a Git working
tree when its inventory covers the reviewed inputs:

~~~sh
skill_dir=<directory-containing-this-SKILL.md>
candidate_tool="$skill_dir/../../scripts/candidate.py"
candidate_id="$(python3 "$candidate_tool" snapshot --repo "$repo" --output "$manifest" | jq -er '.candidate_id | select(type == "string")')"
python3 "$candidate_tool" verify --manifest "$manifest" --expected-candidate-id "$candidate_id"
~~~

Default to `$task_dir/manifests/` outside the product repository. Do not create project
artifact roots or edit its ignore file. Historical schema-2 manifests retain their recorded
inventory and location semantics; legacy internal manifests remain supported explicitly.
Snapshot includes tracked files, other unignored untracked files, actual worktree bytes
and executable state, and each supported
tracked entry's Git index mode and object ID. Add each ignored or repository-external input
that affects acceptance with a repeatable `--input <path>`. Explicit inputs reject a
symlinked parent directory so a mutable alias cannot silently bind a different file; a
final-component symlink remains bound by its target text. Record the acceptance version,
candidate ID, evidence references, and relevant runtime facts separately; generated logs
and caches do not belong in the candidate unless they affect the conclusion. Candidate
manifests use schema version 2; version 1 is rejected with instructions to regenerate,
reverify, and rereview rather than migrated.

Whole-worktree selection remains the default. `candidate.py snapshot --scope <literal-path>`
opts into `scoped-literal-v1`; repeat the flag only for non-overlapping paths whose complete
dependency boundary has been established. Scoped identity binds the canonical literal scope
list, current Git HEAD, selected tracked/untracked bytes and every explicit input. Dirty or
untracked paths outside the scopes are rejected unless that exact path is explicitly bound;
verify repeats the same rule and a changed HEAD invalidates the candidate. Ignored/external
runtime inputs still require `--input`. Use whole-worktree when dependencies, dynamic loading,
aliases or generated inputs are uncertain. Scoped mode is not a cache and never trusts only
mtime/size.

Unreadable files, directories, Git links/submodules, symlinked repository parents, devices,
sockets, and other unsupported input types fail comparison instead of being silently
omitted. Bind a submodule commit or other compound artifact separately when it affects
acceptance. A final symlink is bound by its target text; bind the target separately when its
contents affect the conclusion.

Verify immediately before review, after review, and before final acceptance with the
original `candidate_id` passed as `--expected-candidate-id`. Exit `0` means the selected
bytes and metadata still match that exact reviewed candidate, `1` reports changed paths or
an expected-ID mismatch, and `2` means comparison could not be established. Only `0`
supports reuse of the verdict. The reviewer must return `REVIEWED_CANDIDATE` equal to the
root-verified `candidate_id`; root final acceptance requires that returned value and the
final expected ID to be identical. Root must not derive the final expected ID from a
regenerated or current manifest after review. The tool treats HEAD as source
information rather than proof, and it does not prove semantic correctness, reviewer
isolation, or absence of a temporary mutation that was later restored.

If review begins on one candidate and any selected input changes, stop using that verdict.
Create a new snapshot after correction and the route's required verification: in full,
Root checks delivery identity and Sol performs technical validation; the other routes
retain their Root verification responsibilities. Preserve any
independently reproducible finding from an invalid review. For non-Git or artifact-only
work, bind explicit immutable artifact identifiers and hashes instead of creating a Git
repository solely for this protocol.

## Maintainer verification

From the repository root, run:

~~~sh
sh plugins/sol-advisor/scripts/verify.sh
git diff --check
git status --short
git diff --stat
~~~

The verifier covers the v0.7.3 manifest, exact role inventory/pins, installer safety and
selected-role isolation, all runtime-role fixtures, route and convergence contracts,
candidate-tool behavior, README scope, JSON/TOML parsing, and shell/Python syntax. The
candidate behavior suite was verified on Python 3.12 and Python 3.14; do not treat that
as evidence for untested Python versions.

## Correction-era full-route storage and review admission

For a new full-route contract that opts into `SA-REVIEW-ATTESTATION-1`, task mutation is
fail-closed when the host lacks descriptor-relative publication primitives. Task root,
bootstrap record/lock, and task lock must remain identity-continuous; do not substitute a
normal pathname write after a failed fd capability or identity check. Candidate checks rebuild
only through the manifest's complete recorded selection. The actual `run-check.py` source and
declared acceptance materials must be candidate-bound for candidate scope; interpreter and
child executable remain E-only identities and are rechecked after execution.

For P1 / `SA-REVIEW-ATTESTATION-1`, broad-host publication remains unavailable. New P2
contracts explicitly choose `SA-REVIEW-ATTESTATION-2` and an admission policy. In behavioral
mode, call `review-packet.py begin-behavioral-window` before native dispatch, retain the
actual native runtime receipt and exact prompt digest, then pass the window ID to
`record-review`. Existing input bytes must remain unchanged; new immutable check records
may append. Root-side tooling binds the final metadata rather than asking Sol to predict a
future observation digest. It cannot detect a write restored within one window and must
not be reported as enforced read-only isolation. Hard-required contracts still refuse a
broad host. Old evidence stays historical and cannot approve new bytes.

## Sequential Reviewer operations

Preflight Reviewer once per task, and verify each new native role/model/effort/permission
identity. Start every new Reviewer with `fork_turns: none`; continue the last native
Reviewer with followup_task only when its identity budget is reached (or for unchanged
candidate evidence continuation). Preserve its exact thread and context. For broad-host
review, create and close a new observed begin/end window for every new candidate, including
continuations; do not claim enforced isolation from a read-only boolean.

New full contracts declare review_strategy sequential-budget-v1 and max_reviewers (default 2).
Each input to review-round.py has review_strategy, round_id, scope (P's stage_key),
candidate_id, acceptance_digest, one member, dispositions, closure_dispositions, and
previous_round_id/previous_round_digest (both null for the first step). Each member has
review_id, persisted verdict_id, Root-observed runtime, status, verdict, coverage_complete,
findings and any behavioral_window_id. Full recording rechecks persisted V/runtime/context,
challenge and predecessor provenance. Persist a rejection step before its successor V.

`dispositions` covers exactly this member's findings by review_id:finding_id, with accept
or reject and a reason. `closure_dispositions` covers all previously accepted findings by
round_id:review_id:finding_id: open, resolved plus current evidence, or reject plus evidence
and reason. Even previously resolved findings remain accounted for in every later step.
record-review binds review_sequence, reviewed_candidate_id and review_history from actual
persisted steps; callers do not invent these fields. All statuses consume identities. Canonical
V admission, step publication and recovery recheck this exact observed identity history
independently of the valid-rejection closure. Conflicting or omitted historical metadata fails.
Every old step re-admits its runtime and persisted begin/end window using its own candidate,
not the latest candidate. Missing or changed old provenance stops the affected lane. Exact
same-candidate operation replay retains that V's own history prefix and trusted sequence;
changed replay input or a new operation ID for an existing V cannot reapply old state.
The chain is linear, digest-bound and stage-scoped; omitting, forking, changing budget,
returning to an earlier Reviewer or adding N+1 is rejected. After a fix, old ship never
signs new bytes. A complete current valid ship can be fresh or same-context.

~~~sh
# Standalone audit: pass the complete earlier steps in predecessor order.
python3 "$skill_dir/../../scripts/review-round.py" aggregate --input "$step_input" --previous "$prior_step" --output "$step_result"
# Full: the task owns the policy, prior steps, observed windows and V provenance.
python3 "$skill_dir/../../scripts/review-round.py" record --task-dir "$task_dir" --input "$step_input"
# workflow.py final-accept ... --review-round-id <latest-step-id>
~~~

First-step audit omits --previous; later steps supply it once for every prior record.
Final acceptance and recovery recheck all persisted history, current-candidate identity,
exact latest canonical V, closures, coverage and observed permissions. Design contexts
cannot be reused as product Reviewer identities or substitute for product coverage.
Historical reviewers_per_round inputs keep the old exact-count independent pool and
fresh-after-correction semantics. Existing contracts are never silently migrated.
