#!/usr/bin/env python3
"""Deterministic storage and assembly commands for the full-route protocol.

This module owns mechanical validation, immutable publication, expected-version state
updates, and byte-level assembly.  It never chooses a semantic winner or verdict.
"""

from __future__ import annotations

import argparse
import base64
import copy
import fcntl
import hashlib
import json
import os
import shutil
import secrets
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping

import candidate as candidate_tool
import full_protocol


ERROR_CATEGORIES = frozenset(
    {
        "invalid-input",
        "scope-conflict",
        "stale-baseline",
        "missing-evidence",
        "candidate-changed",
        "runtime-unavailable",
        "execution-failed",
        "execution-incomplete",
        "review-invalid",
    }
)


class WorkflowError(RuntimeError):
    """Structured workflow failure with explicit side-effect and recovery facts."""

    def __init__(
        self, category: str, message: str, *, affected: str,
        side_effect: str = "none", recovery: str = "correct-input-and-retry",
    ) -> None:
        if category not in ERROR_CATEGORIES:
            raise ValueError(f"unsupported workflow error category: {category}")
        if side_effect not in {"none", "durable", "unknown"}:
            raise ValueError(f"unsupported workflow side-effect status: {side_effect}")
        super().__init__(message)
        self.category = category
        self.affected = affected
        self.side_effect = side_effect
        self.recovery = recovery

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "error",
            "category": self.category,
            "message": str(self),
            "affected": self.affected,
            "side_effect": self.side_effect,
            "recovery": self.recovery,
        }


def require_fd_publication_capability() -> None:
    required = (os.open, os.mkdir, os.link, os.rename, os.unlink)
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0) or any(item not in os.supports_dir_fd for item in required):
        raise WorkflowError(
            "runtime-unavailable", "host lacks required directory-fd publication primitives",
            affected="fd-publication", recovery="use-a-supported-runtime",
        )


def _regular_bytes(path: Path, *, category: str = "missing-evidence") -> bytes:
    try:
        details = path.lstat()
    except FileNotFoundError as error:
        raise WorkflowError(
            category, f"required file is missing: {path}", affected=os.fspath(path)
        ) from error
    if not stat.S_ISREG(details.st_mode):
        raise WorkflowError(
            "scope-conflict", f"path is not a regular file: {path}",
            affected=os.fspath(path), recovery="replace-with-task-owned-regular-file",
        )
    try:
        return path.read_bytes()
    except OSError as error:
        raise WorkflowError(
            category, f"cannot read required file {path}: {error}", affected=os.fspath(path)
        ) from error


