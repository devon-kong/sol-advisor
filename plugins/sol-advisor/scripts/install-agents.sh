#!/bin/sh
# Install Sol Advisor's shipped custom-agent templates without changing Codex config.

set -eu

usage() {
  cat <<'EOF'
Usage: install-agents.sh [--target-dir PATH] [--check] [--check-role ROLE ...]

Install Sol Advisor's three current custom-agent templates into the target directory.
Normal mode migrates exact byte-matching historical templates and retires an exact
old-name implementer file. It never overwrites or removes a modified, nonregular,
or symlinked destination.

Without --target-dir, the target is "$CODEX_HOME/agents" when CODEX_HOME is already
set, otherwise "$HOME/.codex/agents".

Options:
  --target-dir PATH  Explicit destination directory (absolute or relative).
  --check            Verify that Luna, Sol implementer, and Reviewer match exactly; do not create,
                     replace, or remove anything.
  --check-role ROLE  Verify only ROLE (luna, implementer, or reviewer); repeatable and
                     implies --check. The legacy sol alias means reviewer. Unknown
                     or missing roles fail without mutation.
  --help             Show this help text.
EOF
}

fail() {
  printf '%s\n' "ERROR: $*" >&2
  exit 1
}

report_preflight_error() {
  printf '%s\n' "ERROR: $*" >&2
  preflight_failed=1
}

role_selected() {
  role=$1
  if [ -z "$check_roles" ]; then
    return 0
  fi
  case ",$check_roles," in
    *,"$role",*) return 0 ;;
    *) return 1 ;;
  esac
}

path_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

sha256_file() {
  shasum -a 256 "$1" 2>/dev/null | awk 'NF >= 1 && length($1) == 64 { print $1; exit }'
}

classify_current_or_legacy() {
  destination=$1
  template=$2
  legacy_digest=$3
  legacy_digest_alt=${4-}
  legacy_digest_third=${5-}
  legacy_digest_fourth=${6-}
  legacy_digest_fifth=${7-}

  if ! path_exists "$destination"; then
    printf '%s\n' missing
  elif [ -L "$destination" ] || [ ! -f "$destination" ]; then
    printf '%s\n' unsafe
  elif cmp -s "$template" "$destination"; then
    printf '%s\n' current
  else
    digest=$(sha256_file "$destination")
    if [ -n "$digest" ] && {
      [ "$digest" = "$legacy_digest" ] || [ "$digest" = "$legacy_digest_alt" ] ||
      [ "$digest" = "$legacy_digest_third" ] || [ "$digest" = "$legacy_digest_fourth" ] ||
      [ "$digest" = "$legacy_digest_fifth" ]
    }; then
      printf '%s\n' legacy
    elif [ -z "$digest" ]; then
      printf '%s\n' unreadable
    else
      printf '%s\n' conflict
    fi
  fi
}

same_state() {
  label=$1
  expected=$2
  actual=$3
  [ "$expected" = "$actual" ] || fail "$label changed after preflight; no further destination files were changed."
}

install_missing() {
  template=$1
  destination=$2
  staged=''

  if path_exists "$destination"; then
    fail "destination changed after preflight and will not be overwritten: $destination"
  fi

  staged=$(mktemp "$target_dir/.sol-advisor-agent.XXXXXX") || fail "could not stage template for installation: $destination"
  if ! cp "$template" "$staged"; then
    rm -f "$staged"
    fail "could not stage template for installation: $destination"
  fi

  if ! ln "$staged" "$destination"; then
    rm -f "$staged"
    fail "destination changed after preflight and will not be overwritten: $destination"
  fi

  rm -f "$staged" || fail "could not remove staged template after installation: $staged"
  printf '%s\n' "INSTALLED: $destination"
}

