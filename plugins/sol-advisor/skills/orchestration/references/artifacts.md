# Artifact layout and retention

Read this reference when a task produces files beyond its intended project changes.
This is a default storage convention, not a new acceptance gate or cleanup authorization.
An explicit user location or existing project convention takes precedence where compatible
with candidate stability. Do not reorganize historical directories as part of adopting it.

## Choose one task location

Resolve the actual workspace root first; for Git work, use the candidate repository root.
Default to `<workspace>/.agent-artifacts/`. Append the anchored `/.agent-artifacts/` entry
to the existing project `.gitignore` when authorized, before freezing; preserve its existing
rules. This keeps generated material out of Git status. If that project file cannot be
edited, the candidate tool still excludes untracked artifact descendants, but report the
remaining Git-status clutter rather than silently changing global Git configuration.

The artifact root and internal manifest parents must be real directories, not symlink
aliases. Keep product source and permanent tests out of this reserved generated-material
namespace. Do not replace or automatically untrack an existing conflicting file or tracked
material. Use an explicit permitted alternative or block artifact-dependent work only.
External manifests remain supported for compatibility, but are not the default layout.

Use a date and short task label plus a unique suffix as the task ID. The enclosing workspace
already separates projects and worktrees; no additional workspace-name/hash directory is
needed. Record the selected absolute task path once in the task prompt or existing handoff;
resumes reuse it.
Different tasks get different task directories; new rounds, findings, and reviewers in the
same task do not get new top-level directories.

~~~text
<workspace>/.agent-artifacts/
  INDEX.md                           # optional navigation when multiple tasks exist
  <date>-<task-label>-<unique-id>/
    work/                            # disposable task-owned working material
      round-01/                      # snapshots, test harnesses, temporary installs/logs
      round-02/
    archive/                         # stable retained evidence, created only when useful
      inputs/<candidate-label>/      # final package and required reproducibility inputs
      logs/                          # selected original failure/control/acceptance outputs
      manifests/                     # candidate manifests at their final absolute paths
      reviews/                       # reviewer verdict and relevant runtime evidence
      report.md                      # final scope, outcome, commands, limitations
      handoff.md                     # only if existing handoff is insufficient
~~~

Create only the directories and records needed by the task. A routine `solo` or `delegate`
edit does not acquire an archive, manifest, full repository copy, or more agents merely
because this layout exists. Assign each auxiliary its owned subdirectory under the same
task path. Avoid a new private driver, duplicate full checkout, or duplicate install for
each test when an existing task tool or stable snapshot suffices.

For an explicitly declared `full` route, retain immutable task contract and
acceptance-relevant immutable artifacts at final task-owned paths before candidate binding.
Mutable state, intents/receipts, design records, progress notes, and final reports are not
candidate identity by default. Do not relabel design approval or progress as final evidence;
use the P/CR/V/A relationship rules in [full-workflow.md](full-workflow.md).

## Place materials by purpose

| Material | Location and lifetime |
|---|---|
| Production changes and meaningful permanent regression tests/fixtures | Existing project source and test directories; part of the deliverable. |
| Intended project documentation and concise status | Existing project documentation/status paths. Finish candidate-bound edits before freezing. |
| Multi-session plans and working handoffs | Reuse existing project records when permitted; otherwise task `work/` while active, or `archive/handoff.md` if needed after closure. |
| Round snapshots, diagnostic scripts, complete intermediate logs, unpacked packages and install prefixes | Task `work/round-NN/`; disposable after closure and dependency checks. |
| One-shot downloads, unpack scratch, test debris | A uniquely owned directory under the OS temporary directory, if losing it cannot prevent resume or acceptance. |
| Essential original failure and valid-control evidence, final commands/results and limitations | Task `archive/`; retain the minimum that supports the conclusion and reproduction. |
| Reviewed manifests, verdicts, final package and required external inputs | Task `archive/` at stable paths before binding; retained for reviewed/high-risk delivery. |

