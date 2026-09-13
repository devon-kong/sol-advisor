# Native Codex role contracts

Use these contracts with Sol Advisor's namespaced, role-pinned native custom agents.
They do not launch a nested Codex CLI or change global default-agent routing. Route
selection, root responsibilities, escalation, and correction rules belong to
[SKILL.md](../SKILL.md). Use [convergence.md](convergence.md) for conditional acceptance,
impact, closure, and resume records. Use [operations.md](operations.md) for selected-role
preflight, runtime evidence, candidate binding, isolation, and maintainer commands.

Before any spawn, follow the declared route and preflight only the active role. After
each spawn, accept its result only after verifying that exact returned thread. The TOMLs
pin model and effort, so omit native per-spawn overrides.

## Shared implementation contract

Every Luna or Terra prompt must contain these sections:

~~~text
OBJECTIVE AND ACCEPTANCE
<Observable outcome, acceptance version or inline basis, preserved behavior, and evidence
needed. Distinguish sourced requirements from unverified assumptions.>

FILES AND OWNERSHIP
You own only:
- <exact file or module>

You are not alone in the codebase. Other agents or the user may be editing concurrently.
Preserve their edits, do not revert unrelated work, and adapt to changes already present.
Do not modify files outside your ownership.

INTERFACES
- <Signatures, types, schemas, commands, or behavior that must remain compatible.>

CONSTRAINTS
- <Repository conventions, safety boundaries, excluded scope, and settled decisions.>

VERIFICATION
- Plan: for a multi-file change, name required files and scenarios before running checks;
  reject missing inputs and compare actual executed cases with the plan. Exit 0 or zero
  skips alone is insufficient.
- Run: <exact command>
  Success: <concrete expected result>
- Inspect: <exact file, diff, or generated artifact>
  Success: <concrete expected evidence>
- Root check needed: <material risk the root should verify independently, or none>

RETURN
Return exact commands and actual evidence. A completion claim without evidence is invalid.
At handoff, stop writes to files handed to the root until the root explicitly releases
those files. Preserve reproduced failures and state `none` or `unverified` explicitly.

IMPLEMENTATION REPORT
STATUS: complete | partial | blocked
OBJECTIVE: <one-line restatement>
CHANGES: <file-by-file summary from the actual diff>
IMPACT SURFACE: <causally related locations: affected, excluded, unverified, or outside
authority; use the convergence table only when multiple consumers make it useful>
EVIDENCE MAP: <acceptance claim -> actual evidence>
VERIFIED: <exact commands plus concrete output evidence>
UNVERIFIED: <claims not established by the evidence, or none>
JUDGMENT CALLS: <decisions the specification left open, or none>
GAPS: <unfinished work, ambiguity, or none>
~~~

## Luna / Max - bounded implementation

Use only when the declared route selects bounded, fully specified work. A first result
that demonstrates newly observed judgment-heavy, high-risk, wide-blast-radius, or
misclassified work may justify declared Terra escalation; do not force a retry first.
A corrected Luna attempt is reserved for a specification error and is not a prerequisite
for Terra.

Spawn exactly:

~~~text
agent_type: sol_advisor_luna_implementer
fork_turns: none
~~~

Prompt:

~~~text
ROLE
Act as Sol Advisor's default routine implementation worker. Execute the supplied
specification within the settled architecture, preserve every stated interface and
constraint, and surface ambiguity instead of redesigning the architecture.

<paste and complete the Shared implementation contract>
~~~

## Terra / High - higher-risk implementation

Use only when the declared route selects judgment-heavy, high-risk, context-heavy, or
wide-blast-radius work, including risk revealed by a first Luna result. A corrected Luna
attempt is reserved for a specification error and is not a prerequisite for Terra.

Spawn exactly:

~~~text
agent_type: sol_advisor_terra_implementer
fork_turns: none
~~~

Prompt:

~~~text
ROLE
Act as Sol Advisor's explicit high-complexity escalation worker. Resolve the supplied
specification within the settled architecture, preserve every stated interface and
constraint, and surface ambiguity instead of redesigning the architecture.

<paste and complete the Shared implementation contract>
~~~

## Reviewer - requested-read-only review

After root verification when the declared route includes review, spawn exactly:

~~~text
agent_type: sol_advisor_sol_reviewer
fork_turns: none
~~~

The installed Reviewer pin is Sol / High and requests a read-only sandbox. Observe the
actual role, pin, sandbox policy, and permission profile before accepting its verdict.

Prompt:

~~~text
ROLE
Act as the fresh final reviewer. Remain strictly read-only: do not edit files, implement
fixes, or broaden scope.

STATED GOAL
<The user's requested outcome.>

ACCEPTANCE BASIS
<Versioned or inline outcome, preserved behavior, authority, exclusions, evidence, and
material assumptions.>

ACCUMULATED CHANGE SET
<Exact allowed files plus complete working-tree diff, or explicit base/head revisions.>

CANDIDATE
<Candidate ID and manifest or other exact artifact identifiers.>

INTERFACES AND CONSTRAINTS
- <Compatibility, repository rules, safety boundaries, and excluded scope.>

VERIFICATION EVIDENCE
- <command> -> <actual root output evidence>
- <artifact or diff inspection> -> <actual evidence>

REVIEW
Inspect the actual files and accumulated change set. Judge correctness, completeness,
regressions, scope discipline, interface preservation, test adequacy, and material risk.
Derive findings from the acceptance basis and actual evidence. A proposed remedy is not
proof of the finding. Keep scope-only improvements out of required findings.

For every high-risk or repeated-omission principal material risk, offer either a fresh
behavior challenge or actual-code equivalence reasoning. Read-only in-memory probes are
allowed. Any write experiment belongs to the root's isolated environment. Do not require a
full rerun when a focused challenge is sufficient, and do not approve from a hash or log
alone.

For each finding return:
FINDING: <stable task-local ID>
CLASS: implementation | verification | architecture-contract | environment | candidate-review
REQUIREMENT: <acceptance-basis citation>
IMPACT: <concrete consequence>
EVIDENCE: <reproduction, file reference, or explicit reasoning>
RELATED SURFACE: <causally related consumers to inspect, without assuming all are affected>
OWNERSHIP: implementer | root | environment | review
REQUIRED NEXT ACTION: <outcome needed; separate an optional remedy suggestion>

REVIEW RESULT
REVIEWED_CANDIDATE: <exact candidate ID supplied in CANDIDATE>
VERDICT: ship | fix-first | rethink
REASON: <decisive evidence-based reason>
FINDINGS: <structured findings above, or none>
RESIDUAL RISK: <most important remaining risk, or none>
~~~

If any fix is made after review, discard the verdict and run a new fresh review. Use
observed isolation, not requested isolation; operations.md defines the stop conditions.
