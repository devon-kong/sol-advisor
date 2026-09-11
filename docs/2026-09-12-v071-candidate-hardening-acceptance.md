# Sol Advisor 0.7.1 candidate-hardening acceptance

Date: 2026-09-12

## Acceptance basis

Acceptance version: `V0701-PATH-CANDIDATE-1`.

The accepted implementation must reject mutable parent aliases for explicit inputs,
prevent manifest output from overwriting bound inputs or links, reject link loops without
mutation on the tested Python runtimes, and let formal verification require the exact
candidate ID supplied to review. It must preserve ordinary repository paths, stable
external files, distinct manifest outputs, final-component input symlinks, the four
routes, the three native roles, and the existing verdict enum.

This iteration excludes a Tester role, model or role changes, global installation,
publishing, and claims about arbitrary concurrent filesystem attackers or reduced
production cost. Candidate schema version 1 is intentionally not migrated because it
cannot recover path identity that was not recorded.

## Implemented behavior

- Candidate schema version 2 includes the schema version in candidate identity.
- Explicit inputs reject `..` and symlinked parent components; a final-component symlink
  remains bound by its link text.
- Manifest output accepts a missing path or an existing regular file under a resolvable
  directory. A final symlink, dangling link, loop, directory, or special file is rejected.
- Output that is the same selected input by path or existing file identity is rejected
  before writing.
- `verify --expected-candidate-id` returns `0` only when the manifest, current contents,
  and earlier candidate ID all match. A well-formed ID mismatch returns changed exit `1`;
  malformed IDs and invalid manifests return structured exit `2`.
- Reviewer and operations contracts require the root-verified candidate ID, the
  reviewer's `REVIEWED_CANDIDATE`, and the final expected ID to agree.

## Root verification

The root independently inspected the complete eight-file implementation diff before this
report was added. No role, model, route, installer, or verdict definition changed.

Both available runtimes passed the candidate behavior suite:

~~~text
Python 3.12.14: Ran 19 tests ... OK
Python 3.14.7: Ran 19 tests ... OK
~~~

The repository verifier completed with:

~~~text
VERIFY PASSED: Sol Advisor v0.7.1 convergence checks completed
~~~

Independent temporary-repository probes on both runtimes established all of the
following:

- a parent-directory input alias is rejected and an existing output sentinel is retained;
- a stable input path snapshots and verifies successfully;
- same-path and hard-link input/output overlaps are rejected without changing either file;
- a cyclic output link is rejected and both links retain their original targets;
- after candidate A is replaced by B at the same manifest path, A's expected ID returns
  changed while B's expected ID matches;
- a schema version 1 manifest returns structured instructions to regenerate, reverify,
  and rereview.

`git diff --check` passed. Python 3.13 was not available locally and is not claimed as a
verified runtime.

## Fresh-review closure

The first fresh reviewer examined candidate
`sha256:cf67728275081b60263bf96bef5f4eadf7dc7d9a15542c89e8fcce65a3bb90e0`
and returned `fix-first`. It found that the schema-version-1 guidance read `.get()` from a
top-level JSON value before proving that the value was an object. Arrays, `null`, and
strings therefore escaped the structured error boundary with `AttributeError`.

The prior validation sweep covered object fields and values but missed top-level JSON
types. The correction changed the method: `validate_manifest` now rejects non-object
values before any field access, and the CLI regression sweeps an array, `null`, and a
string. The root reran that table independently on Python 3.12 and 3.14 and observed exit
`2`, JSON `status: error`, and empty stderr for every value. Both full candidate suites and
the complete repository verifier passed again. The first verdict and candidate are not
eligible for final acceptance; a new candidate requires a new fresh review.

## Isolated installation and execution

A fresh temporary Codex data directory installed the local marketplace as enabled version
0.7.1. Its cached plugin tree matched the working source, and all three companion roles
installed and passed the exact role check. The actual global plugin remained enabled at
version 0.6.1 and was not modified.

The isolated data directory contained no authorized login and no API or access token was
available in the process environment. A launch probe reached Codex sampling and failed
with HTTP 401 before an agent response. Credentials were not read, copied, or linked into
the isolated directory. Consequently, the planned installed-plugin `solo` and `full`
behavior scenarios have not run; they share this missing authentication prerequisite.

## Acceptance state

Implementation and root verification are complete and eligible for candidate-bound fresh
review. The overall iteration remains `PARTIAL`: isolated installation passed, while the
installed-plugin `solo` and `full` execution evidence is blocked by isolated authentication.
Publication, global installation, and controlled production trial remain outside this
iteration.

The exact candidate ID is recorded in the external review handoff and final acceptance
check. It is deliberately not embedded here because this report is itself part of the
candidate contents.
