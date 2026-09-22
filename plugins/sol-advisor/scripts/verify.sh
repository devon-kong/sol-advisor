#!/bin/sh
# Repository-local verification for Sol Advisor's selective native three-role architecture.

set -eu

pass() { printf '%s\n' "PASS: $*"; }
fail() { printf '%s\n' "FAIL: $*" >&2; exit 1; }

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
plugin_dir=$(CDPATH= cd "$script_dir/.." && pwd) || exit 1
repo_dir=$(CDPATH= cd "$plugin_dir/../.." && pwd) || exit 1
installer=$script_dir/install-agents.sh
runtime_inspector=$script_dir/inspect-agent-runtime.sh
candidate_tool=$script_dir/candidate.py
templates=$plugin_dir/agents
manifest=$plugin_dir/.codex-plugin/plugin.json
skill=$plugin_dir/skills/orchestration/SKILL.md
contracts=$plugin_dir/skills/orchestration/references/role-contracts.md
operations=$plugin_dir/skills/orchestration/references/operations.md
convergence=$plugin_dir/skills/orchestration/references/convergence.md
full_workflow=$plugin_dir/skills/orchestration/references/full-workflow.md
protocol_tool=$script_dir/full_protocol.py
workflow_tool=$script_dir/workflow.py
run_check_tool=$script_dir/run-check.py
review_packet_tool=$script_dir/review-packet.py
strict_test_runner=$script_dir/verify-test-suite.py
candidate_tests=$plugin_dir/tests
candidate_test=$candidate_tests/test_candidate.py
behavioral_test=$candidate_tests/test_behavioral_fixtures.py
behavioral_cases=$candidate_tests/behavioral-evals/cases.json
readme=$repo_dir/README.md
ui=$plugin_dir/skills/orchestration/agents/openai.yaml
marketplace=$repo_dir/.agents/plugins/marketplace.json

