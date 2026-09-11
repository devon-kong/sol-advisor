# Sol Advisor 0.7.0 forward behavior evaluation

Date: 2026-09-12

## Method

Five fresh agents received the source skill, a realistic request, and only the raw fixture
needed for that request. They did not receive the expected result, could modify only their
isolated temporary Git directory, and could not spawn other agents. The root inspected the
resulting files, reran the relevant tests or probes, and treated agent reports as claims.

This is a forward behavior check of the new workflow. It is not an old/new controlled
benchmark and does not prove lower token use or wall time. Per-agent token and active-time
metrics were unavailable from the evaluation runtime.

## Results

| Scenario | Observed behavior | Root evidence | Result |
|---|---|---|---|
| Routine feature | Selected `solo`, kept acceptance inline, created no convergence artifact or reviewer | Default output stayed `Hello, Ada`; the new option returned `Hello, Ada!`; 2 tests passed | PASS |
| Shared owner rule | Inspected all three public entry points, fixed the two affected consumers, excluded the already-safe one, and tested rejected plus valid paths | `status_job` and `resume_job` now use the existing ownership gate; 4 tests passed | PASS |
| Evidence-only failure | Classified the problem as verification weakness, rejected the suggested duplicate production validation, and replaced source-text assertions with behavioral evidence | Production remained one validation then one write; 2 tests and two root-run mutation probes distinguished duplicate and reordered calls | PASS |
| Falsified closure after resume | Named the false “every public consumer” claim, explained that two tested entries had been generalized to three, then changed the method to per-entry-point probes | `retry_order` was corrected; rejected and valid paths passed; the closure record identifies cause, surface, evidence, and remaining uncertainty | PASS |
| Changed review candidate | Ran the candidate verifier, rejected reuse of the old verdict, then independently reproduced and retained the finding | Verifier exited `1`; `app.py` changed from candidate `013c…f8d4` to `91fc…da40`; the reported false-string defect remained reproducible | PASS |

For the evidence-only scenario, the root reran `python3 -m unittest -v` and then replaced
`pipeline.publish` in memory with each of these two implementations while running
`PipelineTests.test_publish_validates_once_before_writing_once`:

~~~python
def validate_twice(value, validate, write):
    validate(value)
    return write(validate(value))

def write_before_validate(value, validate, write):
    written = write(value)
    validate(value)
    return written
~~~

The independent probe returned:

~~~text
validate_twice: tests_run=1 failures=1 errors=0
write_before_validate: tests_run=1 failures=1 errors=0
~~~

Both mutants were rejected, so the test distinguishes duplicate validation and reordered
write behavior rather than merely passing against the current implementation.

## Fresh review corrections

The first fresh review found that a manifest with an empty `source` object escaped schema
validation and then raised an uncaught `KeyError`, producing exit `1` instead of structured
error exit `2`. It also identified that the two mutation probes had not yet been rerun by
the root. The implementation now requires the exact `source.head` field, has a regression
for structured failure, and the root-run probes above replace the earlier report-only
evidence.

The second fresh review found the same schema-closure risk in `selection`: an unknown
selector with a recomputed candidate ID was misclassified as content drift. The correction
now validates the exact top-level, source, selection, and per-entry fields. Regressions cover
missing and invalid source data, unknown selection semantics, unknown top-level and entry
fields, identifier corruption, and empty stderr for structured errors.

The third fresh review extended that finding to field values: Python boolean `true` was
accepted as schema version `1`, and noncanonical repository or explicit paths could be
accepted or misclassified as drift. Validation now rejects boolean versions, NUL and Git-
impossible relative paths, dot and parent segments, noncanonical absolute repository paths,
and noncanonical explicit inputs while preserving the explicit final-symlink contract.
The related schema sweep also rejects duplicate JSON keys and impossible empty symlink
targets. End-to-end regressions require structured exit `2` with no traceback for each
case.

The fourth fresh review found one remaining value-type edge: JSON arrays or objects in an
entry's `scope` or `type` reached set membership before their string type was checked,
causing an uncaught `TypeError`. Enum fields are now type-checked before membership, and a
final error boundary converts unexpected value/type/key/encoding failures into structured
exit `2`. Regressions cover arrays and objects in both enum fields with empty stderr.

The fifth review was invalid for acceptance because its syntax check generated ignored
`__pycache__` files under the requested-read-only role. Its independently reproducible
finding was retained: a missing gitlink was recorded only as `missing`, so an index OID
change could still match. The root reproduced that result, then changed inventory to read
Git index modes and reject gitlinks/submodules, unsupported modes, and unmerged stages.
Regression coverage exercises a missing gitlink, a present submodule directory, and a
changed gitlink OID; each must return structured exit `2`.

The generated caches were removed, and the repository verifier now compiles source in
memory and runs unit tests with bytecode writes disabled. A subsequent reviewer can rerun
those checks without mutating the working tree merely by importing the test module.

The sixth fresh review found that normal tracked-entry mode and object ID were parsed but
discarded. A staged executable-mode change or staged blob replacement could therefore
reuse a worktree-only candidate. Supported tracked entries now bind index mode and object
ID as well as actual worktree contents. Regressions cover a staged-only executable change,
a staged blob replacement with the worktree present, and an index OID change while the
worktree path remains missing; each returns content-change exit `1`.

The seventh fresh review found a cross-entry-point error boundary: Python 3.12 raises
`RuntimeError` for some symlink loops during `Path.resolve`, while the CLI caught other
path errors only. The structured error boundary now includes that exception. Regressions
cover loops reached through `--repo`, `--output`, an `--input` parent, and `--manifest`,
all requiring exit `2`, JSON error output, and empty stderr.

A related root path audit also rejects a tracked repository entry whose parent has been
replaced by a symlink, preventing Git path identity from silently traversing into an
external directory. Final symlinks remain supported by binding their target text.

## Acceptance

All five planned behaviors were observed without adding a Tester role or changing the
existing route and verdict interfaces. The checks support releasing the workflow for
further real-task use. Claims about cost savings, general defect escape rate, or optimal
retry limits remain unverified and require comparable production-task data.
