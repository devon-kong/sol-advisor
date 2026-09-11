#!/usr/bin/env python3
"""Snapshot and verify the exact working-tree inputs reviewed by Sol Advisor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Any


SCHEMA_VERSION = 1


class CandidateError(Exception):
    """The candidate could not be established or compared."""


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CandidateError(f"candidate manifest contains duplicate JSON key: {key}")
        value[key] = item
    return value


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def run_git(repo: Path, *args: str, allow_failure: bool = False) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", os.fspath(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    if allow_failure:
        return None
    detail = os.fsdecode(result.stderr).strip() or f"exit {result.returncode}"
    raise CandidateError(f"git {' '.join(args)} failed: {detail}")


def resolve_repo(raw: str) -> Path:
    requested = Path(raw).expanduser().resolve(strict=False)
    output = run_git(requested, "rev-parse", "--show-toplevel")
    assert output is not None
    repo = Path(os.fsdecode(output).strip()).resolve(strict=True)
    if not repo.is_dir():
        raise CandidateError(f"repository root is not a directory: {repo}")
    return repo


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def filesystem_encodable(value: str) -> bool:
    try:
        os.fsencode(value)
        return True
    except UnicodeError:
        return False


def require_manifest_outside_repo(path: Path, repo: Path) -> None:
    resolved = path.expanduser().resolve(strict=False)
    if is_within(resolved, repo):
        raise CandidateError("candidate manifest must be outside the candidate repository")


def canonical_repo_path(path: str) -> bool:
    if (
        not path
        or "\0" in path
        or not filesystem_encodable(path)
        or os.path.isabs(path)
        or os.path.normpath(path) != path
    ):
        return False
    parts = Path(path).parts
    return bool(parts) and all(
        part not in {"", ".", ".."} and part.casefold() != ".git" for part in parts
    )


def canonical_absolute_path(path: str, *, preserve_final_symlink: bool) -> bool:
    if (
        not path
        or "\0" in path
        or not filesystem_encodable(path)
        or not os.path.isabs(path)
        or os.path.normpath(path) != path
    ):
        return False
    candidate = Path(path)
    try:
        if preserve_final_symlink:
            canonical = candidate.parent.resolve(strict=False) / candidate.name
        else:
            canonical = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    return (not preserve_final_symlink or bool(candidate.name)) and os.fspath(canonical) == path


def sha256_fd(fd: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        digest.update(chunk)
    return digest.hexdigest(), size


def stable_regular_file(path: Path, first: os.stat_result) -> dict[str, Any]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CandidateError(f"cannot open candidate file {path}: {exc.strerror}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise CandidateError(f"candidate path changed type while opening: {path}")
        if (before.st_dev, before.st_ino) != (first.st_dev, first.st_ino):
            raise CandidateError(f"candidate path changed while opening: {path}")
        digest, size = sha256_fd(fd)
        after = os.fstat(fd)
    except OSError as exc:
        raise CandidateError(f"cannot read candidate file {path}: {exc.strerror}") from exc
    finally:
        os.close(fd)

    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise CandidateError(f"candidate file changed while reading: {path}")
    try:
        final = os.lstat(path)
    except OSError as exc:
        raise CandidateError(f"candidate path changed after reading {path}: {exc.strerror}") from exc
    if (final.st_dev, final.st_ino) != (before.st_dev, before.st_ino):
        raise CandidateError(f"candidate path changed after reading: {path}")
    return {
        "type": "file",
        "sha256": digest,
        "size": size,
        "executable": bool(before.st_mode & 0o111),
    }


def inspect_path(path: Path, *, allow_missing: bool) -> dict[str, Any]:
    try:
        first = os.lstat(path)
    except FileNotFoundError:
        if allow_missing:
            return {"type": "missing"}
        raise CandidateError(f"explicit candidate input does not exist: {path}")
    except OSError as exc:
        raise CandidateError(f"cannot inspect candidate path {path}: {exc.strerror}") from exc

    if stat.S_ISREG(first.st_mode):
        return stable_regular_file(path, first)
    if stat.S_ISLNK(first.st_mode):
        try:
            target = os.readlink(path)
            final = os.lstat(path)
        except OSError as exc:
            raise CandidateError(f"cannot read candidate symlink {path}: {exc.strerror}") from exc
        if (first.st_dev, first.st_ino) != (final.st_dev, final.st_ino):
            raise CandidateError(f"candidate symlink changed while reading: {path}")
        return {
            "type": "symlink",
            "target": target,
            "sha256": hashlib.sha256(os.fsencode(target)).hexdigest(),
        }
    raise CandidateError(f"unsupported candidate input type: {path}")


def repo_inventory(repo: Path) -> list[tuple[str, dict[str, str] | None]]:
    tracked_output = run_git(repo, "ls-files", "-z", "--stage")
    assert tracked_output is not None
    paths: dict[str, dict[str, str] | None] = {}
    for record in (item for item in tracked_output.split(b"\0") if item):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.split(b" ", 2)
        except ValueError as exc:
            raise CandidateError("git returned an invalid tracked-file inventory") from exc
        path = os.fsdecode(raw_path)
        decoded_mode = mode.decode("ascii", errors="strict")
        decoded_object_id = object_id.decode("ascii", errors="strict")
        if stage != b"0":
            raise CandidateError(f"unmerged index entry is unsupported: {path}")
        if decoded_mode == "160000":
            raise CandidateError(f"Git link or submodule input is unsupported: {path}")
        if decoded_mode not in {"100644", "100755", "120000"}:
            raise CandidateError(f"unsupported Git index mode {decoded_mode}: {path}")
        if not (
            len(decoded_object_id) in {40, 64}
            and all(character in "0123456789abcdef" for character in decoded_object_id)
        ):
            raise CandidateError(f"invalid Git index object ID: {path}")
        if path in paths:
            raise CandidateError(f"duplicate tracked-file inventory entry: {path}")
        paths[path] = {"mode": decoded_mode, "oid": decoded_object_id}

    other_output = run_git(repo, "ls-files", "-z", "--others", "--exclude-standard")
    assert other_output is not None
    for raw_path in (item for item in other_output.split(b"\0") if item):
        path = os.fsdecode(raw_path)
        if path in paths:
            raise CandidateError(f"duplicate worktree inventory entry: {path}")
        paths[path] = None
    return sorted(paths.items(), key=lambda item: os.fsencode(item[0]))


def current_head(repo: Path) -> str | None:
    output = run_git(repo, "rev-parse", "--verify", "HEAD", allow_failure=True)
    return os.fsdecode(output).strip() if output is not None else None


def normalize_explicit_inputs(values: list[str]) -> list[str]:
    normalized: set[str] = set()
    for value in values:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        # Canonicalize the parent while preserving the final component so an explicit
        # symlink binds the link and its target text rather than silently following it.
        path = path.parent.resolve(strict=False) / path.name
        normalized.add(os.fspath(path))
    return sorted(normalized, key=os.fsencode)


def build_candidate(
    repo: Path, explicit_inputs: list[str], *, explicit_allow_missing: bool = False
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for relative, index in repo_inventory(repo):
        path = repo / relative
        try:
            resolved_parent = path.parent.resolve(strict=False)
        except RuntimeError as exc:
            raise CandidateError(f"cannot resolve candidate parent for {relative}: {exc}") from exc
        if resolved_parent != path.parent:
            raise CandidateError(f"symlinked repository parent is unsupported: {relative}")
        details = inspect_path(path, allow_missing=True)
        entries.append({"scope": "repo", "path": relative, "index": index, **details})
    for absolute in explicit_inputs:
        details = inspect_path(Path(absolute), allow_missing=explicit_allow_missing)
        entries.append({"scope": "input", "path": absolute, **details})
    entries.sort(key=lambda item: (item["scope"], os.fsencode(item["path"])))
    selection = {
        "repo_inventory": "tracked-and-unignored-untracked",
        "explicit_inputs": explicit_inputs,
    }
    identity = {"selection": selection, "entries": entries}
    candidate_id = "sha256:" + hashlib.sha256(canonical_json(identity)).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "repo": os.fspath(repo),
        "source": {"head": current_head(repo)},
        "selection": selection,
        "entries": entries,
    }


def validate_manifest(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("schema_version"), int)
        or isinstance(value.get("schema_version"), bool)
        or value.get("schema_version") != SCHEMA_VERSION
    ):
        raise CandidateError("unsupported or missing candidate manifest schema")
    if set(value) != {
        "schema_version",
        "candidate_id",
        "repo",
        "source",
        "selection",
        "entries",
    }:
        raise CandidateError("candidate manifest top-level fields are invalid")
    if not isinstance(value.get("repo"), str) or not canonical_absolute_path(
        value["repo"], preserve_final_symlink=False
    ):
        raise CandidateError("candidate manifest repo path is not canonical")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) != {"head"}:
        raise CandidateError("candidate manifest source is invalid")
    head = source["head"]
    if head is not None and not (
        isinstance(head, str)
        and len(head) in {40, 64}
        and all(character in "0123456789abcdef" for character in head)
    ):
        raise CandidateError("candidate manifest source head is invalid")
    selection = value.get("selection")
    if not isinstance(selection, dict):
        raise CandidateError("candidate manifest selection is invalid")
    if set(selection) != {"repo_inventory", "explicit_inputs"}:
        raise CandidateError("candidate manifest selection fields are invalid")
    if selection.get("repo_inventory") != "tracked-and-unignored-untracked":
        raise CandidateError("candidate manifest repository inventory is unsupported")
    explicit = selection.get("explicit_inputs")
    if not isinstance(explicit, list) or any(
        not isinstance(item, str)
        or not canonical_absolute_path(item, preserve_final_symlink=True)
        for item in explicit
    ):
        raise CandidateError("candidate manifest explicit inputs are invalid")
    if explicit != sorted(set(explicit), key=os.fsencode):
        raise CandidateError("candidate manifest explicit inputs are not canonical")
    entries = value.get("entries")
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise CandidateError("candidate manifest entries are invalid")
    keys: list[tuple[str, str]] = []
    for entry in entries:
        scope, path, kind = entry.get("scope"), entry.get("path"), entry.get("type")
        if (
            not isinstance(scope, str)
            or scope not in {"repo", "input"}
            or not isinstance(path, str)
        ):
            raise CandidateError("candidate manifest entry identity is invalid")
        if scope == "repo" and not canonical_repo_path(path):
            raise CandidateError("candidate manifest repository path is invalid")
        if scope == "input" and not canonical_absolute_path(
            path, preserve_final_symlink=True
        ):
            raise CandidateError("candidate manifest explicit path is invalid")
        if not isinstance(kind, str) or kind not in {"file", "symlink", "missing"}:
            raise CandidateError("candidate manifest entry type is invalid")
        base_fields = {"scope", "path", "type"}
        if scope == "repo":
            base_fields.add("index")
            index = entry.get("index")
            if index is not None:
                if not isinstance(index, dict) or set(index) != {"mode", "oid"}:
                    raise CandidateError("candidate manifest Git index entry is invalid")
                mode, object_id = index.get("mode"), index.get("oid")
                if not (
                    isinstance(mode, str)
                    and mode in {"100644", "100755", "120000"}
                    and isinstance(object_id, str)
                    and len(object_id) in {40, 64}
                    and all(character in "0123456789abcdef" for character in object_id)
                ):
                    raise CandidateError("candidate manifest Git index metadata is invalid")
        elif "index" in entry:
            raise CandidateError("explicit candidate input cannot contain Git index metadata")
        if kind == "file":
            expected_fields = base_fields | {"sha256", "size", "executable"}
            if set(entry) != expected_fields:
                raise CandidateError("candidate manifest file entry fields are invalid")
            digest, size, executable = (
                entry.get("sha256"),
                entry.get("size"),
                entry.get("executable"),
            )
            if not (
                isinstance(digest, str)
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
                and isinstance(size, int)
                and not isinstance(size, bool)
                and size >= 0
                and isinstance(executable, bool)
            ):
                raise CandidateError("candidate manifest file entry is invalid")
        elif kind == "symlink":
            expected_fields = base_fields | {"target", "sha256"}
            if set(entry) != expected_fields:
                raise CandidateError("candidate manifest symlink entry fields are invalid")
            target, digest = entry.get("target"), entry.get("sha256")
            if not (
                isinstance(target, str)
                and bool(target)
                and "\0" not in target
                and filesystem_encodable(target)
                and isinstance(digest, str)
                and digest == hashlib.sha256(os.fsencode(target)).hexdigest()
            ):
                raise CandidateError("candidate manifest symlink entry is invalid")
        elif set(entry) != base_fields:
            raise CandidateError("candidate manifest missing entry is invalid")
        keys.append((scope, path))
    if keys != sorted(set(keys), key=lambda item: (item[0], os.fsencode(item[1]))):
        raise CandidateError("candidate manifest entries are not canonical")
    input_paths = [path for scope, path in keys if scope == "input"]
    if input_paths != explicit:
        raise CandidateError("candidate manifest explicit entries do not match selection")
    if any(entry["type"] == "missing" for entry in entries if entry["scope"] == "input"):
        raise CandidateError("candidate manifest cannot snapshot a missing explicit input")
    identity = {"selection": selection, "entries": entries}
    expected = "sha256:" + hashlib.sha256(canonical_json(identity)).hexdigest()
    if value.get("candidate_id") != expected:
        raise CandidateError("candidate manifest identifier does not match its contents")
    return value


def write_manifest(path: Path, value: dict[str, Any]) -> None:
    parent = path.parent
    if not parent.is_dir():
        raise CandidateError(f"manifest parent directory does not exist: {parent}")
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise CandidateError(f"cannot write candidate manifest {path}: {exc.strerror}") from exc


def entry_map(entries: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(item["scope"], item["path"]): item for item in entries}


def compare_entries(
    expected: list[dict[str, Any]], current: list[dict[str, Any]]
) -> list[dict[str, str]]:
    old, new = entry_map(expected), entry_map(current)
    changes: list[dict[str, str]] = []
    for key in sorted(set(old) | set(new), key=lambda item: (item[0], os.fsencode(item[1]))):
        if key not in old:
            change = "added"
        elif key not in new:
            change = "removed"
        elif old[key] != new[key]:
            change = "modified"
        else:
            continue
        changes.append({"scope": key[0], "path": key[1], "change": change})
    return changes


def snapshot_command(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.repo)
    output = Path(args.output).expanduser().resolve(strict=False)
    require_manifest_outside_repo(output, repo)
    explicit = normalize_explicit_inputs(args.input)
    manifest = build_candidate(repo, explicit)
    write_manifest(output, manifest)
    print(
        json.dumps(
            {
                "status": "snapshotted",
                "candidate_id": manifest["candidate_id"],
                "manifest": os.fspath(output),
                "entry_count": len(manifest["entries"]),
            },
            sort_keys=True,
        )
    )
    return 0


def verify_command(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve(strict=True)
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = validate_manifest(json.load(handle, object_pairs_hook=unique_json_object))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"cannot read candidate manifest {manifest_path}: {exc}") from exc
    repo = resolve_repo(manifest["repo"])
    require_manifest_outside_repo(manifest_path, repo)
    current = build_candidate(
        repo, manifest["selection"]["explicit_inputs"], explicit_allow_missing=True
    )
    changes = compare_entries(manifest["entries"], current["entries"])
    matched = not changes and current["candidate_id"] == manifest["candidate_id"]
    print(
        json.dumps(
            {
                "status": "match" if matched else "changed",
                "candidate_id": manifest["candidate_id"],
                "current_candidate_id": current["candidate_id"],
                "head_changed": current["source"]["head"]
                != manifest["source"]["head"],
                "changes": changes,
            },
            sort_keys=True,
        )
    )
    return 0 if matched else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Bind Sol Advisor review evidence to exact working-tree inputs."
    )
    commands = result.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="write a candidate manifest")
    snapshot.add_argument("--repo", required=True, help="Git working tree to snapshot")
    snapshot.add_argument("--output", required=True, help="manifest path outside the repository")
    snapshot.add_argument(
        "--input",
        action="append",
        default=[],
        help="ignored or repository-external input to include; repeat as needed",
    )
    snapshot.set_defaults(handler=snapshot_command)
    verify = commands.add_parser("verify", help="compare a manifest with current inputs")
    verify.add_argument("--manifest", required=True, help="manifest created by snapshot")
    verify.set_defaults(handler=verify_command)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except CandidateError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