tmp_base=/tmp
tmp_env=$(printenv TMPDIR 2>/dev/null || true)
if [ -n "$tmp_env" ]; then tmp_base=$tmp_env; fi
case "$tmp_base" in /*) ;; *) tmp_base=/tmp ;; esac
tmp_dir=''
cleanup() {
  if [ -n "$tmp_dir" ] && [ -d "$tmp_dir" ]; then
    case "$tmp_dir" in
      "$tmp_base"/sol-advisor-verify.*) rm -rf "$tmp_dir" ;;
      *) printf '%s\n' "REFUSING cleanup of unexpected directory: $tmp_dir" >&2 ;;
    esac
  fi
}
trap cleanup 0 HUP INT TERM
tmp_dir=$(mktemp -d "$tmp_base/sol-advisor-verify.XXXXXX") || fail "could not create disposable verification directory"

luna_file=sol-advisor-luna-implementer.toml
terra_file=sol-advisor-terra-implementer.toml
sol_file=sol-advisor-sol-reviewer.toml
legacy_luna_sha256=fba1b42849d93737e83b094a2ab0b1611f87ac37db7438c8bbdf581f0813f8eb
legacy_terra_sha256=4425a8c1f21ce8c6af93f96adc253bbc33ea301f1389b3fa8ce350be08584eca
legacy_luna_v050_sha256=5cfaf77f14757074ca5d3cfecd0b8204c91dc14eff8d6119985c64416ddf4853
legacy_terra_v050_sha256=dc329fe87f6f6610c13157ec16432f91c79cf5a541ee3e7448f6afb165dd18ce
legacy_terra_v073_sha256=77ed2f36bb149da5d9032230c3d6f5e5cd56b059b3fa5f59085249bba06e1f3a
legacy_reviewer_v073_sha256=0333acf0ef562bcfebd06009ac09bd1dd8cbc04c4cf28e08e9e049bd8bf202d2

snapshot_files() {
  target=$1
  if [ ! -d "$target" ]; then
    printf '%s\n' MISSING
    return
  fi
  find "$target" -mindepth 1 -maxdepth 1 -print | LC_ALL=C sort | while IFS= read -r path; do
    if [ -L "$path" ]; then
      printf 'L %s -> %s\n' "$(basename "$path")" "$(readlink "$path")"
    elif [ -f "$path" ]; then
      shasum -a 256 "$path"
    else
      printf 'O %s\n' "$(basename "$path")"
    fi
  done
}

write_legacy_roles() {
  target=$1
  mkdir -p "$target"
  cat > "$target/$luna_file" <<'LEGACY_LUNA'
name = "sol_advisor_luna_implementer"
description = "Sol Advisor's routine implementation lane for bounded, fully specified work."
model = "gpt-5.6-luna"
model_reasoning_effort = "max"

developer_instructions = """
You are Sol Advisor's routine implementation worker. Execute the supplied five-part
implementation specification exactly when it is bounded and largely determined by
the contract. Preserve stated interfaces and constraints, make only the files you
own, and adapt to concurrent edits instead of reverting work you do not own.

Surface material ambiguity, missing acceptance criteria, scope conflicts, or failed
verification rather than redesigning the architecture. Run the requested checks and
report actual evidence. Do not silently substitute a different role, model, or
reasoning level; this installed custom-agent profile is the required routine lane.
"""
LEGACY_LUNA
  cat > "$target/$terra_file" <<'LEGACY_TERRA'
name = "sol_advisor_terra_implementer"
description = "Sol Advisor's complex implementation lane for context-heavy or higher-risk work."
model = "gpt-5.6-terra"
model_reasoning_effort = "max"

developer_instructions = """
You are Sol Advisor's complex implementation worker. Resolve difficult implementation
details within the settled architecture, including context-heavy, higher-risk, or
wider-blast-radius work. Preserve every stated interface and constraint, stay within
the owned file set, and document material judgment calls.

You are not alone in the codebase: preserve concurrent edits and do not revert
unrelated work. Surface ambiguity, scope conflicts, or verification failures rather
than changing the architecture without direction. Run the requested checks and report
actual evidence. Do not silently substitute a different role, model, or reasoning
level; this installed custom-agent profile is the required complex lane.
"""
LEGACY_TERRA
  cp "$templates/$sol_file" "$target/$sol_file"
  [ "$(shasum -a 256 "$target/$luna_file" | awk '{print $1}')" = "$legacy_luna_sha256" ] || fail "legacy Luna fixture digest drifted"
  [ "$(shasum -a 256 "$target/$terra_file" | awk '{print $1}')" = "$legacy_terra_sha256" ] || fail "legacy Terra fixture digest drifted"
}

write_v050_roles() {
  target=$1
  mkdir -p "$target"
  cat > "$target/$luna_file" <<'V050_LUNA'
name = "sol_advisor_luna_implementer"
description = "Sol Advisor's default routine implementation lane for bounded, fully specified work."
model = "gpt-5.6-luna"
model_reasoning_effort = "max"

developer_instructions = """
You are Sol Advisor's default routine implementation worker. Execute the supplied
five-part implementation specification when the work is bounded and largely
determined by the contract. Preserve every stated interface and constraint, stay
within the owned file set, and document material judgment calls.

You are not alone in the codebase: preserve concurrent edits and do not revert
unrelated work. Surface material ambiguity, scope conflicts, or verification failures
rather than redesigning the architecture. Run the requested checks and report actual
evidence. If one corrected attempt shows that the work is judgment-heavy, high-risk,
or misclassified as routine, stop and return that signal so the parent can escalate
it to Terra / High. Do not silently substitute a different role, model, or reasoning
level; this installed custom-agent profile is the required routine lane.
"""
V050_LUNA
  cat > "$target/$terra_file" <<'V050_TERRA'
name = "sol_advisor_terra_implementer"
description = "Sol Advisor's explicit high-complexity escalation lane for judgment-heavy or high-risk work."
model = "gpt-5.6-terra"
model_reasoning_effort = "high"

developer_instructions = """
You are Sol Advisor's explicit high-complexity escalation worker. Execute the
supplied five-part implementation specification within the settled architecture when
the parent identifies judgment-heavy, high-risk, or wider-blast-radius work, or when
one corrected Luna attempt shows that routine routing was a misclassification.
Preserve every stated interface and constraint, stay within the owned file set, and
document material judgment calls.

You are not alone in the codebase: preserve concurrent edits and do not revert
unrelated work. Surface ambiguity, scope conflicts, or verification failures rather
than redesigning the architecture without direction. Run the requested checks and
report actual evidence. Do not silently substitute a different role, model, or
reasoning level; this installed custom-agent profile is the required escalation lane.
"""
V050_TERRA
  cp "$templates/$sol_file" "$target/$sol_file"
  [ "$(shasum -a 256 "$target/$luna_file" | awk '{print $1}')" = "$legacy_luna_v050_sha256" ] || fail "v0.5.0 Luna fixture digest drifted"
  [ "$(shasum -a 256 "$target/$terra_file" | awk '{print $1}')" = "$legacy_terra_v050_sha256" ] || fail "v0.5.0 Terra fixture digest drifted"
}

write_v073_roles() {
  target=$1
  mkdir -p "$target"
  cp "$templates/$luna_file" "$target/$luna_file"
  cat > "$target/$terra_file" <<'V073_TERRA'
name = "sol_advisor_terra_implementer"
description = "Sol Advisor's explicit high-complexity escalation lane for judgment-heavy or high-risk work."
model = "gpt-5.6-terra"
model_reasoning_effort = "high"

developer_instructions = """
You are Sol Advisor's explicit high-complexity escalation worker. Execute the
supplied five-part implementation specification within the settled architecture when
the parent identifies judgment-heavy, high-risk, or wider-blast-radius work, whether
that is known before delegation or revealed by the first Luna result. A corrected
Luna attempt is reserved for a specification error and is not a prerequisite for
Terra escalation.
Preserve every stated interface and constraint, stay within the owned file set, and
document material judgment calls.

You are not alone in the codebase: preserve concurrent edits and do not revert
unrelated work. Surface ambiguity, scope conflicts, or verification failures rather
than redesigning the architecture without direction. Run the requested checks and
report actual evidence. Do not silently substitute a different role, model, or
reasoning level; this installed custom-agent profile is the required escalation lane.
"""
V073_TERRA
  cat > "$target/$sol_file" <<'V073_REVIEWER'
name = "sol_advisor_sol_reviewer"
description = "Sol Advisor's fresh, read-only final review lane for inspected diffs and evidence."
model = "gpt-5.6-sol"
model_reasoning_effort = "high"
sandbox_mode = "read-only"

developer_instructions = """
You are Sol Advisor's fresh final reviewer. Remain strictly read-only: do not create,
modify, delete, format, or implement files, and do not broaden the requested scope.
Inspect the actual files, accumulated change set, stated interfaces and constraints,
and verification evidence in a fresh context.

Return exactly one verdict: ship, fix-first, or rethink. Base the verdict on concrete,
evidence-backed findings. Use fix-first only for bounded required corrections and
rethink when the architecture or scope must change. Do not silently substitute a
different role, model, or reasoning level; this installed custom-agent profile is the
required read-only review lane.
"""
V073_REVIEWER
  [ "$(shasum -a 256 "$target/$terra_file" | awk '{print $1}')" = "$legacy_terra_v073_sha256" ] || fail "v0.7.3 Terra fixture digest drifted"
  [ "$(shasum -a 256 "$target/$sol_file" | awk '{print $1}')" = "$legacy_reviewer_v073_sha256" ] || fail "v0.7.3 Reviewer fixture digest drifted"
}

for required in "$installer" "$runtime_inspector" "$candidate_tool" "$protocol_tool" "$workflow_tool" "$run_check_tool" "$review_packet_tool" "$strict_test_runner" "$manifest" "$marketplace" "$skill" "$contracts" "$operations" "$convergence" "$full_workflow" "$readme" "$ui" "$candidate_test" "$behavioral_test" "$behavioral_cases"; do
  test -f "$required" || fail "required file missing: $required"
done
pass "required files present"

grep -Fq '$orchestration' "$ui" || fail "UI metadata omits the orchestration entry"
grep -Fq 'default_prompt:' "$ui" || fail "UI metadata omits the default route prompt"
grep -Fq 'SELECTIVE ROUTE' "$ui" || fail "UI metadata default prompt omits route declaration"
grep -Fq 'For root startup, load only skill guidance, then declare the route before other task tools; never batch loading with task discovery.' "$ui" || fail "UI metadata omits startup sequencing"
grep -Eq '^  default_prompt: .*For root startup, load only skill guidance, then declare the route before other task tools; never batch loading with task discovery\.' "$ui" || fail "UI metadata startup prompt is not inside interface"
if grep -Eq '^default_prompt:' "$ui"; then fail "UI metadata has a root-level default_prompt"; fi
pass "UI metadata exposes orchestration and its default route prompt"

jq empty "$manifest"
[ "$(jq -r '.version' "$manifest")" = 0.8.0 ] || fail "manifest version is not 0.8.0"
jq -e '.name == "sol-advisor" and (.plugins | length) == 1 and .plugins[0].name == "sol-advisor" and .plugins[0].source.source == "local" and .plugins[0].source.path == "./plugins/sol-advisor"' "$marketplace" >/dev/null || fail "marketplace metadata does not point to the sole local sol-advisor plugin"
grep -Fq 'SELECTIVE ROUTE' "$manifest" || fail "manifest omits route declaration"
jq -e '.interface.longDescription | contains("fail closed") and contains("combined candidate")' "$manifest" >/dev/null || fail "manifest omits full-v2 candidate/evidence fail-closed semantics"
grep -Fq 'For root startup, load only skill guidance, then declare the route before other task tools; never batch loading with task discovery.' "$manifest" || fail "manifest omits startup sequencing"
pass "manifest JSON and v0.8.0 discovery copy"

python3 - "$templates" <<'PY'
from pathlib import Path
import sys
import tomllib

root = Path(sys.argv[1])
expected = {
    "sol-advisor-luna-implementer.toml": {
        "name": "sol_advisor_luna_implementer",
        "model": "gpt-5.6-luna",
        "model_reasoning_effort": "max",
    },
    "sol-advisor-terra-implementer.toml": {
        "name": "sol_advisor_terra_implementer",
        "model": "gpt-5.6-terra",
        "model_reasoning_effort": "high",
    },
    "sol-advisor-sol-reviewer.toml": {
        "name": "sol_advisor_sol_reviewer",
        "model": "gpt-5.6-sol",
        "model_reasoning_effort": "high",
        "sandbox_mode": "read-only",
    },
}
actual = {path.name for path in root.glob("*.toml")}
if actual != set(expected):
    raise SystemExit(f"expected exactly {sorted(expected)}, found {sorted(actual)}")
for filename, pins in expected.items():
    data = tomllib.loads((root / filename).read_text(encoding="utf-8"))
    for field in ("name", "description", "developer_instructions"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise SystemExit(f"{filename}: missing {field}")
    for field, value in pins.items():
        if data.get(field) != value:
            raise SystemExit(f"{filename}: {field}={data.get(field)!r}, expected {value!r}")
print("three exact role pins are valid")
PY
pass "exact three-role TOML inventory"

grep -Fq "legacy_luna_sha256=$legacy_luna_sha256" "$installer" || fail "installer legacy Luna digest mismatch"
grep -Fq "legacy_terra_sha256=$legacy_terra_sha256" "$installer" || fail "installer legacy Terra digest mismatch"
grep -Fq "legacy_luna_v050_sha256=$legacy_luna_v050_sha256" "$installer" || fail "installer v0.5.0 Luna digest mismatch"
grep -Fq "legacy_terra_v050_sha256=$legacy_terra_v050_sha256" "$installer" || fail "installer v0.5.0 Terra digest mismatch"
grep -Fq "legacy_terra_v073_sha256=$legacy_terra_v073_sha256" "$installer" || fail "installer v0.7.3 Terra digest mismatch"
grep -Fq "legacy_reviewer_v073_sha256=$legacy_reviewer_v073_sha256" "$installer" || fail "installer v0.7.3 Reviewer digest mismatch"
pass "immutable historical migration fingerprints"

no_home_target=$tmp_dir/no-home-explicit
env -u HOME -u CODEX_HOME PATH="$PATH" sh "$installer" --target-dir "$no_home_target"
for role in "$luna_file" "$terra_file" "$sol_file"; do
  cmp -s "$templates/$role" "$no_home_target/$role" || fail "explicit target without HOME mismatch: $role"
done
pass "explicit target works without HOME or CODEX_HOME"

clean_target=$tmp_dir/clean
sh "$installer" --target-dir "$clean_target"
for role in "$luna_file" "$terra_file" "$sol_file"; do
  cmp -s "$templates/$role" "$clean_target/$role" || fail "clean install mismatch: $role"
done
sh "$installer" --target-dir "$clean_target" --check
before=$(snapshot_files "$clean_target")
sh "$installer" --target-dir "$clean_target"
after=$(snapshot_files "$clean_target")
[ "$before" = "$after" ] || fail "idempotent install changed current roles"
pass "clean install, exact check, and idempotence"

selective_target=$tmp_dir/selective
sh "$installer" --target-dir "$selective_target"
printf '%s\n' modified >> "$selective_target/$terra_file"
before=$(snapshot_files "$selective_target")
sh "$installer" --target-dir "$selective_target" --check-role luna
sh "$installer" --target-dir "$selective_target" --check-role reviewer
sh "$installer" --target-dir "$selective_target" --check-role luna --check-role reviewer
after=$(snapshot_files "$selective_target")
[ "$before" = "$after" ] || fail "selective Luna/Reviewer check mutated conflicting Terra target"
if sh "$installer" --target-dir "$selective_target" --check-role terra >/dev/null 2>&1; then
  fail "selective Terra check accepted conflicting Terra target"
fi
after=$(snapshot_files "$selective_target")
[ "$before" = "$after" ] || fail "selective Terra refusal mutated target"
if sh "$installer" --target-dir "$selective_target" --check >/dev/null 2>&1; then
  fail "all-role --check accepted conflicting Terra target"
fi
if sh "$installer" --target-dir "$selective_target" --check-role >/dev/null 2>&1; then
  fail "missing --check-role argument was accepted"
fi
if sh "$installer" --target-dir "$selective_target" --check-role unknown >/dev/null 2>&1; then
  fail "unknown --check-role argument was accepted"
fi
after=$(snapshot_files "$selective_target")
[ "$before" = "$after" ] || fail "invalid selective check mutated target"
sh "$installer" --target-dir "$selective_target" --check-role sol
pass "selective Luna/Reviewer check, legacy Reviewer alias, Terra refusal, all-role compatibility, and invalid-role refusal"

selective_terra_target=$tmp_dir/selective-terra
sh "$installer" --target-dir "$selective_terra_target"
printf '%s\n' modified >> "$selective_terra_target/$luna_file"
before=$(snapshot_files "$selective_terra_target")
sh "$installer" --target-dir "$selective_terra_target" --check-role terra --check-role reviewer
after=$(snapshot_files "$selective_terra_target")
[ "$before" = "$after" ] || fail "selective Terra/Reviewer check mutated conflicting Luna target"
if sh "$installer" --target-dir "$selective_terra_target" --check-role luna >/dev/null 2>&1; then
  fail "selective Luna check accepted conflicting Luna target"
fi
after=$(snapshot_files "$selective_terra_target")
[ "$before" = "$after" ] || fail "selective Luna refusal mutated target"
if sh "$installer" --target-dir "$selective_terra_target" --check >/dev/null 2>&1; then
  fail "all-role --check accepted conflicting Luna target"
fi
after=$(snapshot_files "$selective_terra_target")
[ "$before" = "$after" ] || fail "all-role Luna refusal mutated target"
pass "repeatable selective checks, Luna refusal, and all-role compatibility"

isolated_plugin=$tmp_dir/isolated-plugin
isolated_templates=$isolated_plugin/agents
isolated_installer=$isolated_plugin/scripts/install-agents.sh
isolated_target=$tmp_dir/isolated-terra
mkdir -p "$isolated_templates" "$(dirname "$isolated_installer")" "$isolated_target"
cp "$installer" "$isolated_installer"
cp "$templates/$terra_file" "$isolated_templates/$terra_file"
cp "$templates/$terra_file" "$isolated_target/$terra_file"
ln -s /missing-luna "$isolated_target/$luna_file"
mkdir "$isolated_target/$sol_file"
sh "$isolated_installer" --target-dir "$isolated_target" --check-role terra
before=$(snapshot_files "$isolated_target")
printf '%s\n' modified >> "$isolated_target/$terra_file"
selected_mismatch=$(snapshot_files "$isolated_target")
if sh "$isolated_installer" --target-dir "$isolated_target" --check-role terra >/dev/null 2>&1; then
  fail "selected Terra mismatch was accepted in isolated-role fixture"
fi
after=$(snapshot_files "$isolated_target")
[ "$before" != "$after" ] || fail "isolated Terra fixture did not create its selected mismatch"
[ "$selected_mismatch" = "$after" ] || fail "selected Terra mismatch check mutated the destination"
if [ "$(tail -n 1 "$isolated_target/$terra_file")" != modified ]; then
  fail "selected Terra mismatch fixture changed the destination"
fi
pass "selected Terra check isolates absent unselected sources and unsafe unselected destinations"

missing_target=$tmp_dir/missing
if sh "$installer" --target-dir "$missing_target" --check; then fail "--check accepted missing target"; fi
test ! -e "$missing_target" || fail "--check mutated missing target"
pass "missing-target check refusal is non-mutating"

codex_home=$tmp_dir/codex-home
CODEX_HOME="$codex_home" sh "$installer"
for role in "$luna_file" "$terra_file" "$sol_file"; do
  cmp -s "$templates/$role" "$codex_home/agents/$role" || fail "CODEX_HOME install mismatch: $role"
done
test ! -e "$codex_home/config.toml" || fail "installer created config.toml"
relative_parent=$tmp_dir/relative-parent
mkdir "$relative_parent"
(cd "$relative_parent" && sh "$installer" --target-dir relative-agents)
cmp -s "$templates/$luna_file" "$relative_parent/relative-agents/$luna_file" || fail "relative target Luna mismatch"
pass "CODEX_HOME and relative target behavior"

migration_target=$tmp_dir/migration
write_legacy_roles "$migration_target"
sh "$installer" --target-dir "$migration_target"
for role in "$luna_file" "$terra_file" "$sol_file"; do
  cmp -s "$templates/$role" "$migration_target/$role" || fail "historical migration mismatch: $role"
done
sh "$installer" --target-dir "$migration_target" --check
pass "exact historical Luna/Terra migration"

v050_migration_target=$tmp_dir/v050-migration
write_v050_roles "$v050_migration_target"
sh "$installer" --target-dir "$v050_migration_target"
for role in "$luna_file" "$terra_file" "$sol_file"; do
  cmp -s "$templates/$role" "$v050_migration_target/$role" || fail "v0.5.0 migration mismatch: $role"
done
sh "$installer" --target-dir "$v050_migration_target" --check
pass "exact v0.5.0 Luna/Terra migration"

v073_migration_target=$tmp_dir/v073-migration
write_v073_roles "$v073_migration_target"
before=$(snapshot_files "$v073_migration_target")
if sh "$installer" --target-dir "$v073_migration_target" --check >/dev/null 2>&1; then
  fail "check-only accepted exact v0.7.3 templates as current"
fi
after=$(snapshot_files "$v073_migration_target")
[ "$before" = "$after" ] || fail "v0.7.3 check-only mutated the migration target"
sh "$installer" --target-dir "$v073_migration_target"
for role in "$luna_file" "$terra_file" "$sol_file"; do
  cmp -s "$templates/$role" "$v073_migration_target/$role" || fail "v0.7.3 migration mismatch: $role"
done
sh "$installer" --target-dir "$v073_migration_target" --check
pass "exact v0.7.3 Terra/Reviewer migration with check-only no-write"

modified_v073_reviewer=$tmp_dir/modified-v073-reviewer
write_v073_roles "$modified_v073_reviewer"
printf 'X' >> "$modified_v073_reviewer/$sol_file"
before=$(snapshot_files "$modified_v073_reviewer")
if sh "$installer" --target-dir "$modified_v073_reviewer" >/dev/null 2>&1; then
  fail "installer replaced a user-modified v0.7.3 Reviewer"
fi
after=$(snapshot_files "$modified_v073_reviewer")
[ "$before" = "$after" ] || fail "modified v0.7.3 Reviewer refusal partially mutated target"
pass "modified v0.7.3 Reviewer refusal with zero partial mutation"

modified_v050_luna=$tmp_dir/modified-v050-luna
write_v050_roles "$modified_v050_luna"
printf 'X' >> "$modified_v050_luna/$luna_file"
before=$(snapshot_files "$modified_v050_luna")
if sh "$installer" --target-dir "$modified_v050_luna"; then fail "installer replaced modified v0.5.0 Luna"; fi
after=$(snapshot_files "$modified_v050_luna")
[ "$before" = "$after" ] || fail "modified v0.5.0 Luna refusal partially mutated target"
pass "modified v0.5.0 Luna refusal with zero partial mutation"

modified_v050_terra=$tmp_dir/modified-v050-terra
write_v050_roles "$modified_v050_terra"
printf 'X' >> "$modified_v050_terra/$terra_file"
before=$(snapshot_files "$modified_v050_terra")
if sh "$installer" --target-dir "$modified_v050_terra"; then fail "installer replaced modified v0.5.0 Terra"; fi
after=$(snapshot_files "$modified_v050_terra")
[ "$before" = "$after" ] || fail "modified v0.5.0 Terra refusal partially mutated target"
pass "modified v0.5.0 Terra refusal with zero partial mutation"

modified_luna=$tmp_dir/modified-luna
write_legacy_roles "$modified_luna"
printf '%s\n' modified >> "$modified_luna/$luna_file"
before=$(snapshot_files "$modified_luna")
if sh "$installer" --target-dir "$modified_luna"; then fail "installer replaced modified Luna"; fi
after=$(snapshot_files "$modified_luna")
[ "$before" = "$after" ] || fail "modified-Luna refusal partially mutated target"
pass "modified Luna refusal with zero partial mutation"

modified_terra=$tmp_dir/modified-terra
write_legacy_roles "$modified_terra"
printf '%s\n' modified >> "$modified_terra/$terra_file"
before=$(snapshot_files "$modified_terra")
if sh "$installer" --target-dir "$modified_terra"; then fail "installer replaced modified Terra"; fi
after=$(snapshot_files "$modified_terra")
[ "$before" = "$after" ] || fail "modified-Terra refusal partially mutated target"
pass "differing legacy Terra refusal with zero partial mutation"

modified_current=$tmp_dir/modified-current
sh "$installer" --target-dir "$modified_current"
printf '%s\n' modified >> "$modified_current/$luna_file"
before=$(snapshot_files "$modified_current")
if sh "$installer" --target-dir "$modified_current"; then fail "installer replaced modified current Luna"; fi
after=$(snapshot_files "$modified_current")
[ "$before" = "$after" ] || fail "modified current Luna refusal partially mutated target"
pass "modified current-role refusal with zero partial mutation"

unsafe=$tmp_dir/unsafe
mkdir "$unsafe"
ln -s "$templates/$luna_file" "$unsafe/$luna_file"
before=$(snapshot_files "$unsafe")
if sh "$installer" --target-dir "$unsafe"; then fail "installer accepted symlinked Luna"; fi
after=$(snapshot_files "$unsafe")
[ "$before" = "$after" ] || fail "symlink refusal partially mutated target"
test ! -e "$unsafe/$terra_file" || fail "symlink refusal partially installed Terra"
test ! -e "$unsafe/$sol_file" || fail "symlink refusal partially installed Sol"
pass "unsafe destination refusal with zero partial mutation"

runtime_sessions=$tmp_dir/runtime-sessions
runtime_day=$runtime_sessions/2026/08/15
mkdir -p "$runtime_day"
runtime_id=11111111-1111-7111-8111-111111111111
runtime_rollout=$runtime_day/rollout-2026-08-15T00-00-00-$runtime_id.jsonl
printf '%s\n' \
  '{"type":"response_item","payload":{"prompt":"DO_NOT_LEAK_PROMPT"}}' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$runtime_id\",\"parent_thread_id\":\"00000000-0000-7000-8000-000000000000\",\"agent_role\":\"sol_advisor_luna_implementer\",\"agent_path\":\"/root/fixture\",\"model_provider\":\"openai\",\"cwd\":\"/fixture\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"},"permission_profile":{"type":"disabled"},"cwd":"/fixture"}}' \
  > "$runtime_rollout"
runtime_output=$(sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$runtime_id")
printf '%s\n' "$runtime_output" | jq -e --arg id "$runtime_id" '
  .thread_id == $id and .agent_role == "sol_advisor_luna_implementer"
  and .model == "gpt-5.6-luna" and .effort == "max"
  and .sandbox_policy_type == "danger-full-access"
  and .permission_profile_type == "disabled"
' >/dev/null || fail "runtime inspector returned wrong Luna/Max evidence"
if printf '%s\n' "$runtime_output" | grep -Fq DO_NOT_LEAK; then fail "runtime inspector leaked payload"; fi
if sh "$runtime_inspector" --sessions-dir "$runtime_sessions" invalid >/dev/null 2>&1; then fail "runtime inspector accepted invalid id"; fi
zero_id=22222222-2222-7222-8222-222222222222
if sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$zero_id" >/dev/null 2>&1; then fail "runtime inspector accepted zero matches"; fi
pass "runtime inspector Luna/Max routing and safe refusal"

terra_id=33333333-3333-7333-8333-333333333333
terra_rollout=$runtime_day/rollout-2026-08-15T00-00-01-$terra_id.jsonl
printf '%s\n' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$terra_id\",\"parent_thread_id\":\"00000000-0000-7000-8000-000000000000\",\"agent_role\":\"sol_advisor_terra_implementer\",\"agent_path\":\"/root/fixture\",\"model_provider\":\"openai\",\"cwd\":\"/fixture\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-terra","effort":"high","sandbox_policy":{"type":"danger-full-access"},"permission_profile":{"type":"disabled"},"cwd":"/fixture"}}' \
  > "$terra_rollout"
terra_output=$(sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$terra_id")
printf '%s\n' "$terra_output" | jq -e --arg id "$terra_id" '
  .thread_id == $id and .agent_role == "sol_advisor_terra_implementer"
  and .model == "gpt-5.6-terra" and .effort == "high"
  and .sandbox_policy_type == "danger-full-access"
  and .permission_profile_type == "disabled"
' >/dev/null || fail "runtime inspector returned wrong Terra/High evidence"
pass "runtime inspector Terra/High routing evidence"

reviewer_id=44444444-4444-7444-8444-444444444444
reviewer_rollout=$runtime_day/rollout-2026-08-15T00-00-02-$reviewer_id.jsonl
printf '%s\n' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$reviewer_id\",\"parent_thread_id\":\"00000000-0000-7000-8000-000000000000\",\"agent_role\":\"sol_advisor_sol_reviewer\",\"agent_path\":\"/root/fixture\",\"model_provider\":\"openai\",\"cwd\":\"/fixture\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-sol","effort":"high","sandbox_policy":{"type":"read-only"},"permission_profile":{"type":"disabled"},"cwd":"/fixture"}}' \
  > "$reviewer_rollout"
reviewer_output=$(sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$reviewer_id")
printf '%s\n' "$reviewer_output" | jq -e --arg id "$reviewer_id" '
  .thread_id == $id and .agent_role == "sol_advisor_sol_reviewer"
  and .model == "gpt-5.6-sol" and .effort == "high"
  and .sandbox_policy_type == "read-only"
  and .permission_profile_type == "disabled"
' >/dev/null || fail "runtime inspector returned wrong Reviewer Sol/High/read-only evidence"
pass "runtime inspector Reviewer Sol/High/read-only evidence"

for document in "$contracts" "$operations"; do
  grep -Fq 'agent_type: sol_advisor_luna_implementer' "$document" || fail "missing Luna spawn in $document"
  grep -Fq 'agent_type: sol_advisor_terra_implementer' "$document" || fail "missing Terra spawn in $document"
  grep -Fq 'agent_type: sol_advisor_sol_reviewer' "$document" || fail "missing Reviewer spawn in $document"
  grep -Fq 'fork_turns: none' "$document" || fail "missing fresh context in $document"
  if grep -Eq 'agent_type:.*terra_max' "$document"; then fail "retired Terra-Max spawn remains in $document"; fi
  if grep -Eq '^[[:space:]]*(model|reasoning_effort):' "$document"; then fail "per-spawn override remains in $document"; fi
done
grep -Fq 'references/operations.md' "$skill" || fail "skill does not link operations reference"
grep -Fq 'references/convergence.md' "$skill" || fail "skill does not link convergence reference"
grep -Fq 'For root startup, load only skill guidance, then declare the route before other task tools; never batch loading with task discovery.' "$skill" || fail "skill metadata omits startup sequencing"
grep -Fq '../../scripts/install-agents.sh' "$operations" || fail "operations does not resolve installer relatively"
grep -Fq '../../scripts/inspect-agent-runtime.sh' "$operations" || fail "operations does not resolve inspector relatively"
grep -Fq '../../scripts/candidate.py' "$operations" || fail "operations does not resolve candidate tool relatively"
grep -Fq 'SELECTIVE ROUTE' "$skill" || fail "skill omits route declaration"
grep -Fq 'mode: solo | delegate | audit | full' "$skill" || fail "skill omits exact route modes"
grep -Fq 'Before declaring a route, the root may read this skill and the references directly linked' "$skill" || fail "skill omits read-only route-declaration exemption"
grep -Fq 'Do not batch skill/reference loading with repository discovery or other task tools before' "$skill" || fail "skill permits batched pre-declaration discovery"
grep -Fq 'No other task tool call may precede this declaration' "$skill" || fail "skill permits tool-before-route"
grep -Fq 'Solo is the default' "$skill" || fail "skill omits solo default"
grep -Fq 'One auxiliary agent is the default maximum' "$skill" || fail "skill omits auxiliary limit"
grep -Fq 'A later declaration may only escalate the route when newly' "$skill" || fail "skill omits escalation gate"
grep -Fq 'never silently downgrade' "$skill" || fail "skill permits silent downgrade"
grep -Fqi 'public metadata' "$skill" || fail "skill lacks public-metadata evidence rule"
grep -Fqi 'local inspector' "$skill" || fail "skill lacks runtime fallback rule"
grep -Fqi 'root captures exact before/after repository and artifact state' "$operations" || fail "operations lack behavioral read-only state check"
grep -Fq 'REVIEW RESULT' "$contracts" || fail "Reviewer contract lacks a distinct structured result heading"
grep -Fq 'REVIEWED_CANDIDATE:' "$contracts" || fail "Reviewer contract lacks reviewed-candidate return"
grep -Fq -- '--expected-candidate-id' "$operations" || fail "operations omit reviewed-candidate verification"
grep -Fq 'must not derive the final expected ID' "$operations" || fail "operations permit regenerated final candidate IDs"
if grep -Eni 'primary.{0,80}(model|effort)|Sol / High.{0,80}primary|primary.{0,80}Sol / High' \
  "$readme" "$manifest" "$skill" "$contracts" "$operations"; then
  fail "primary model/effort coupling remains in user/runtime policy"
fi
grep -Fq -- '--check-role reviewer' "$operations" || fail "operations do not use canonical Reviewer check label"
grep -Fq 'legacy `sol` value remains an alias for `reviewer`' "$operations" || fail "operations omit legacy sol compatibility"
grep -Fq 'only the active auxiliary stage' "$skill" || fail "skill does not scope auxiliary preflight to the active stage"
grep -Fq 'Do not validate an unspawned auxiliary' "$operations" || fail "operations validate unspawned auxiliaries"
for mode in solo delegate audit full; do
  grep -Fq "\`$mode\`" "$skill" || fail "skill omits $mode mode"
done
grep -Fqi 'auxiliary work must substitute for root work' "$skill" || fail "skill permits duplicate auxiliary work"
grep -Fqi 'first Luna result' "$contracts" || fail "contracts omit Luna-to-Terra escalation"
grep -Fqi 'not a prerequisite' "$contracts" || fail "contracts make corrected Luna mandatory"
grep -Fq 'do not request a fresh review' "$skill" || fail "skill makes delegate review mandatory"
grep -Fq '`solo` and `delegate` do not receive a fresh reviewer' "$skill" || fail "skill makes solo/delegate review mandatory"
grep -Fq 'audit: the root implements the required correction, re-verifies, and obtains a new' "$skill" || fail "skill does not assign audit corrections to root"
grep -Fq 'full: the relevant peer Terra stage handles the required correction' "$skill" || fail "skill does not return full corrections to the owning peer Terra stage"
grep -Fq 'new delivery/candidate identity' "$skill" || fail "skill does not invalidate full candidate identity after correction"
if grep -Fq 'fix-first: delegate the required correction' "$skill"; then fail "skill retains unconditional fix-first delegation"; fi
grep -Fq 'Every mode, including `solo`, handles a discovered defect' "$skill" || fail "skill does not make defect handling uniform"
grep -Fq 'or reproduce the failure' "$skill" || fail "skill omits failure preservation or reproduction"
grep -Fq 'does not create an automatic extra agent, reviewer, manifest, table, or repository-wide' "$skill" || fail "skill adds automatic defect overhead"
grep -Fq 'worker stops writes to files handed to the root' "$skill" || fail "skill omits worker handoff write stop"
grep -Fq 'The plan may be inline; it does not require a separate artifact' "$skill" || fail "skill requires a standalone verification plan artifact"
for phrase in \
  'OBJECTIVE AND ACCEPTANCE' \
  'IMPACT SURFACE' \
  'EVIDENCE MAP' \
  'UNVERIFIED' \
  'At handoff, stop writes to files handed to the root until the root explicitly releases' \
  'For every high-risk or repeated-omission principal material risk' \
  'CLASS: implementation | verification | architecture-contract | environment | candidate-review' \
  'REQUIRED NEXT ACTION'; do
  grep -Fq "$phrase" "$contracts" || fail "role contracts omit: $phrase"
done
for phrase in \
  'ACCEPTANCE VERSION' \
  'RULE OR MECHANISM' \
  'OBSERVED:' \
  'FALSIFIED:' \
  'PUBLISH: publishAttempt(A, identity={jobId, generation})' \
  'LAST ASYNC BOUNDARY: await final completion' \
  'EVIDENCE-BACKED EXCLUSION:' \
  'the same method is not a changed attempt'; do
  grep -Fq "$phrase" "$convergence" || fail "convergence reference omits: $phrase"
done
pass "route, acceptance, impact-surface, review, and correction contracts"

for phrase in \
  'agent_type: sol_advisor_luna_implementer' \
  'agent_type: sol_advisor_terra_implementer' \
  'agent_type: sol_advisor_sol_reviewer' \
  'fork_turns: none' \
  'runtime_inspector' \
  'Prefer the UUID supplied by public details when present' \
  'parent UUID and the exact returned canonical path' \
  'public call ID when it is' \
  'absent, ambiguous, multiple, or conflicting mapping pauses only the active' \
  'Never pass a canonical path as a UUID' \
  'not a role fallback, a resolver CLI, a helper' \
  'stable dependency-complete copy or record a relevant pre/post digest' \
  'sandbox_mode = read-only' \
  'install-agents.sh --check'; do
  grep -Fqi "$phrase" "$operations" || fail "operations reference omits: $phrase"
done
pass "operations preserves native mechanics without route-policy duplication"

grep -Fq 'codex plugin marketplace add devon-kong/sol-advisor --ref main' "$readme" || fail "README omits the GitHub marketplace install source"
grep -Fq 'codex plugin add' "$readme" || fail "README omits plugin quick start"
grep -Fq 'scripts/install-agents.sh' "$readme" || fail "README omits companion install"
if grep -Eq 'agent_type:|fork_turns:|inspect-agent-runtime|sandbox_policy|sandbox_mode' "$readme"; then
  fail "README exposes maintainer routing/runtime machinery"
fi
grep -Fq '| `solo` |' "$readme" || fail "README route table omits solo"
grep -Fq '| `delegate` |' "$readme" || fail "README route table omits delegate"
grep -Fq '| `audit` |' "$readme" || fail "README route table omits audit"
grep -Fq '| `full` |' "$readme" || fail "README route table omits full"
python3 - "$readme" <<'PY'
from pathlib import Path
import sys

lines = [line.strip() for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
install_lines = [
    line
    for line in lines
    if line.startswith('plugin_dir="$(codex plugin add sol-advisor@sol-advisor --json')
    and "scripts/install-agents.sh" in line
]
if len(install_lines) != 2:
    raise SystemExit(f"expected two guarded companion install examples, found {len(install_lines)}")
for line in install_lines:
    required = [
        "jq -er '.installedPath | select(type == \"string\" and length > 0)'",
        'test -d "$plugin_dir"',
        'test -f "$plugin_dir/scripts/install-agents.sh"',
    ]
    if any(check not in line for check in required):
        raise SystemExit(f"unguarded companion install example: {line}")
    if line.index("sh \"") < line.index(required[-1]):
        raise SystemExit(f"installer executes before directory/file guards: {line}")
print("two companion install examples are fail-closed and guarded")
PY
pass "README is concise, user-first, route-tabled, and keeps maintainer machinery out"

if grep -ERn 'sol_advisor_terra_max|sol-advisor-terra-max|sol_advisor_terra_tester|sol-advisor-terra-tester' \
  "$templates" "$skill" "$contracts" "$operations" "$convergence"; then
  fail "forbidden second Terra role remains"
fi
pass "current role inventory has no second Terra interface"

test -d "$candidate_tests" || fail "candidate behavior tests are missing"
all_test_output=$(PYTHONDONTWRITEBYTECODE=1 python3 "$strict_test_runner" --tests-dir "$candidate_tests" \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_corrected_p2_review_rejects_reused_predecessor_context_through_record_review \
  --required-id test_full_protocol.CompleteRelationshipTests.test_corrected_p2_reviewer_freshness_covers_transitive_ancestry \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_public_acceptance_rejects_another_stages_final_check \
  --required-id test_flow_alignment.FlowAlignmentProtocolTests.test_p2_final_check_must_be_reachable_for_every_stage \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_probe_cannot_read_ignored_or_git_files_inside_declared_directory \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_third_stage_reuses_second_stage_cumulative_acceptance \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_intermediate_acceptance_recovers_only_missing_receipt \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_no_required_pre_review_checks_allows_empty_packet \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_two_stages_real_checks_review_and_final_accept_cli \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_new_sandboxed_probe_and_behavioral_review_keep_old_evidence \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_accepted_selection_cannot_be_rebound \
  --required-id test_flow_alignment_integration.FlowIntegrationTests.test_old_run_log_tamper_is_rejected_at_review \
  --required-id test_flow_alignment_integration.WindowTests.test_old_evidence_drift_rejects \
  --required-id test_candidate.CandidateToolTests.test_scoped_selection_is_explicit_versioned_and_binds_head_and_bytes \
  --required-id test_full_protocol.PublicRelationshipClosureTests.test_acceptance_recomputes_final_evidence_and_root_authority \
  --required-id test_workflow.WorkflowTests.test_assemble_recovers_artifacts_before_state_and_state_before_receipt \
  --required-id test_run_check.RunCheckTests.test_timeout_kills_a_child_that_ignores_term \
  --required-id test_review_packet.ReviewPacketTests.test_record_review_requires_observed_sol_and_applies_ship_transition \
  --required-id test_behavioral_fixtures.BehavioralFixtureTests.test_full_v2_action_trace_grader_distinguishes_valid_and_invalid_mechanisms \
  --required-id test_scoped_chain.ScopedChainTests.test_scoped_candidate_run_persists_real_evidence_before_packet \
  --required-id test_scoped_chain.ScopedChainTests.test_scoped_chain_records_packet_challenge_and_tagged_hard_review_from_real_runs \
  --required-id test_scoped_chain.ScopedChainTests.test_scoped_readme_byte_drift_rejects_review_before_its_intent \
  --required-id test_scoped_chain.ScopedChainTests.test_scoped_chain_accepts_after_runner_persists_distinct_final_candidate_evidence \
  --required-id test_scoped_chain.ScopedChainTests.test_scoped_readme_byte_drift_rejects_final_acceptance_before_its_intent \
  --required-id test_verify_test_suite.VerifyTestSuiteTests.test_accepts_discovered_required_test_that_actually_passes \
  --required-id test_verify_test_suite.VerifyTestSuiteTests.test_rejects_required_test_missing_from_dynamic_discovery \
  --required-id test_verify_test_suite.VerifyTestSuiteTests.test_rejects_skipped_required_test_instead_of_accepting_ok_skipped \
  --required-id test_verify_test_suite.VerifyTestSuiteTests.test_rejects_expected_failure_required_test \
  --required-id test_verify_test_suite.VerifyTestSuiteTests.test_rejects_skip_even_when_another_required_test_passes 2>&1) || {
  printf '%s\n' "$all_test_output" >&2
  fail "full Python suite did not execute every required mechanism successfully"
}
printf '%s\n' "$all_test_output"
printf '%s\n' "$all_test_output" | python3 -m json.tool >/dev/null || fail "strict test runner did not emit JSON evidence"
python3 -c 'import json,sys; result=json.load(sys.stdin); raise SystemExit(0 if result.get("status") == "pass" and result.get("discovered") and not result.get("skipped") and not result.get("expected_failures") else 1)' <<EOF || fail "strict test runner did not prove a nonempty, fully executed suite"
$all_test_output
EOF
pass "dynamic full Python discovery executed every required mechanism with no skips or expected failures"

sh -n "$installer"
sh -n "$runtime_inspector"
sh -n "$script_dir/verify.sh"
pass "shell syntax"

printf '%s\n' "VERIFY PASSED: Sol Advisor v0.8.0 full-v2 checks completed in $tmp_dir"
