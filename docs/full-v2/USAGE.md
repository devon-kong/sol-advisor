# Full-v2 local usage

This document describes the unreleased 0.8.0 source tree. It does not prove that an existing
Codex task has hot-loaded these files.

> New full tasks use `SA-FULL-V2-P2`; active P1 tasks retain their old interpretation.
> The flow-alignment revision has new integration tests and an explicit behavioral review
> path. Its current verification/review status is in `FINAL-REPORT.md` and the retained
> `.agent-artifacts/20260922-flow-alignment/` evidence. Earlier 162-test snapshots and
> historical reviews do not approve these new bytes. No production installation occurred.

## Route behavior

The user supplies a goal and its constraints, not a task-store JSON document. A typical
request is:

~~~text
Use full mode for this change. Plan the dependent stages first. Run independent Sol implementer
work in parallel only when it saves work, and let each Sol implementer deliver its own changes,
tests and self-review. Have Sol validate the actual combined candidate, starting with
critical counterexamples. Root manages decisions and stage acceptance without repeating
the technical review. Do not install or publish without authorization.
~~~

Root constructs the contract and tool records from that goal. The protocol's own
implementation phases are not a mandatory seven-stage template for ordinary tasks.
Use one stage for a bounded coherent result, and several stages when real dependencies
or reviewable milestones justify them. Progress messages keep work visible; ordinary
test failures stay in the responsible Sol implementer's repair loop.

- `solo`, `delegate`, and `audit` retain their prior responsibilities.
- `full` is exceptional. Root writes the immutable task/stage/work/check contract, owns plan,
  scheduling, conflicts, authority and final acceptance. Independent work may use peer Sol implementer
  instances; no Sol implementer leads, aggregates or accepts another Sol implementer.
- Each Sol implementer returns its own M/D/delivery-E and stops writes. Deterministic tools select exact
  attempts and assemble bytes; they never perform a semantic merge or select the “best” result.
- One fresh Sol context checks critical risks and, if they pass, completes the remaining stage
  scope. Sol returns data and does not write product/artifacts. Root-side tools publish challenge,
  CR and V records.
- A fix creates a new delivery/candidate and needs a fresh review. P2 checks both reviewer
  thread and context against persisted rejection ancestry; reusing either identity or lacking
  the identity needed to establish independence is refused. Same-candidate evidence continuation
  and exact replay remain valid. Design approval is never code approval.

## Tool entry points

Run from the repository root:

~~~sh
python3 plugins/sol-advisor/scripts/workflow.py --help
python3 plugins/sol-advisor/scripts/run-check.py --help
python3 plugins/sol-advisor/scripts/review-packet.py --help
python3 plugins/sol-advisor/scripts/candidate.py --help
~~~

`workflow.py` initializes/validates task storage, receives one immutable delivery at a time,
assembles explicit selections from one clean baseline, exposes status, and exposes the
`final-accept` CLI gate, reconstructing prior contexts from retained records. Mutations use operation intents/receipts and expected-version state CAS.

`run-check.py` accepts a contract check key or a registered P2 probe request. The contract supplies argv, cwd, timeout and
environment policy. Do not pass shell text. Candidate checks also need the exact schema-2 manifest
and CB. Result meanings are `pass`, `fail`, or `incomplete`; a PASS-looking log never overrides the
real exit/timeout/candidate facts.

`review-packet.py` has commands for `bundle`, `prepare-challenge`, `record-challenge`,
`record-review`, and `record-design-review`. CLI relationship packages contain the P1 context
fields plus base64 manifest bytes; use the immutable package generated for the selected candidate,
not self-reported IDs.

`prepare-challenge --arg` is repeatable and represents one exact argv suffix vector. Omit it for a
legacy empty suffix; when supplied, every value and order must match a contract-authorized vector.
An unlisted vector is rejected before an intent is published.

