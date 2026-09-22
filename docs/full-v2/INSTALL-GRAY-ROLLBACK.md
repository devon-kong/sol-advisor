# Install, gray validation, and rollback

## Current boundary

0.8.0 is an unreleased development source tree. No production plugin/cache/global configuration was
changed during this task. Existing tasks continue to use the version loaded when they started.

The e7da, c7b5 and c23e candidate/review receipts are historical only. c7b5/c23e formal E passed
135/135 and 143/143, but both fresh Sol technical reviews returned `fix-first` and formal V
admission was unavailable. Those 162-test solo-correction records are historical, not current
readiness or a gray gate. Later P2 flow-alignment source review is retained externally at
`.agent-artifacts/20260922-flow-alignment/archive/sol-review-4.md`; its ship applies only to its
recorded candidate. Subsequent repairs need their own candidate and evidence. No hard native V/A
has been signed on this host.
A behaviorally read-only prompt alone is not review admission. P1 remains fail-closed;
new P2 tasks may explicitly use Root-recorded before/after observations. This does not
enforce native read-only permissions or detect write-then-restore. Hard-required tasks
still need a hard-read-only host.

## Isolated companion-role rehearsal

Choose a task-owned directory, never the real global agent directory:

~~~sh
target_dir="$PWD/.agent-artifacts/full-v2-gray/agents"
sh plugins/sol-advisor/scripts/install-agents.sh --target-dir "$target_dir"
sh plugins/sol-advisor/scripts/install-agents.sh --target-dir "$target_dir" --check
sh plugins/sol-advisor/scripts/install-agents.sh --target-dir "$target_dir" --check-role terra --check-role reviewer
~~~

`--check` and `--check-role` are no-write. The installer migrates exact known historical files,
including exact 0.7.3 Terra and Reviewer bytes. A user-modified, symlinked, nonregular, unreadable or
unknown destination is a conflict and must remain untouched.

An explicit `--target-dir` is self-sufficient and does not require `HOME` or `CODEX_HOME`. When the
option is omitted, the installer resolves the default from `CODEX_HOME/agents` or `HOME/.codex/agents`
and fails if neither environment value exists.

## Gray gate

Before any production installation:

1. Run `sh plugins/sol-advisor/scripts/verify.sh` from the development repository.
2. Use a host-supported isolated plugin-development load path and record the actual loaded plugin
   path/version, or explicitly load the workspace Skill/references/role files in each fresh native
   validation session and record their hashes. Do not infer loading from edited source or copy
   authentication into a new home.
3. Start brand-new native tasks. Inspect every spawned role/model/effort; for Sol also inspect the
   actual sandbox/permission profile. Existing tasks are invalid for this proof.
4. Run the required native cases: non-full preservation, one full stage, two independent Terra
   deliveries, shared-interface serialization, critical early failure followed by a fresh complete
   review, unavailable Sol, cancellation/recovery, and final exact-candidate acceptance.
5. Freeze the whole-worktree candidate and obtain a fresh independent Sol ship verdict for that
   exact ID. Do not promote on fixture-only evidence.

Historical development-source sessions and their receipts remain useful examples, but do not prove
the corrected source or supply a current gray verdict. The P2 observation protocol must be exercised with actual native reviewer identity;
synthetic hard-read-only fixtures do not prove hard native V/A. No production
installation was performed.

## Production installation

Use only the documented Codex plugin manager or another host-supported installation flow after the
gray gate passes and the user explicitly authorizes production installation. Then run the companion
installer from the installed plugin directory and start a new task. Do not directly edit plugin cache
or global configuration.

## Rollback

1. Stop creating new 0.8.0 tasks; do not mutate tasks already preserving evidence.
2. Select the previously known-good plugin package/ref through the host-supported plugin manager.
   Baseline source for this project is commit `d5b999bbc68766712895cb83aabcdcc5efcac923`, version
   `0.7.3`; do not assume a tag or marketplace version that has not been verified.
3. Restore companion roles only from that known-good package using its installer. Do not overwrite a
   user-modified role file; resolve the conflict manually with the user.
4. Start a new task and verify the loaded plugin path/version plus role hashes. Existing tasks do not
   hot-reload rollback files.
5. Preserve 0.8.0 manifests, red samples, receipts and reports. Rollback does not rewrite history or
   convert an old verdict into approval of other bytes.

No branch deletion, reset, production deployment, publication or credential operation is part of
rollback.
