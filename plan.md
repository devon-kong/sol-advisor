# Sol Advisor 0.7.1 implementation plan

## Outcome

Keep the existing `solo`, `delegate`, `audit`, and `full` routes and the three pinned
native roles. Improve first-pass completeness and correction convergence with a shared
acceptance basis, causal impact-surface checks, explicit failure attribution, independent
root verification, stable-candidate evidence, and resumable closure records.

## Changes

- Extend the orchestration and role contracts without making heavy artifacts mandatory
  for routine work.
- Add a convergence reference for acceptance, impact-surface, closure, and resume records.
- Harden the deterministic candidate snapshot/verification tool: explicit inputs must use
  stable parent paths, manifest outputs must not overwrite selected inputs, and a formal
  verification can require the earlier reviewed candidate ID. It checks reviewed worktree
  bytes, executable state, and relevant Git index mode/object IDs, but does not infer
  correctness, root cause, or enforced isolation.
- Preserve existing role TOMLs, installer behavior, route names, verdicts, and selected-role
  runtime checks.
- Update the local plugin version to 0.7.1, candidate schema to version 2, and document
  only Python versions actually exercised by the candidate behavior suite.

## Verification

- Extend the repository verifier and add behavioral tests for candidate contents,
  untracked and explicit inputs, mode and symlink changes, invalid manifests, and failure
  handling.
- Run isolated Agent scenarios for routine work, related consumers, evidence-only failure,
  repeated closure failure, and candidate/reviewer invalidation. At least one scenario
  exercises a fresh review.
- Run the complete verifier, skill validation, Python tests, and `git diff --check`.

## Boundaries

Do not add a Tester role, change model pins, alter global installation, commit, or push.
Keep the historical retrospective unchanged. A failed behavioral scenario remains an
explicit delivery gap rather than being hidden by wording-only checks.


# Sol Advisor 0.7.2 execution plan (2026-09-13)

Current authorized work: implement the conversation-approved plan. Preserve the prior
0.7.1 plan above as history. Every mode fixes discovered defects through causal consumer
inspection and negative/valid-path proof; ordinary work stays lightweight. Add stable
verification handoff, required-test coverage checks, and high-risk review challenges.
Keep four routes, three roles, their pins, verdicts, candidate schema2 and tool APIs.

Root owns this plan, five generic behavioral fixtures, independent verification and final
acceptance report. Terra owns source rule references, UI metadata, README, manifest and
verify.sh. No global config/cache installation, business repo edits, commit or push.

Before new rules are evaluated, fixture expectations are frozen: routine remains light;
shared quantity validation rejects bool across all three consumers while quote stays;
delegate stops writer or invalidates drifting dependency proof; falsified early-check
closure must cover both publish/merge final identity and expiry; read-only review rejects
matching-byte candidate with absent required test and post-prepare expired publication.
No expected outcomes are sent to evaluator agents; they receive only raw copied inputs.

Run full verifier and existing19 candidate tests, validate skill/plugin, perform five fresh
forward behavior evaluations, inspect outputs/root-derived checks, then bind source and
evidence to a fresh full-mode review. Correct valid findings with Terra, rerun affected
checks and obtain fresh review. Deliver scoped local0.7.2 acceptance, no cost claims.


## 2026-09-13 explicit publication authority update
Userrequested optimizationbackgrounddocumentation and workspaceupload toGitHub after
development; useralsoexplicitly forbidslocalinstallation. Supersedes priorno-commit/push
for intendedsource/fixtures/audit/background/acceptanceallowlist only. Preparebackground
and portablevalidationrecord, stageallowlist BEFOREnewcandidate/freshreview (indexbound),
then commit/pushverifiedfinalcandidatewithoutforce, inspectremoteSHA/filecompleteness.
Preserveunrelateduntracked installedv071admission and localonlycaches/scratch; noinstall
or globalconfigchanges. Initialfreshreview V072-RUNTIME-UUID-001 fix-first acknowledged;
correctactiveUUIDrecoverydocument/verification first, then obtainnewfreshreview.

## 2026-09-14 artifact layout and retention optimization

Scope: improve future Sol Advisor artifact rules only. Do not move, delete, or inspect
historical business evidence further. Preserve unrelated dirty work and installed caches;
this source update does not authorize installation, publication, commit, or push.

Use one external artifact root, one workspace identity, and one stable task directory.
Rounds and auxiliary lanes stay beneath that task. Keep disposable work separate from
retained acceptance inputs from the start, so final manifests never need a path-breaking
archive move. Formal tests and project documentation use existing repository conventions;
post-freeze review records remain outside the candidate. Ordinary work stays lightweight.

Root owns source guidance, the conditional artifact reference, README explanation, and
validation. Change no candidate schema, role pins, route selection, or installer behavior.
Check cross-reference consistency, complete plugin verification, skill/plugin validation,
and whitespace. Report that guidance validation is not proof of future agent compliance.

### 2026-09-14 user correction: keep artifacts inside the workspace

Supersedes the external-default layout above for future tasks. Use workspace-root
`.agent-artifacts/<task-id>/{work,archive}` and an anchored Git ignore entry. Candidate
snapshots exclude only untracked descendants of that reserved root, never tracked files
or similarly named/nested paths. Explicit `--input` still binds required archive inputs.
Permit internal manifests only within that stable directory; reject aliases and overlap.

Bind the inventory policy into candidate identity, keep old schema2 manifests on their
original policy, and retain outside manifests for compatibility. Do not migrate old business
evidence or install/publish this update. Add behavioral tests for ignored/unignored artifact
writes, explicit input drift, tracked and neighboring source changes, manifest self-binding,
symlink/overlap failures, and old-policy verification. Run complete verification and a
fresh independent forward check of the revised tool before reporting its limits.

### 2026-09-14 publication authority

User explicitly authorized commit and push to GitHub. Publish the artifact-layout update
as 0.7.3, with manifest/verifier version alignment. Stage only the intended source, tests,
guidance, README, ignore rule, and this plan; keep local evidence and unrelated untracked
assets untouched. Revalidate release metadata and staged bytes, bind a new staged candidate,
commit and push without force, then verify remote SHA and every published file. No local
plugin installation or global configuration change is authorized by this publication.