For a tagged design review, `--design-input` is required. Its only design verdicts are
`design-approved`, `fix-first`, and `rethink`. Dispatch Sol with `REVIEW_SCOPE: design`
and retain its `DESIGN_VERDICT`; unavailable/invalid uses null. Product scopes
(`stage`, `final`, `stage+final`) return `VERDICT`, whose positive result is `ship`.
Do not translate a product verdict into design approval or the reverse.

The repository verifier initializes fixture scratch directories automatically. On a failed
suite, its JSON includes `diagnostic.path` and `diagnostic.sha256` for the original traceback
and captured output. This exclusive temporary log survives the verifier's own cleanup;
copy it into the task archive when retaining long-term evidence.

The offline action-trace grader requires ordered `stages` with `stage_key` and required
`work_keys`. Lifecycle events bind `stage_key`/`attempt_id`, with delivery and candidate
identities linking each handoff. It reports `compliant`, `complete`, and `status` separately:
a valid prefix is `incomplete` with `passed: false`; only all declared stages accepted in
order can pass. This calibrates trace evaluation, not native Agent behavior or runtime V/A.

## Stages, late checks and new probes

For new tasks, Root selects `protocol: SA-FULL-V2-P2`. Every work item has a `stage_key`;
every stage declares `stage` or `stage+final` review scope. The sole terminal stage covers
the final goal. Required checks declare `phase: pre-review` or `phase: pre-ship` and
`required: true|false`; an optional `stage_key` limits a check to that stage. Omit it for
a check needed at every stage. Candidate checks may use `cwd: "$candidate"` to execute
against the exact assembled workspace instead of a guessed future path.

Root calls `assemble --stage <stage>` with only that stage's selections. Tools verify the
accepted upstream chain and combine its retained deliveries with the new work. Root does
not ask a Sol implementer to aggregate peer results. A terminal review covers this actual cumulative
candidate; summaries of separate green tests are insufficient.

`bundle` freezes the pre-review evidence. After critical challenges, run required pre-ship
checks against the same CB and pass their JSON list to `record-review --pre-ship-evidence`.
They are bound to V without changing P. Missing/failed required evidence blocks ship;
optional checks are not silently made required. `final_candidate_verify: true` is a
separate identity check after V, not a pre-ship business-test rerun. P2 requires each
stage to have an applicable final check declared with candidate scope and pre-ship phase;
a misplaced or missing final check is rejected when the contract is initialized.

For a new probe, the optional contract `probe_policy` bounds the Python interpreter,
timeout, task-relative read paths and environment, and forbids network. Root saves Sol's
probe source in its owned temporary input area, then calls:

~~~sh
python3 plugins/sol-advisor/scripts/review-packet.py register-probe \
  --task-dir "$task_dir" --relationship "$relationship" \
  --request-id "$request_id" --source "$probe_source" --timeout-seconds 10
~~~

Run the returned request through `run-check.py`, using `__new_probe__` as the check key and
`challenge-<request-id>` as the run ID, then `record-challenge` as for a predeclared check.
The runner binds the registered source and actual sandbox policy. On macOS, reads are
restricted to regular candidate files selected by the declared paths, the registered
probe source, and Python/system runtime resources. Directory selectors never grant recursive
reads: ignored files, Git metadata, and conventional credential paths remain unreadable. Writes go to a
private run directory, and network is denied. Another interpreter or missing sandbox
refuses dynamic probe execution; it does not weaken the policy. Sol never edits product.

For explicit behavioral review under `SA-REVIEW-ATTESTATION-2`, Root calls
`begin-behavioral-window` before native reviewer dispatch. After the response, Root
supplies the observed native runtime and the same `--behavioral-window-id` to
`record-review`. Existing evidence/log bytes are protected, while new immutable checks may
append. `end-behavioral-window` can close the interval explicitly; exact retries are
idempotent. This observation cannot detect write-then-restore and does not enforce native
read-only permissions. Hard-required review still needs an observed hard-read-only host.

For design review before a product candidate exists, Root calls
`begin-design-window --task-dir "$task_dir" --window-id "$window_id" --design-input "$design_input"`
on `review-packet.py`, then dispatches the design reviewer. Pass the same input and
`--behavioral-window-id` to `record-design-review`. Design and implementation review
require different observed native contexts. A design-approved DR never authorizes delivery.

