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