replace_legacy_role() {
  label=$1
  template=$2
  destination=$3
  legacy_digest=$4
  legacy_digest_alt=${5-}
  legacy_digest_third=${6-}
  staged=''

  [ "$(classify_current_or_legacy "$destination" "$template" "$legacy_digest" "$legacy_digest_alt" "$legacy_digest_third")" = legacy ] ||
    fail "legacy $label destination changed after preflight and will not be replaced: $destination"

  staged=$(mktemp "$target_dir/.sol-advisor-agent.XXXXXX") || fail "could not stage migrated $label template: $destination"
  if ! cp "$template" "$staged"; then
    rm -f "$staged"
    fail "could not stage migrated $label template: $destination"
  fi

  [ "$(classify_current_or_legacy "$destination" "$template" "$legacy_digest" "$legacy_digest_alt" "$legacy_digest_third")" = legacy ] || {
    rm -f "$staged"
    fail "legacy $label destination changed after preflight and will not be replaced: $destination"
  }

  if ! mv -f "$staged" "$destination"; then
    rm -f "$staged"
    fail "could not replace exact legacy $label template: $destination"
  fi

  printf '%s\n' "MIGRATED: $destination"
}

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
template_dir=$script_dir/../agents

target_dir=''
check_only=0
check_roles=''

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-dir)
      [ "$#" -ge 2 ] || fail "--target-dir requires a path."
      [ -n "$2" ] || fail "--target-dir requires a non-empty path."
      case "$2" in
        --*) fail "--target-dir path must be explicit; prefix an option-like relative name with ./ or use an absolute path." ;;
      esac
      target_dir=$2
      shift 2
      ;;
    --check)
      check_only=1
      shift
      ;;
    --check-role)
      [ "$#" -ge 2 ] || fail "--check-role requires a role: luna, implementer, or reviewer (legacy: sol)."
      case "$2" in
        luna|implementer) role=$2 ;;
        reviewer|sol) role=reviewer ;;
        *) fail "unknown --check-role '$2'; expected luna, implementer, or reviewer (legacy: sol)." ;;
      esac
      check_only=1
      check_roles=$check_roles$role,
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1 (run with --help for usage)."
      ;;
  esac
done

if [ -z "$target_dir" ]; then
  if [ -n "${CODEX_HOME-}" ]; then
    target_dir=$CODEX_HOME/agents
  else
    [ -n "${HOME-}" ] || fail "HOME is unset and CODEX_HOME was not supplied; pass --target-dir explicitly."
    target_dir=$HOME/.codex/agents
  fi
fi

