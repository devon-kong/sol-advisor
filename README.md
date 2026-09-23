# Sol Advisor

Sol Advisor is a Codex-only workflow for capability-routed software delivery. You
provide the outcome and constraints; the root owns planning, implementation or
delegation, verification, and acceptance.

## Install from GitHub

You need a current Codex CLI or ChatGPT desktop app with plugins enabled, native
custom-agent support, jq, and Python 3. The candidate behavior suite is verified on Python
3.12 and 3.14; other Python versions are not claimed here. Luna / XHigh, Sol implementer / High, or
Sol reviewer / XHigh access is needed only when that auxiliary is used.

This source tree describes the `0.8.2` full-v2 protocol. Installing from a
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
| `audit` | Independent final scrutiny matters more than delegation. | Root implements; a fresh read-only Reviewer inspects the diff. |
| `full` | Explicit broad or high-risk exception. | Root schedules independent peer Sol implementer work when useful, tools assemble exact deliveries, and one fresh read-only Sol reviewer checks the real combined candidate. |

Solo is the default and non-full behavior is unchanged. One auxiliary remains the default
maximum outside `full`; full is the explicit exception and may use multiple peer Sol implementer
instances only for genuinely independent work. The root declares a `SELECTIVE ROUTE` with the mode and concise risk
rationale before the first task tool call. It can escalate only when newly
observed risk justifies it and never silently downgrades. You do not need to select or
manage a lane.

Auxiliary work substitutes for root work; it does not duplicate it. In `solo`, `delegate`,
and `audit`, existing Root verification responsibilities remain. In `full`, each Sol implementer owns
its own implementation, tests, self-review and delivery; there is no lead/integrator Sol implementer.
The Root plans, schedules, resolves interface or authority conflicts, binds the mechanically
combined candidate and makes final acceptance without a default duplicate technical rerun.
The same fresh Sol context performs critical checks and then the remaining stage review.
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

Generated material uses `<workspace>/.agent-artifacts/<task-id>/`, with correction rounds
beneath it and an anchored project Git ignore entry. New candidates exclude untracked
material under that exact root; tracked files and explicit acceptance inputs stay bound.
Disposable `work/` is separate from a stable, minimal
`archive/`; required reviewed inputs live at their retained paths before candidate binding.
Permanent tests and project documentation follow existing repository conventions. Ordinary
edits need no mandatory archive, and the convention does not authorize deleting old evidence.

## Updating

Update the marketplace plugin, reinstall the companion roles, and start a new task:

~~~sh
codex plugin marketplace upgrade sol-advisor
plugin_dir="$(codex plugin add sol-advisor@sol-advisor --json | jq -er '.installedPath | select(type == "string" and length > 0)')" && test -d "$plugin_dir" && test -f "$plugin_dir/scripts/install-agents.sh" && sh "$plugin_dir/scripts/install-agents.sh"
~~~

The installer automatically migrates only exact known historical templates, including the
shipped 0.7.3 old-name implementer and Reviewer bytes. User-modified, symlinked, nonregular or otherwise
unknown destinations are refused without partial replacement. Use `--check` for a no-write
preflight. Roll back by reinstalling the prior plugin version and its exact companion roles,
then start another new task; existing tasks do not hot-reload role or Skill changes.