def _json_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _regular_bytes(path)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=candidate_tool.unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, candidate_tool.CandidateError) as error:
        raise WorkflowError(
            "invalid-input", f"invalid JSON file {path}: {error}", affected=os.fspath(path)
        ) from error
    if not isinstance(value, dict):
        raise WorkflowError(
            "invalid-input", f"JSON input must be an object: {path}", affected=os.fspath(path)
        )
    return value, raw


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _open_child_dir(parent_fd: int, component: str, *, create: bool) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(component, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        os.mkdir(component, 0o700, dir_fd=parent_fd)
        return os.open(component, flags, dir_fd=parent_fd)


def _read_fd_bytes(parent_fd: int, name: str) -> bytes | None:
    try:
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise WorkflowError("scope-conflict", "immutable target is not regular", affected=name)
        result: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            result.append(chunk)
        return b"".join(result)
    finally:
        os.close(descriptor)


def _publish_task_immutable_bytes_locked(
    task: Path, clean: list[str], payload: bytes,
    *, before_link: Callable[[], None] | None = None,
) -> str:
    """Publish immutable bytes while the caller holds the task dual lock."""

    anchor_fd = os.open(task.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    root_fd: int | None = None
    parent_fd: int | None = None
    opened: list[int] = []
    temporary: str | None = None
    try:
        root_component = _task_component(task.name, "task root component")
        root_fd = _open_child_dir(anchor_fd, root_component, create=False)
        parent_fd = root_fd
        for component in clean[:-1]:
            child = _open_child_dir(parent_fd, component, create=True)
            if parent_fd != root_fd:
                opened.append(parent_fd)
            parent_fd = child
        existing = _read_fd_bytes(parent_fd, clean[-1])
        if existing is not None:
            if existing == payload:
                return "identical"
            raise WorkflowError("scope-conflict", "immutable task target already differs", affected=clean[-1])
        for _ in range(32):
            candidate = "tmp-" + secrets.token_hex(16)
            try:
                descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
                temporary = candidate
                break
            except FileExistsError:
                continue
        else:
            raise WorkflowError("execution-incomplete", "cannot allocate unique fd-relative temporary file", affected=clean[-1])
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if before_link is not None:
            before_link()
        # Reopen the task root and logical parent to prove retained fds still name them.
        named_root = _open_child_dir(anchor_fd, root_component, create=False)
        named_parent = named_root
        reopened: list[int] = []
        try:
            if _fd_identity(named_root) != _fd_identity(root_fd):
                raise WorkflowError("execution-incomplete", "task root changed before publication", affected=os.fspath(task), side_effect="unknown")
            for component in clean[:-1]:
                child = _open_child_dir(named_parent, component, create=False)
                if named_parent != named_root:
                    reopened.append(named_parent)
                named_parent = child
            if _fd_identity(named_parent) != _fd_identity(parent_fd):
                raise WorkflowError("execution-incomplete", "task output parent changed before publication", affected=clean[-1], side_effect="unknown")
        finally:
            for descriptor_to_close in reversed(reopened):
                os.close(descriptor_to_close)
            if named_parent != named_root:
                os.close(named_parent)
            os.close(named_root)
        try:
            os.link(temporary, clean[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
        except FileExistsError:
            existing = _read_fd_bytes(parent_fd, clean[-1])
            if existing == payload:
                return "identical"
            raise WorkflowError("scope-conflict", "immutable task target raced with different bytes", affected=clean[-1])
        os.fsync(parent_fd)
        if _read_fd_bytes(parent_fd, clean[-1]) != payload:
            raise WorkflowError("execution-incomplete", "task output changed after fd publication", affected=clean[-1], side_effect="unknown")
        return "created"
    except OSError as error:
        raise WorkflowError("execution-incomplete", f"fd-relative task publication failed: {error}", affected=os.fspath(task), side_effect="unknown") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except (FileNotFoundError, OSError):
                pass
        for descriptor_to_close in reversed(opened):
            os.close(descriptor_to_close)
        if parent_fd is not None and parent_fd != root_fd:
            os.close(parent_fd)
        if root_fd is not None:
            os.close(root_fd)
        os.close(anchor_fd)


def publish_task_immutable_bytes(
    task_dir: Path | str, components: list[str], payload: bytes,
    *, before_link: Callable[[], None] | None = None,
) -> str:
    """Create-no-replace task output using only retained directory descriptors."""

    if not components:
        raise WorkflowError("invalid-input", "task output component chain is empty", affected="components")
    clean = [_task_component(item, "task output component") for item in components]
    task = Path(task_dir).absolute()
    with _task_lock(task):
        return _publish_task_immutable_bytes_locked(task, clean, payload, before_link=before_link)


def publish_task_path_bytes(task_dir: Path | str, path: Path | str, payload: bytes) -> str:
    task = Path(task_dir).absolute()
    target = Path(path).absolute()
    try:
        relative = target.relative_to(task)
    except ValueError as error:
        raise WorkflowError("scope-conflict", "task publication path escapes task root", affected=os.fspath(target)) from error
    return publish_task_immutable_bytes(task, list(relative.parts), payload)


def publish_task_path_json(task_dir: Path | str, path: Path | str, value: object) -> str:
    return publish_task_path_bytes(task_dir, path, full_protocol.canonical_json_bytes(value))


def replace_task_path_json(task_dir: Path | str, path: Path | str, value: object) -> None:
    """Atomically replace a task JSON record relative to retained directory fds.

    Callers already hold ``_task_lock``; this helper intentionally does not acquire it again.
    """

    task = Path(task_dir).absolute()
    target = Path(path).absolute()
    try:
        relative = target.relative_to(task)
    except ValueError as error:
        raise WorkflowError("scope-conflict", "task replacement path escapes task root", affected=os.fspath(target)) from error
    parts = [_task_component(part, "task output component") for part in relative.parts]
    payload = full_protocol.canonical_json_bytes(value)
    anchor_fd = os.open(task.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    root_fd: int | None = None
    parent_fd: int | None = None
    opened: list[int] = []
    temporary: str | None = None
    try:
        root_fd = _open_child_dir(anchor_fd, _task_component(task.name, "task root component"), create=False)
        parent_fd = root_fd
        for component in parts[:-1]:
            child = _open_child_dir(parent_fd, component, create=True)
            if parent_fd != root_fd:
                opened.append(parent_fd)
            parent_fd = child
        temporary = "tmp-" + secrets.token_hex(16)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(temporary, parts[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = None
        os.fsync(parent_fd)
        if _read_fd_bytes(parent_fd, parts[-1]) != payload:
            raise WorkflowError("execution-incomplete", "task state changed after fd replacement", affected=parts[-1], side_effect="unknown")
    except OSError as error:
        raise WorkflowError("execution-incomplete", f"fd-relative task replacement failed: {error}", affected=os.fspath(task), side_effect="unknown") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except (FileNotFoundError, OSError):
                pass
        for descriptor_to_close in reversed(opened):
            os.close(descriptor_to_close)
        if parent_fd is not None and parent_fd != root_fd:
            os.close(parent_fd)
        if root_fd is not None:
            os.close(root_fd)
        os.close(anchor_fd)


def _open_task_parent(task: Path, parts: list[str], *, create: bool) -> tuple[int, int, list[int]]:
    anchor_fd = os.open(task.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    root_fd = _open_child_dir(anchor_fd, _task_component(task.name, "task root component"), create=False)
    parent_fd = root_fd
    opened: list[int] = []
    for component in parts:
        child = _open_child_dir(parent_fd, _task_component(component, "task output component"), create=create)
        if parent_fd != root_fd:
            opened.append(parent_fd)
        parent_fd = child
    return anchor_fd, root_fd, [*opened, parent_fd]


def open_task_private_file(task_dir: Path | str, components: list[str]) -> int:
    """Create an unlinked-from-path-race private task file and return its descriptor."""

    if not components:
        raise WorkflowError("invalid-input", "private task file component chain is empty", affected="components")
    task = Path(task_dir).absolute()
    clean = [_task_component(item, "task output component") for item in components]
    anchor_fd, root_fd, descriptors = _open_task_parent(task, clean[:-1], create=True)
    parent_fd = descriptors[-1] if descriptors else root_fd
    try:
        return os.open(clean[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
    except OSError as error:
        raise WorkflowError("execution-incomplete", f"cannot create private task file: {error}", affected=clean[-1], side_effect="unknown") from error
    finally:
        for descriptor in reversed(descriptors):
            if descriptor != root_fd:
                os.close(descriptor)
        os.close(root_fd)
        os.close(anchor_fd)


def read_task_path_bytes(task_dir: Path | str, components: list[str]) -> bytes:
    if not components:
        raise WorkflowError("invalid-input", "task read component chain is empty", affected="components")
    task = Path(task_dir).absolute()
    clean = [_task_component(item, "task output component") for item in components]
    anchor_fd, root_fd, descriptors = _open_task_parent(task, clean[:-1], create=False)
    parent_fd = descriptors[-1] if descriptors else root_fd
    try:
        value = _read_fd_bytes(parent_fd, clean[-1])
        if value is None:
            raise WorkflowError("missing-evidence", "task path is missing", affected=clean[-1])
        return value
    finally:
        for descriptor in reversed(descriptors):
            if descriptor != root_fd:
                os.close(descriptor)
        os.close(root_fd)
        os.close(anchor_fd)


def move_directory_into_task(task_dir: Path | str, path: Path | str, source: Path | str) -> None:
    """Atomically move an isolated staging directory into the verified task tree."""

    task = Path(task_dir).absolute()
    target = Path(path).absolute()
    staging = Path(source).absolute()
    try:
        relative = target.relative_to(task)
    except ValueError as error:
        raise WorkflowError("scope-conflict", "task directory destination escapes task root", affected=os.fspath(target)) from error
    parts = [_task_component(part, "task output component") for part in relative.parts]
    if not staging.is_dir() or staging.is_symlink():
        raise WorkflowError("invalid-input", "staging output is not a real directory", affected=os.fspath(staging))
    anchor_fd, root_fd, descriptors = _open_task_parent(task, parts[:-1], create=True)
    parent_fd = descriptors[-1] if descriptors else root_fd
    source_parent_fd = os.open(staging.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise WorkflowError("scope-conflict", "task directory target already exists", affected=parts[-1])
        os.rename(staging.name, parts[-1], src_dir_fd=source_parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        moved_fd = _open_child_dir(parent_fd, parts[-1], create=False)
        os.close(moved_fd)
    except OSError as error:
        raise WorkflowError("execution-incomplete", f"cannot move staging directory into task: {error}", affected=parts[-1], side_effect="unknown") from error
    finally:
        os.close(source_parent_fd)
        for descriptor in reversed(descriptors):
            if descriptor != root_fd:
                os.close(descriptor)
        os.close(root_fd)
        os.close(anchor_fd)


def _fd_file_digest(parent_fd: int, name: str) -> str:
    descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise WorkflowError("review-invalid", "task tree has a non-regular file", affected=name)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _task_tree_entries(directory_fd: int, prefix: str = "", excluded_root_names: set[str] | None = None) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    with os.scandir(directory_fd) as scan:
        names = sorted((entry.name for entry in scan), key=os.fsencode)
    for name in names:
        if name in {".", ".."}:
            continue
        if not prefix and excluded_root_names and name in excluded_root_names:
            continue
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        path = name if not prefix else f"{prefix}/{name}"
        if stat.S_ISLNK(details.st_mode) or not (stat.S_ISREG(details.st_mode) or stat.S_ISDIR(details.st_mode)):
            raise WorkflowError("review-invalid", "task tree contains an unsupported alias or type", affected=path)
        if stat.S_ISREG(details.st_mode):
            entries.append({"path": path, "type": "file", "mode": stat.S_IMODE(details.st_mode), "sha256": _fd_file_digest(directory_fd, name)})
            continue
        child_fd = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            entries.append({"path": path, "type": "dir", "mode": stat.S_IMODE(details.st_mode)})
            entries.extend(_task_tree_entries(child_fd, path, excluded_root_names))
        finally:
            os.close(child_fd)
    return entries


def task_tree_identity(task_dir: Path | str, *, excluded_root_names: set[str] | None = None) -> dict[str, object]:
    task = Path(task_dir).absolute()
    anchor_fd = os.open(task.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        root_fd = _open_child_dir(anchor_fd, _task_component(task.name, "task root component"), create=False)
        try:
            entries = _task_tree_entries(root_fd, excluded_root_names=excluded_root_names)
        finally:
            os.close(root_fd)
    finally:
        os.close(anchor_fd)
    return {"entries": entries, "digest": full_protocol.canonical_digest(entries)}


@contextmanager
def reviewer_window(task_dir: Path | str) -> Iterator[dict[str, object]]:
    """Freeze cooperating writers and reject any task-tree mutation by the reviewer."""

    task = Path(task_dir).absolute()
    result: dict[str, object] = {}
    with _task_lock(task):
        before = task_tree_identity(task)
        yield result
        after = task_tree_identity(task)
        result.update({"before_tree_digest": before["digest"], "after_tree_digest": after["digest"]})
        if before["digest"] != after["digest"]:
            raise WorkflowError("review-invalid", "reviewer window changed task-root bytes", affected=os.fspath(task), side_effect="unknown", recovery="invalidate-review-and-reconcile")


def _checked_window_record(path: Path, digest_key: str) -> dict[str, Any]:
    record, payload = _json_bytes(path)
    if payload != full_protocol.canonical_json_bytes(record) or record.get(digest_key) != full_protocol.canonical_digest({key: value for key, value in record.items() if key != digest_key}):
        raise WorkflowError("candidate-changed", "reviewer window record drifted", affected=os.fspath(path))
    return record


def begin_reviewer_window(task_dir: Path | str, *, window_id: str, candidate_identity: Mapping[str, object]) -> dict[str, object]:
    """Capture every existing input before dispatch; later evidence may only append."""
    task = Path(task_dir).absolute()
    window_id = _task_component(window_id, "reviewer window ID")
    if not isinstance(candidate_identity, Mapping) or not candidate_identity:
        raise WorkflowError("invalid-input", "reviewer window candidate identity is required", affected=window_id)
    path = task / "review-windows" / window_id / "begin.json"
    with _task_lock(task):
        if path.exists() or path.is_symlink():
            record = _checked_window_record(path, "begin_record_digest")
            if record.get("candidate") != dict(candidate_identity):
                raise WorkflowError("scope-conflict", "reviewer window cannot be rebound", affected=window_id)
            return record
        before = task_tree_identity(task, excluded_root_names={"review-windows"})
        record = {"window_id": window_id, "candidate": dict(candidate_identity), "task_tree": before["digest"], "protected_entries": before["entries"], "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
        record["begin_record_digest"] = full_protocol.canonical_digest(record)
        _publish_task_immutable_bytes_locked(task, ["review-windows", window_id, "begin.json"], full_protocol.canonical_json_bytes(record))
    return record


def end_reviewer_window(task_dir: Path | str, *, window_id: str, candidate_identity: Mapping[str, object], runtime_receipt: Mapping[str, object]) -> dict[str, object]:
    """Bind Root's post-review observation, retaining all pre-existing evidence."""
    task = Path(task_dir).absolute()
    window_id = _task_component(window_id, "reviewer window ID")
    thread_id = runtime_receipt.get("thread_id")
    context_id = runtime_receipt.get("context_id", thread_id)
    if any(not isinstance(value, str) or not value for value in (thread_id, context_id)):
        raise WorkflowError("runtime-unavailable", "reviewer lifecycle identity is unavailable", affected=window_id)
    with _task_lock(task):
        begin = _checked_window_record(task / "review-windows" / window_id / "begin.json", "begin_record_digest")
        end_path = task / "review-windows" / window_id / "end.json"
        if begin.get("candidate") != dict(candidate_identity):
            raise WorkflowError("review-invalid", "reviewer candidate changed", affected=window_id)
        if end_path.exists() or end_path.is_symlink():
            end = _checked_window_record(end_path, "end_record_digest")
            if end.get("begin_record_digest") != begin["begin_record_digest"] or end.get("candidate") != dict(candidate_identity) or end.get("reviewer_thread_id") != thread_id or end.get("context_id") != context_id:
                raise WorkflowError("scope-conflict", "closed reviewer window cannot be rebound", affected=window_id)
        else:
            after = task_tree_identity(task, excluded_root_names={"review-windows"})
            protected = begin.get("protected_entries")
            if not isinstance(protected, list) or full_protocol.canonical_digest(protected) != begin.get("task_tree"):
                raise WorkflowError("review-invalid", "reviewer window lacks its protected input inventory", affected=window_id)
            current = {entry["path"]: entry for entry in after["entries"]}
            if any(current.get(entry["path"]) != entry for entry in protected):
                raise WorkflowError("review-invalid", "reviewer lifecycle changed existing task inputs", affected=window_id)
            old_paths = {entry["path"] for entry in protected}
            additions = [entry for entry in after["entries"] if entry["path"] not in old_paths]
            permitted = {"runs", "evidence", "challenges", "review-probes", "operation-intent", "operation-receipt"}
            if any(entry["path"].split("/")[0] not in permitted for entry in additions):
                raise WorkflowError("review-invalid", "reviewer lifecycle added unauthorized task inputs", affected=window_id)
            end = {"window_id": window_id, "begin_record_digest": begin["begin_record_digest"], "candidate": dict(candidate_identity), "task_tree": begin["task_tree"], "appended_records_digest": full_protocol.canonical_digest(additions), "reviewer_thread_id": thread_id, "context_id": context_id, "ended_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
            if end["ended_at"] <= begin["started_at"]:
                raise WorkflowError("execution-incomplete", "reviewer lifecycle clock did not advance", affected=window_id)
            end["end_record_digest"] = full_protocol.canonical_digest(end)
            _publish_task_immutable_bytes_locked(task, ["review-windows", window_id, "end.json"], full_protocol.canonical_json_bytes(end))
    return {"window_id": window_id, "context_id": end["context_id"], "reviewer_thread_id": end["reviewer_thread_id"], "candidate_before": begin["candidate"], "candidate_after": end["candidate"], "task_tree_before": begin["task_tree"], "task_tree_after": end["task_tree"], "begin_record_digest": begin["begin_record_digest"], "end_record_digest": end["end_record_digest"], "started_at": begin["started_at"], "ended_at": end["ended_at"]}


def _fd_identity(descriptor: int) -> dict[str, int]:
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode) and not stat.S_ISDIR(details.st_mode):
        raise WorkflowError("scope-conflict", "bootstrap identity is not a regular file or directory", affected="bootstrap")
    identity = {"st_dev": details.st_dev, "st_ino": details.st_ino, "mode": stat.S_IMODE(details.st_mode)}
    if stat.S_ISREG(details.st_mode):
        identity["st_nlink"] = details.st_nlink
    return identity


def _read_fd_json(parent_fd: int, name: str) -> dict[str, Any] | None:
    try:
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise WorkflowError("scope-conflict", "bootstrap record is not a single regular file", affected=name)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        value = json.loads(b"".join(chunks).decode("utf-8"), object_pairs_hook=candidate_tool.unique_json_object)
        if not isinstance(value, dict):
            raise WorkflowError("invalid-input", "bootstrap record is not an object", affected=name)
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, candidate_tool.CandidateError) as error:
        if isinstance(error, WorkflowError):
            raise
        raise WorkflowError("execution-incomplete", f"cannot read bootstrap record: {error}", affected=name) from error
    finally:
        os.close(descriptor)


def _publish_fd_json(parent_fd: int, name: str, value: object) -> None:
    payload = full_protocol.canonical_json_bytes(value)
    temporary = "tmp-" + secrets.token_hex(16)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=parent_fd,
    )
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
    except FileExistsError:
        existing = _read_fd_json(parent_fd, name)
        if existing != value:
            raise WorkflowError("scope-conflict", "bootstrap record already differs", affected=name)
    finally:
        os.unlink(temporary, dir_fd=parent_fd)
    reread = _read_fd_json(parent_fd, name)
    if reread != value:
        raise WorkflowError("execution-incomplete", "bootstrap record changed after publication", affected=name, side_effect="unknown")
    os.fsync(parent_fd)


def bootstrap_task(
    anchor_path: Path | str, root_components: list[str], contract: Mapping[str, object], state: Mapping[str, object],
) -> dict[str, object]:
    """Create or validate the ancestor-local bootstrap identity before task writes."""

    require_fd_publication_capability()
    if not root_components:
        raise WorkflowError("invalid-input", "task root component chain must not be empty", affected="root_components")
    try:
        components = [full_protocol.canonical_component(item, "task root component") for item in root_components]
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("invalid-input", str(error), affected="root_components") from error
    anchor = Path(anchor_path).absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        anchor_fd = os.open(anchor, flags)
    except OSError as error:
        raise WorkflowError("runtime-unavailable", f"cannot open stable task ancestor: {error}", affected=os.fspath(anchor)) from error
    name_digest = hashlib.sha256("/".join(components).encode("utf-8")).hexdigest()
    lock_name = f"sa-bootstrap-lock-{name_digest}"
    record_name = f"sa-bootstrap-record-{name_digest}"
    try:
        bootstrap_fd = os.open(lock_name, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=anchor_fd)
        lock_identity = _fd_identity(bootstrap_fd)
        if not stat.S_ISREG(os.fstat(bootstrap_fd).st_mode) or lock_identity["st_nlink"] != 1:
            raise WorkflowError("scope-conflict", "bootstrap lock is not a single regular file", affected=lock_name)
        fcntl.flock(bootstrap_fd, fcntl.LOCK_EX)
        named_lock_fd = os.open(lock_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=anchor_fd)
        try:
            if _fd_identity(named_lock_fd) != lock_identity:
                raise WorkflowError("execution-incomplete", "bootstrap lock was replaced", affected=lock_name)
        finally:
            os.close(named_lock_fd)
        record = _read_fd_json(anchor_fd, record_name)
        current_fd = anchor_fd
        root_fd: int | None = None
        if record is None:
            try:
                existing_root_fd = os.open(components[0], flags, dir_fd=anchor_fd)
            except FileNotFoundError:
                existing_root_fd = None
            if existing_root_fd is not None:
                os.close(existing_root_fd)
                raise WorkflowError("execution-incomplete", "task root exists without a bootstrap record", affected=os.fspath(anchor.joinpath(*components)), side_effect="unknown")
            for component in components:
                try:
                    child_fd = os.open(component, flags, dir_fd=current_fd)
                except FileNotFoundError:
                    os.mkdir(component, 0o700, dir_fd=current_fd)
                    child_fd = os.open(component, flags, dir_fd=current_fd)
                if current_fd != anchor_fd:
                    os.close(current_fd)
                current_fd = child_fd
            root_fd = current_fd
            task_lock_fd = os.open(".workflow.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
            try:
                task_lock = _fd_identity(task_lock_fd)
                if not stat.S_ISREG(os.fstat(task_lock_fd).st_mode) or task_lock["st_nlink"] != 1:
                    raise WorkflowError("scope-conflict", "task lock is not a single regular file", affected=".workflow.lock")
            finally:
                os.close(task_lock_fd)
            record = {
                "schema": "SA-TASK-BOOTSTRAP-1", "anchor": _fd_identity(anchor_fd),
                "root_components": components, "bootstrap_lock": lock_identity,
                "task_root": _fd_identity(root_fd), "task_lock": task_lock,
                "initial_contract_digest": full_protocol.canonical_digest(contract),
                "initial_state_digest": full_protocol.canonical_digest(state),
            }
            record["bootstrap_digest"] = full_protocol.canonical_digest(record)
            _publish_fd_json(anchor_fd, record_name, record)
            os.close(root_fd)
            root_fd = None
        else:
            if record.get("bootstrap_digest") != full_protocol.canonical_digest({key: item for key, item in record.items() if key != "bootstrap_digest"}):
                raise WorkflowError("invalid-input", "bootstrap record digest is invalid", affected=record_name)
            if record.get("root_components") != components or record.get("bootstrap_lock") != lock_identity:
                raise WorkflowError("scope-conflict", "bootstrap record does not bind this task", affected=record_name)
            if record.get("initial_contract_digest") != full_protocol.canonical_digest(contract) or record.get("initial_state_digest") != full_protocol.canonical_digest(state):
                raise WorkflowError("scope-conflict", "bootstrap record does not bind the initial request", affected=record_name)
            root_fd = os.open(components[0], flags, dir_fd=anchor_fd)
            try:
                if record.get("task_root") != _fd_identity(root_fd):
                    raise WorkflowError("execution-incomplete", "task root identity changed", affected=os.fspath(anchor.joinpath(*components)))
                record_task_lock_fd = os.open(".workflow.lock", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
                try:
                    if record.get("task_lock") != _fd_identity(record_task_lock_fd):
                        raise WorkflowError("execution-incomplete", "task lock identity changed", affected=".workflow.lock")
                finally:
                    os.close(record_task_lock_fd)
                names = set(os.listdir(root_fd))
                permitted = {".workflow.lock", "task-contract.json", "state.json"}
                unexpected = names.difference(permitted)
                if unexpected:
                    raise WorkflowError("execution-incomplete", "task bootstrap has unexpected early artifacts", affected=", ".join(sorted(unexpected)), side_effect="unknown")
                contract_bytes = _read_fd_bytes(root_fd, "task-contract.json")
                state_bytes = _read_fd_bytes(root_fd, "state.json")
                expected_contract = full_protocol.canonical_json_bytes(contract)
                expected_state = full_protocol.canonical_json_bytes(state)
                if contract_bytes is None and state_bytes is not None:
                    raise WorkflowError("execution-incomplete", "task bootstrap has state without contract", affected="state.json", side_effect="unknown")
                if contract_bytes is not None and contract_bytes != expected_contract:
                    raise WorkflowError("scope-conflict", "task bootstrap contract bytes differ", affected="task-contract.json")
                if state_bytes is not None and state_bytes != expected_state:
                    raise WorkflowError("scope-conflict", "task bootstrap state bytes differ", affected="state.json")
            finally:
                os.close(root_fd)
        return {"record": record, "anchor": anchor, "task": anchor.joinpath(*components)}
    except OSError as error:
        raise WorkflowError("execution-incomplete", f"bootstrap failed: {error}", affected=os.fspath(anchor), side_effect="unknown") from error
    finally:
        try:
            fcntl.flock(bootstrap_fd, fcntl.LOCK_UN)
            os.close(bootstrap_fd)
        except UnboundLocalError:
            pass
        os.close(anchor_fd)


@contextmanager
def _task_lock(task_dir: Path) -> Iterator[None]:
    task = task_dir.absolute()
    anchor = task.parent
    component = _task_component(task.name, "task root component")
    name_digest = hashlib.sha256(component.encode("utf-8")).hexdigest()
    lock_name = f"sa-bootstrap-lock-{name_digest}"
    record_name = f"sa-bootstrap-record-{name_digest}"
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        anchor_fd = os.open(anchor, flags)
        bootstrap_fd = os.open(lock_name, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), dir_fd=anchor_fd)
    except OSError as error:
        raise WorkflowError("execution-incomplete", f"task bootstrap lock is unavailable: {error}", affected=os.fspath(task)) from error
    try:
        fcntl.flock(bootstrap_fd, fcntl.LOCK_EX)
        record = _read_fd_json(anchor_fd, record_name)
        if record is None or record.get("bootstrap_digest") != full_protocol.canonical_digest({key: item for key, item in (record or {}).items() if key != "bootstrap_digest"}):
            raise WorkflowError("execution-incomplete", "task bootstrap record is unavailable or invalid", affected=record_name)
        bootstrap_identity = _fd_identity(bootstrap_fd)
        named_bootstrap_fd = os.open(lock_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=anchor_fd)
        try:
            if record.get("bootstrap_lock") != bootstrap_identity or _fd_identity(named_bootstrap_fd) != bootstrap_identity:
                raise WorkflowError("execution-incomplete", "task bootstrap lock identity changed", affected=lock_name)
        finally:
            os.close(named_bootstrap_fd)
        root_fd = os.open(component, flags, dir_fd=anchor_fd)
        try:
            if record.get("task_root") != _fd_identity(root_fd):
                raise WorkflowError("execution-incomplete", "task root identity changed", affected=os.fspath(task))
            descriptor = os.open(".workflow.lock", os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                named_task_fd = os.open(".workflow.lock", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
                try:
                    task_identity = _fd_identity(descriptor)
                    if task_identity != _fd_identity(named_task_fd) or record.get("task_lock") != task_identity:
                        raise WorkflowError("execution-incomplete", "task lock identity changed", affected=".workflow.lock")
                finally:
                    os.close(named_task_fd)
                try:
                    yield
                finally:
                    named_bootstrap_fd: int | None = None
                    named_root_fd: int | None = None
                    named_task_fd: int | None = None
                    try:
                        named_bootstrap_fd = os.open(lock_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=anchor_fd)
                        named_root_fd = os.open(component, flags, dir_fd=anchor_fd)
                        named_task_fd = os.open(".workflow.lock", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=named_root_fd)
                        if record.get("bootstrap_lock") != _fd_identity(bootstrap_fd) or _fd_identity(named_bootstrap_fd) != _fd_identity(bootstrap_fd):
                            raise WorkflowError("execution-incomplete", "bootstrap lock changed before mutation completion", affected=lock_name)
                        if record.get("task_root") != _fd_identity(named_root_fd) or _fd_identity(named_root_fd) != _fd_identity(root_fd):
                            raise WorkflowError("execution-incomplete", "task root changed before mutation completion", affected=os.fspath(task))
                        if record.get("task_lock") != _fd_identity(descriptor) or _fd_identity(named_task_fd) != _fd_identity(descriptor):
                            raise WorkflowError("execution-incomplete", "task lock changed before mutation completion", affected=".workflow.lock")
                    except OSError as error:
                        raise WorkflowError("execution-incomplete", f"task lock continuity check failed: {error}", affected=os.fspath(task), side_effect="unknown") from error
                    finally:
                        for fd in (named_task_fd, named_root_fd, named_bootstrap_fd):
                            if fd is not None:
                                os.close(fd)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
        finally:
            os.close(root_fd)
    finally:
        fcntl.flock(bootstrap_fd, fcntl.LOCK_UN)
        os.close(bootstrap_fd)
        os.close(anchor_fd)


def initialize_task(task_dir: Path | str, contract_value: object, state_value: object) -> dict[str, object]:
    task = Path(task_dir).absolute()
    try:
        contract = full_protocol.validate_task_contract(contract_value)
        state = full_protocol.validate_state(state_value)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError(
            "invalid-input", f"invalid initial task records: {error}", affected=os.fspath(task)
        ) from error
    if state["contract_digest"] != contract["contract_digest"]:
        raise WorkflowError(
            "invalid-input", "initial state does not bind the task contract",
            affected=os.fspath(task),
        )
    bootstrap_task(task.parent, [task.name], contract, state)
    publish_task_path_json(task, task / "task-contract.json", contract)
    with _task_lock(task):
        state_path = task / "state.json"
        if state_path.exists() or state_path.is_symlink():
            existing, _ = _json_bytes(state_path)
            if existing != state:
                raise WorkflowError(
                    "scope-conflict", "task state already exists with different bytes",
                    affected=os.fspath(state_path), recovery="use-a-new-task-directory",
                )
        else:
            replace_task_path_json(task, state_path, state)
    return {"contract": contract, "state": state}


def read_task(task_dir: Path | str) -> dict[str, object]:
    task = Path(task_dir).absolute()
    contract, _ = _json_bytes(task / "task-contract.json")
    state, _ = _json_bytes(task / "state.json")
    try:
        checked_contract = full_protocol.validate_task_contract(contract)
        checked_state = full_protocol.validate_state(state)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError(
            "invalid-input", f"invalid task record: {error}", affected=os.fspath(task)
        ) from error
    if checked_state["contract_digest"] != checked_contract["contract_digest"]:
        raise WorkflowError(
            "invalid-input", "state contract digest differs from task contract",
            affected=os.fspath(task),
        )
    return {"contract": checked_contract, "state": checked_state}


def update_state_cas(
    task_dir: Path | str, *, expected_version: int, updates: Mapping[str, object],
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    with _task_lock(task):
        records = read_task(task)
        state = records["state"]
        if state["version"] != expected_version:
            raise WorkflowError(
                "stale-baseline",
                f"state version {state['version']} differs from expected {expected_version}",
                affected=os.fspath(task / "state.json"),
                recovery="reload-state-and-create-a-new-operation",
            )
        after = copy.deepcopy(state)
        for key, value in updates.items():
            if key == "version":
                raise WorkflowError(
                    "invalid-input", "state version is managed by CAS",
                    affected=os.fspath(task / "state.json"),
                )
            if key not in after:
                raise WorkflowError(
                    "invalid-input", f"unsupported state update field: {key}",
                    affected=os.fspath(task / "state.json"),
                )
            after[key] = copy.deepcopy(value)
        after["version"] = expected_version + 1
        try:
            checked = full_protocol.validate_state(after)
        except full_protocol.ProtocolValidationError as error:
            raise WorkflowError(
                "invalid-input", f"invalid state transition: {error}",
                affected=os.fspath(task / "state.json"),
            ) from error
        replace_task_path_json(task, task / "state.json", checked)
        return checked


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _task_component(value: object, label: str) -> str:
    try:
        return full_protocol.canonical_component(value, label)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("invalid-input", str(error), affected=str(value)) from error


def _intent_path(task: Path, op_id: str) -> Path:
    return task / "operation-intent" / f"{_task_component(op_id, 'operation ID')}.json"


def _receipt_path(task: Path, op_id: str) -> Path:
    return task / "operation-receipt" / f"{_task_component(op_id, 'operation ID')}.json"


def _operation_status(
    task: Path, intent: Mapping[str, object],
) -> tuple[str, dict[str, Any] | None]:
    intent_path = _intent_path(task, str(intent["op_id"]))
    receipt_path = _receipt_path(task, str(intent["op_id"]))
    if intent_path.exists() or intent_path.is_symlink():
        existing, _ = _json_bytes(intent_path)
        try:
            full_protocol.assert_same_operation(existing, intent)
        except full_protocol.OperationConflictError as error:
            raise WorkflowError(
                "scope-conflict", f"operation ID was reused with another request: {error}",
                affected=str(intent["op_id"]), recovery="use-a-new-operation-id",
            ) from error
        if receipt_path.exists() or receipt_path.is_symlink():
            receipt, _ = _json_bytes(receipt_path)
            try:
                checked = full_protocol.validate_operation_receipt(receipt, existing)
            except full_protocol.ProtocolValidationError as error:
                raise WorkflowError(
                    "execution-incomplete", f"operation receipt is invalid: {error}",
                    affected=os.fspath(receipt_path), side_effect="unknown",
                    recovery="preserve-and-root-reconcile",
                ) from error
            return "complete", checked
        return "recover", None
    publish_task_path_json(task, intent_path, full_protocol.validate_operation_intent(intent))
    return "new", None


def begin_creator_operation(task_dir: Path | str, intent: Mapping[str, object]) -> bool:
    """Atomically admit one creator for the narrow prepare/run/record-CR transactions."""
    task = Path(task_dir).absolute()
    checked = full_protocol.validate_operation_intent(intent)
    op_id = str(checked["op_id"])
    path = _intent_path(task, op_id)

    def admission_identities() -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        component = _task_component(task.name, "task root component")
        name_digest = hashlib.sha256(component.encode("utf-8")).hexdigest()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        anchor_fd: int | None = None
        bootstrap_fd: int | None = None
        root_fd: int | None = None
        task_lock_fd: int | None = None
        try:
            anchor_fd = os.open(task.parent, flags)
            bootstrap_fd = os.open(
                f"sa-bootstrap-lock-{name_digest}",
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=anchor_fd,
            )
            root_fd = os.open(component, flags, dir_fd=anchor_fd)
            task_lock_fd = os.open(
                ".workflow.lock", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd,
            )
            return (_fd_identity(bootstrap_fd), _fd_identity(root_fd), _fd_identity(task_lock_fd))
        except OSError as error:
            raise WorkflowError(
                "execution-incomplete", f"creator admission identity check failed: {error}",
                affected=os.fspath(task), side_effect="unknown",
            ) from error
        finally:
            for descriptor in (task_lock_fd, root_fd, bootstrap_fd, anchor_fd):
                if descriptor is not None:
                    os.close(descriptor)

    def validate_admission_state() -> None:
        records = read_task(task)
        if records["contract"]["contract_digest"] != checked["contract_digest"]:
            raise WorkflowError(
                "scope-conflict", "creator intent contract differs from current task contract",
                affected=op_id, recovery="reload-task-and-create-a-new-operation",
            )
        if records["state"]["version"] != checked["expected_state_version"]:
            raise WorkflowError(
                "stale-baseline",
                f"state version {records['state']['version']} differs from expected {checked['expected_state_version']}",
                affected=os.fspath(task / "state.json"),
                recovery="reload-state-and-create-a-new-operation",
            )

    with _task_lock(task):
        if path.exists() or path.is_symlink():
            existing, _ = _json_bytes(path)
            try:
                full_protocol.assert_same_operation(existing, checked)
            except full_protocol.OperationConflictError as error:
                raise WorkflowError("scope-conflict", f"operation ID was reused with another request: {error}", affected=op_id) from error
            return False
        validate_admission_state()
        expected_identities = admission_identities()

        def revalidate_before_link() -> None:
            validate_admission_state()
            if admission_identities() != expected_identities:
                raise WorkflowError(
                    "execution-incomplete", "creator admission identity changed before intent publication",
                    affected=op_id, side_effect="unknown",
                )

        outcome = _publish_task_immutable_bytes_locked(
            task,
            ["operation-intent", f"{_task_component(op_id, 'operation ID')}.json"],
            full_protocol.canonical_json_bytes(checked),
            before_link=revalidate_before_link,
        )
        return outcome == "created"


def publish_operation_receipt(task_dir: Path | str, receipt: Mapping[str, object]) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    op_id = str(receipt.get("op_id", ""))
    intent, _ = _json_bytes(_intent_path(task, op_id))
    try:
        checked = full_protocol.validate_operation_receipt(receipt, intent)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError(
            "invalid-input", f"invalid operation receipt: {error}", affected=op_id
        ) from error
    publish_task_path_json(task, _receipt_path(task, op_id), checked)
    return checked


def _validate_runtime_receipt(
    runtime: Mapping[str, object], delivery: Mapping[str, object], work_key: str, *, expected_stage_key: str | None = None,
) -> dict[str, Any]:
    required = {"thread_id", "agent_role", "model", "effort", "task_id", "stage_key", "work_key"}
    if not required.issubset(runtime) or any(
        not isinstance(runtime[key], str) or not runtime[key] for key in required
    ):
        raise WorkflowError(
            "runtime-unavailable", "runtime receipt lacks observed identity fields",
            affected=work_key, recovery="rerun-native-runtime-inspection",
        )
    if (
        runtime["agent_role"] != "sol_advisor_sol_implementer"
        or runtime["model"] != "gpt-6-sol"
        or runtime["effort"] != "high"
        or runtime["work_key"] != work_key
        or (expected_stage_key is not None and runtime["stage_key"] != expected_stage_key)
    ):
        raise WorkflowError(
            "review-invalid", "runtime receipt is not the required Sol implementer identity/work item",
            affected=work_key, recovery="obtain-correct-native-runtime-receipt",
        )
    attestation = delivery.get("attestation")
    expected = {
        "thread_id": runtime["thread_id"],
        "role": runtime["agent_role"],
        "model": runtime["model"],
        "effort": runtime["effort"],
        "self_review": "complete",
        "runtime_receipt_digest": full_protocol.canonical_digest(runtime),
    }
    if attestation != expected:
        raise WorkflowError(
            "review-invalid", "delivery attestation does not bind the observed runtime receipt",
            affected=str(delivery.get("delivery_id", work_key)),
            recovery="regenerate-delivery-from-observed-terra-context",
        )
    return dict(runtime)


def _validate_bundle(
    raw: bytes, material: Mapping[str, object], work: Mapping[str, object],
) -> dict[str, Any]:
    try:
        bundle = json.loads(raw.decode("utf-8"), object_pairs_hook=candidate_tool.unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, candidate_tool.CandidateError) as error:
        raise WorkflowError(
            "invalid-input", f"delivery bundle is invalid JSON: {error}",
            affected=str(material.get("material_id", "material")),
        ) from error
    if not isinstance(bundle, dict) or set(bundle) != {"schema_version", "baseline_id", "changes"}:
        raise WorkflowError(
            "invalid-input", "delivery bundle has unsupported fields",
            affected=str(material.get("material_id", "material")),
        )
    if raw != full_protocol.canonical_json_bytes(bundle):
        raise WorkflowError(
            "invalid-input", "delivery bundle must use canonical JSON bytes",
            affected=str(material.get("material_id", "material")),
        )
    if bundle["schema_version"] != 1 or bundle["baseline_id"] != material["baseline_id"]:
        raise WorkflowError(
            "stale-baseline", "delivery bundle baseline does not bind its material",
            affected=str(material.get("material_id", "material")),
        )
    if material["bundle"].get("sha256") != _sha256(raw):
        raise WorkflowError(
            "candidate-changed", "delivery bundle bytes differ from the ready material",
            affected=str(material.get("material_id", "material")),
            recovery="create-a-new-delivery-attempt",
        )
    changes = bundle["changes"]
    if not isinstance(changes, list) or not changes:
        raise WorkflowError(
            "invalid-input", "delivery bundle must contain changes",
            affected=str(material.get("material_id", "material")),
        )
    paths: list[str] = []
    required_change = {
        "path", "operation", "mode", "before_sha256", "after_sha256", "content_base64"
    }
    for change in changes:
        if not isinstance(change, dict) or set(change) != required_change:
            raise WorkflowError(
                "invalid-input", "delivery change has unsupported fields",
                affected=str(material.get("material_id", "material")),
            )
        path = _safe_relative_path(change["path"])
        if change["operation"] not in {"add", "modify", "delete"}:
            raise WorkflowError("invalid-input", "delivery operation is unsupported", affected=path)
        if change["mode"] not in {"100644", "100755"}:
            raise WorkflowError("invalid-input", "delivery file mode is unsupported", affected=path)
        paths.append(path)
    if len(paths) != len(set(paths)) or sorted(paths) != sorted(material["bundle"]["files"]):
        raise WorkflowError(
            "scope-conflict", "delivery bundle paths differ from material ownership",
            affected=str(material.get("material_id", "material")),
        )
    if sorted(paths) != sorted(work.get("paths", [])):
        raise WorkflowError(
            "scope-conflict", "delivery bundle paths differ from the work-item contract",
            affected=str(material.get("work_key", "work")),
        )
    return bundle


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise WorkflowError("invalid-input", "path must be non-empty", affected="path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or value != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        raise WorkflowError(
            "scope-conflict", f"path is not a canonical repository-relative path: {value!r}",
            affected=value,
        )
    return value


def _load_receive_inputs(
    contract: Mapping[str, object], *, material_path: Path, delivery_path: Path,
    evidence_path: Path, bundle_path: Path, runtime_path: Path,
) -> dict[str, Any]:
    material, material_bytes = _json_bytes(material_path)
    delivery, delivery_bytes = _json_bytes(delivery_path)
    evidence, evidence_bytes = _json_bytes(evidence_path)
    runtime, runtime_bytes = _json_bytes(runtime_path)
    bundle_bytes = _regular_bytes(bundle_path)
    work_key = material.get("work_key")
    work_items = contract.get("work_items")
    if not isinstance(work_key, str) or not isinstance(work_items, Mapping) or work_key not in work_items:
        raise WorkflowError("invalid-input", "material names an unknown work item", affected=str(work_key))
    work = work_items[work_key]
    if not isinstance(work, Mapping):
        raise WorkflowError("invalid-input", "work item is not an object", affected=work_key)
    expected_baseline = work.get("baseline_id")
    if expected_baseline is not None and material.get("baseline_id") != expected_baseline:
        raise WorkflowError(
            "stale-baseline", "material baseline differs from the work-item baseline",
            affected=work_key, recovery="create-delivery-from-current-common-baseline",
        )
    try:
        checked_material = full_protocol.validate_material(
            material, contract, {"work_key": work_key, "paths": work.get("paths")}
        )
        checked_delivery = full_protocol.validate_delivery(
            delivery, checked_material, contract,
            {"work_key": work_key, "paths": work.get("paths")},
        )
        checked_evidence = full_protocol.validate_evidence(
            evidence, contract, "delivery", checked_material["material_id"]
        )
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError(
            "invalid-input", f"delivery relationship is invalid: {error}",
            affected=work_key,
        ) from error
    if (
        checked_delivery["delivery_evidence_id"] != checked_evidence["evidence_id"]
        or checked_evidence["result"] != "pass"
    ):
        raise WorkflowError(
            "missing-evidence", "delivery does not bind one passing delivery E",
            affected=str(checked_delivery["delivery_id"]),
        )
    _validate_runtime_receipt(runtime, checked_delivery, work_key, expected_stage_key=work.get("stage_key"))
    bundle = _validate_bundle(bundle_bytes, checked_material, work)
    return {
        "work_key": work_key,
        "work": dict(work),
        "material": checked_material,
        "material_bytes": full_protocol.canonical_json_bytes(checked_material),
        "delivery": checked_delivery,
        "delivery_bytes": full_protocol.canonical_json_bytes(checked_delivery),
        "evidence": checked_evidence,
        "evidence_bytes": full_protocol.canonical_json_bytes(checked_evidence),
        "bundle": bundle,
        "bundle_bytes": bundle_bytes,
        "runtime": runtime,
        "runtime_bytes": full_protocol.canonical_json_bytes(runtime),
    }


def _receive_request(
    *, op_id: str, expected_state_version: int, payloads: Mapping[str, bytes],
) -> dict[str, object]:
    return {
        "op_id": op_id,
        "command_kind": "receive",
        "expected_state_version": expected_state_version,
        "material_sha256": _sha256(payloads["material"]),
        "delivery_sha256": _sha256(payloads["delivery"]),
        "evidence_sha256": _sha256(payloads["evidence"]),
        "bundle_sha256": _sha256(payloads["bundle"]),
        "runtime_sha256": _sha256(payloads["runtime"]),
    }


def _operation_receipt(
    intent: Mapping[str, object], *, outcome: str, side_effect: str,
    actual_output_ids: list[str], state_before: int, state_after: int,
) -> dict[str, object]:
    return {
        "record_type": "operation-receipt",
        "op_id": intent["op_id"],
        "request_digest": intent["request_digest"],
        "command_kind": intent["command_kind"],
        "outcome": outcome,
        "side_effect": side_effect,
        "actual_output_ids": actual_output_ids,
        "state_version_before": state_before,
        "state_version_after": state_after,
    }


def receive_delivery(
    task_dir: Path | str, *, op_id: str, expected_state_version: int,
    material_path: Path | str, delivery_path: Path | str,
    delivery_evidence_path: Path | str, bundle_path: Path | str,
    runtime_receipt_path: Path | str,
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    records = read_task(task)
    contract = records["contract"]
    raw_paths = [
        Path(material_path).absolute(), Path(delivery_path).absolute(),
        Path(delivery_evidence_path).absolute(), Path(bundle_path).absolute(),
        Path(runtime_receipt_path).absolute(),
    ]
    payloads = {
        "material": _regular_bytes(raw_paths[0]),
        "delivery": _regular_bytes(raw_paths[1]),
        "evidence": _regular_bytes(raw_paths[2]),
        "bundle": _regular_bytes(raw_paths[3]),
        "runtime": _regular_bytes(raw_paths[4]),
    }
    request = _receive_request(
        op_id=op_id, expected_state_version=expected_state_version, payloads=payloads
    )
    request_digest = full_protocol.canonical_digest(request)
    existing_intent_path = _intent_path(task, op_id)
    if existing_intent_path.exists() or existing_intent_path.is_symlink():
        existing_intent, _ = _json_bytes(existing_intent_path)
        if existing_intent.get("request_digest") != request_digest:
            raise WorkflowError(
                "scope-conflict", "operation ID was reused with changed input bytes",
                affected=op_id, recovery="use-a-new-operation-id",
            )
    inputs = _load_receive_inputs(
        contract,
        material_path=raw_paths[0], delivery_path=raw_paths[1],
        evidence_path=raw_paths[2], bundle_path=raw_paths[3], runtime_path=raw_paths[4],
    )
    delivery_id = inputs["delivery"]["delivery_id"]
    output_dir = task / "deliveries" / delivery_id
    output_paths = {
        "M": output_dir / "material.json",
        "D": output_dir / "delivery.json",
        "E": output_dir / "delivery-evidence.json",
        "bundle": output_dir / "bundle.json",
        "runtime": output_dir / "runtime.json",
    }
    intent = {
        "record_type": "operation-intent",
        "op_id": op_id,
        "command_kind": "receive",
        "request_digest": request_digest,
        "contract_digest": contract["contract_digest"],
        "expected_state_version": expected_state_version,
        "planned_output_types": list(output_paths),
        "planned_output_paths": [os.fspath(path) for path in output_paths.values()],
    }
    if not (existing_intent_path.exists() or existing_intent_path.is_symlink()) and records["state"]["version"] != expected_state_version:
        raise WorkflowError(
            "stale-baseline", "receive expected state is stale",
            affected=op_id, recovery="reload-state-and-create-a-new-operation",
        )
    status, completed = _operation_status(task, intent)
    if completed is not None:
        return completed
    if status == "new" and records["state"]["version"] != expected_state_version:
        # Intent publication must never happen for an already-observed stale state.
        raise WorkflowError(
            "stale-baseline", "receive state changed before publication",
            affected=op_id, side_effect="durable", recovery="preserve-intent-and-root-reconcile",
        )
    actual_ids = [
        inputs["material"]["material_id"], delivery_id,
        inputs["evidence"]["evidence_id"], "sha256:" + _sha256(inputs["bundle_bytes"]),
        full_protocol.canonical_digest(inputs["runtime"]),
    ]
    payloads = {
        "M": inputs["material_bytes"],
        "D": inputs["delivery_bytes"],
        "E": inputs["evidence_bytes"],
        "bundle": inputs["bundle_bytes"],
        "runtime": inputs["runtime_bytes"],
    }
    existing = [path.exists() or path.is_symlink() for path in output_paths.values()]
    if status == "recover":
        if not any(existing):
            receipt = _operation_receipt(
                intent, outcome="failure", side_effect="none", actual_output_ids=[],
                state_before=expected_state_version, state_after=expected_state_version,
            )
            return publish_operation_receipt(task, receipt)
        if not all(existing):
            receipt = _operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown", actual_output_ids=[],
                state_before=expected_state_version, state_after=expected_state_version,
            )
            return publish_operation_receipt(task, receipt)
        for kind, path in output_paths.items():
            if _regular_bytes(path, category="candidate-changed") != payloads[kind]:
                raise WorkflowError(
                    "candidate-changed", "received immutable output drifted",
                    affected=os.fspath(path), side_effect="unknown",
                    recovery="preserve-and-root-reconcile",
                )
    else:
        for kind, path in output_paths.items():
            publish_task_path_bytes(task, path, payloads[kind])

    current = read_task(task)["state"]
    if current["version"] == expected_state_version:
        work_status = dict(current["work_status"])
        work_status[inputs["work_key"]] = "received"
        try:
            update_state_cas(
                task,
                expected_version=expected_state_version,
                updates={
                    "work_status": work_status,
                    "last_operation_receipt": op_id,
                },
            )
        except WorkflowError:
            observed = read_task(task)["state"]["version"]
            receipt = _operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown",
                actual_output_ids=actual_ids, state_before=expected_state_version,
                state_after=observed,
            )
            return publish_operation_receipt(task, receipt)
    elif not (
        current["version"] == expected_state_version + 1
        and current["last_operation_receipt"] == op_id
        and current["work_status"].get(inputs["work_key"]) == "received"
    ):
        receipt = _operation_receipt(
            intent, outcome="ambiguous", side_effect="unknown", actual_output_ids=actual_ids,
            state_before=expected_state_version, state_after=current["version"],
        )
        return publish_operation_receipt(task, receipt)
    receipt = _operation_receipt(
        intent, outcome="success", side_effect="durable", actual_output_ids=actual_ids,
        state_before=expected_state_version, state_after=expected_state_version + 1,
    )
    return publish_operation_receipt(task, receipt)


def _run_git(repo: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", os.fspath(repo), *arguments],
            check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise WorkflowError(
            "invalid-input", f"cannot inspect baseline repository: {error}",
            affected=os.fspath(repo),
        ) from error


def _load_selected_deliveries(
    task: Path, contract: Mapping[str, object], selected: Mapping[str, str], *, exact_work_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    work_items = contract["work_items"]
    required = set(work_items) if exact_work_keys is None else exact_work_keys
    if set(selected) != required:
        raise WorkflowError(
            "missing-evidence", "assembly selection must name the exact stage work items once",
            affected="selection",
        )
    result: list[dict[str, Any]] = []
    for work_key in sorted(selected):
        delivery_id = selected[work_key]
        if not isinstance(delivery_id, str) or not delivery_id:
            raise WorkflowError("invalid-input", "selected delivery ID is invalid", affected=work_key)
        delivery_id = _task_component(delivery_id, "delivery ID")
        directory = task / "deliveries" / delivery_id
        try:
            item = _load_receive_inputs(
                contract,
                material_path=directory / "material.json",
                delivery_path=directory / "delivery.json",
                evidence_path=directory / "delivery-evidence.json",
                bundle_path=directory / "bundle.json",
                runtime_path=directory / "runtime.json",
            )
        except WorkflowError as error:
            if error.category in {"missing-evidence", "invalid-input"}:
                raise WorkflowError(
                    "candidate-changed", f"selected delivery is incomplete or drifted: {error}",
                    affected=delivery_id, recovery="select-a-new-valid-attempt",
                ) from error
            raise
        if item["work_key"] != work_key or item["delivery"]["delivery_id"] != delivery_id:
            raise WorkflowError(
                "scope-conflict", "selected delivery does not bind its work item/ID",
                affected=delivery_id,
            )
        item["directory"] = directory
        result.append(item)
    return result


def _is_staged_contract(contract: Mapping[str, object]) -> bool:
    return contract.get("protocol") == full_protocol.STAGED_PROTOCOL_VERSION


def _stage_work_keys(contract: Mapping[str, object], stage_key: str) -> set[str]:
    stages = contract["stages"]
    if stage_key not in stages:
        raise WorkflowError("invalid-input", "unknown assembly stage", affected=stage_key)
    keys = {key for key, item in contract["work_items"].items() if item.get("stage_key") == stage_key}
    if not keys:
        raise WorkflowError("missing-evidence", "stage has no work items", affected=stage_key)
    return keys


def _accepted_stage_index(task: Path, stage_key: str) -> dict[str, Any]:
    path = task / "stage-acceptances" / f"{_task_component(stage_key, 'stage key')}.json"
    value, _ = _json_bytes(path)
    required = {"stage_key", "acceptance_id", "candidate_bridge_id", "selected_attempts", "final_accept_op_id", "final_candidate_evidence_id"}
    if set(value) != required or value["stage_key"] != stage_key or not isinstance(value["selected_attempts"], dict):
        raise WorkflowError("candidate-changed", "accepted-stage index is malformed", affected=stage_key)
    acceptance_path = task / "acceptances" / _task_component(value["acceptance_id"], "acceptance ID") / "A.json"
    acceptance, _ = _json_bytes(acceptance_path)
    if acceptance.get("record_type") != "A" or acceptance.get("acceptance_id") != value["acceptance_id"] or acceptance.get("accepted_stage_key") != stage_key or acceptance.get("candidate_bridge_id") != value["candidate_bridge_id"] or acceptance.get("final_candidate_evidence_id") != value["final_candidate_evidence_id"]:
        raise WorkflowError("candidate-changed", "accepted-stage index does not bind the persisted acceptance", affected=stage_key)
    intent, _ = _json_bytes(_intent_path(task, _task_component(value["final_accept_op_id"], "final acceptance operation ID")))
    receipt, _ = _json_bytes(_receipt_path(task, _task_component(value["final_accept_op_id"], "final acceptance operation ID")))
    try:
        checked_receipt = full_protocol.validate_operation_receipt(receipt, intent)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("candidate-changed", f"accepted-stage final receipt is invalid: {error}", affected=stage_key) from error
    if intent.get("command_kind") != "final-accept" or checked_receipt.get("outcome") != "success" or checked_receipt.get("side_effect") != "durable" or value["acceptance_id"] not in checked_receipt.get("actual_output_ids", []):
        raise WorkflowError("missing-evidence", "accepted-stage index lacks a successful final-accept receipt", affected=stage_key)
    context = _load_persisted_acceptance_context(task, value["acceptance_id"])
    relationship = context.relationship
    expected_selection = {item["work_key"]: item["delivery_id"] for item in relationship.deliveries if relationship.task_contract["work_items"][item["work_key"]]["stage_key"] == stage_key}
    if value["selected_attempts"] != expected_selection or relationship.task_contract != read_task(task)["contract"]:
        raise WorkflowError("candidate-changed", "accepted-stage selection does not match reviewed deliveries", affected=stage_key)
    _require_current_candidate(relationship.manifest, context.candidate_verify_receipt, affected=stage_key)
    for evidence in [*(relationship.candidate_evidence or []), *(relationship.pre_ship_evidence or []), relationship.challenge_evidence, context.final_candidate_evidence]:
        if evidence is not None:
            require_persisted_run_evidence(task, evidence, affected=stage_key)
    try:
        full_protocol.validate_acceptance(context.acceptance, context=relationship,
            candidate_bridge=relationship.candidate_bridge, packet=relationship.packet,
            verdict=relationship.verdict, final_candidate_evidence=context.final_candidate_evidence,
            root_authority=context.root_authority, candidate_verify_receipt=context.candidate_verify_receipt,
            task_contract=relationship.task_contract, dependency_acceptance_contexts=context.dependency_acceptance_contexts,
            trusted_observation_time=context.root_authority["observed_at"])
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("review-invalid", f"prior acceptance provenance is invalid: {error}", affected=stage_key) from error
    return value


def _required_prior_stage_selection(task: Path, contract: Mapping[str, object], stage_key: str) -> dict[str, str]:
    result: dict[str, str] = {}
    seen: set[str] = set()

    def visit(key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        for dependency in contract["stages"][key]["depends_on"]:
            visit(dependency)
            index = _accepted_stage_index(task, dependency)
            for work_key, delivery_id in index["selected_attempts"].items():
                if work_key in result and result[work_key] != delivery_id:
                    raise WorkflowError("candidate-changed", "prior accepted stage selection rebinds a work item", affected=work_key)
                result[work_key] = delivery_id

    visit(stage_key)
    return result


def _stage_order(contract: Mapping[str, object]) -> dict[str, int]:
    order: dict[str, int] = {}
    def visit(key: str) -> None:
        if key in order:
            return
        for dependency in contract["stages"][key]["depends_on"]:
            visit(dependency)
        order[key] = len(order)
    for key in contract["stages"]:
        visit(key)
    return order


def _reject_ownership_overlap(items: list[Mapping[str, Any]]) -> None:
    owners: list[tuple[str, PurePosixPath]] = []
    for item in items:
        for value in item["work"]["paths"]:
            path = PurePosixPath(_safe_relative_path(value))
            for prior_owner, prior in owners:
                if path == prior or path in prior.parents or prior in path.parents:
                    raise WorkflowError(
                        "scope-conflict",
                        f"work-item ownership overlaps: {prior_owner}:{prior} and {item['work_key']}:{path}",
                        affected=str(path), recovery="root-resolve-ownership-before-assembly",
                    )
            owners.append((item["work_key"], path))


def _verify_baseline(repo: Path, baseline_id: str) -> None:
    if not repo.is_dir() or (repo / ".git").is_symlink():
        raise WorkflowError("invalid-input", "baseline is not a safe Git worktree", affected=os.fspath(repo))
    head = _run_git(repo, "rev-parse", "HEAD").strip()
    status = _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if head != baseline_id or status:
        raise WorkflowError(
            "candidate-changed", "baseline HEAD or worktree bytes changed",
            affected=os.fspath(repo), recovery="freeze-a-new-common-baseline",
        )


def _apply_bundle(workspace: Path, bundle: Mapping[str, object]) -> None:
    for change in bundle["changes"]:
        relative = _safe_relative_path(change["path"])
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.resolve(strict=True) != target.parent:
            raise WorkflowError(
                "scope-conflict", "bundle path traverses a symlinked parent",
                affected=relative,
            )
        exists = target.exists() or target.is_symlink()
        if exists:
            details = target.lstat()
            if not stat.S_ISREG(details.st_mode):
                raise WorkflowError(
                    "scope-conflict", "bundle target is not a regular file",
                    affected=relative,
                )
        operation = change["operation"]
        before_hash = _sha256(target.read_bytes()) if exists and stat.S_ISREG(target.lstat().st_mode) else None
        if operation == "add":
            if exists or change["before_sha256"] is not None:
                raise WorkflowError("scope-conflict", "add target already exists", affected=relative)
        else:
            if not exists or change["before_sha256"] != before_hash:
                raise WorkflowError(
                    "stale-baseline", "bundle before hash differs from baseline bytes",
                    affected=relative, recovery="create-delivery-from-current-common-baseline",
                )
        if operation == "delete":
            if change["after_sha256"] is not None or change["content_base64"] is not None:
                raise WorkflowError("invalid-input", "delete change contains output bytes", affected=relative)
            target.unlink()
            continue
        try:
            content = base64.b64decode(change["content_base64"], validate=True)
        except (TypeError, ValueError) as error:
            raise WorkflowError("invalid-input", "change content is not valid base64", affected=relative) from error
        if change["after_sha256"] != _sha256(content):
            raise WorkflowError("candidate-changed", "change output hash mismatch", affected=relative)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            mode = 0o755 if change["mode"] == "100755" else 0o644
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            _fsync_directory(target.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _assembly_request(
    *, op_id: str, expected_state_version: int, baseline_repo: Path,
    baseline_id: str, selected: Mapping[str, str], stage_key: str | None = None,
) -> dict[str, object]:
    request: dict[str, object] = {
        "op_id": op_id,
        "command_kind": "assemble",
        "expected_state_version": expected_state_version,
        "baseline_repo": os.fspath(baseline_repo.absolute()),
        "baseline_id": baseline_id,
        "selected": dict(sorted(selected.items())),
    }
    if stage_key is not None:
        request["stage_key"] = stage_key
    return request


def _candidate_verify_receipt(manifest: Mapping[str, object]) -> dict[str, object]:
    current = candidate_tool.current_candidate_from_manifest(dict(manifest))
    changes = candidate_tool.compare_entries(manifest["entries"], current["entries"])
    return {
        "status": "match" if not changes and current["candidate_id"] == manifest["candidate_id"] else "changed",
        "candidate_id": manifest["candidate_id"],
        "current_candidate_id": current["candidate_id"],
        "head_changed": current["source"]["head"] != manifest["source"]["head"],
        "changes": changes,
        "expected_candidate_id": manifest["candidate_id"],
        "expected_candidate_id_match": True,
    }


def _require_current_candidate(
    manifest: Mapping[str, object], supplied_receipt: Mapping[str, object],
    *, affected: str,
) -> None:
    try:
        observed = _candidate_verify_receipt(manifest)
    except (candidate_tool.CandidateError, OSError, KeyError, TypeError) as error:
        raise WorkflowError(
            "candidate-changed", f"cannot verify the final candidate: {error}",
            affected=affected, recovery="rebuild-and-rereview-the-candidate",
        ) from error
    if observed.get("status") != "match" or dict(supplied_receipt) != observed:
        raise WorkflowError(
            "candidate-changed", "supplied verify receipt does not match a fresh candidate comparison",
            affected=affected, recovery="rebuild-and-rereview-the-candidate",
        )


def _build_assembly(
    task: Path, op_id: str, baseline_repo: Path, selected_items: list[dict[str, Any]],
    contract: Mapping[str, object], *, stage_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    directory = task / "assemblies" / op_id
    workspace = directory / "workspace"
    if directory.exists() or directory.is_symlink():
        raise WorkflowError(
            "scope-conflict", "assembly output directory already exists without recoverable intent",
            affected=os.fspath(directory), recovery="use-a-new-operation-id",
        )
    staging_root = Path(tempfile.mkdtemp(prefix="sol-advisor-assembly.")).resolve(strict=True)
    staging_workspace = staging_root / "workspace"
    try:
        shutil.copytree(baseline_repo, staging_workspace, symlinks=True)
        (staging_workspace / ".agent-artifacts").mkdir(mode=0o700, exist_ok=True)
        for item in selected_items:
            _apply_bundle(staging_workspace, item["bundle"])
        with _task_lock(task):
            move_directory_into_task(task, workspace, staging_workspace)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    assembly_id = f"I-{op_id}"
    output_id = f"output-{op_id}"
    manifest_id = f"manifest-{op_id}"
    bridge_id = f"CB-{op_id}"
    deliveries = [item["delivery"] for item in selected_items]
    materials = [item["material"] for item in selected_items]
    evidence = [item["evidence"] for item in selected_items]
    assembly = {
        "record_type": "I",
        "assembly_id": assembly_id,
        "contract_digest": contract["contract_digest"],
        "baseline_id": selected_items[0]["material"]["baseline_id"],
        "delivery_ids": [item["delivery"]["delivery_id"] for item in selected_items],
        "material_ids": [item["material"]["material_id"] for item in selected_items],
        "output_identity_id": output_id,
        "schema2_manifest_id": manifest_id,
        "candidate_bridge_id": bridge_id,
    }
    if _is_staged_contract(contract):
        assembly["stage_key"] = stage_key
        assembly["review_scope"] = contract["stages"][stage_key]["review_scope"]
    output_identity = {"output_identity_id": output_id, "assembly_id": assembly_id}
    assembly_path = directory / "I.json"
    publish_task_path_json(task, assembly_path, assembly)
    publish_task_path_json(task, directory / "output-identity.json", output_identity)
    explicit_inputs = {
        "I": {assembly_id: os.fspath(assembly_path.absolute())},
        "D": {
            item["delivery"]["delivery_id"]: os.fspath((item["directory"] / "delivery.json").absolute())
            for item in selected_items
        },
        "M": {
            item["material"]["material_id"]: os.fspath((item["directory"] / "material.json").absolute())
            for item in selected_items
        },
        "bundle": {
            item["material"]["material_id"]: os.fspath((item["directory"] / "bundle.json").absolute())
            for item in selected_items
        },
    }
    input_paths = candidate_tool.normalize_explicit_inputs(
        [path for group in explicit_inputs.values() for path in group.values()]
    )
    if _is_staged_contract(contract):
        # The runner is an actual verification dependency, outside ordinary product fixtures.
        input_paths = candidate_tool.normalize_explicit_inputs([*input_paths, *[os.fspath(Path(__file__).with_name(name).resolve()) for name in ("run-check.py", "workflow.py", "full_protocol.py", "candidate.py")]])
    manifest = candidate_tool.build_candidate(workspace, input_paths)
    manifest_path = directory / "candidate-manifest.json"
    publish_task_path_json(task, manifest_path, manifest)
    manifest_bytes = _regular_bytes(manifest_path)
    bridge = {
        "record_type": "CB",
        "bridge_id": bridge_id,
        "contract_digest": contract["contract_digest"],
        "manifest_schema_version": 2,
        "manifest_path": os.fspath(manifest_path.absolute()),
        "manifest_hash": "sha256:" + _sha256(manifest_bytes),
        "candidate_id": manifest["candidate_id"],
        "manifest_candidate_id": manifest["candidate_id"],
        "selection_policy": manifest["selection"]["repo_inventory"],
        "assembly_id": assembly_id,
        "delivery_ids": assembly["delivery_ids"],
        "material_ids": assembly["material_ids"],
        "explicit_inputs": explicit_inputs,
    }
    bridge["correspondence_digest"] = full_protocol.canonical_digest(
        {
            "manifest": manifest,
            "assembly": assembly,
            "deliveries": deliveries,
            "materials": materials,
            "delivery_evidence": evidence,
            "explicit_inputs": explicit_inputs,
        }
    )
    verify = _candidate_verify_receipt(manifest)
    context = full_protocol.RelationshipContext(
        task_contract=contract,
        candidate_bridge=bridge,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        candidate_verify_receipt=verify,
        assembly=assembly,
        deliveries=deliveries,
        materials=materials,
        delivery_evidence=evidence,
    )
    try:
        full_protocol.validate_candidate_bridge(bridge, context=context)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError(
            "execution-incomplete", f"assembled candidate bridge is invalid: {error}",
            affected=op_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    publish_task_path_json(task, directory / "CB.json", bridge)
    return assembly, output_identity, manifest, bridge


def _load_assembly(
    task: Path, op_id: str, selected_items: list[dict[str, Any]],
    contract: Mapping[str, object],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    directory = task / "assemblies" / op_id
    assembly, _ = _json_bytes(directory / "I.json")
    output, _ = _json_bytes(directory / "output-identity.json")
    manifest, manifest_bytes = _json_bytes(directory / "candidate-manifest.json")
    bridge, _ = _json_bytes(directory / "CB.json")
    if (
        set(output) != {"output_identity_id", "assembly_id"}
        or output.get("output_identity_id") != assembly.get("output_identity_id")
        or output.get("assembly_id") != assembly.get("assembly_id")
    ):
        raise WorkflowError(
            "candidate-changed", "assembled output identity drifted from I",
            affected=op_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    try:
        manifest = candidate_tool.validate_manifest(manifest)
    except candidate_tool.CandidateError as error:
        raise WorkflowError(
            "candidate-changed", f"assembled manifest is invalid: {error}",
            affected=op_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    verify = _candidate_verify_receipt(manifest)
    deliveries = [item["delivery"] for item in selected_items]
    materials = [item["material"] for item in selected_items]
    evidence = [item["evidence"] for item in selected_items]
    context = full_protocol.RelationshipContext(
        task_contract=contract, candidate_bridge=bridge, manifest=manifest,
        manifest_bytes=manifest_bytes, candidate_verify_receipt=verify,
        assembly=assembly, deliveries=deliveries, materials=materials,
        delivery_evidence=evidence,
    )
    try:
        full_protocol.validate_candidate_bridge(bridge, context=context)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError(
            "candidate-changed", f"assembled records no longer validate: {error}",
            affected=op_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    return assembly, output, manifest, bridge


def assemble_candidate(
    task_dir: Path | str, *, op_id: str, expected_state_version: int,
    baseline_repo: Path | str, selected: Mapping[str, str], stage_key: str | None = None,
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    baseline = Path(baseline_repo).absolute()
    records = read_task(task)
    contract = records["contract"]
    work_items = contract["work_items"]
    staged = _is_staged_contract(contract)
    prior_selected: dict[str, str] = {}
    if staged:
        if not isinstance(stage_key, str) or not stage_key:
            raise WorkflowError("invalid-input", "staged assembly requires a stage selector", affected=op_id)
        active_stage = records["state"]["stage_status"].get("stage_key")
        if active_stage is not None and active_stage != stage_key:
            raise WorkflowError("scope-conflict", "assembly stage is not active", affected=stage_key)
        stage_work = _stage_work_keys(contract, stage_key)
        prior_selected = _required_prior_stage_selection(task, contract, stage_key)
        if set(prior_selected).intersection(selected):
            raise WorkflowError("scope-conflict", "selected delivery tries to rebind a prior accepted stage", affected=stage_key)
        current_items = _load_selected_deliveries(task, contract, selected, exact_work_keys=stage_work)
        prior_items = _load_selected_deliveries(task, contract, prior_selected, exact_work_keys=set(prior_selected)) if prior_selected else []
        # Same-stage overlap is forbidden; dependency-ordered overlap is applied
        # only through the later bundle's exact before hash.
        _reject_ownership_overlap(current_items)
        rank = _stage_order(contract)
        selected_items = sorted([*prior_items, *current_items], key=lambda item: (rank[item["work"].get("stage_key")], item["work_key"]))
        selected_all = {**prior_selected, **dict(selected)}
    else:
        if stage_key is not None:
            raise WorkflowError("invalid-input", "legacy assembly does not accept a stage selector", affected=op_id)
        selected_items = []
        selected_all = dict(selected)
    baseline_ids = {item.get("baseline_id") for item in work_items.values() if isinstance(item, Mapping)}
    if len(baseline_ids) != 1 or None in baseline_ids:
        raise WorkflowError(
            "stale-baseline", "work items do not declare one common baseline",
            affected="work_items", recovery="revise-the-task-contract",
        )
    baseline_id = next(iter(baseline_ids))
    request = _assembly_request(
        op_id=op_id, expected_state_version=expected_state_version,
        baseline_repo=baseline, baseline_id=baseline_id, selected=selected_all, stage_key=stage_key,
    )
    request_digest = full_protocol.canonical_digest(request)
    directory = task / "assemblies" / op_id
    output_paths = [
        directory / "I.json", directory / "output-identity.json",
        directory / "candidate-manifest.json", directory / "CB.json",
    ]
    intent = {
        "record_type": "operation-intent",
        "op_id": op_id,
        "command_kind": "assemble",
        "request_digest": request_digest,
        "contract_digest": contract["contract_digest"],
        "expected_state_version": expected_state_version,
        "planned_output_types": ["I", "output-identity", "schema2-manifest", "CB"],
        "planned_output_paths": [os.fspath(path) for path in output_paths],
    }
    intent_path = _intent_path(task, op_id)
    if intent_path.exists() or intent_path.is_symlink():
        status, completed = _operation_status(task, intent)
        if completed is not None:
            return completed
        if not staged:
            selected_items = _load_selected_deliveries(task, contract, selected)
            _reject_ownership_overlap(selected_items)
    else:
        if records["state"]["version"] != expected_state_version:
            raise WorkflowError(
                "stale-baseline", "assembly expected state is stale", affected=op_id,
                recovery="reload-state-and-create-a-new-operation",
            )
        if not staged:
            selected_items = _load_selected_deliveries(task, contract, selected)
            _reject_ownership_overlap(selected_items)
        _verify_baseline(baseline, baseline_id)
        status, completed = _operation_status(task, intent)
        if completed is not None:
            return completed
    common = {item["material"]["baseline_id"] for item in selected_items}
    if common != {baseline_id}:
        raise WorkflowError(
            "stale-baseline", "selected deliveries do not share the contract baseline",
            affected=op_id, recovery="select-attempts-from-one-common-baseline",
        )
    existing = [path.exists() or path.is_symlink() for path in output_paths]
    if status == "recover":
        workspace_exists = (directory / "workspace").exists() or (directory / "workspace").is_symlink()
        if not any(existing):
            receipt = _operation_receipt(
                intent,
                outcome="ambiguous" if workspace_exists else "failure",
                side_effect="unknown" if workspace_exists else "none",
                actual_output_ids=[], state_before=expected_state_version,
                state_after=expected_state_version,
            )
            return publish_operation_receipt(task, receipt)
        if not all(existing):
            receipt = _operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown", actual_output_ids=[],
                state_before=expected_state_version, state_after=expected_state_version,
            )
            return publish_operation_receipt(task, receipt)
        assembly, output, manifest, bridge = _load_assembly(
            task, op_id, selected_items, contract
        )
    else:
        assembly, output, manifest, bridge = _build_assembly(
            task, op_id, baseline, selected_items, contract, stage_key=stage_key
        )
    actual_ids = [
        assembly["assembly_id"], output["output_identity_id"],
        assembly["schema2_manifest_id"], bridge["bridge_id"],
    ]
    current = read_task(task)["state"]
    updates = {
        "selected_attempts": dict(sorted(selected_all.items())),
        "current_ids": dict(
            current["current_ids"],
            assembly_index=assembly["assembly_id"],
            candidate_binding=bridge["bridge_id"],
        ),
        "work_status": {
            key: "ready" if key in selected else value
            for key, value in current["work_status"].items()
        },
        "last_operation_receipt": op_id,
    }
    if current["version"] == expected_state_version:
        try:
            update_state_cas(task, expected_version=expected_state_version, updates=updates)
        except WorkflowError:
            observed = read_task(task)["state"]["version"]
            receipt = _operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown",
                actual_output_ids=actual_ids, state_before=expected_state_version,
                state_after=observed,
            )
            return publish_operation_receipt(task, receipt)
    elif not (
        current["version"] == expected_state_version + 1
        and current["last_operation_receipt"] == op_id
        and current["selected_attempts"] == dict(sorted(selected_all.items()))
        and current["current_ids"].get("assembly_index") == assembly["assembly_id"]
        and current["current_ids"].get("candidate_binding") == bridge["bridge_id"]
    ):
        receipt = _operation_receipt(
            intent, outcome="ambiguous", side_effect="unknown", actual_output_ids=actual_ids,
            state_before=expected_state_version, state_after=current["version"],
        )
        return publish_operation_receipt(task, receipt)
    receipt = _operation_receipt(
        intent, outcome="success", side_effect="durable", actual_output_ids=actual_ids,
        state_before=expected_state_version, state_after=expected_state_version + 1,
    )
    return publish_operation_receipt(task, receipt)


def _acceptance_context_identity(context: full_protocol.AcceptanceContext) -> dict[str, object]:
    return {
        "acceptance": full_protocol.canonical_digest(context.acceptance),
        "relationship": _relationship_identity(context.relationship),
        "final_candidate_evidence": full_protocol.canonical_digest(context.final_candidate_evidence),
        "root_authority": full_protocol.canonical_digest(context.root_authority),
        "candidate_verify_receipt": full_protocol.canonical_digest(context.candidate_verify_receipt),
        "dependencies": {
            key: _acceptance_context_identity(value)
            for key, value in sorted(context.dependency_acceptance_contexts.items())
        },
    }


def _relationship_identity(context: full_protocol.RelationshipContext) -> dict[str, object]:
    if not isinstance(context, full_protocol.RelationshipContext):
        raise WorkflowError(
            "invalid-input", "final acceptance requires a complete RelationshipContext",
            affected="relationship",
        )

    def one(value: Mapping[str, object] | None) -> str | None:
        return None if value is None else full_protocol.canonical_digest(value)

    def many(values: list[Mapping[str, object]] | None) -> list[str] | None:
        return None if values is None else [full_protocol.canonical_digest(value) for value in values]

    return {
        "task_contract": full_protocol.canonical_digest(context.task_contract),
        "candidate_bridge": full_protocol.canonical_digest(context.candidate_bridge),
        "manifest": full_protocol.canonical_digest(context.manifest),
        "manifest_bytes_sha256": _sha256(context.manifest_bytes),
        "candidate_verify_receipt": full_protocol.canonical_digest(context.candidate_verify_receipt),
        "assembly": full_protocol.canonical_digest(context.assembly),
        "deliveries": many(context.deliveries),
        "materials": many(context.materials),
        "delivery_evidence": many(context.delivery_evidence),
        "packet": one(context.packet),
        "candidate_evidence": many(context.candidate_evidence),
        "pre_ship_evidence": many(context.pre_ship_evidence),
        "applicable_rejection_roots": context.applicable_rejection_roots,
        "predecessor_verdicts": None if context.predecessor_verdicts is None else {
            key: full_protocol.canonical_digest(value)
            for key, value in sorted(context.predecessor_verdicts.items())
        },
        "expected_coverage": context.expected_coverage,
        "challenge_request": one(context.challenge_request),
        "challenge_evidence": one(context.challenge_evidence),
        "challenge_receipt": one(context.challenge_receipt),
        "verdict": one(context.verdict),
        "observed_attestation": one(context.observed_attestation),
    }


def probe_sandbox(task: Path, run_id: str, check: Mapping[str, object], contract: Mapping[str, object]) -> dict[str, object]:
    """Exact macOS child policy; unsupported interpreters/platforms fail closed."""
    executable = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or not executable.is_file():
        raise WorkflowError("runtime-unavailable", "isolated probe execution needs macOS sandbox-exec", affected=run_id)
    argv = check["argv"]
    if len(argv) != 2 or Path(argv[0]).resolve() != Path(sys.executable).resolve():
        raise WorkflowError("runtime-unavailable", "new probes support only this runner's Python interpreter", affected=run_id)
    write_dir = task / "runs" / _task_component(run_id, "run ID") / "probe-write"
    roots = ["/System", "/usr/lib", "/usr/share", "/Library/Apple", "/dev", sys.base_prefix, sys.prefix, os.fspath(Path(sys.base_prefix).resolve()), os.fspath(Path(sys.prefix).resolve())]
    roots.extend([os.fspath(write_dir), os.fspath(Path(sys.executable).resolve().parent), os.fspath(Path(sys.executable).parent)])
    files = check["probe_read_files"]
    parents = {os.fspath(parent) for root in [*roots, *files, os.fspath(task)] for parent in Path(root).parents}
    reads = " ".join(f"(subpath {json.dumps(root)})" for root in sorted(set(roots)))
    reads += " " + " ".join(f"(literal {json.dumps(path)})" for path in files)
    reads += " " + " ".join(f"(literal {json.dumps(parent)})" for parent in sorted(parents))
    profile = f"(version 1) (allow default) (deny network*) (deny file-read-data) (allow file-read-data {reads}) (deny file-write*) (allow file-write* (subpath {json.dumps(os.fspath(write_dir))}))"
    launched = [os.fspath(executable), "-p", profile, argv[0], "-I", "-S", "-B", argv[1]]
    return {"executable": os.fspath(executable), "sha256": hashlib.sha256(_regular_bytes(executable)).hexdigest(), "profile": profile, "executed_argv": launched}


def registered_probe_check(task: Path, request: Mapping[str, object], contract: Mapping[str, object]) -> dict[str, object]:
    try:
        checked = full_protocol.validate_challenge_request(request, contract)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("invalid-input", str(error), affected="probe") from error
    probe = checked.get("probe")
    if checked.get("check_key") != "__new_probe__" or not isinstance(probe, Mapping):
        raise WorkflowError("invalid-input", "request is not a registered probe", affected="probe")
    source = task / str(probe["source_path"])
    if hashlib.sha256(_regular_bytes(source)).hexdigest() != probe["source_sha256"]:
        raise WorkflowError("candidate-changed", "registered probe source drifted", affected=os.fspath(source))
    # A directory in the policy is a selector, never a recursive sandbox grant.
    # Git-ignored files and .git metadata copied with a baseline are not candidate inputs.
    workspace = candidate_check_cwd(task, {"cwd": "$candidate"}, checked["candidate_bridge_id"])
    manifest, _ = _json_bytes(workspace.parent / "candidate-manifest.json")
    selectors = [task / _safe_relative_path(path) for path in contract["probe_policy"]["read_paths"]]
    for selector in selectors:
        if selector.resolve() != selector.absolute():
            raise WorkflowError("scope-conflict", "probe read policy contains a path alias", affected=os.fspath(selector))
    files = [source]
    for entry in manifest["entries"]:
        if entry.get("scope") != "repo" or entry.get("type") != "file":
            continue
        relative = _safe_relative_path(entry["path"])
        parts = Path(relative).parts
        if any(part.lower().startswith(".env") or part.lower() in {".git", ".ssh", "secrets", "credentials"} for part in parts):
            continue
        path = workspace / relative
        if not any(path == selector or selector in path.parents for selector in selectors):
            continue
        if path.resolve() != path.absolute() or hashlib.sha256(_regular_bytes(path)).hexdigest() != entry["sha256"]:
            raise WorkflowError("candidate-changed", "probe input differs from the bound regular file", affected=relative)
        files.append(path)
    return {"scope": "challenge", "argv": list(probe["argv"]), "cwd": os.fspath(task), "timeout_seconds": probe["timeout_seconds"], "required": True, "acceptance_material_paths": [os.fspath(source)], "probe_read_files": sorted(os.fspath(path) for path in files)}


def candidate_check_cwd(task: Path, check: Mapping[str, object], subject_id: str) -> Path | None:
    if check.get("cwd") != "$candidate":
        return None
    if not subject_id.startswith("CB-"):
        raise WorkflowError("invalid-input", "candidate cwd needs an assembled bridge", affected=subject_id)
    op_id = _task_component(subject_id[3:], "assembly ID")
    directory = task / "assemblies" / op_id
    bridge, _ = _json_bytes(directory / "CB.json")
    manifest, payload = _json_bytes(directory / "candidate-manifest.json")
    if bridge.get("bridge_id") != subject_id or bridge.get("candidate_id") != manifest.get("candidate_id") or bridge.get("manifest_hash") != "sha256:" + hashlib.sha256(payload).hexdigest():
        raise WorkflowError("candidate-changed", "candidate cwd bridge does not match manifest", affected=subject_id)
    cwd = directory / "workspace"
    if manifest.get("repo") != os.fspath(cwd):
        raise WorkflowError("candidate-changed", "candidate cwd escaped the assembly", affected=subject_id)
    return cwd


def require_persisted_run_evidence(task: Path, evidence: Mapping[str, object], *, affected: str) -> None:
    evidence_id = evidence.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith("E-"):
        raise WorkflowError("missing-evidence", "evidence ID cannot identify a run", affected=affected)
    run_id = evidence_id[2:]
    try:
        full_protocol.canonical_component(run_id, "run ID")
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("missing-evidence", f"evidence run ID is invalid: {error}", affected=affected) from error
    directory = task / "runs" / run_id
    paths = {
        "request": directory / "request.json",
        "E": task / "evidence" / f"E-{run_id}.json",
        "run-record": directory / "run-record.json",
        "stdout": directory / "stdout.log",
        "stderr": directory / "stderr.log",
    }
    try:
        request, request_bytes = _json_bytes(paths["request"])
        stored, evidence_bytes = _json_bytes(paths["E"])
        intent, intent_bytes = _json_bytes(task / "operation-intent" / f"{run_id}.json")
        record, record_bytes = _json_bytes(paths["run-record"])
        receipt, receipt_bytes = _json_bytes(task / "operation-receipt" / f"{run_id}.json")
        contract = read_task(task)["contract"]
    except WorkflowError as error:
        raise WorkflowError("missing-evidence", f"evidence has no complete run provenance: {error}", affected=evidence_id) from error
    if any(payload != full_protocol.canonical_json_bytes(value) for value, payload in (
        (request, request_bytes), (stored, evidence_bytes), (intent, intent_bytes),
        (record, record_bytes), (receipt, receipt_bytes),
    )):
        raise WorkflowError("candidate-changed", "run JSON is not canonical", affected=evidence_id)
    check_key = request.get("check_key")
    check = contract.get("checks", {}).get(check_key) if isinstance(check_key, str) else None
    if check_key == "__new_probe__":
        probe_id = _task_component(request.get("challenge_request_id"), "probe request ID")
        probe_request, _ = _json_bytes(task / "challenges" / probe_id / "request.json")
        check = registered_probe_check(task, probe_request, contract)
        expected_sandbox = probe_sandbox(task, run_id, check, contract)
        if request.get("sandbox") != expected_sandbox or record.get("executed_argv") != expected_sandbox["executed_argv"]:
            raise WorkflowError("candidate-changed", "probe sandbox execution identity differs", affected=evidence_id)

        if request.get("challenge_request_digest") != probe_request["request_digest"] or request.get("subject_id") != f"{probe_request['packet_id']}:{probe_request['candidate_bridge_id']}":
            raise WorkflowError("candidate-changed", "probe run does not bind its request", affected=evidence_id)

    if not isinstance(check, Mapping) or not isinstance(request.get("argv"), list):
        raise WorkflowError("candidate-changed", "run request lacks an authorized check", affected=evidence_id)
    declared_argv = check.get("argv")
    actual_argv = request["argv"]
    if not isinstance(declared_argv, list) or actual_argv[:len(declared_argv)] != declared_argv:
        raise WorkflowError("candidate-changed", "run argv differs from declared check", affected=evidence_id)
    suffix = actual_argv[len(declared_argv):]
    if suffix and suffix not in check.get("allowed_argv_suffixes", []):
        raise WorkflowError("candidate-changed", "run argv suffix is not authorized", affected=evidence_id)
    if (
        request.get("run_id") != run_id
        or request.get("contract_digest") != contract.get("contract_digest")
        or request.get("check") != dict(check)
        or request.get("scope") != check.get("scope")
        or request.get("cwd") != os.fspath(candidate_check_cwd(task, check, str(request.get("subject_id"))) or Path(str(check.get("cwd"))).absolute())
        or request.get("timeout_seconds") != float(check.get("timeout_seconds", 0))
    ):
        raise WorkflowError("candidate-changed", "run request differs from task authority", affected=evidence_id)
    request_digest = full_protocol.canonical_digest(request)
    expected_intent = {
        "record_type": "operation-intent", "op_id": run_id, "command_kind": "run-check",
        "request_digest": request_digest, "contract_digest": contract["contract_digest"],
        "expected_state_version": intent.get("expected_state_version"),
        "planned_output_types": list(paths),
        "planned_output_paths": [os.fspath(path) for path in paths.values()],
    }
    try:
        full_protocol.assert_same_operation(intent, expected_intent)
        checked = full_protocol.validate_evidence(stored, contract, str(request["scope"]), str(request.get("subject_id")))
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("candidate-changed", f"run authority/evidence is invalid: {error}", affected=evidence_id) from error
    if (
        checked != dict(evidence) or checked.get("run_request_digest") != request_digest
        or any(checked.get(key) != request.get(key) for key in (
            "contract_digest", "scope", "subject_id", "check_key", "harness_identity",
            "environment_identity", "runtime_identity",
        ))
        or record.get("run_id") != run_id or record.get("request") != request
        or record.get("request_digest") != request_digest
        or record.get("argv") != actual_argv or record.get("cwd") != request["cwd"]
        or record.get("result") != checked.get("result")
    ):
        raise WorkflowError("candidate-changed", "run provenance does not bind supplied E", affected=evidence_id)
    try:
        checked = full_protocol.validate_operation_receipt(receipt, intent)
    except full_protocol.ProtocolValidationError as error:
        raise WorkflowError("missing-evidence", f"run receipt is invalid: {error}", affected=evidence_id) from error
    if (
        checked.get("outcome") != "success" or checked.get("side_effect") != "durable"
        or checked.get("actual_output_ids") != ["request", evidence_id, "run-record", "stdout", "stderr"]
        or checked.get("state_version_before") != intent.get("expected_state_version")
        or checked.get("state_version_after") != intent.get("expected_state_version")
    ):
        raise WorkflowError("missing-evidence", "run receipt does not bind all five outputs", affected=evidence_id)
    exit_code = record.get("exit_code")
    if (
        record.get("started") is not True or record.get("terminal_observed") is not True
        or isinstance(exit_code, bool) or not isinstance(exit_code, int)
        or record.get("timed_out") is not False
        or record.get("cleanup") != "not-needed" or record.get("group_state") != "quiet"
        or record.get("acceptance_materials_before") != request.get("acceptance_materials")
        or record.get("acceptance_materials_after") != request.get("acceptance_materials")
        or (request["scope"] == "candidate" and (
            record.get("candidate_status_before") != "match" or record.get("candidate_status_after") != "match"
        ))
        or record.get("result") != ("pass" if exit_code == 0 else "fail")
    ):
        raise WorkflowError("missing-evidence", "run is not an independently terminal check", affected=evidence_id)
    logs = stored.get("logs")
    if not isinstance(logs, list) or [log.get("kind") if isinstance(log, Mapping) else None for log in logs] != ["stdout", "stderr"]:
        raise WorkflowError("missing-evidence", "E lacks both exact run logs", affected=evidence_id)
    for log in logs:
        kind = str(log["kind"])
        payload = _regular_bytes(paths[kind], category="candidate-changed")
        if (
            log.get("path") != os.fspath(paths[kind])
            or log.get("sha256") != hashlib.sha256(payload).hexdigest()
            or log.get("size") != len(payload) or log.get("truncated") is not False
            or record.get(f"{kind}_sha256") != hashlib.sha256(payload).hexdigest()
            or record.get(f"{kind}_size") != len(payload)
            or record.get(f"{kind}_truncated") is not False
        ):
            raise WorkflowError("candidate-changed", "E log provenance drifted or truncated", affected=evidence_id)


def require_persisted_p2_predecessor_closure(
    task: Path, *, contract: Mapping[str, object], closure: list[str],
    predecessor_verdicts: Mapping[str, Mapping[str, object]], affected: str,
) -> None:
    """Bind a P2 review's supplied rejection ancestry to published V records."""

    if contract.get("protocol") != full_protocol.STAGED_PROTOCOL_VERSION:
        return
    for verdict_id in closure:
        expected = predecessor_verdicts.get(verdict_id)
        if not isinstance(expected, Mapping):
            raise WorkflowError(
                "review-invalid", "P2 predecessor closure is missing a verdict record",
                affected=affected, recovery="reload-persisted-predecessor-reviews",
            )
        path = task / "reviews" / _task_component(verdict_id, "predecessor verdict ID") / "V.json"
        try:
            observed, raw = _json_bytes(path)
        except WorkflowError as error:
            raise WorkflowError(
                "missing-evidence", f"P2 predecessor review is unavailable: {error}",
                affected=affected, recovery="reload-persisted-predecessor-reviews",
            ) from error
        if raw != full_protocol.canonical_json_bytes(expected) or observed != dict(expected):
            raise WorkflowError(
                "review-invalid", "P2 predecessor review differs from its persisted V record",
                affected=affected, recovery="reload-persisted-predecessor-reviews",
            )


def final_accept(
    task_dir: Path | str, *, op_id: str, expected_state_version: int,
    acceptance: Mapping[str, object], relationship: full_protocol.RelationshipContext,
    final_candidate_evidence: Mapping[str, object], root_authority: Mapping[str, object],
    candidate_verify_receipt: Mapping[str, object],
    dependency_acceptance_contexts: Mapping[str, full_protocol.AcceptanceContext],
    trusted_observation_time: object,
) -> dict[str, Any]:
    """Validate prior review/authority and durably record one final stage acceptance."""

    task = Path(task_dir).absolute()
    records = read_task(task)
    require_persisted_run_evidence(task, final_candidate_evidence, affected=op_id)
    contract = records["contract"]
    staged = _is_staged_contract(contract)
    stage_key = acceptance.get("accepted_stage_key") if isinstance(acceptance, Mapping) else None
    if staged:
        if not isinstance(stage_key, str) or stage_key not in contract["stages"]:
            raise WorkflowError("invalid-input", "staged acceptance names an unknown stage", affected=op_id)
        if records["state"]["stage_status"].get("stage_key") != stage_key and not (_intent_path(task, op_id).exists() or _intent_path(task, op_id).is_symlink()):
            raise WorkflowError("scope-conflict", "acceptance is not for the active stage", affected=stage_key)
        # This read is the actual predecessor gate; a caller cannot supply a
        # decorative dependency map while skipping the accepted-stage record.
        _required_prior_stage_selection(task, contract, stage_key)
    request = {
        "op_id": op_id,
        "command_kind": "final-accept",
        "expected_state_version": expected_state_version,
        "acceptance": full_protocol.canonical_digest(acceptance),
        "relationship": _relationship_identity(relationship),
        "final_candidate_evidence": full_protocol.canonical_digest(final_candidate_evidence),
        "root_authority": full_protocol.canonical_digest(root_authority),
        "candidate_verify_receipt": full_protocol.canonical_digest(candidate_verify_receipt),
        "dependency_acceptance_contexts": {
            key: _acceptance_context_identity(value)
            for key, value in sorted(dependency_acceptance_contexts.items())
        },
        "trusted_observation_time": (
            trusted_observation_time.isoformat()
            if hasattr(trusted_observation_time, "isoformat")
            else trusted_observation_time
        ),
    }
    request_digest = full_protocol.canonical_digest(request)
    acceptance_id = acceptance.get("acceptance_id")
    if not isinstance(acceptance_id, str) or not acceptance_id:
        raise WorkflowError("invalid-input", "acceptance ID is missing", affected=op_id)
    directory = task / "acceptances" / acceptance_id
    output_paths = {
        "A": directory / "A.json",
        "final-candidate-E": directory / "final-candidate-evidence.json",
        "root-authority": directory / "root-authority.json",
        "candidate-verify-receipt": directory / "candidate-verify-receipt.json",
    }
    stage_index: dict[str, object] | None = None
    if staged:
        assert isinstance(stage_key, str)
        stage_index = {
            "stage_key": stage_key, "acceptance_id": acceptance_id,
            "candidate_bridge_id": acceptance.get("candidate_bridge_id"),
            "selected_attempts": {
                key: value for key, value in records["state"]["selected_attempts"].items()
                if contract["work_items"].get(key, {}).get("stage_key") == stage_key
            },
            "final_accept_op_id": op_id,
            "final_candidate_evidence_id": acceptance.get("final_candidate_evidence_id"),
        }
        output_paths["stage-index"] = task / "stage-acceptances" / f"{_task_component(stage_key, 'stage key')}.json"
    intent = {
        "record_type": "operation-intent",
        "op_id": op_id,
        "command_kind": "final-accept",
        "request_digest": request_digest,
        "contract_digest": contract["contract_digest"],
        "expected_state_version": expected_state_version,
        "planned_output_types": list(output_paths),
        "planned_output_paths": [os.fspath(path) for path in output_paths.values()],
    }
    checked_acceptance: dict[str, Any] | None = None
    intent_path = _intent_path(task, op_id)
    if intent_path.exists() or intent_path.is_symlink():
        status, completed = _operation_status(task, intent)
        if completed is not None:
            return completed
    else:
        state = records["state"]
        if state["version"] != expected_state_version:
            raise WorkflowError(
                "stale-baseline", "final acceptance expected state is stale",
                affected=op_id, recovery="reload-state-and-create-a-new-operation",
            )
        if relationship.task_contract != contract:
            raise WorkflowError(
                "review-invalid", "acceptance relationship uses another task contract",
                affected=acceptance_id,
            )
        if candidate_verify_receipt != relationship.candidate_verify_receipt:
            raise WorkflowError(
                "review-invalid", "final candidate verify receipt differs from the reviewed relationship",
                affected=acceptance_id,
            )
        _require_current_candidate(
            relationship.manifest, candidate_verify_receipt, affected=acceptance_id
        )
        current = state["current_ids"]
        if (
            state["stage_status"].get("review_status") != "reviewed-awaiting-final-accept"
            or current.get("candidate_binding") != relationship.candidate_bridge.get("bridge_id")
            or relationship.packet is None
            or current.get("review_packet") != relationship.packet.get("packet_id")
            or relationship.verdict is None
            or current.get("verdict") != relationship.verdict.get("verdict_id")
        ):
            raise WorkflowError(
                "review-invalid", "state does not identify the reviewed candidate/P/V awaiting acceptance",
                affected=acceptance_id,
            )
        try:
            checked_acceptance = full_protocol.validate_acceptance(
                acceptance,
                context=relationship,
                candidate_bridge=relationship.candidate_bridge,
                packet=relationship.packet,
                verdict=relationship.verdict,
                final_candidate_evidence=final_candidate_evidence,
                root_authority=root_authority,
                candidate_verify_receipt=candidate_verify_receipt,
                task_contract=contract,
                dependency_acceptance_contexts=dependency_acceptance_contexts,
                trusted_observation_time=trusted_observation_time,
            )
            assert relationship.packet is not None
            require_persisted_p2_predecessor_closure(
                task, contract=contract, closure=list(relationship.packet["rejection_closure"]),
                predecessor_verdicts=relationship.predecessor_verdicts or {}, affected=acceptance_id,
            )
        except full_protocol.ProtocolValidationError as error:
            raise WorkflowError(
                "review-invalid", f"final acceptance relationship is invalid: {error}",
                affected=acceptance_id, recovery="obtain-fresh-valid-review-and-root-authority",
            ) from error
        status, completed = _operation_status(task, intent)
        if completed is not None:
            return completed
    if checked_acceptance is None:
        try:
            _require_current_candidate(
                relationship.manifest, candidate_verify_receipt, affected=acceptance_id
            )
            checked_acceptance = full_protocol.validate_acceptance(
                acceptance, context=relationship,
                candidate_bridge=relationship.candidate_bridge, packet=relationship.packet,
                verdict=relationship.verdict,
                final_candidate_evidence=final_candidate_evidence,
                root_authority=root_authority,
                candidate_verify_receipt=candidate_verify_receipt,
                task_contract=contract,
                dependency_acceptance_contexts=dependency_acceptance_contexts,
                trusted_observation_time=trusted_observation_time,
            )
            assert relationship.packet is not None
            require_persisted_p2_predecessor_closure(
                task, contract=contract, closure=list(relationship.packet["rejection_closure"]),
                predecessor_verdicts=relationship.predecessor_verdicts or {}, affected=acceptance_id,
            )
        except full_protocol.ProtocolValidationError as error:
            raise WorkflowError(
                "candidate-changed", f"acceptance inputs drifted during recovery: {error}",
                affected=acceptance_id, side_effect="unknown",
                recovery="preserve-and-root-reconcile",
            ) from error
    payload_values = {
        "A": checked_acceptance,
        "final-candidate-E": dict(final_candidate_evidence),
        "root-authority": dict(root_authority),
        "candidate-verify-receipt": dict(candidate_verify_receipt),
    }
    if stage_index is not None:
        payload_values["stage-index"] = stage_index
    payloads = {
        key: full_protocol.canonical_json_bytes(value)
        for key, value in payload_values.items()
    }
    existing = [path.exists() or path.is_symlink() for path in output_paths.values()]
    if status == "recover":
        if not any(existing):
            receipt = _operation_receipt(
                intent, outcome="failure", side_effect="none", actual_output_ids=[],
                state_before=expected_state_version, state_after=expected_state_version,
            )
            return publish_operation_receipt(task, receipt)
        if not all(existing):
            receipt = _operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown", actual_output_ids=[],
                state_before=expected_state_version, state_after=expected_state_version,
            )
            return publish_operation_receipt(task, receipt)
        for key, path in output_paths.items():
            if _regular_bytes(path, category="candidate-changed") != payloads[key]:
                raise WorkflowError(
                    "candidate-changed", "acceptance output drifted",
                    affected=os.fspath(path), side_effect="unknown",
                    recovery="preserve-and-root-reconcile",
                )
    else:
        for key, path in output_paths.items():
            publish_task_path_bytes(task, path, payloads[key])
    actual_ids = [
        checked_acceptance["acceptance_id"], final_candidate_evidence["evidence_id"],
        root_authority["root_authority_id"],
        full_protocol.canonical_digest(candidate_verify_receipt),
    ]
    current = read_task(task)["state"]
    stage_status = dict(current["stage_status"], status="accepted")
    if staged:
        assert isinstance(stage_key, str)
        accepted_now = {stage_key}
        for candidate_stage in contract["stages"]:
            try:
                _accepted_stage_index(task, candidate_stage)
                accepted_now.add(candidate_stage)
            except WorkflowError:
                pass
        for candidate_stage, definition in contract["stages"].items():
            if candidate_stage not in accepted_now and set(definition["depends_on"]).issubset(accepted_now):
                stage_status = {"stage_key": candidate_stage, "status": "running", "review_status": "reviewing"}
                break
    current_ids = dict(current["current_ids"], acceptance=acceptance_id)
    updates = {
        "stage_status": stage_status,
        "current_ids": current_ids,
        "last_operation_receipt": op_id,
    }
    if current["version"] == expected_state_version:
        try:
            update_state_cas(task, expected_version=expected_state_version, updates=updates)
        except WorkflowError:
            observed = read_task(task)["state"]["version"]
            receipt = _operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown",
                actual_output_ids=actual_ids, state_before=expected_state_version,
                state_after=observed,
            )
            return publish_operation_receipt(task, receipt)
    elif not (
        current["version"] == expected_state_version + 1
        and current["last_operation_receipt"] == op_id
        and current["stage_status"] == stage_status
        and current["current_ids"].get("acceptance") == acceptance_id
    ):
        receipt = _operation_receipt(
            intent, outcome="ambiguous", side_effect="unknown", actual_output_ids=actual_ids,
            state_before=expected_state_version, state_after=current["version"],
        )
        return publish_operation_receipt(task, receipt)
    receipt = _operation_receipt(
        intent, outcome="success", side_effect="durable", actual_output_ids=actual_ids,
        state_before=expected_state_version, state_after=expected_state_version + 1,
    )
    return publish_operation_receipt(task, receipt)


def _load_cli_json(path: str) -> dict[str, Any]:
    return _json_bytes(Path(path).absolute())[0]


def _relationship_from_stored_package(value: Mapping[str, object]) -> full_protocol.RelationshipContext:
    required = {"task_contract", "candidate_bridge", "manifest", "manifest_bytes_base64", "candidate_verify_receipt", "assembly", "deliveries", "materials", "delivery_evidence"}
    if not required.issubset(value):
        raise WorkflowError("missing-evidence", "stored review context is incomplete", affected="review-context")
    try:
        manifest_bytes = base64.b64decode(value["manifest_bytes_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise WorkflowError("candidate-changed", "stored review context manifest bytes are invalid", affected="review-context") from error
    from dataclasses import fields
    values = {field.name: value.get(field.name) for field in fields(full_protocol.RelationshipContext) if field.name != "manifest_bytes"}
    values["manifest_bytes"] = manifest_bytes
    return full_protocol.RelationshipContext(**values)


def _load_persisted_acceptance_context(task: Path, acceptance_id: str, active: set[str] | None = None) -> full_protocol.AcceptanceContext:
    active = set() if active is None else active
    if acceptance_id in active:
        raise WorkflowError("candidate-changed", "persisted acceptance contexts contain a cycle", affected=acceptance_id)
    active.add(acceptance_id)
    try:
        directory = task / "acceptances" / _task_component(acceptance_id, "acceptance ID")
        acceptance, _ = _json_bytes(directory / "A.json")
        final_evidence, _ = _json_bytes(directory / "final-candidate-evidence.json")
        authority, _ = _json_bytes(directory / "root-authority.json")
        verify, _ = _json_bytes(directory / "candidate-verify-receipt.json")
        verdict_id = acceptance.get("verdict_id")
        if not isinstance(verdict_id, str) or not verdict_id:
            raise WorkflowError("candidate-changed", "persisted acceptance lacks verdict", affected=acceptance_id)
        relationship_package, _ = _json_bytes(task / "reviews" / _task_component(verdict_id, "verdict ID") / "context.json")
        relationship = _relationship_from_stored_package(relationship_package)
        try:
            if relationship.packet is None:
                raise full_protocol.RelationshipValidationError(
                    "persisted acceptance review context lacks its packet"
                )
            closure = full_protocol._validate_predecessor_closure(
                list(relationship.packet["rejection_roots"]),
                relationship.predecessor_verdicts or {},
            )
        except (KeyError, TypeError, full_protocol.ProtocolValidationError) as error:
            raise WorkflowError(
                "review-invalid", f"persisted acceptance predecessor provenance is invalid: {error}",
                affected=acceptance_id, recovery="preserve-and-root-reconcile",
            ) from error
        require_persisted_p2_predecessor_closure(
            task, contract=relationship.task_contract, closure=closure,
            predecessor_verdicts=relationship.predecessor_verdicts or {}, affected=acceptance_id,
        )
        deps = {stage: _load_persisted_acceptance_context(task, dependency, active) for stage, dependency in acceptance.get("dependency_acceptance_ids", {}).items()}
        return full_protocol.AcceptanceContext(acceptance=acceptance, relationship=relationship, final_candidate_evidence=final_evidence, root_authority=authority, candidate_verify_receipt=verify, dependency_acceptance_contexts=deps)
    finally:
        active.remove(acceptance_id)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Mechanical full-route workflow storage")
    commands = result.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--task-dir", required=True)
    initialize.add_argument("--contract", required=True)
    initialize.add_argument("--state", required=True)
    validate = commands.add_parser("validate-task")
    validate.add_argument("--task-dir", required=True)
    status = commands.add_parser("status")
    status.add_argument("--task-dir", required=True)
    receive = commands.add_parser("receive")
    receive.add_argument("--task-dir", required=True)
    receive.add_argument("--op-id", required=True)
    receive.add_argument("--expected-state-version", required=True, type=int)
    receive.add_argument("--material", required=True)
    receive.add_argument("--delivery", required=True)
    receive.add_argument("--delivery-evidence", required=True)
    receive.add_argument("--bundle", required=True)
    receive.add_argument("--runtime-receipt", required=True)
    assemble = commands.add_parser("assemble")
    assemble.add_argument("--task-dir", required=True)
    assemble.add_argument("--op-id", required=True)
    assemble.add_argument("--expected-state-version", required=True, type=int)
    assemble.add_argument("--baseline-repo", required=True)
    assemble.add_argument("--selected", required=True, help="JSON file mapping work key to delivery ID")
    assemble.add_argument("--stage", help="required only by the opt-in staged protocol")
    final = commands.add_parser("final-accept")
    final.add_argument("--task-dir", required=True)
    final.add_argument("--op-id", required=True)
    final.add_argument("--expected-state-version", required=True, type=int)
    final.add_argument("--acceptance", required=True)
    final.add_argument("--final-evidence", required=True)
    final.add_argument("--root-authority", required=True)
    final.add_argument("--trusted-observation-time", required=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "init":
            output = initialize_task(
                arguments.task_dir, _load_cli_json(arguments.contract), _load_cli_json(arguments.state)
            )
        elif arguments.command in {"validate-task", "status"}:
            output = read_task(arguments.task_dir)
        elif arguments.command == "receive":
            output = receive_delivery(
                arguments.task_dir, op_id=arguments.op_id,
                expected_state_version=arguments.expected_state_version,
                material_path=arguments.material, delivery_path=arguments.delivery,
                delivery_evidence_path=arguments.delivery_evidence,
                bundle_path=arguments.bundle, runtime_receipt_path=arguments.runtime_receipt,
            )
        elif arguments.command == "final-accept":
            acceptance = _load_cli_json(arguments.acceptance)
            verdict_id = acceptance.get("verdict_id")
            if not isinstance(verdict_id, str) or not verdict_id:
                raise WorkflowError("invalid-input", "acceptance lacks verdict ID", affected=arguments.op_id)
            task = Path(arguments.task_dir).absolute()
            package, _ = _json_bytes(task / "reviews" / _task_component(verdict_id, "verdict ID") / "context.json")
            relationship = _relationship_from_stored_package(package)
            dependencies = {stage: _load_persisted_acceptance_context(task, item) for stage, item in acceptance.get("dependency_acceptance_ids", {}).items()}
            output = final_accept(
                arguments.task_dir, op_id=arguments.op_id, expected_state_version=arguments.expected_state_version,
                acceptance=acceptance, relationship=relationship,
                final_candidate_evidence=_load_cli_json(arguments.final_evidence),
                root_authority=_load_cli_json(arguments.root_authority),
                candidate_verify_receipt=relationship.candidate_verify_receipt,
                dependency_acceptance_contexts=dependencies,
                trusted_observation_time=arguments.trusted_observation_time,
            )
        else:
            output = assemble_candidate(
                arguments.task_dir, op_id=arguments.op_id,
                expected_state_version=arguments.expected_state_version,
                baseline_repo=arguments.baseline_repo, selected=_load_cli_json(arguments.selected),
                stage_key=arguments.stage,
            )
        print(json.dumps(output, sort_keys=True))
        return 0
    except WorkflowError as error:
        print(json.dumps(error.as_dict(), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