case "$target_dir" in
  /*) ;;
  *) target_dir=$(pwd -P)/$target_dir ;;
esac

case "$target_dir" in
  /|//) fail "refusing to use the filesystem root as an agent target directory." ;;
esac

implementer_file=sol-advisor-sol-implementer.toml
retired_implementer_file=sol-advisor-terra-implementer.toml
luna_file=sol-advisor-luna-implementer.toml
reviewer_file=sol-advisor-sol-reviewer.toml
implementer_template=$template_dir/$implementer_file
luna_template=$template_dir/$luna_file
reviewer_template=$template_dir/$reviewer_file
implementer_destination=$target_dir/$implementer_file
retired_implementer_destination=$target_dir/$retired_implementer_file
luna_destination=$target_dir/$luna_file
reviewer_destination=$target_dir/$reviewer_file

# Immutable historical byte digests, calculated from the shipped v0.2.0 role files:
# git show bbc3dc1:plugins/sol-advisor/agents/sol-advisor-luna-implementer.toml | shasum -a 256
# git show bbc3dc1:plugins/sol-advisor/agents/sol-advisor-terra-implementer.toml | shasum -a 256
legacy_luna_sha256=fba1b42849d93737e83b094a2ab0b1611f87ac37db7438c8bbdf581f0813f8eb
legacy_terra_sha256=4425a8c1f21ce8c6af93f96adc253bbc33ea301f1389b3fa8ce350be08584eca
# Immutable v0.5.0 role digests, calculated from the shipped base profiles.
legacy_luna_v050_sha256=5cfaf77f14757074ca5d3cfecd0b8204c91dc14eff8d6119985c64416ddf4853
legacy_terra_v050_sha256=dc329fe87f6f6610c13157ec16432f91c79cf5a541ee3e7448f6afb165dd18ce
# Exact 0.7.3 profiles replaced by the full-v2 role cores.
legacy_terra_v073_sha256=77ed2f36bb149da5d9032230c3d6f5e5cd56b059b3fa5f59085249bba06e1f3a
legacy_reviewer_v073_sha256=0333acf0ef562bcfebd06009ac09bd1dd8cbc04c4cf28e08e9e049bd8bf202d2
legacy_reviewer_v080_sha256=579aee6f9f82e84b3a3bbd89e05fcb139051a7232cd20c43ab51c0642a4af0da
# Exact old-name v0.8.0 and pre-rename GPT-6 implementer templates.
legacy_terra_v080_sha256=65ed1207a864efc7265212bcaca0dd3d59054515070f9e328986767c4fce2ee6
legacy_terra_gpt6_sha256=678f8a6076a8ff1e640b69b48ab876f04dccb98ef8e92fe534ffb2c2b8111b51

preflight_failed=0
if path_exists "$target_dir"; then
  if [ -L "$target_dir" ] || [ ! -d "$target_dir" ]; then
    report_preflight_error "target directory is not a real directory: $target_dir"
  fi
fi

if [ "$check_only" -eq 1 ]; then
  if role_selected luna; then
    [ -f "$luna_template" ] && [ ! -L "$luna_template" ] ||
      report_preflight_error "shipped Luna template is missing or not a regular file: $luna_template"
    luna_state=$(classify_current_or_legacy "$luna_destination" "$luna_template" "$legacy_luna_sha256" "$legacy_luna_v050_sha256")
    [ "$luna_state" = current ] ||
      report_preflight_error "Luna template is $luna_state, not the current exact file: $luna_destination"
  fi
  if role_selected implementer; then
    [ -f "$implementer_template" ] && [ ! -L "$implementer_template" ] ||
      report_preflight_error "shipped Sol implementer template is missing or not a regular file: $implementer_template"
    implementer_state=$(classify_current_or_legacy "$implementer_destination" "$implementer_template" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256")
    [ "$implementer_state" = current ] ||
      report_preflight_error "Sol implementer template is $implementer_state, not the current exact file: $implementer_destination"
    path_exists "$retired_implementer_destination" &&
      report_preflight_error "retired implementer file is still present: $retired_implementer_destination"
  fi
  if role_selected reviewer; then
    [ -f "$reviewer_template" ] && [ ! -L "$reviewer_template" ] ||
      report_preflight_error "shipped Reviewer template is missing or not a regular file: $reviewer_template"
    reviewer_state=$(classify_current_or_legacy "$reviewer_destination" "$reviewer_template" "$legacy_reviewer_v073_sha256" "$legacy_reviewer_v080_sha256" '')
    [ "$reviewer_state" = current ] ||
      report_preflight_error "Reviewer template is $reviewer_state, not the current exact file: $reviewer_destination"
  fi
else
  for template in "$luna_template" "$implementer_template" "$reviewer_template"; do
    [ -f "$template" ] && [ ! -L "$template" ] ||
      fail "shipped template is missing or not a regular file: $template"
  done
  luna_state=$(classify_current_or_legacy "$luna_destination" "$luna_template" "$legacy_luna_sha256" "$legacy_luna_v050_sha256")
  implementer_state=$(classify_current_or_legacy "$implementer_destination" "$implementer_template" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256")
  retired_implementer_state=$(classify_current_or_legacy "$retired_implementer_destination" "$implementer_template" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256" "$legacy_terra_v080_sha256" "$legacy_terra_gpt6_sha256")
  reviewer_state=$(classify_current_or_legacy "$reviewer_destination" "$reviewer_template" "$legacy_reviewer_v073_sha256" "$legacy_reviewer_v080_sha256" '')
  case "$luna_state" in
    current|legacy|missing) ;;
    *) report_preflight_error "Luna destination is $luna_state and will not be replaced: $luna_destination" ;;
  esac
  case "$implementer_state" in
    current|legacy|missing) ;;
    *) report_preflight_error "Sol implementer destination is $implementer_state and will not be replaced: $implementer_destination" ;;
  esac
  case "$retired_implementer_state" in
    missing|current|legacy) ;;
    *) report_preflight_error "retired implementer file is $retired_implementer_state and will not be removed: $retired_implementer_destination" ;;
  esac
  case "$reviewer_state" in
    current|legacy|missing) ;;
    *) report_preflight_error "Reviewer destination is $reviewer_state and will not be replaced: $reviewer_destination" ;;
  esac
fi

[ "$preflight_failed" -eq 0 ] || exit 1

if [ "$check_only" -eq 1 ]; then
  if [ -n "$check_roles" ]; then
    printf '%s\n' "CHECK PASSED: selected role templates exactly match $template_dir."
  else
    printf '%s\n' "CHECK PASSED: Luna, Sol implementer, and Reviewer exactly match $template_dir."
  fi
  exit 0
fi

if [ ! -d "$target_dir" ]; then
  mkdir -p "$target_dir" || fail "could not create target directory: $target_dir"
fi
[ -d "$target_dir" ] && [ ! -L "$target_dir" ] ||
  fail "target directory changed after preflight: $target_dir"

same_state Luna "$luna_state" "$(classify_current_or_legacy "$luna_destination" "$luna_template" "$legacy_luna_sha256" "$legacy_luna_v050_sha256")"
same_state Sol-implementer "$implementer_state" "$(classify_current_or_legacy "$implementer_destination" "$implementer_template" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256")"
same_state Retired-implementer "$retired_implementer_state" "$(classify_current_or_legacy "$retired_implementer_destination" "$implementer_template" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256" "$legacy_terra_v080_sha256" "$legacy_terra_gpt6_sha256")"
same_state Reviewer "$reviewer_state" "$(classify_current_or_legacy "$reviewer_destination" "$reviewer_template" "$legacy_reviewer_v073_sha256" "$legacy_reviewer_v080_sha256" '')"

case "$luna_state" in
  missing) install_missing "$luna_template" "$luna_destination" ;;
  legacy) replace_legacy_role Luna "$luna_template" "$luna_destination" "$legacy_luna_sha256" "$legacy_luna_v050_sha256" ;;
  current) printf '%s\n' "ALREADY CURRENT: $luna_destination" ;;
esac

case "$implementer_state" in
  missing) install_missing "$implementer_template" "$implementer_destination" ;;
  legacy) replace_legacy_role Sol-implementer "$implementer_template" "$implementer_destination" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256" ;;
  current) printf '%s\n' "ALREADY CURRENT: $implementer_destination" ;;
esac

case "$retired_implementer_state" in
  current|legacy)
    same_state Retired-implementer "$retired_implementer_state" "$(classify_current_or_legacy "$retired_implementer_destination" "$implementer_template" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256" "$legacy_terra_v080_sha256" "$legacy_terra_gpt6_sha256")"
    rm -f "$retired_implementer_destination" || fail "could not retire old-name implementer file: $retired_implementer_destination"
    printf '%s\n' "RETIRED: $retired_implementer_destination"
    ;;
esac

case "$reviewer_state" in
  missing) install_missing "$reviewer_template" "$reviewer_destination" ;;
  legacy) replace_legacy_role Reviewer "$reviewer_template" "$reviewer_destination" "$legacy_reviewer_v073_sha256" "$legacy_reviewer_v080_sha256" '' ;;
  current) printf '%s\n' "ALREADY CURRENT: $reviewer_destination" ;;
esac

[ "$(classify_current_or_legacy "$luna_destination" "$luna_template" "$legacy_luna_sha256" "$legacy_luna_v050_sha256")" = current ] ||
  fail "post-install exactness check failed: $luna_destination"
[ "$(classify_current_or_legacy "$implementer_destination" "$implementer_template" "$legacy_terra_sha256" "$legacy_terra_v050_sha256" "$legacy_terra_v073_sha256")" = current ] ||
  fail "post-install exactness check failed: $implementer_destination"
[ "$(classify_current_or_legacy "$reviewer_destination" "$reviewer_template" "$legacy_reviewer_v073_sha256" "$legacy_reviewer_v080_sha256" '')" = current ] ||
  fail "post-install exactness check failed: $reviewer_destination"
path_exists "$retired_implementer_destination" && fail "retired implementer file remains: $retired_implementer_destination"

printf '%s\n' "INSTALL PASSED: Luna, Sol implementer, and Reviewer exactly match $template_dir."