Do not put active multi-session state, the only copy of an unresolved counterexample, or
required acceptance inputs in OS temporary storage. If temporary evidence disappears,
reproduce it or mark the affected claim unverified; do not reuse a verdict without its proof.
Archive evidence must be redacted; do not copy credentials or private session captures
merely to make an archive complete.

## Retain without breaking candidate identity

`archive/` is the stable evidence destination from the outset, not a destination to which
a reviewed directory is later moved. Before the final snapshot, copy only necessary
reproducibility inputs from `work/` to their final archive paths and verify the copied
bytes. External inputs passed to `candidate.py --input` must use those final paths. The
manifest itself belongs in `archive/manifests/`. Follow the original candidate-ID checks
in [operations.md](operations.md); storage changes never relax them.

Keep reviewer returns and final reports in untracked `.agent-artifacts/` after freezing.
New snapshots automatically exclude only untracked descendants of that exact repository-root
directory, regardless of whether the Git ignore entry exists. Tracked artifact files remain
bound; nested or similarly named directories are not automatically excluded. Required
artifact inputs remain bound through explicit `--input`, even when Git ignores them.
Do not bind the still-changing index, handoff, verdict, or final report as an acceptance input. If a
project report must be edited after review, treat that repository change according to the
existing candidate invalidation rules. Prefer artifact-relative references inside the
report for navigation, but do not rewrite paths inside a signed-off manifest or claim a
moved manifest still verifies. Compression alone does not preserve live path availability;
document extraction to original paths if reproduction requires it.

The inventory policy is recorded in selection and hashed into candidate identity. Existing
schema2 manifests using `tracked-and-unignored-untracked` keep that original policy and
must remain outside the repository; they are not silently converted to artifact exclusions.
New manifests use `tracked-and-unignored-untracked-except-root-agent-artifacts` and may
live under root `.agent-artifacts/`. A policy change requires a new candidate and review.
The tool rejects manifests elsewhere inside the repository, self-binding outputs, and
outputs overlapping selected source or explicit inputs, including hardlink aliases.

The optional `scoped-literal-v1` policy is a distinct schema-2 selection identity, not a
reinterpretation of an old manifest. It records canonical non-overlapping literal repository
paths and the source HEAD, rejects dirty/untracked paths outside those scopes unless explicitly
bound, and still hashes selected bytes plus explicit ignored/external inputs. Default and legacy
manifests retain their prior field set and meaning. Fall back to whole-worktree selection when
the dependency boundary is not proven.

Keep only inputs relevant to the acceptance claim. Do not recursively bind every prior
task archive, every installed dependency tree, or all historical logs just because they
exist. Preserve required inputs and failures with their scope; earlier unaffected evidence
may be referenced rather than copied into each new task.

## Close and clean proportionally

At closure, report the task path, retained evidence, disposable work, and unresolved items
in the existing handoff or final response. No separate cleanup report is required. Permanent
regression tests retain the reusable counterexample; archive original output when it supports
a material closure or explains a falsified earlier claim. Duplicate green runs and obsolete
installation prefixes ordinarily need no long-term retention.

Unless a user or project policy says otherwise, recommend a 30-day grace period for
closed-task `work/`; this is not an automatic timer, scheduled cleanup, or permission to
delete. While a task is open or blocked, keep its necessary state and unresolved failures.
Retained high-risk/reviewed evidence has no default expiry; a routine task may need only
its project changes and a concise result, with no permanent external archive.

For corrected full-route tasks, keep the bootstrap record outside the task root under the
stable ancestor and keep review-window attestations/design inputs as immutable relationship
artifacts. Do not move, rewrite, or use a previous record/attestation as a signature for a
new candidate.

Within authorized cleanup, remove only positively identified task-owned disposable files
after confirming no active process, resume record, accepted manifest, or retained report
depends on them. If a retained claim still references `work/`, preserve that material or
obtain new evidence and review where required; do not hide the dependency by relabeling it.
Never clean other tasks, legacy evidence, business runtime locks, credentials, or unrelated
dirty work through this convention.
