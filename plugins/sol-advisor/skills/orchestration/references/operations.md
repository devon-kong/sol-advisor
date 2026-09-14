# Native operations

This reference owns role pins, spawn mechanics, companion installation, selected-role
preflight, runtime evidence, candidate binding, reviewer isolation, and maintainer
verification. Route selection and root responsibilities belong to [SKILL.md](../SKILL.md);
worker and reviewer prompts belong to [role-contracts.md](role-contracts.md).

## Role pins and spawn mechanics

The installed TOMLs are the source of truth:

| Role type | Model | Effort | Use |
|---|---|---|---|
| sol_advisor_luna_implementer | gpt-5.6-luna | max | Bounded implementation |
| sol_advisor_terra_implementer | gpt-5.6-terra | high | Judgment-heavy or high-risk implementation |
| sol_advisor_sol_reviewer | gpt-5.6-sol | high | Fresh review; requests read-only sandbox |

Use the selected exact role with a fresh context:

~~~text
agent_type: sol_advisor_luna_implementer
fork_turns: none
~~~

~~~text
agent_type: sol_advisor_terra_implementer
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
byte-exact historical Luna/Terra templates; modified, unsafe, nonregular, symlinked,
or conflicting destinations remain refusals, with all mutation preflighted.

For task-scoped preflight, non-mutatingly check only the role about to be spawned:

| Stage | Companion check |
|---|---|
| Before Luna | `--check-role luna` |
| Before Terra | `--check-role terra` |
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

A Reviewer returns exactly `ship`, `fix-first`, or `rethink`. A fix invalidates the
prior verdict; re-verify and obtain a new fresh review as required by SKILL.md.

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

Select the stable task archive location using [artifacts.md](artifacts.md) before snapshot.
Put the manifest and required external inputs at their retained paths from the start;
do not move a reviewed directory from temporary work to an archive afterward.

For `audit` and `full`, bind root verification, the reviewer return, and final acceptance
to the same candidate. Use the shipped tool for a Git working tree when its inventory
covers the reviewed inputs:

~~~sh
skill_dir=<directory-containing-this-SKILL.md>
candidate_tool="$skill_dir/../../scripts/candidate.py"
candidate_id="$(python3 "$candidate_tool" snapshot --repo "$repo" --output "$manifest" | jq -er '.candidate_id | select(type == "string")')"
python3 "$candidate_tool" verify --manifest "$manifest" --expected-candidate-id "$candidate_id"
~~~

Default to `<repo>/.agent-artifacts/<task-id>/archive/manifests/` for the manifest.
Only that repository-root artifact namespace permits internal manifests; other internal
locations are rejected. External manifests remain supported for compatibility. New snapshot
selection excludes untracked descendants of root `.agent-artifacts/`, never tracked files
or nested/similarly named directories. The policy is hashed into candidate identity;
existing schema2 manifests keep their original recorded policy and external-only location.
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
Create a new snapshot only after correction and root re-verification. Preserve any
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
