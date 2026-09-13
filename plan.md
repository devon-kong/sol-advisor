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
