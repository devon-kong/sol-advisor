# Sol Advisor

Sol Advisor is a Codex-only workflow for capability-routed software delivery. You
provide the outcome and constraints; the root owns planning, implementation or
delegation, verification, and acceptance.

## Install from GitHub

You need a current Codex CLI or ChatGPT desktop app with plugins enabled, native
custom-agent support, jq, and Python 3. The candidate behavior suite is verified on Python
3.12 and 3.14; other Python versions are not claimed here. Luna / XHigh, Sol implementer / High, or
Sol reviewer / High access is needed only when that auxiliary is used. The source
templates pin both Sol roles to `gpt-6.1-sol` / `high`; Luna stays at `gpt-6-luna` /
`xhigh`. This source change does not update an existing plugin or installed roles.

This source tree describes the `0.9.0` full-v2 protocol with orchestration review rounds. Installing from a
published marketplace ref may still load an older version; verify the installed manifest
and start a new task before evaluating full-v2 behavior.

~~~sh
codex plugin marketplace add devon-kong/sol-advisor --ref main
plugin_dir="$(codex plugin add sol-advisor@sol-advisor --json | jq -er '.installedPath | select(type == "string" and length > 0)')" && test -d "$plugin_dir" && test -f "$plugin_dir/scripts/install-agents.sh" && sh "$plugin_dir/scripts/install-agents.sh"
~~~

The companion installer verifies the three exact role files after installation. It
fails closed: modified, unsafe, nonregular, symlinked, unknown, or differing files are
left untouched. It does not edit Codex configuration. Start a fresh Codex task after
installation so native roles are discovered.

Use this prompt in the new task:

~~~text
Use $sol-advisor:orchestration to build this feature and verify it. You may read this
skill and its linked guidance first; declare the selective route before other task tools.
~~~

## Routes

| Mode | Use it when | Delivery |
|---|---|---|
| `solo` | Default; risk is contained. | Root plans, implements, tests, and self-reviews. |
| `delegate` | A complete spec is better executed by one implementer. | Luna / XHigh for bounded work, or Sol implementer / High for judgment-heavy or high-risk work; root verifies. |
| `audit` | Independent final scrutiny matters more than delegation. | Root implements; the configured fresh read-only Reviewers inspect the diff. |
| `full` | Explicit broad or high-risk exception. | Root schedules independent peer Sol implementer work when useful, tools assemble exact deliveries, and the configured fresh read-only Sol Reviewers check the real combined candidate. |

Solo is the default. Delegate uses at most one implementer; audit/full default to
`reviewers_per_round = 2`. A user may request any positive integer, including 1, 3 or 10.
This is the number of independent fresh Reviewers in one round, not a correction-round limit.
When runtime slots are limited, Root runs batches and keeps the same candidate frozen.
Reviewers never see peer results before returning. Root adjudicates findings against
requirement, evidence, impact and scope, groups duplicate causes, and never uses majority
votes or adds an N+1 tie-breaker. Unavailable results stop acceptance; corrections require
an entirely fresh round. Full remains an explicit exception and may use independent peer
implementers when useful. The root declares a `SELECTIVE ROUTE` with the mode and concise risk
rationale before the first task tool call. It can escalate only when newly
observed risk justifies it and never silently downgrades. You do not need to select or
manage a lane.

Auxiliary work substitutes for root work; it does not duplicate it. In `solo`, `delegate`,
and `audit`, existing Root verification responsibilities remain. In `full`, each Sol implementer owns
its own implementation, tests, self-review and delivery; there is no lead/integrator Sol implementer.
The Root plans, schedules, resolves interface or authority conflicts, binds the mechanically
combined candidate and makes final acceptance without a default duplicate technical rerun.
Each fresh Sol context performs critical checks and then the remaining stage review.
Any implementation correction requires a new candidate and fresh review.

The root also keeps one acceptance basis across implementation and review. When a defect
appears, it preserves or reproduces the failure, checks causally related consumers, fixes
confirmed defects within scope, and checks the rejected path plus a valid neighbor. This
does not automatically add agents or broad review work. Multi-file checks name the files
and scenarios they actually ran; a green command alone is not enough. Repeated corrections
must change the failed method and seek new evidence. Reviewed Git work is bound to an exact
candidate snapshot so a verdict cannot silently carry over to changed bytes.

For a reviewed route, final acceptance verifies the original candidate ID rather than a
newly regenerated candidate. This keeps a valid review attached to the bytes it inspected.

## Full-v2 local tools

Full-v2 uses small standard-library tools under `plugins/sol-advisor/scripts/`:

- `workflow.py` stores the immutable task contract, CAS state, peer deliveries, mechanical
  assembly and final acceptance. It rejects baseline/path conflicts and never performs a
  semantic merge.
- `run-check.py` runs contract-declared checks or explicitly authorized sandboxed probes with bounded logs,
  timeout process-group cleanup and immutable evidence.
- `review-packet.py` freezes review packets and publishes request-bound challenge/CR/V/DR
  records from observed runtime facts; Sol itself does not write the product.
- `candidate.py` keeps whole-worktree selection as the default. `--scope <literal-path>` is
  an opt-in `scoped-literal-v1` mode only for proven dependency boundaries; it binds HEAD,
  rejects unbound outside dirty paths and falls back to whole-worktree when uncertain.

These tools do not install the plugin, start an Agent, authorize network/business actions,
or turn fixture results into a review verdict.

Sol Advisor does not require or create project `.agent-artifacts/`. Routine work needs
no runtime directory. Audit/full file-backed state defaults to one private directory under
`$TMPDIR` (or `/tmp`); explicit external durable storage remains supported. Assembly skips
untracked historical artifact trees while preserving tracked source. Existing artifacts and
candidate inventory semantics remain untouched; no automatic historical cleanup or ignore
file mutation is performed. Temporary state loss makes affected evidence unavailable, so
cross-session durable recovery requires an explicit persistent location before binding.

`scripts/review-round.py` is a small orchestration pool checker. New full contracts declare
`review_policy.reviewers_per_round`; the formal V remains single, and final-accept also gates
on a persisted complete round via `--review-round-id`. A binds the round ID and digest.
Existing full contracts without this field retain their original interpretation.

## Updating

Update the marketplace plugin, reinstall the companion roles, and start a new task:

~~~sh
codex plugin marketplace upgrade sol-advisor
plugin_dir="$(codex plugin add sol-advisor@sol-advisor --json | jq -er '.installedPath | select(type == "string" and length > 0)')" && test -d "$plugin_dir" && test -f "$plugin_dir/scripts/install-agents.sh" && sh "$plugin_dir/scripts/install-agents.sh"
~~~

The installer automatically migrates only exact known historical templates, including the
shipped 0.7.3 old-name implementer and Reviewer bytes, and the exact 0.8.2 Sol
implementer and Reviewer profiles. User-modified, symlinked, nonregular or otherwise
unknown destinations are refused without partial replacement. Use `--check` for a no-write
preflight. Roll back by reinstalling the prior plugin version and its exact companion roles,
then start another new task; existing tasks do not hot-reload role or Skill changes.
