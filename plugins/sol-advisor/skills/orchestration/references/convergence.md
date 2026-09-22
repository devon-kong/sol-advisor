# Convergence records

Use these compact records for high-risk, cross-module, long-running, resumed, or repeated
correction work. Routine work can keep the same facts inline. These records support
judgment; completed fields are not proof by themselves.

## Acceptance basis

~~~text
ACCEPTANCE VERSION: <stable label>
OUTCOME: <observable user or system result>
PRESERVE: <interfaces, valid paths, safety properties, and quality targets>
AUTHORITY: <allowed files and actions>
EXCLUDED: <explicit non-goals and prohibited actions>
EVIDENCE: <claim -> required behavioral, integration, benchmark, or inspection evidence>
ASSUMPTIONS: <fact/source, or unverified hypothesis and planned check>
~~~

User instructions and repository contracts remain authoritative. Record their source.
Reasonable implementation choices may be settled within granted authority. A product
change, lower acceptance standard, or wider permission requires new authority rather than
an edited acceptance record.

## Full-route protocol separation

For an explicitly declared `full` route, label the design decision, stage progress, and
final acceptance separately. DR is never candidate, packet, V, or A authority. State
records progress/selection only and cannot replace immutable provenance. Final acceptance
requires the same-candidate chain and a fresh valid `ship`, not a green delivery or design
approval. Use [full-workflow.md](full-workflow.md) for artifact and recovery rules.

## Impact surface

For a local defect, prose is enough. When a mechanism or rule has multiple consumers,
record the minimum auditable table:

~~~text
RULE OR MECHANISM: <what causally connects the locations>
LOCATION | STATUS | REQUIREMENT | EVIDENCE | AUTHORITY
<entry>  | affected | ... | ... | allowed
<entry>  | excluded | ... | ... | n/a
<entry>  | unverified | ... | missing | allowed
<entry>  | affected | ... | ... | out-of-scope
~~~

Inspection scope may be broader than confirmed impact, and confirmed impact may be
broader than mutation authority. Do not collapse these sets. Search results are inventory
evidence; they do not prove runtime semantics.

### Compact causal example

~~~text
RULE OR MECHANISM: publish/send/consume completion identity
PUBLISH: publishAttempt(A, identity={jobId, generation}) | affected | sends both fields
SEND: worker send identity={jobId, generation} | affected | retains that exact identity
CONSUME: consumeResult identity={jobId, generation} | affected | compares both fields
LAST ASYNC BOUNDARY: await final completion, not only the pre-await poll
FINAL DEADLINE DECISION: deadline is decided after that await; a completion observed before
  the next poll is not accepted until its matching final result is consumed
ERROR OR UNKNOWN: expiry returns `TIMEOUT`; a mismatched or absent final result returns
  `UNKNOWN`, never `DONE`
VALID NEIGHBOR: matching final result before deadline returns `DONE`
EXCLUDED CONSUMER: publishAttempt(B) passes the same full identity, awaits its final
  result, and returns typed `TIMEOUT`/`UNKNOWN`; an exercised trace supports exclusion
EVIDENCE-BACKED EXCLUSION: the trace includes the publish, send, consume, final await,
  deadline decision, and typed result for B; a shared name alone does not exclude it
~~~

## Closure record

After correcting a material finding, record:

~~~text
OBSERVED: <concrete failure and consequence>
CAUSE: <supported explanation and confidence>
SURFACE: <affected and explicitly excluded consumers>
CHANGE: <what was corrected and why>
EVIDENCE: <commands, artifacts, and independently derived check; Sol owns technical
validation in full, Root owns route-appropriate verification otherwise>
UNVERIFIED: <remaining uncertainty or none>
~~~

If later evidence contradicts `CAUSE`, `SURFACE`, or `EVIDENCE`, identify the exact
closure claim it falsifies. The next attempt must change the design, inventory, harness,
or other relevant method and name the new information it seeks. A different prompt with
the same method is not a changed attempt.

Formatting-only corrections need the affected structural check but do not force unrelated
business reruns. Preserve evidence that does not depend on the changed bytes.

## Resume record

Use an existing handoff or status artifact when one exists. Otherwise keep one short
record separate from candidate inputs that need to remain stable:

When files are needed, use the single task path in [artifacts.md](artifacts.md). Retain
material failures and required resume inputs; preserving evidence does not require keeping
every duplicate working copy forever. Record that task path in the existing handoff rather
than opening a separate top-level directory for each closure or review.

~~~text
ACCEPTANCE: <version and source>
CANDIDATE: <candidate ID and manifest, or explicit artifact identifiers>
OPEN: <unresolved blocking findings>
LAST CLOSURE: <claim and evidence>
FALSIFIED: <new evidence that changed the prior conclusion, or none>
NEXT: <method, expected new information, and owner>
STOP: <budget, retry, authority, or human-input boundary>
~~~

On resume, compare the record to current files and evidence. Do not carry forward a
`ship`, accepted state, or closure claim when its candidate or supporting conditions no
longer match. Correction budgets are user-defined. An authorized resume preserves prior
failures and the cumulative record; it does not reset a falsified closure.

## Multi-file verification plan

~~~text
FILES: <required files or artifacts>
SCENARIOS: <rejected path and adjacent valid path, with expected result>
MISSING INPUTS: <none, or stop>
EXECUTED: <actual cases matched to SCENARIOS>
RESULT: <evidence beyond exit code or skip count>
~~~

Reject an incomplete plan before claiming verification. This plan may stay inline; it does
not require a separate artifact. Use a stable dependency-complete copy or relevant
pre/post digest when independent writers can change the inputs.
