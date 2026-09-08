# Native operations

This reference owns role pins, spawn mechanics, companion installation, selected-role
preflight, runtime evidence, reviewer isolation, and maintainer verification. Route
selection and root responsibilities belong to [SKILL.md](../SKILL.md); worker and
reviewer prompts belong to [role-contracts.md](role-contracts.md).

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

Public spawn/details metadata is authoritative. If it omits model or effort, resolve
the helper relative to the installed skill and inspect the exact native thread ID:

~~~sh
skill_dir=<directory-containing-this-SKILL.md>
runtime_inspector="$skill_dir/../../scripts/inspect-agent-runtime.sh"
sh "$runtime_inspector" <native-subagent-thread-id>
~~~

The helper emits allowlisted routing fields and refuses invalid IDs, zero/multiple
matches, missing fields, or conflicting values. If public and local evidence both
exist, they must agree. It is not a model-selection fallback.

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

## Maintainer verification

From the repository root, run:

~~~sh
sh plugins/sol-advisor/scripts/verify.sh
git diff --check
git status --short
git diff --stat
~~~

The verifier covers the v0.6.1 manifest, exact role inventory/pins, installer safety
and selected-role isolation, all runtime-role fixtures, route contracts, README scope,
JSON/TOML parsing, and shell syntax.