The contracted prompt digest binds the initial read-only reviewer instructions. Subsequent
messages may deliver requested evidence within that authority; a change to permissions or
review scope needs a new contract/window, not an evidence-only continuation.

After V and the distinct final candidate identity check, Root calls:

~~~sh
python3 plugins/sol-advisor/scripts/workflow.py final-accept \
  --task-dir "$task_dir" --op-id "$accept_op" \
  --expected-state-version "$state_version" --acceptance "$acceptance" \
  --final-evidence "$final_evidence" --root-authority "$root_authority" \
  --trusted-observation-time "$observation_time"
~~~

The tool loads the stored review and dependency contexts; Root does not construct a
nested ancestry JSON by hand. Inputs to this command are Root's decision and observed
identity facts, not a substitute for a valid current Sol verdict.

## Candidate selection

Default, compatible whole-worktree snapshot:

~~~sh
python3 plugins/sol-advisor/scripts/candidate.py snapshot \
  --repo "$repo" --output "$manifest" --input "$retained_input"
~~~

Optional scoped mode, only after proving the dependency boundary:

~~~sh
python3 plugins/sol-advisor/scripts/candidate.py snapshot \
  --repo "$repo" --output "$manifest" \
  --scope plugins/sol-advisor --input "$retained_input"
~~~

Scoped mode binds the literal scope list and Git HEAD, rejects unbound dirty/untracked paths outside
the scope, and still binds explicit ignored/external inputs. It is slower on the measured small
fixture; use whole-worktree whenever dynamic loading, generated files or dependencies are uncertain.

Before review, after review and before final acceptance, verify the original ID:

~~~sh
python3 plugins/sol-advisor/scripts/candidate.py verify \
  --manifest "$manifest" --expected-candidate-id "$candidate_id"
~~~

Never regenerate an ID and treat it as the reviewed expected ID.

## Four full-route examples

These examples show the orchestration shape. The JSON files are immutable records produced from
the task contract and observed native runtime; they are not hand-written substitutes for Agent
identity. `expected-state-version` must come from the immediately preceding `status` result.

### One Sol implementer, one stage

Root creates a contract with one work item, one owner and one common Git baseline, then initializes
the task store:

~~~sh
python3 plugins/sol-advisor/scripts/workflow.py init \
  --task-dir "$task_dir" --contract "$inputs/contract.json" --state "$inputs/state.json"
~~~

Root sends Sol implementer the complete objective/acceptance, owned files, interfaces, constraints and
verification contract directly. For a development-source trial, include the exact
`plugins/sol-advisor/agents/sol-advisor-sol-implementer.toml` path and hash. The worker loads that
core, its contract and relevant product code; Root keeps orchestration-reference loading and
tool publication. Add a specific risk-method reference only when the owned work needs it.

After the native Sol implementer completes its own implementation, tests and self-review, Root records that
single delivery without re-performing its technical work:

~~~sh
python3 plugins/sol-advisor/scripts/workflow.py receive \
  --task-dir "$task_dir" --op-id receive-api-1 --expected-state-version 0 \
  --material "$inputs/api/M.json" --delivery "$inputs/api/D.json" \
  --delivery-evidence "$inputs/api/E.json" --bundle "$inputs/api/bundle.json" \
  --runtime-receipt "$inputs/api/runtime.json"

python3 plugins/sol-advisor/scripts/workflow.py assemble \
  --task-dir "$task_dir" --op-id assemble-stage-1 --stage "$stage_key" --expected-state-version 1 \
  --baseline-repo "$baseline_repo" --selected "$inputs/selected-api.json"
~~~

Root runs only the contract's mechanical pre-review checks. A fresh Sol then performs the critical
challenge and remaining-scope review on the assembled candidate. A `ship` is valid only after its
runtime, challenge, E/CR and V relationships pass `review-packet.py inspect` and the original
candidate ID still verifies.

