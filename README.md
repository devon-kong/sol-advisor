# Sol Advisor

Sol Advisor is a Codex-only workflow for capability-routed software delivery. You
provide the outcome and constraints; the root owns planning, implementation or
delegation, verification, and acceptance.

## Install from GitHub

You need a current Codex CLI or ChatGPT desktop app with plugins enabled, native
custom-agent support, jq, and Python 3. The candidate behavior suite is verified on Python
3.12 and 3.14; other Python versions are not claimed here. Luna / Max, Terra / High, or
Reviewer Sol / High access is needed only when that auxiliary is used.

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
Use $sol-advisor:orchestration to build this feature and verify it. Declare the selective route before task tools.
~~~

## Routes

| Mode | Use it when | Delivery |
|---|---|---|
| `solo` | Default; risk is contained. | Root plans, implements, tests, and self-reviews. |
| `delegate` | A complete spec is better executed by one implementer. | Luna / Max for bounded work, or Terra / High for judgment-heavy or high-risk work; root verifies. |
| `audit` | Independent final scrutiny matters more than delegation. | Root implements; a fresh read-only Reviewer inspects the diff. |
| `full` | Explicit broad or high-risk exception. | One selected implementer, root verification, then fresh Reviewer scrutiny. |

Solo is the default. One auxiliary is the default maximum; `full` is the explicit
exception. The root declares a `SELECTIVE ROUTE` with the mode and concise risk
rationale before the first task tool call. It can escalate only when newly
observed risk justifies it and never silently downgrades. You do not need to select or
manage a lane.

Auxiliary work substitutes for root work; it does not duplicate it. The root inspects
the complete diff and reruns the requested checks. When the selected route includes a
review, the Reviewer returns ship, fix-first, or rethink; any fix requires a new review.

The root also keeps one acceptance basis across implementation and review. When a defect
appears, it checks causally related entry points and separates implementation errors from
evidence, architecture, environment, or review failures. Repeated corrections must change
the failed method and seek new evidence. Reviewed Git work is bound to an exact candidate
snapshot so a verdict cannot silently carry over to changed bytes.

For a reviewed route, final acceptance verifies the original candidate ID rather than a
newly regenerated candidate. This keeps a valid review attached to the bytes it inspected.

## Updating

Update the marketplace plugin, reinstall the companion roles, and start a new task:

~~~sh
codex plugin marketplace upgrade sol-advisor
plugin_dir="$(codex plugin add sol-advisor@sol-advisor --json | jq -er '.installedPath | select(type == "string" and length > 0)')" && test -d "$plugin_dir" && test -f "$plugin_dir/scripts/install-agents.sh" && sh "$plugin_dir/scripts/install-agents.sh"
~~~
