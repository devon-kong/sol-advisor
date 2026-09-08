# Native Codex role contracts

Use these contracts with Sol Advisor's namespaced, role-pinned native custom agents.
They do not launch a nested Codex CLI or change global default-agent routing. Route
selection, root responsibilities, escalation, and correction rules belong to
[SKILL.md](../SKILL.md). Use [operations.md](operations.md) for selected-role preflight,
runtime evidence, isolation, and maintainer commands.

Before any spawn, follow the declared route and preflight only the active role. After
each spawn, accept its result only after verifying that exact returned thread. The TOMLs
pin model and effort, so omit native per-spawn overrides.

## Shared implementation contract

Every Luna or Terra prompt must contain all five sections:

~~~text
OBJECTIVE
<Observable outcome and why it matters.>

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
- Run: <exact command>
  Success: <concrete expected result>
- Inspect: <exact file, diff, or generated artifact>
  Success: <concrete expected evidence>

RETURN
Return exact commands and actual evidence. A completion claim without evidence is invalid.

IMPLEMENTATION REPORT
STATUS: complete | partial | blocked
OBJECTIVE: <one-line restatement>
CHANGES: <file-by-file summary from the actual diff>
VERIFIED: <exact commands plus concrete output evidence>
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

ACCUMULATED CHANGE SET
<Exact allowed files plus complete working-tree diff, or explicit base/head revisions.>

INTERFACES AND CONSTRAINTS
- <Compatibility, repository rules, safety boundaries, and excluded scope.>

VERIFICATION EVIDENCE
- <command> -> <actual root output evidence>
- <artifact or diff inspection> -> <actual evidence>

REVIEW
Inspect the actual files and accumulated change set. Judge correctness, completeness,
regressions, scope discipline, interface preservation, test adequacy, and material risk.

REVIEW RESULT
VERDICT: ship | fix-first | rethink
REASON: <decisive evidence-based reason>
FINDINGS: <precise file references and required fixes, or none>
RESIDUAL RISK: <most important remaining risk, or none>
~~~

If any fix is made after review, discard the verdict and run a new fresh review. Use
observed isolation, not requested isolation; operations.md defines the stop conditions.