### Two independent peer Sol implementer deliveries

Root first proves that `api` and `docs` have disjoint ownership and no unresolved shared mutable
interface. The two native Sol implementer tasks may then run concurrently. They remain peers and each returns
its own M/D/E/bundle/runtime package. Durable receipt publication is serialized through state CAS:

~~~sh
python3 plugins/sol-advisor/scripts/workflow.py receive \
  --task-dir "$task_dir" --op-id receive-api-1 --expected-state-version 0 \
  --material "$inputs/api/M.json" --delivery "$inputs/api/D.json" \
  --delivery-evidence "$inputs/api/E.json" --bundle "$inputs/api/bundle.json" \
  --runtime-receipt "$inputs/api/runtime.json"

python3 plugins/sol-advisor/scripts/workflow.py receive \
  --task-dir "$task_dir" --op-id receive-docs-1 --expected-state-version 1 \
  --material "$inputs/docs/M.json" --delivery "$inputs/docs/D.json" \
  --delivery-evidence "$inputs/docs/E.json" --bundle "$inputs/docs/bundle.json" \
  --runtime-receipt "$inputs/docs/runtime.json"

python3 plugins/sol-advisor/scripts/workflow.py assemble \
  --task-dir "$task_dir" --op-id assemble-stage-1 --stage "$stage_key" --expected-state-version 2 \
  --baseline-repo "$baseline_repo" --selected "$inputs/selected-api-docs.json"
~~~

`selected-api-docs.json` maps each work key to one exact delivery ID. Overlap, a different baseline
or a stale state version is rejected; Root resolves the cause and returns it to the responsible work
item. No Sol implementer merges, accepts or summarizes the other Sol implementer's result. Sol reviews the real combined
candidate, not two green summaries.

### High-risk design challenge before implementation

For a genuinely high-risk decision, one Sol implementer may produce a design/probe record without changing
the product. A fresh design Sol challenges that record. Root publishes the observed review through
the tool rather than letting Sol write task artifacts:

~~~sh
python3 plugins/sol-advisor/scripts/review-packet.py record-design-review \
  --task-dir "$task_dir" --review "$inputs/design-review.json" \
  --design-input "$inputs/design-input.json" \
  --reviewer-runtime "$inputs/design-sol-runtime.json"
~~~

A valid design `design-approved` permits implementation to start; it is not product approval.
The eventual code candidate must be reviewed by a different fresh Sol context. A correction creates
a new candidate and another fresh implementation review.

### Interrupted mutation and recovery

There is deliberately no `workflow.py recover` command. Recovery is tied to the immutable operation
intent: inspect state, then repeat the *same* command with the *same* operation ID and identical
request bytes.

~~~sh
python3 plugins/sol-advisor/scripts/workflow.py status --task-dir "$task_dir"

python3 plugins/sol-advisor/scripts/workflow.py assemble \
  --task-dir "$task_dir" --op-id assemble-stage-1 --stage "$stage_key" --expected-state-version 2 \
  --baseline-repo "$baseline_repo" --selected "$inputs/selected-api-docs.json"
~~~

The tool returns the existing receipt, completes a safe state/receipt transition from verified
durable outputs, or records an ambiguous/failure receipt. Never change inputs under the same
operation ID. If source bytes, baseline or selection changed, preserve the old evidence and start a
new operation/candidate; uncertain side effects require Root reconciliation rather than replay.

## Evidence interpretation

Unit tests, deterministic trace graders, real Agent behavior and independent review are different
evidence classes. P2 supports explicitly contracted behavioral reviewer admission through a
Root-observed begin/end window. That window is not hard isolation and cannot detect write-then-restore.
Hard-required tasks still need an observed read-only host. Current native evidence must name its
exact source candidate and task; historical runs do not approve later bytes. The five paired cases are bounded earlier implementer runs rather than a
three-repeat end-to-end full-route comparison. See `FINAL-REPORT.md`, `metrics.json` and
`docs/full-v2/REQUIREMENTS-MAP.md` before claiming readiness, cost reduction or production safety.
