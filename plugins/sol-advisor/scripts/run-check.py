#!/usr/bin/env python3
"""Run one predeclared full-route check and publish immutable evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import candidate as candidate_tool
import full_protocol
import workflow


DEFAULT_LOG_LIMIT = 64 * 1024


def _candidate_receipt(manifest_path: Path) -> tuple[dict[str, Any], dict[str, object], bytes]:
    manifest, manifest_bytes = workflow._json_bytes(manifest_path)
    try:
        checked = candidate_tool.validate_manifest(manifest)
        current = candidate_tool.current_candidate_from_manifest(checked)
        changes = candidate_tool.compare_entries(checked["entries"], current["entries"])
    except (candidate_tool.CandidateError, OSError, KeyError, TypeError) as error:
        raise workflow.WorkflowError(
            "candidate-changed", f"cannot compare candidate: {error}",
            affected=os.fspath(manifest_path), recovery="rebuild-and-rereview-candidate",
        ) from error
    receipt = {
        "status": "match" if not changes and current["candidate_id"] == checked["candidate_id"] else "changed",
        "candidate_id": checked["candidate_id"],
        "current_candidate_id": current["candidate_id"],
        "head_changed": current["source"]["head"] != checked["source"]["head"],
        "changes": changes,
        "expected_candidate_id": checked["candidate_id"],
        "expected_candidate_id_match": True,
    }
    return checked, receipt, manifest_bytes


def _declared_environment(policy: object) -> dict[str, str]:
    if not isinstance(policy, list):
        raise workflow.WorkflowError(
            "invalid-input", "environment policy must be a list", affected="environment_policy"
        )
    desired: dict[str, str] = {}
    for entry in policy:
        if not isinstance(entry, Mapping):
            raise workflow.WorkflowError(
                "invalid-input", "environment policy entry is not an object",
                affected="environment_policy",
            )
        if entry.get("present") is True and entry.get("classification") == "non-sensitive":
            try:
                desired[str(entry.get("name"))] = base64.b64decode(
                    str(entry.get("value_bytes_base64")), validate=True
                ).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as error:
                raise workflow.WorkflowError(
                    "invalid-input", "non-sensitive environment value is invalid",
                    affected=str(entry.get("name")),
                ) from error
    try:
        return full_protocol.validate_environment_policy(policy, desired)
    except full_protocol.EnvironmentPolicyError as error:
        category = "runtime-unavailable" if "sensitive" in str(error) or "unclassified" in str(error) else "invalid-input"
        raise workflow.WorkflowError(
            category, f"child environment is unavailable: {error}",
            affected="environment_policy", recovery="remove-sensitive-runtime-need-or-authorize-separately",
        ) from error


def _validate_check(
    contract: Mapping[str, object], check_key: str, argv_suffix: list[str],
    *, candidate_cwd: Path | None = None,
) -> tuple[dict[str, Any], list[str], Path, float]:
    checks = contract.get("checks")
    if not isinstance(checks, Mapping) or check_key not in checks or not isinstance(checks[check_key], Mapping):
        raise workflow.WorkflowError("invalid-input", "check key is not predeclared", affected=check_key)
    check = dict(checks[check_key])
    allowed = {"scope", "argv", "cwd", "timeout_seconds", "required", "acceptance_material_paths", "final_candidate_verify", "allowed_argv_suffixes"}
    if contract.get("protocol") == full_protocol.STAGED_PROTOCOL_VERSION:
        allowed.update({"phase", "stage_key"})
    if not set(check).issubset(allowed):
        raise workflow.WorkflowError(
            "invalid-input", "check configuration has unsupported fields", affected=check_key
        )
    argv = check.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
        raise workflow.WorkflowError("invalid-input", "check argv is invalid", affected=check_key)
    if any(not isinstance(item, str) or "\x00" in item for item in argv_suffix):
        raise workflow.WorkflowError("invalid-input", "argv suffix is invalid", affected=check_key)
    allowed_suffixes = check.get("allowed_argv_suffixes", [])
    if not isinstance(allowed_suffixes, list) or any(not isinstance(vector, list) or any(not isinstance(item, str) or "\x00" in item for item in vector) for vector in allowed_suffixes):
        raise workflow.WorkflowError("invalid-input", "allowed argv suffixes are invalid", affected=check_key)
    if argv_suffix and argv_suffix not in allowed_suffixes:
        raise workflow.WorkflowError("invalid-input", "argv suffix is not an exact contract-authorized vector", affected=check_key)
    executable = Path(argv[0])
    try:
        resolved_executable = executable.resolve(strict=True)
        details = resolved_executable.stat()
    except OSError as error:
        raise workflow.WorkflowError(
            "runtime-unavailable", f"check executable is unavailable: {error}",
            affected=argv[0],
        ) from error
    if not executable.is_absolute() or not stat.S_ISREG(details.st_mode) or not os.access(resolved_executable, os.X_OK):
        raise workflow.WorkflowError(
            "runtime-unavailable", "check executable must be an absolute executable regular file",
            affected=argv[0],
        )
    cwd_value = check.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value:
        raise workflow.WorkflowError("invalid-input", "check cwd is invalid", affected=check_key)
    if cwd_value == "$candidate":
        if candidate_cwd is None or check.get("scope") != "candidate":
            raise workflow.WorkflowError("invalid-input", "candidate cwd requires a bound candidate", affected=check_key)
        cwd = candidate_cwd
    else:
        cwd = Path(cwd_value).absolute()
    if not cwd.is_dir() or cwd.is_symlink():
        raise workflow.WorkflowError("invalid-input", "check cwd is not a safe directory", affected=os.fspath(cwd))
    timeout = check.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 3600:
        raise workflow.WorkflowError("invalid-input", "check timeout is invalid", affected=check_key)
    if check.get("scope") not in full_protocol.EVIDENCE_SCOPES:
        raise workflow.WorkflowError("invalid-input", "check scope is unsupported", affected=check_key)
    materials = check.get("acceptance_material_paths", [])
    if (
        not isinstance(materials, list)
        or any(not isinstance(item, str) or not item or "\0" in item for item in materials)
        or len(set(materials)) != len(materials)
    ):
        raise workflow.WorkflowError("invalid-input", "acceptance material paths are invalid", affected=check_key)
    return check, [*argv, *argv_suffix], cwd, float(timeout)


def _runtime_identity() -> str:
    return full_protocol.canonical_digest(
        {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable": os.path.realpath(sys.executable),
        }
    )


def _material_inventory(path_value: str, *, label: str) -> dict[str, object]:
    path = Path(path_value).absolute()
    if label not in {"host-python", "child-executable"} and not candidate_tool.parents_have_no_symlinks(path):
        raise workflow.WorkflowError("invalid-input", "acceptance material has a symlinked parent alias", affected=path_value)
    try:
        details = path.lstat()
    except OSError as error:
        raise workflow.WorkflowError("runtime-unavailable", f"acceptance material is unavailable: {error}", affected=path_value) from error
    if stat.S_ISLNK(details.st_mode):
        try:
            link_text = os.readlink(path)
            target = path.resolve(strict=True)
            target_details = target.stat()
        except OSError as error:
            raise workflow.WorkflowError("runtime-unavailable", f"acceptance material symlink is unavailable: {error}", affected=path_value) from error
        if not stat.S_ISREG(target_details.st_mode):
            raise workflow.WorkflowError("invalid-input", "acceptance material symlink target is not regular", affected=path_value)
        if target_details.st_nlink != 1:
            raise workflow.WorkflowError("invalid-input", "acceptance material symlink target has hardlink aliases", affected=path_value)
        return {
            "label": label, "roles": [label], "requested_path": os.fspath(path), "resolved_path": os.fspath(target),
            "type": "symlink", "link_sha256": hashlib.sha256(os.fsencode(link_text)).hexdigest(),
            "target_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "target_mode": stat.S_IMODE(target_details.st_mode), "inode": [target_details.st_dev, target_details.st_ino],
        }
    if not stat.S_ISREG(details.st_mode):
        raise workflow.WorkflowError("invalid-input", "acceptance material is not regular", affected=path_value)
    if details.st_nlink != 1:
        raise workflow.WorkflowError("invalid-input", "acceptance material has hardlink aliases", affected=path_value)
    return {
        "label": label, "roles": [label], "requested_path": os.fspath(path), "resolved_path": os.fspath(path),
        "type": "file", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "mode": stat.S_IMODE(details.st_mode), "inode": [details.st_dev, details.st_ino],
    }


def _child_material_path(value: str, cwd: Path) -> str:
    path = Path(value)
    return os.fspath(path if path.is_absolute() else cwd / path)


def _effective_materials(check: Mapping[str, object], argv: list[str], cwd: Path, *, staged: bool = False) -> list[dict[str, object]]:
    declared = check.get("acceptance_material_paths", [])
    assert isinstance(declared, list)
    paths: list[tuple[str, str]] = [("runner-source", os.fspath(Path(__file__).absolute()))]
    if staged:
        paths.extend(("runner-source", os.fspath(Path(module.__file__).resolve())) for module in (workflow, full_protocol, workflow.candidate_tool))
    paths.extend(("acceptance-material", _child_material_path(value, cwd)) for value in declared)
    # An interpreter's first positional program is executable acceptance material even
    # when the contract did not redundantly declare it.  Any existing positional file
    # after that is an input resolved using the child cwd, not the parent process cwd.
    if len(argv) > 1:
        script = _child_material_path(argv[1], cwd)
        if Path(script).is_file() or Path(script).is_symlink():
            paths.append(("child-script", script))
            for value in argv[2:]:
                candidate = _child_material_path(value, cwd)
                if Path(candidate).is_file() or Path(candidate).is_symlink():
                    paths.append(("argv-input", candidate))
    paths.extend((("host-python", os.fspath(Path(sys.executable).absolute())), ("child-executable", argv[0])))
    result: list[dict[str, object]] = []
    automatic = {"host-python", "child-executable"}
    for label, value in paths:
        item = _material_inventory(value, label=label)
        same_path = next((existing for existing in result if existing["requested_path"] == item["requested_path"] and existing["resolved_path"] == item["resolved_path"]), None)
        if same_path is not None:
            same_path["roles"].append(label)
            continue
        if any(existing["inode"] == item["inode"] for existing in result):
            raise workflow.WorkflowError("invalid-input", "acceptance material paths share an inode alias", affected=str(item["requested_path"]))
        result.append(item)
    return result


def _require_candidate_bound_materials(manifest: Mapping[str, object], materials: list[dict[str, object]]) -> None:
    repo = Path(str(manifest["repo"])).resolve(strict=True)
    entries = {(item["scope"], item["path"]) for item in manifest["entries"] if isinstance(item, Mapping)}
    explicit = set(manifest["selection"]["explicit_inputs"])
    for item in materials:
        if item["label"] not in {"runner-source", "acceptance-material", "child-script", "argv-input"}:
            continue
        requested = Path(str(item["requested_path"])).resolve(strict=True)
        try:
            relative = requested.relative_to(repo).as_posix()
        except ValueError:
            if os.fspath(requested) not in explicit or ("input", os.fspath(requested)) not in entries:
                raise workflow.WorkflowError("missing-evidence", "candidate check material is not explicitly candidate-bound", affected=os.fspath(requested))
        else:
            if ("repo", relative) not in entries:
                raise workflow.WorkflowError("missing-evidence", "candidate check material is outside the selected candidate inventory", affected=relative)


def _harness_identity(check: Mapping[str, object], argv: list[str], materials: list[dict[str, object]]) -> str:
    source = Path(__file__).read_bytes()
    return full_protocol.canonical_digest(
        {
            "schema": 2,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "check": dict(check),
            "argv": argv,
            "acceptance_materials": materials,
        }
    )


def _environment_identity(policy: object, environment: Mapping[str, str]) -> str:
    entries = []
    for name in sorted(environment):
        encoded = environment[name].encode("utf-8")
        entries.append({"name": name, "present": True, "length": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()})
    return full_protocol.canonical_digest({"schema": 1, "policy": policy, "entries": entries})


def _run_paths(task: Path, run_id: str) -> dict[str, Path]:
    directory = task / "runs" / run_id
    return {
        "request": directory / "request.json",
        "E": task / "evidence" / f"E-{run_id}.json",
        "run-record": directory / "run-record.json",
        "stdout": directory / "stdout.log",
        "stderr": directory / "stderr.log",
    }


def _run_output_ids(run_id: str) -> list[str]:
    return ["request", f"E-{run_id}", "run-record", "stdout", "stderr"]


def _require_exact_json(path: Path, expected: Mapping[str, object], *, affected: str) -> dict[str, Any]:
    try:
        observed, payload = workflow._json_bytes(path)
    except workflow.WorkflowError as error:
        raise workflow.WorkflowError(
            "missing-evidence", f"required immutable JSON is unavailable: {error}", affected=affected,
            side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    if payload != full_protocol.canonical_json_bytes(expected) or observed != dict(expected):
        raise workflow.WorkflowError(
            "candidate-changed", "immutable JSON bytes differ from the caller-bound value",
            affected=affected, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    return observed


def _require_completed_prepare(
    task: Path, request: Mapping[str, object], contract: Mapping[str, object], *, affected: str,
) -> dict[str, Any]:
    """Require the prepare transaction; run-check never repairs another owner's receipt."""
    request_id = str(request["request_id"])
    request_path = task / "challenges" / request_id / "request.json"
    intent_path = task / "operation-intent" / f"prepare-challenge-{request_id}.json"
    try:
        stored_intent, _ = workflow._json_bytes(intent_path)
        checked_intent = full_protocol.validate_operation_intent(stored_intent)
    except (workflow.WorkflowError, full_protocol.ProtocolValidationError) as error:
        raise workflow.WorkflowError(
            "missing-evidence", f"challenge prepare intent is missing or invalid: {error}",
            affected=affected, recovery="prepare-a-new-authorized-challenge",
        ) from error
    expected_intent = {
        "record_type": "operation-intent", "op_id": f"prepare-challenge-{request_id}",
        "command_kind": "prepare-challenge",
        "request_digest": full_protocol.canonical_digest({"action": "prepare-challenge", "request": dict(request)}),
        "contract_digest": contract["contract_digest"],
        "expected_state_version": checked_intent["expected_state_version"],
        "planned_output_types": ["challenge-request"],
        "planned_output_paths": [os.fspath(request_path)],
    }
    try:
        full_protocol.assert_same_operation(checked_intent, expected_intent)
    except full_protocol.ProtocolValidationError as error:
        raise workflow.WorkflowError(
            "candidate-changed", f"challenge prepare intent drifted: {error}", affected=affected,
            side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    _require_exact_json(request_path, request, affected=affected)
    try:
        stored_receipt, _ = workflow._json_bytes(workflow._receipt_path(task, str(expected_intent["op_id"])))
        receipt = full_protocol.validate_operation_receipt(stored_receipt, expected_intent)
    except (workflow.WorkflowError, full_protocol.ProtocolValidationError) as error:
        raise workflow.WorkflowError(
            "missing-evidence", f"challenge prepare receipt is missing or invalid: {error}",
            affected=affected, recovery="prepare-owner-must-complete-receipt-only-recovery",
        ) from error
    if (
        receipt["outcome"] != "success" or receipt["side_effect"] != "durable"
        or receipt["actual_output_ids"] != [request_id]
        or receipt["state_version_before"] != expected_intent["expected_state_version"]
        or receipt["state_version_after"] != expected_intent["expected_state_version"]
    ):
        raise workflow.WorkflowError(
            "candidate-changed", "challenge prepare receipt does not prove the exact request transaction",
            affected=affected, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    return dict(request)


def _validate_run_outputs(
    task: Path, run_id: str, contract: Mapping[str, object], request: Mapping[str, object],
) -> dict[str, Any]:
    paths = _run_paths(task, run_id)
    directory = paths["request"].parent
    _require_exact_json(paths["request"], request, affected=run_id)
    evidence, _ = workflow._json_bytes(task / "evidence" / f"E-{run_id}.json")
    record, _ = workflow._json_bytes(directory / "run-record.json")
    try:
        checked = full_protocol.validate_evidence(
            evidence, contract, str(request["scope"]), str(request["subject_id"])
        )
    except full_protocol.ProtocolValidationError as error:
        raise workflow.WorkflowError(
            "candidate-changed", f"stored E is invalid: {error}", affected=run_id,
            side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    if request.get("challenge_request_digest") is not None and (
        checked.get("challenge_request_id") != request.get("challenge_request_id")
        or checked.get("challenge_request_digest") != request.get("challenge_request_digest")
    ):
        raise workflow.WorkflowError(
            "candidate-changed", "stored challenge E does not bind its request",
            affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    if record.get("request") != dict(request) or record.get("argv") != request.get("argv") or record.get("cwd") != request.get("cwd"):
        raise workflow.WorkflowError("candidate-changed", "stored run record does not retain the canonical request/argv/cwd", affected=run_id, side_effect="unknown")
    if (
        record.get("run_id") != run_id
        or record.get("request_digest") != full_protocol.canonical_digest(request)
        or record.get("result") != checked.get("result")
        or checked.get("run_request_digest") != full_protocol.canonical_digest(request)
    ):
        raise workflow.WorkflowError(
            "candidate-changed", "stored run record does not bind E/request",
            affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    logs = checked.get("logs")
    if not isinstance(logs, list) or [item.get("kind") if isinstance(item, Mapping) else None for item in logs] != ["stdout", "stderr"]:
        raise workflow.WorkflowError(
            "candidate-changed", "stored E log metadata is incomplete",
            affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    for item in logs:
        if not isinstance(item, Mapping) or item.get("kind") not in {"stdout", "stderr"}:
            raise workflow.WorkflowError(
                "candidate-changed", "stored E log metadata is invalid",
                affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
            )
        path = directory / f"{item['kind']}.log"
        payload = workflow._regular_bytes(path, category="candidate-changed")
        if (
            item.get("path") != os.fspath(path)
            or item.get("sha256") != hashlib.sha256(payload).hexdigest()
            or not isinstance(item.get("size"), int)
            or isinstance(item.get("size"), bool)
            or item.get("size") < len(payload)
            or not isinstance(item.get("truncated"), bool)
            or (item.get("truncated") is False and item.get("size") != len(payload))
        ):
            raise workflow.WorkflowError(
                "candidate-changed", "stored E log bytes/metadata drifted",
                affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
            )
        if record.get(f"{item['kind']}_sha256") != hashlib.sha256(payload).hexdigest():
            raise workflow.WorkflowError(
                "candidate-changed", "stored run record does not bind exact published log bytes",
                affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
            )
        if record.get(f"{item['kind']}_size") != item["size"] or record.get(f"{item['kind']}_truncated") != item["truncated"]:
            raise workflow.WorkflowError(
                "candidate-changed", "stored run record does not bind log size/truncation",
                affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
            )
    exit_code = record.get("exit_code")
    if isinstance(exit_code, bool) or (exit_code is not None and not isinstance(exit_code, int)) or (
        record.get("terminal_observed") is not (exit_code is not None)
    ):
        raise workflow.WorkflowError("candidate-changed", "stored run terminal observation is inconsistent", affected=run_id, side_effect="unknown")
    incomplete = (
        record.get("started") is not True or exit_code is None
        or record.get("timed_out") is not False
        or record.get("cleanup") != "not-needed" or record.get("group_state") != "quiet"
        or record.get("acceptance_materials_before") != request.get("acceptance_materials")
        or record.get("acceptance_materials_after") != request.get("acceptance_materials")
        or (request["scope"] == "candidate" and (
            record.get("candidate_status_before") != "match" or record.get("candidate_status_after") != "match"
        ))
        or any(item["truncated"] is True for item in logs)
    )
    expected_result = "incomplete" if incomplete else ("pass" if exit_code == 0 else "fail")
    if record.get("result") != expected_result:
        raise workflow.WorkflowError("candidate-changed", "stored run result is inconsistent with its terminal facts", affected=run_id, side_effect="unknown")
    return {"evidence": checked, "run_record": record}


def _validate_run_receipt(task: Path, intent: Mapping[str, object], run_id: str) -> dict[str, Any]:
    try:
        stored, _ = workflow._json_bytes(workflow._receipt_path(task, str(intent["op_id"])))
        receipt = full_protocol.validate_operation_receipt(stored, intent)
    except (workflow.WorkflowError, full_protocol.ProtocolValidationError) as error:
        raise workflow.WorkflowError(
            "execution-incomplete", f"run operation receipt is invalid: {error}", affected=run_id,
            side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    if (
        receipt["outcome"] != "success" or receipt["side_effect"] != "durable"
        or receipt["actual_output_ids"] != _run_output_ids(run_id)
        or receipt["state_version_before"] != intent["expected_state_version"]
        or receipt["state_version_after"] != intent["expected_state_version"]
    ):
        raise workflow.WorkflowError(
            "candidate-changed", "run receipt does not bind the complete five-output transaction",
            affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    return receipt


def _process_group_state(process_group_id: int) -> str:
    try:
        os.killpg(process_group_id, 0)
        return "live"
    except ProcessLookupError:
        return "quiet"
    except PermissionError:
        return "unknown"
    except OSError:
        return "unknown"


def _wait_for_group(process_group_id: int, deadline: float) -> str:
    state = _process_group_state(process_group_id)
    while state != "quiet" and time.monotonic() < deadline:
        time.sleep(0.01)
        state = _process_group_state(process_group_id)
    return state


def _terminate_process_group(process: subprocess.Popen[bytes], process_group_id: int) -> tuple[int | None, str, str]:
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except (PermissionError, OSError):
        return process.poll(), "unknown", _process_group_state(process_group_id)
    try:
        exit_code = process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        exit_code = process.poll()
    group_state = _process_group_state(process_group_id)
    if group_state == "live":
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            group_state = "quiet"
        except (PermissionError, OSError):
            return exit_code, "unknown", _process_group_state(process_group_id)
        else:
            group_state = _wait_for_group(process_group_id, time.monotonic() + 1.0)
    try:
        exit_code = process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        exit_code = process.poll()
    if group_state in {"live", "unknown"}:
        group_state = _wait_for_group(process_group_id, time.monotonic() + 0.5)
    return exit_code, "terminated" if group_state == "quiet" else "unknown", group_state


def execute_check(
    task_dir: Path | str, *, run_id: str, check_key: str, subject_id: str,
    argv_suffix: list[str] | None = None,
    candidate_manifest_path: Path | str | None = None,
    candidate_bridge_path: Path | str | None = None,
    challenge_request: Mapping[str, object] | None = None,
    log_limit: int = DEFAULT_LOG_LIMIT,
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    records = workflow.read_task(task)
    contract = records["contract"]
    try:
        run_id = full_protocol.canonical_component(run_id, "run ID")
    except full_protocol.ProtocolValidationError as error:
        raise workflow.WorkflowError("invalid-input", str(error), affected=str(run_id)) from error
    if not isinstance(subject_id, str) or not subject_id:
        raise workflow.WorkflowError("invalid-input", "evidence subject is invalid", affected=run_id)
    if isinstance(log_limit, bool) or not isinstance(log_limit, int) or log_limit < 1 or log_limit > 4 * 1024 * 1024:
        raise workflow.WorkflowError("invalid-input", "log limit is invalid", affected=run_id)
    new_probe = check_key == "__new_probe__"
    checked_request: dict[str, Any] | None = None
    if new_probe:
        if challenge_request is None:
            raise workflow.WorkflowError("missing-evidence", "new probe requires a prepared request", affected=run_id)
        try:
            checked_request = full_protocol.validate_challenge_request(challenge_request, contract)
        except full_protocol.ProtocolValidationError as error:
            raise workflow.WorkflowError("invalid-input", f"new probe request is invalid: {error}", affected=run_id) from error
        probe = checked_request.get("probe")
        assert isinstance(probe, Mapping)
        source = task / str(probe["source_path"])
        source_bytes = workflow._regular_bytes(source)
        if hashlib.sha256(source_bytes).hexdigest() != probe["source_sha256"]:
            raise workflow.WorkflowError("candidate-changed", "registered probe source bytes drifted", affected=run_id)
        if argv_suffix:
            raise workflow.WorkflowError("scope-conflict", "registered probe does not accept argv suffixes", affected=run_id)
        check = workflow.registered_probe_check(task, checked_request, contract)
        argv, cwd, timeout = list(probe["argv"]), task, int(probe["timeout_seconds"])
    else:
        candidate_cwd = workflow.candidate_check_cwd(task, contract.get("checks", {}).get(check_key, {}), subject_id)
        check, argv, cwd, timeout = _validate_check(contract, check_key, list(argv_suffix or []), candidate_cwd=candidate_cwd)
    if check.get("stage_key") is not None:
        stage = records["state"]["stage_status"].get("stage_key")
        if candidate_bridge_path is not None:
            index, _ = workflow._json_bytes(Path(candidate_bridge_path).parent / "I.json")
            stage = index.get("stage_key")
        if stage != check["stage_key"]:
            raise workflow.WorkflowError("scope-conflict", "check belongs to another stage", affected=check_key)
    environment = _declared_environment(contract["environment_policy"])
    if new_probe:
        names = checked_request["probe"]["environment"]
        if any(name not in environment for name in names):
            raise workflow.WorkflowError("runtime-unavailable", "probe requests an undeclared environment value", affected=run_id)
        environment = {name: environment[name] for name in names}
    materials_before = _effective_materials(check, argv, cwd, staged=contract["protocol"] == full_protocol.STAGED_PROTOCOL_VERSION)
    scope = check["scope"]
    candidate_before: dict[str, object] | None = None
    manifest_hash: str | None = None
    bridge: dict[str, Any] | None = None
    manifest_path: Path | None = None
    if scope == "candidate":
        if candidate_manifest_path is None or candidate_bridge_path is None:
            raise workflow.WorkflowError(
                "missing-evidence", "candidate check requires manifest and CB",
                affected=run_id,
            )
        manifest_path = Path(candidate_manifest_path).absolute()
        manifest, candidate_before, manifest_bytes = _candidate_receipt(manifest_path)
        if candidate_before["status"] != "match":
            raise workflow.WorkflowError(
                "candidate-changed", "candidate changed before check start",
                affected=subject_id, recovery="create-a-new-candidate",
            )
        _require_candidate_bound_materials(manifest, materials_before)
        bridge, _ = workflow._json_bytes(Path(candidate_bridge_path).absolute())
        if (
            bridge.get("bridge_id") != subject_id
            or bridge.get("candidate_id") != manifest["candidate_id"]
            or bridge.get("manifest_candidate_id") != manifest["candidate_id"]
        ):
            raise workflow.WorkflowError(
                "candidate-changed", "candidate check CB/manifest relationship is invalid",
                affected=subject_id,
            )
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        if check.get("final_candidate_verify") is True:
            current = records["state"]["current_ids"]
            if (
                records["state"]["stage_status"].get("review_status") != "reviewed-awaiting-final-accept"
                or current.get("candidate_binding") != bridge.get("bridge_id")
                or not current.get("review_packet") or not current.get("verdict")
            ):
                raise workflow.WorkflowError(
                    "review-invalid", "final candidate verification requires the current reviewed P/CB/V",
                    affected=run_id, recovery="complete-a-fresh-reviewed-packet-before-final-verification",
                )
    if scope == "challenge":
        if challenge_request is None:
            raise workflow.WorkflowError("missing-evidence", "challenge check requires a request", affected=run_id)
        if checked_request is None:
            try:
                checked_request = full_protocol.validate_challenge_request(challenge_request, contract)
            except full_protocol.ProtocolValidationError as error:
                raise workflow.WorkflowError(
                    "invalid-input", f"challenge request is invalid: {error}", affected=run_id
                ) from error
        if checked_request["check_key"] != check_key or subject_id != f"{checked_request['packet_id']}:{checked_request['candidate_bridge_id']}":
            raise workflow.WorkflowError(
                "scope-conflict", "challenge check subject/request mismatch", affected=run_id
            )
        if list(checked_request.get("argv_suffix", [])) != list(argv_suffix or []):
            raise workflow.WorkflowError("scope-conflict", "challenge argv suffix differs from its request", affected=run_id)
        _require_completed_prepare(task, checked_request, contract, affected=run_id)
    request = {
        "run_id": run_id,
        "contract_digest": contract["contract_digest"],
        "check_key": check_key,
        "check": dict(check),
        "scope": scope,
        "subject_id": subject_id,
        "argv": argv,
        "cwd": os.fspath(cwd),
        "timeout_seconds": timeout,
        "environment_identity": _environment_identity(contract["environment_policy"], environment),
        "harness_identity": _harness_identity(check, argv, materials_before),
        "acceptance_materials": materials_before,
        "runtime_identity": _runtime_identity(),
        "candidate_id": None if candidate_before is None else candidate_before["candidate_id"],
        "manifest_sha256": manifest_hash,
        "challenge_request_digest": None if checked_request is None else checked_request["request_digest"],
        "challenge_request_id": None if checked_request is None else checked_request["request_id"],
        "log_limit": log_limit,
    }
    if new_probe:
        request["probe_source_sha256"] = checked_request["probe"]["source_sha256"]
        request["sandbox"] = workflow.probe_sandbox(task, run_id, check, contract)
    request_digest = full_protocol.canonical_digest(request)
    intent_path = task / "operation-intent" / f"{run_id}.json"
    if intent_path.exists() or intent_path.is_symlink():
        existing_intent, _ = workflow._json_bytes(intent_path)
        expected_version = existing_intent.get("expected_state_version")
        if existing_intent.get("request_digest") != request_digest:
            raise workflow.WorkflowError(
                "scope-conflict", "run ID was reused with a different request",
                affected=run_id, recovery="use-a-new-run-id",
            )
    else:
        expected_version = records["state"]["version"]
    output_paths = _run_paths(task, run_id)
    directory = output_paths["request"].parent
    intent = {
        "record_type": "operation-intent",
        "op_id": run_id,
        "command_kind": "run-check",
        "request_digest": request_digest,
        "contract_digest": contract["contract_digest"],
        "expected_state_version": expected_version,
        "planned_output_types": list(output_paths),
        "planned_output_paths": [os.fspath(path) for path in output_paths.values()],
    }
    creator = workflow.begin_creator_operation(task, intent)
    if not creator:
        output = None
        if all(path.exists() and not path.is_symlink() for path in output_paths.values()):
            output = _validate_run_outputs(task, run_id, contract, request)
        if output is None:
            raise workflow.WorkflowError(
                "execution-incomplete", "prior run has no complete terminal evidence",
                affected=run_id, side_effect="unknown",
                recovery="use-a-new-run-id-after-root-reconciliation",
            )
        receipt_path = workflow._receipt_path(task, run_id)
        if receipt_path.exists() or receipt_path.is_symlink():
            receipt = _validate_run_receipt(task, intent, run_id)
        else:
            receipt = workflow.publish_operation_receipt(
                task,
                workflow._operation_receipt(
                    intent, outcome="success", side_effect="durable",
                    actual_output_ids=_run_output_ids(run_id),
                    state_before=expected_version, state_after=expected_version,
                ),
            )
        output["receipt"] = receipt
        return output

    workflow.publish_task_path_json(task, output_paths["request"], request)

    stdout_raw = directory / ".stdout.raw"
    stderr_raw = directory / ".stderr.raw"
    started = False
    timed_out = False
    cleanup = "not-started"
    group_state = "not-started"
    exit_code: int | None = None
    start_ns = time.monotonic_ns()
    process: subprocess.Popen[bytes] | None = None
    try:
        stdout_fd = workflow.open_task_private_file(task, ["runs", run_id, ".stdout.raw"])
        stderr_fd = workflow.open_task_private_file(task, ["runs", run_id, ".stderr.raw"])
        with os.fdopen(stdout_fd, "wb") as stdout_handle, os.fdopen(stderr_fd, "wb") as stderr_handle:
            try:
                run_argv = argv
                if new_probe:
                    probe_dir = directory / "probe-write"
                    probe_dir.mkdir(mode=0o700, exist_ok=True)
                    run_argv = request["sandbox"]["executed_argv"]
                process = subprocess.Popen(
                    run_argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                    stdout=stdout_handle, stderr=stderr_handle, start_new_session=True,
                )
            except OSError:
                cleanup = "not-started"
            else:
                started = True
                try:
                    exit_code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                if timed_out:
                    exit_code, cleanup, group_state = _terminate_process_group(process, process.pid)
                else:
                    group_state = _process_group_state(process.pid)
                    if group_state == "quiet":
                        cleanup = "not-needed"
                    else:
                        exit_code, cleanup, group_state = _terminate_process_group(process, process.pid)
    finally:
        end_ns = time.monotonic_ns()
    stdout_all = workflow.read_task_path_bytes(task, ["runs", run_id, ".stdout.raw"])
    stderr_all = workflow.read_task_path_bytes(task, ["runs", run_id, ".stderr.raw"])
    stdout = stdout_all[:log_limit]
    stderr = stderr_all[:log_limit]
    candidate_after: dict[str, object] | None = None
    if scope == "candidate" and manifest_path is not None:
        _, candidate_after, _ = _candidate_receipt(manifest_path)
    try:
        materials_after = _effective_materials(check, argv, cwd, staged=contract["protocol"] == full_protocol.STAGED_PROTOCOL_VERSION)
    except workflow.WorkflowError:
        materials_after = []
    if not started or timed_out or cleanup != "not-needed" or group_state != "quiet" or materials_before != materials_after or (candidate_after is not None and candidate_after["status"] != "match") or len(stdout_all) > log_limit or len(stderr_all) > log_limit:
        result = "incomplete"
    elif exit_code == 0:
        result = "pass"
    else:
        result = "fail"
    evidence = {
        "record_type": "E",
        "evidence_id": f"E-{run_id}",
        "contract_digest": contract["contract_digest"],
        "scope": scope,
        "subject_id": subject_id,
        "check_key": check_key,
        "harness_identity": request["harness_identity"],
        "environment_identity": request["environment_identity"],
        "runtime_identity": request["runtime_identity"],
        "run_request_digest": request_digest,
        "result": result,
        "logs": [
            {"kind": "stdout", "path": os.fspath(output_paths["stdout"]), "sha256": hashlib.sha256(stdout).hexdigest(), "size": len(stdout_all), "truncated": len(stdout_all) > log_limit},
            {"kind": "stderr", "path": os.fspath(output_paths["stderr"]), "sha256": hashlib.sha256(stderr).hexdigest(), "size": len(stderr_all), "truncated": len(stderr_all) > log_limit},
        ],
    }
    if checked_request is not None:
        evidence["challenge_request_id"] = checked_request["request_id"]
        evidence["challenge_request_digest"] = checked_request["request_digest"]
    if check.get("final_candidate_verify") is True:
        assert candidate_before is not None
        receipt_digest = full_protocol.canonical_digest(candidate_before)
        evidence.update({
            "phase": "final-candidate-verify",
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "sequence": records["state"]["version"],
            "candidate_verify_receipt_id": receipt_digest,
            "candidate_verify_receipt_digest": receipt_digest,
        })
    evidence["evidence_digest"] = full_protocol.canonical_digest(evidence)
    try:
        checked_evidence = full_protocol.validate_evidence(evidence, contract, scope, subject_id)
    except full_protocol.ProtocolValidationError as error:
        raise workflow.WorkflowError(
            "execution-incomplete", f"generated evidence is invalid: {error}",
            affected=run_id, side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    run_record = {
        "run_id": run_id,
        "request": request,
        "request_digest": request_digest,
        "started": started,
        "terminal_observed": exit_code is not None,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "cleanup": cleanup,
        "group_state": group_state,
        "result": result,
        "elapsed_ns": end_ns - start_ns,
        "stdout_size": len(stdout_all),
        "stderr_size": len(stderr_all),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_truncated": len(stdout_all) > log_limit,
        "stderr_truncated": len(stderr_all) > log_limit,
        "acceptance_materials_before": materials_before,
        "acceptance_materials_after": materials_after,
        "candidate_status_before": None if candidate_before is None else candidate_before["status"],
        "candidate_status_after": None if candidate_after is None else candidate_after["status"],
        "final_candidate_verify": check.get("final_candidate_verify") is True,
        "argv": argv,
        "cwd": os.fspath(cwd),
    }
    if new_probe:
        run_record["executed_argv"] = request["sandbox"]["executed_argv"]
    workflow.publish_task_path_bytes(task, output_paths["stdout"], stdout)
    workflow.publish_task_path_bytes(task, output_paths["stderr"], stderr)
    workflow.publish_task_path_json(task, output_paths["run-record"], run_record)
    workflow.publish_task_path_json(task, output_paths["E"], checked_evidence)
    receipt = workflow.publish_operation_receipt(
        task,
        workflow._operation_receipt(
            intent, outcome="success", side_effect="durable",
            actual_output_ids=_run_output_ids(run_id),
            state_before=expected_version, state_after=expected_version,
        ),
    )
    try:
        stdout_raw.unlink()
        stderr_raw.unlink()
    except FileNotFoundError:
        pass
    return {"evidence": checked_evidence, "run_record": run_record, "receipt": receipt}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run one predeclared full-route check")
    result.add_argument("--task-dir", required=True)
    result.add_argument("--run-id", required=True)
    result.add_argument("--check-key", required=True)
    result.add_argument("--subject-id", required=True)
    result.add_argument("--candidate-manifest")
    result.add_argument("--candidate-bridge")
    result.add_argument("--challenge-request")
    result.add_argument("--arg", action="append", default=[])
    result.add_argument("--log-limit", type=int, default=DEFAULT_LOG_LIMIT)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        challenge = None
        if arguments.challenge_request:
            challenge, _ = workflow._json_bytes(Path(arguments.challenge_request).absolute())
        output = execute_check(
            arguments.task_dir, run_id=arguments.run_id, check_key=arguments.check_key,
            subject_id=arguments.subject_id, argv_suffix=arguments.arg,
            candidate_manifest_path=arguments.candidate_manifest,
            candidate_bridge_path=arguments.candidate_bridge,
            challenge_request=challenge, log_limit=arguments.log_limit,
        )
        print(json.dumps(output, sort_keys=True))
        return 0
    except workflow.WorkflowError as error:
        print(json.dumps(error.as_dict(), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
