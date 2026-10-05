# Temporary runtime storage

Sol Advisor does not require or create a project `.agent-artifacts/` directory. Routine
solo/delegate work needs no runtime directory. Product source, permanent tests and intended
documentation follow the project's existing conventions. Do not add an artifact ignore
entry to a user's repository or move/delete historical evidence to adopt this policy.

When audit/full tools need file-backed state, allocate one private, uniquely owned directory
outside the product repository under the OS temporary directory:

~~~sh
runtime_dir="$(mktemp -d "${TMPDIR:-/tmp}/sol-advisor.XXXXXX")"
runtime_dir="$(cd "$runtime_dir" && pwd -P)"
task_dir="$runtime_dir/task"
~~~

Use the canonical absolute path (macOS temporary paths can have a system symlink ancestor).
Leave `task_dir` absent until workflow.py init creates it; the private parent also owns its
bootstrap records. Do not pass the already-created mktemp parent as the task root.
Record it once in the task prompt or existing handoff. Reuse that same directory across
reviewers, batches and correction rounds. Never copy prior artifact trees into a new
candidate. Tools still support an explicit user-approved external persistent location.

Keep only necessary runtime state, manifests, checks, probes and review returns. Immutable
records stay at their original paths throughout the active task; candidate-bound external
inputs must not move. Reports can cite existing project tests and the final chat result;
there is no mandatory archive, full checkout per reviewer, retention timer or cleanup report.

Temporary storage can disappear. Missing state means the affected provenance, resume and
acceptance claim is unavailable: recreate the evidence and obtain fresh review, never infer
success. If reliable cross-session recovery or long-lived proof is needed, select an explicit
persistent external location before binding inputs. Do not promise durable resume from TMPDIR.

After closure, clean only positively identified task-owned disposable temporary files when
no active process, unresolved failure, resume record or retained claim depends on them and
cleanup is authorized. Open/blocked tasks retain necessary state. Historical project artifacts,
other tasks, credentials, runtime locks and unrelated work are never cleanup targets.

Candidate schema-2 inventory policies retain their original interpretation. The existing
root-artifact exclusion remains for compatibility with historical workspaces; tracked files
and explicit inputs stay bound. Internal manifests are a legacy opt-in, not the default.
New manifests belong outside the product repository. Changes to selected bytes still invalidate
review. See [operations.md](operations.md) for candidate verification.
