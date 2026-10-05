# Native operations

This reference owns role pins, spawn mechanics, companion installation, selected-role
preflight, runtime evidence, candidate binding, reviewer isolation, and maintainer
verification. Route selection and root responsibilities belong to [SKILL.md](../SKILL.md);
worker and reviewer prompts belong to [role-contracts.md](role-contracts.md).

For a declared `full` route, use [full-workflow.md](full-workflow.md) before task-contract
publication. Root plans and later binds/verifies the candidate, Sol implementer independently delivers
owned work, and fresh Sol performs critical-then-complete read-only review. Root does not
add a default duplicate technical rerun. No protocol rule authorizes role substitution,
install, credentials, business networking, publication, or push.

## Role pins and spawn mechanics

The installed TOMLs are the source of truth:

| Role type | Model | Effort | Use |
|---|---|---|---|
| sol_advisor_luna_implementer | gpt-6-luna | xhigh | Bounded implementation |
| sol_advisor_sol_implementer | gpt-6.1-sol | high | Judgment-heavy or high-risk implementation |
| sol_advisor_sol_reviewer | gpt-6.1-sol | high | Fresh review; requests read-only sandbox |

Use the selected exact role with a fresh context:

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
A fix invalidates the prior valid verdict; re-verify and obtain a new fresh review as
required by SKILL.md. For `full`, P3 performs the same-observed-context challenge handshake
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

## Reviewer pool operations

Preflight the selected Reviewer once per task; verify role/model/effort/isolation for each
returned native thread. Freeze one candidate and acceptance basis across all N returns.
Queue batches when slots are limited; release completed agents before starting later ones.
Do not pass peer results between Reviewers. Record per-member status, verdict, coverage,
findings and the Root-observed runtime receipt. Root records every finding's disposition
(accept/reject plus evidence-based reason). Aggregate with:

~~~sh
python3 "$skill_dir/../../scripts/review-round.py" aggregate --input "$round_input" --output "$round_result"
# Full: persist under the existing task, then bind this ID in A and final-accept.
python3 "$skill_dir/../../scripts/review-round.py" record --task-dir "$task_dir" --input "$round_input"
# workflow.py final-accept ... --review-round-id <round-id>
~~~

Round input contains round_id, scope, candidate_id, acceptance_digest, members,
dispositions and optional reviewers_per_round (default 2). For full, scope equals P's
stage_key (or final for P1), acceptance_digest equals contract_digest. Each member has
review_id, candidate_id, acceptance_digest, status, verdict, coverage_complete, findings,
and runtime. Findings have finding_id, class, requirement, evidence, impact, scope,
required_outcome and optional root_cause. Dispositions are keyed by review_id:finding_id.
An accepted blocker needs all four requirement/evidence/impact/scope fields and current scope;
an unsupported finding can only be rejected with a concrete Root reason. Every full member
uses the existing tagged attestation admission, including exact runtime/permission/prompt facts.
A broad host additionally names behavioral_window_id: Root must begin before dispatch and end
after the response using review-packet.py's existing window commands. Close every member's
window before publishing V or round records. A boolean is never isolation evidence. Record
validates persisted window digests, candidate and native identities; final-accept/recovery
recheck them. Audit aggregate with behavioral attestations also supplies --review-policy and
--isolation-admission hard-or-behavioral. This is observation, not enforced isolation.

After correction, all identities must be fresh. The tool checks complete persisted round
digests before using history, plus design-review and prior-candidate identities for every
member. The selected canonical V still requires a valid ship response. If every original
member rejected only unsupported findings, Root preserves those raw returns and dispositions;
the selected member can continue in the same context on the settled acceptance basis to
supply canonical V. This is no additional Reviewer and never rewrites the raw return.
The full round gate checks member identity and complete coverage rather than requiring its
original verdict to be ship. Final acceptance requires both the Root-adjudicated round and
that existing valid V. The tool checks persisted full rounds;
audit callers pass every previous result with repeatable --previous. Missing/invalid members,
identity reuse, changed bindings or incomplete coverage prevent acceptance. Design rounds
remain design-only and do not authorize product acceptance.
