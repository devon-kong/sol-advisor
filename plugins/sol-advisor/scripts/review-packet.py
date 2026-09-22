#!/usr/bin/env python3
"""Publish and validate full-route review packets, challenges, and verdicts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import full_protocol
import workflow


def _protocol_error(
    error: Exception, *, category: str, affected: str, recovery: str,
) -> workflow.WorkflowError:
    return workflow.WorkflowError(
        category, str(error), affected=affected, recovery=recovery
    )


def _require_current_relationship(context: full_protocol.RelationshipContext, *, affected: str) -> None:
    try:
        workflow._require_current_candidate(
            context.manifest, context.candidate_verify_receipt, affected=affected
        )
        full_protocol.validate_candidate_bridge(context.candidate_bridge, context=context)
    except workflow.WorkflowError:
        raise
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="candidate-changed", affected=affected,
            recovery="reassemble-and-reverify-candidate",
        ) from error


def _require_persisted_evidence(
    task: Path, evidence: Mapping[str, object], *, affected: str,
) -> None:
    """Compatibility wrapper for the shared task-side provenance guard."""
    return workflow.require_persisted_run_evidence(task, evidence, affected=affected)


def _bundle_request(
    context: full_protocol.RelationshipContext,
    candidate_evidence: list[Mapping[str, object]],
    expected_coverage: list[str],
    predecessor_verdicts: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    return {
        "relationship": workflow._relationship_identity(context),
        "candidate_evidence": [full_protocol.canonical_digest(item) for item in candidate_evidence],
        "expected_coverage": expected_coverage,
        "predecessor_verdicts": {
            key: full_protocol.canonical_digest(value)
            for key, value in sorted(predecessor_verdicts.items())
        },
    }


def inspect_task(task_dir: Path | str) -> dict[str, Any]:
    """Read task state only after P2 review contexts bind their stored ancestry."""

    task = Path(task_dir).absolute()
    records = workflow.read_task(task)
    if records["contract"].get("protocol") != full_protocol.STAGED_PROTOCOL_VERSION:
        return records
    for path in (task / "reviews").glob("*/context.json"):
        context, _ = workflow._json_bytes(path)
        packet = context.get("packet")
        predecessors = context.get("predecessor_verdicts")
        if not isinstance(packet, Mapping) or not isinstance(predecessors, Mapping):
            raise workflow.WorkflowError(
                "review-invalid", "stored P2 review context lacks predecessor provenance",
                affected=os.fspath(path), recovery="preserve-and-root-reconcile",
            )
        try:
            closure = full_protocol._validate_predecessor_closure(
                list(packet["rejection_roots"]), predecessors,
            )
        except (KeyError, TypeError, full_protocol.ProtocolValidationError) as error:
            raise _protocol_error(
                error, category="review-invalid", affected=os.fspath(path),
                recovery="preserve-and-root-reconcile",
            ) from error
        workflow.require_persisted_p2_predecessor_closure(
            task, contract=records["contract"], closure=closure,
            predecessor_verdicts=predecessors, affected=os.fspath(path),
        )
    return records


def bundle_review_packet(
    task_dir: Path | str, *, op_id: str, expected_state_version: int,
    context: full_protocol.RelationshipContext,
    candidate_evidence: list[Mapping[str, object]],
    expected_coverage: list[str],
    predecessor_verdicts: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    records = workflow.read_task(task)
    contract = records["contract"]
    state = records["state"]
    if context.task_contract != contract:
        raise workflow.WorkflowError(
            "candidate-changed", "packet context uses another task contract", affected=op_id
        )
    if not candidate_evidence and contract["protocol"] != full_protocol.STAGED_PROTOCOL_VERSION:
        raise workflow.WorkflowError(
            "missing-evidence", "review packet has no candidate evidence", affected=op_id
        )
    evidence_ids: set[str] = set()
    check_keys: set[str] = set()
    for item in candidate_evidence:
        _require_persisted_evidence(task, item, affected=op_id)
        try:
            checked = full_protocol.validate_evidence(
                item, contract, "candidate", context.candidate_bridge["bridge_id"]
            )
        except full_protocol.ProtocolValidationError as error:
            raise _protocol_error(
                error, category="missing-evidence", affected=op_id,
                recovery="run-the-required-candidate-checks",
            ) from error
        if contract.get("protocol") == full_protocol.STAGED_PROTOCOL_VERSION and contract["checks"][checked["check_key"]].get("phase") != "pre-review":
            raise workflow.WorkflowError(
                "missing-evidence", "pre-ship evidence must remain outside the immutable review packet",
                affected=checked["evidence_id"], recovery="run-it-after-critical-challenge-in-the-same-review-context",
            )
        if checked["result"] != "pass":
            raise workflow.WorkflowError(
                "missing-evidence", "complete packet requires passing candidate evidence",
                affected=checked["evidence_id"], recovery="repair-and-rerun-check",
            )
        if checked["evidence_id"] in evidence_ids or checked["check_key"] in check_keys:
            raise workflow.WorkflowError(
                "missing-evidence", "candidate evidence IDs/checks must be unique",
                affected=op_id,
            )
        evidence_ids.add(checked["evidence_id"])
        check_keys.add(checked["check_key"])
    _require_current_relationship(context, affected=op_id)
    existing_intent_path = task / "operation-intent" / f"{op_id}.json"
    if not (existing_intent_path.exists() or existing_intent_path.is_symlink()) and state["version"] != expected_state_version:
        raise workflow.WorkflowError(
            "stale-baseline", "bundle expected state is stale", affected=op_id,
            recovery="reload-state-and-create-a-new-operation",
        )
    if (
        state["current_ids"].get("assembly_index") != context.assembly.get("assembly_id")
        or state["current_ids"].get("candidate_binding") != context.candidate_bridge.get("bridge_id")
    ):
        raise workflow.WorkflowError(
            "candidate-changed", "state does not select the packet candidate/I",
            affected=op_id,
        )
    roots = list(state["applicable_rejection_roots"])
    try:
        closure = full_protocol._validate_predecessor_closure(roots, predecessor_verdicts)
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="missing-evidence", affected=op_id,
            recovery="supply-the-complete-predecessor-verdict-closure",
        ) from error
    workflow.require_persisted_p2_predecessor_closure(
        task, contract=contract, closure=closure,
        predecessor_verdicts=predecessor_verdicts, affected=op_id,
    )
    packet_id = f"P-{op_id}"
    packet = {
        "record_type": "P",
        "packet_id": packet_id,
        "contract_digest": contract["contract_digest"],
        "candidate_bridge_id": context.candidate_bridge["bridge_id"],
        "assembly_id": context.assembly["assembly_id"],
        "delivery_ids": list(context.assembly["delivery_ids"]),
        "candidate_evidence_ids": sorted(evidence_ids),
        "coverage": {
            "complete": True,
            "checks": sorted(check_keys),
            "required_scopes": list(contract["required_coverage"]),
        },
        "rejection_roots": roots,
        "rejection_closure": closure,
    }
    if contract.get("protocol") == full_protocol.STAGED_PROTOCOL_VERSION:
        packet.update(stage_key=context.assembly["stage_key"], review_scope=context.assembly["review_scope"])
    relationship = replace(
        context,
        packet=packet,
        candidate_evidence=list(candidate_evidence),
        applicable_rejection_roots=roots,
        predecessor_verdicts=dict(predecessor_verdicts),
        expected_coverage=list(expected_coverage),
    )
    try:
        checked_packet = full_protocol.validate_review_packet(packet, context=relationship)
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="missing-evidence", affected=op_id,
            recovery="complete-packet-inputs-before-review",
        ) from error
    request_digest = full_protocol.canonical_digest(
        _bundle_request(context, candidate_evidence, expected_coverage, predecessor_verdicts)
    )
    directory = task / "review-packets" / packet_id
    output_paths = {"P": directory / "P.json"}
    for index, item in enumerate(candidate_evidence):
        output_paths[f"candidate-E-{index}"] = directory / "candidate-evidence" / f"{item['evidence_id']}.json"
    intent = {
        "record_type": "operation-intent", "op_id": op_id, "command_kind": "bundle",
        "request_digest": request_digest, "contract_digest": contract["contract_digest"],
        "expected_state_version": expected_state_version,
        "planned_output_types": list(output_paths),
        "planned_output_paths": [os.fspath(path) for path in output_paths.values()],
    }
    status, completed = workflow._operation_status(task, intent)
    if completed is not None:
        return {"packet": checked_packet, "context": relationship, "receipt": completed}
    payloads = {"P": full_protocol.canonical_json_bytes(checked_packet)}
    for index, item in enumerate(candidate_evidence):
        payloads[f"candidate-E-{index}"] = full_protocol.canonical_json_bytes(item)
    existing = [path.exists() or path.is_symlink() for path in output_paths.values()]
    if status == "recover":
        if not all(existing):
            receipt = workflow.publish_operation_receipt(
                task,
                workflow._operation_receipt(
                    intent, outcome="ambiguous" if any(existing) else "failure",
                    side_effect="unknown" if any(existing) else "none", actual_output_ids=[],
                    state_before=expected_state_version, state_after=expected_state_version,
                ),
            )
            raise workflow.WorkflowError(
                "execution-incomplete", "packet publication was incomplete",
                affected=op_id, side_effect=receipt["side_effect"],
                recovery="use-a-new-operation-after-root-reconciliation",
            )
        for key, path in output_paths.items():
            if workflow._regular_bytes(path, category="candidate-changed") != payloads[key]:
                raise workflow.WorkflowError(
                    "candidate-changed", "packet output drifted", affected=os.fspath(path),
                    side_effect="unknown", recovery="preserve-and-root-reconcile",
                )
    else:
        for key, path in output_paths.items():
            workflow.publish_task_path_bytes(task, path, payloads[key])
    current = workflow.read_task(task)["state"]
    current_ids = dict(current["current_ids"], review_packet=packet_id)
    stage_status = dict(current["stage_status"], status="reviewing", review_status="reviewing")
    updates = {
        "current_ids": current_ids,
        "stage_status": stage_status,
        "last_operation_receipt": op_id,
    }
    if current["version"] == expected_state_version:
        try:
            workflow.update_state_cas(task, expected_version=expected_state_version, updates=updates)
        except workflow.WorkflowError:
            observed = workflow.read_task(task)["state"]["version"]
            receipt = workflow.publish_operation_receipt(
                task,
                workflow._operation_receipt(
                    intent, outcome="ambiguous", side_effect="unknown",
                    actual_output_ids=[packet_id, *sorted(evidence_ids)],
                    state_before=expected_state_version, state_after=observed,
                ),
            )
            return {"packet": checked_packet, "context": relationship, "receipt": receipt}
    elif not (
        current["version"] == expected_state_version + 1
        and current["last_operation_receipt"] == op_id
        and current["current_ids"].get("review_packet") == packet_id
    ):
        receipt = workflow.publish_operation_receipt(
            task,
            workflow._operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown",
                actual_output_ids=[packet_id, *sorted(evidence_ids)],
                state_before=expected_state_version, state_after=current["version"],
            ),
        )
        return {"packet": checked_packet, "context": relationship, "receipt": receipt}
    receipt = workflow.publish_operation_receipt(
        task,
        workflow._operation_receipt(
            intent, outcome="success", side_effect="durable",
            actual_output_ids=[packet_id, *sorted(evidence_ids)],
            state_before=expected_state_version, state_after=expected_state_version + 1,
        ),
    )
    return {"packet": checked_packet, "context": relationship, "receipt": receipt}


def _challenge_operation_id(kind: str, request_id: str) -> str:
    """Keep the prepare and CR journals disjoint from each other and the run ID."""
    return f"{kind}-{workflow._task_component(request_id, 'challenge request ID')}"


def _challenge_intent(
    *, task: Path, request: Mapping[str, object], kind: str,
    output_type: str, output_path: Path, request_material: Mapping[str, object],
    expected_state_version: int,
) -> dict[str, object]:
    op_id = _challenge_operation_id(kind, str(request["request_id"]))
    return {
        "record_type": "operation-intent", "op_id": op_id, "command_kind": kind,
        "request_digest": full_protocol.canonical_digest(request_material),
        "contract_digest": request["contract_digest"],
        "expected_state_version": expected_state_version,
        "planned_output_types": [output_type],
        "planned_output_paths": [os.fspath(output_path)],
    }


def _challenge_paths(task: Path, request_id: str) -> tuple[Path, Path]:
    component = workflow._task_component(request_id, "challenge request ID")
    directory = task / "challenges" / component
    return directory, directory / "request.json"


def _require_exact_json(path: Path, expected: Mapping[str, object], *, affected: str) -> dict[str, Any]:
    try:
        observed, raw = workflow._json_bytes(path)
    except workflow.WorkflowError as error:
        raise workflow.WorkflowError(
            "missing-evidence", f"required challenge transaction output is unavailable: {error}",
            affected=affected, recovery="preserve-and-root-reconcile",
        ) from error
    if raw != full_protocol.canonical_json_bytes(expected) or observed != dict(expected):
        raise workflow.WorkflowError(
            "candidate-changed", "challenge transaction output drifted", affected=affected,
            side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    return observed


def _validate_single_output_receipt(
    task: Path, intent: Mapping[str, object], *, output_id: str, affected: str,
) -> dict[str, Any]:
    try:
        receipt, _ = workflow._json_bytes(workflow._receipt_path(task, str(intent["op_id"])))
        checked = full_protocol.validate_operation_receipt(receipt, intent)
    except (workflow.WorkflowError, full_protocol.ProtocolValidationError) as error:
        raise workflow.WorkflowError(
            "missing-evidence", f"challenge transaction receipt is invalid: {error}",
            affected=affected, recovery="preserve-and-root-reconcile",
        ) from error
    if (
        checked["outcome"] != "success" or checked["side_effect"] != "durable"
        or checked["actual_output_ids"] != [output_id]
        or checked["state_version_before"] != intent["expected_state_version"]
        or checked["state_version_after"] != intent["expected_state_version"]
    ):
        raise workflow.WorkflowError(
            "execution-incomplete", "challenge transaction receipt does not prove its sole output",
            affected=affected, side_effect="unknown", recovery="preserve-and-root-reconcile",
        )
    return checked


def _single_output_challenge_transaction(
    task: Path, *, intent: Mapping[str, object], output_path: Path,
    output: Mapping[str, object], output_id: str, affected: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create one business output, or only finish an exact prior output's receipt."""
    intent_path = workflow._intent_path(task, str(intent["op_id"]))
    receipt_path = workflow._receipt_path(task, str(intent["op_id"]))
    output_exists = output_path.exists() or output_path.is_symlink()
    intent_exists = intent_path.exists() or intent_path.is_symlink()
    receipt_exists = receipt_path.exists() or receipt_path.is_symlink()
    if not intent_exists and (output_exists or receipt_exists):
        raise workflow.WorkflowError(
            "execution-incomplete", "challenge transaction has output or receipt without intent",
            affected=affected, side_effect="unknown", recovery="use-a-new-request-id-after-root-reconciliation",
        )

    creator = workflow.begin_creator_operation(task, intent)
    if creator:
        if output_path.exists() or output_path.is_symlink() or receipt_path.exists() or receipt_path.is_symlink():
            raise workflow.WorkflowError(
                "execution-incomplete", "challenge transaction changed during creator admission",
                affected=affected, side_effect="unknown", recovery="preserve-and-root-reconcile",
            )
        workflow.publish_task_path_json(task, output_path, output)
    else:
        try:
            existing_intent, _ = workflow._json_bytes(intent_path)
            full_protocol.assert_same_operation(existing_intent, intent)
        except (workflow.WorkflowError, full_protocol.ProtocolValidationError) as error:
            raise workflow.WorkflowError(
                "scope-conflict", f"existing challenge operation differs: {error}", affected=affected,
                recovery="use-a-new-request-id",
            ) from error
        if not (output_path.exists() or output_path.is_symlink()):
            raise workflow.WorkflowError(
                "execution-incomplete", "challenge transaction is intent-only and cannot be replayed",
                affected=affected, side_effect="unknown", recovery="use-a-new-request-id-after-root-reconciliation",
            )
        _require_exact_json(output_path, output, affected=affected)

    if receipt_path.exists() or receipt_path.is_symlink():
        return _require_exact_json(output_path, output, affected=affected), _validate_single_output_receipt(
            task, intent, output_id=output_id, affected=affected,
        )
    _require_exact_json(output_path, output, affected=affected)
    receipt = workflow.publish_operation_receipt(
        task,
        workflow._operation_receipt(
            intent, outcome="success", side_effect="durable", actual_output_ids=[output_id],
            state_before=intent["expected_state_version"], state_after=intent["expected_state_version"],
        ),
    )
    return dict(output), receipt


def _challenge_prerequisites(
    task: Path, relationship: full_protocol.RelationshipContext, *, affected: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = workflow.read_task(task)
    if relationship.task_contract != records["contract"]:
        raise workflow.WorkflowError(
            "candidate-changed", "challenge relationship uses another task contract", affected=affected,
            recovery="reload-current-task-relationship",
        )
    _require_current_relationship(relationship, affected=affected)
    try:
        packet = full_protocol.validate_relationship_context(relationship, target="packet")
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="review-invalid", affected=affected, recovery="rebuild-the-review-packet",
        ) from error
    packet_path = task / "review-packets" / workflow._task_component(packet["packet_id"], "packet ID") / "P.json"
    _require_exact_json(packet_path, packet, affected=affected)
    state = records["state"]
    if (
        state["current_ids"].get("review_packet") != packet["packet_id"]
        or state["current_ids"].get("candidate_binding") != relationship.candidate_bridge["bridge_id"]
    ):
        raise workflow.WorkflowError(
            "candidate-changed", "challenge P/CB are no longer selected by task state", affected=affected,
            recovery="rebuild-review-packet-for-current-candidate",
        )
    return records, packet


def _prepare_challenge_intent(task: Path, request: Mapping[str, object], expected_state_version: int) -> dict[str, object]:
    _, request_path = _challenge_paths(task, str(request["request_id"]))
    return _challenge_intent(
        task=task, request=request, kind="prepare-challenge", output_type="challenge-request",
        output_path=request_path, request_material={"action": "prepare-challenge", "request": request},
        expected_state_version=expected_state_version,
    )


def prepare_challenge(
    task_dir: Path | str, *, relationship: full_protocol.RelationshipContext,
    request_id: str, check_key: str, authority_decision: str, argv_suffix: list[str] | None = None,
    probe: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    records, packet = _challenge_prerequisites(task, relationship, affected=request_id)
    request = {
        "record_type": "challenge-request", "request_id": request_id,
        "request_digest": "", "contract_digest": records["contract"]["contract_digest"],
        "packet_id": packet["packet_id"], "candidate_bridge_id": relationship.candidate_bridge["bridge_id"],
        "check_key": check_key, "authority_decision": authority_decision, "argv_suffix": list(argv_suffix or []),
    }
    if probe is not None:
        request["probe"] = dict(probe)
    request["request_digest"] = full_protocol.canonical_digest(
        {key: value for key, value in request.items() if key != "request_digest"}
    )
    try:
        checked = full_protocol.validate_challenge_request(request, records["contract"])
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="invalid-input", affected=request_id,
            recovery="use-a-predeclared-authorized-challenge-check",
        ) from error
    _, request_path = _challenge_paths(task, str(checked["request_id"]))
    intent = _prepare_challenge_intent(task, checked, records["state"]["version"])
    prepared, _ = _single_output_challenge_transaction(
        task, intent=intent, output_path=request_path, output=checked,
        output_id=checked["request_id"], affected=str(checked["request_id"]),
    )
    return prepared


def register_probe(
    task_dir: Path | str, *, relationship: full_protocol.RelationshipContext,
    request_id: str, source_bytes: bytes, timeout_seconds: int,
) -> dict[str, Any]:
    """Root-side registration for one immutable, sandboxed reviewer probe.

    This is deliberately source publication plus the existing challenge request
    transaction, not an arbitrary shell runner or a contract mutation.
    """
    task = Path(task_dir).absolute()
    records, _ = _challenge_prerequisites(task, relationship, affected=request_id)
    policy = records["contract"].get("probe_policy")
    if not isinstance(policy, Mapping):
        raise workflow.WorkflowError("invalid-input", "task contract has no new-probe policy", affected=request_id)
    component = workflow._task_component(request_id, "probe request ID")
    source_relative = f"{policy['scratch_root']}/{component}.py"
    source_path = task / source_relative
    if not isinstance(source_bytes, bytes) or not source_bytes:
        raise workflow.WorkflowError("invalid-input", "probe source must be non-empty bytes", affected=request_id)
    argv_prefix = policy["allowed_argv_prefixes"][0]
    probe = {
        "source_path": source_relative, "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "argv": [*argv_prefix, source_relative], "cwd": policy["allowed_cwd"],
        "environment": [], "timeout_seconds": timeout_seconds, "network": "forbidden",
    }
    # Reject all policy/timeout/path errors before publishing source bytes.  The
    # later prepare transaction then binds this exact already-checked payload.
    preview = {"record_type": "challenge-request", "request_id": request_id, "request_digest": "", "contract_digest": records["contract"]["contract_digest"], "packet_id": relationship.packet["packet_id"] if relationship.packet else "", "candidate_bridge_id": relationship.candidate_bridge["bridge_id"], "check_key": "__new_probe__", "authority_decision": "root-registered-probe", "argv_suffix": [], "probe": probe}
    preview["request_digest"] = full_protocol.canonical_digest({key: value for key, value in preview.items() if key != "request_digest"})
    try:
        full_protocol.validate_challenge_request(preview, records["contract"])
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(error, category="invalid-input", affected=request_id, recovery="correct-probe-policy-before-registration") from error
    workflow.publish_task_path_bytes(task, source_path, source_bytes)
    if workflow._regular_bytes(source_path, category="candidate-changed") != source_bytes:
        raise workflow.WorkflowError("candidate-changed", "registered probe source drifted", affected=request_id)
    return prepare_challenge(
        task, relationship=relationship, request_id=request_id, check_key="__new_probe__",
        authority_decision="root-registered-probe", probe=probe,
    )


def _require_completed_prepare(
    task: Path, request: Mapping[str, object], expected_state_version: int,
) -> dict[str, Any]:
    request_id = str(request["request_id"])
    _, request_path = _challenge_paths(task, request_id)
    intent = _prepare_challenge_intent(task, request, expected_state_version)
    intent_path = workflow._intent_path(task, str(intent["op_id"]))
    if not (intent_path.exists() or intent_path.is_symlink()):
        raise workflow.WorkflowError(
            "missing-evidence", "challenge prepare intent is missing", affected=request_id,
            recovery="prepare-a-new-authorized-challenge",
        )
    try:
        stored_intent, _ = workflow._json_bytes(intent_path)
        full_protocol.assert_same_operation(stored_intent, intent)
    except (workflow.WorkflowError, full_protocol.ProtocolValidationError) as error:
        raise workflow.WorkflowError(
            "candidate-changed", f"challenge prepare intent drifted: {error}", affected=request_id,
            side_effect="unknown", recovery="preserve-and-root-reconcile",
        ) from error
    _require_exact_json(request_path, request, affected=request_id)
    return _validate_single_output_receipt(task, intent, output_id=request_id, affected=request_id)


def record_challenge_evidence(
    task_dir: Path | str, *, relationship: full_protocol.RelationshipContext,
    request: Mapping[str, object], evidence: Mapping[str, object],
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    request_id = str(request.get("request_id", ""))
    records, packet = _challenge_prerequisites(task, relationship, affected=request_id)
    try:
        checked_request = full_protocol.validate_challenge_request(request, records["contract"])
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="review-invalid", affected=request_id,
            recovery="rerun-the-authorized-challenge-with-a-new-request",
        ) from error
    _, request_path = _challenge_paths(task, str(checked_request["request_id"]))
    persisted_request = _require_exact_json(request_path, checked_request, affected=request_id)
    _require_completed_prepare(task, persisted_request, records["state"]["version"])
    try:
        _require_persisted_evidence(task, evidence, affected=request_id)
        checked_evidence = full_protocol._validate_challenge_evidence(
            evidence, persisted_request, records["contract"]
        )
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="review-invalid", affected=request_id,
            recovery="rerun-the-authorized-challenge-with-a-new-request",
        ) from error
    if (
        persisted_request["packet_id"] != packet["packet_id"]
        or persisted_request["candidate_bridge_id"] != relationship.candidate_bridge["bridge_id"]
    ):
        raise workflow.WorkflowError(
            "review-invalid", "challenge request does not bind the current P/CB", affected=request_id,
        )
    if checked_evidence["evidence_id"] != f"E-challenge-{request_id}":
        raise workflow.WorkflowError(
            "review-invalid", "challenge E ID does not bind the request operation", affected=request_id,
        )
    receipt = {
        "record_type": "CR", "challenge_receipt_id": f"CR-{request_id}",
        "challenge_request_id": request_id, "packet_id": persisted_request["packet_id"],
        "candidate_bridge_id": persisted_request["candidate_bridge_id"],
        "evidence_id": checked_evidence["evidence_id"],
        "challenge_request_digest": persisted_request["request_digest"],
    }
    try:
        receipt = full_protocol.validate_challenge_receipt(receipt, persisted_request)
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="review-invalid", affected=request_id, recovery="recreate-the-challenge-receipt",
        ) from error
    directory, _ = _challenge_paths(task, request_id)
    intent = _challenge_intent(
        task=task, request=persisted_request, kind="record-challenge", output_type="CR",
        output_path=directory / "CR.json",
        request_material={
            "action": "record-challenge", "request": persisted_request,
            "evidence": checked_evidence,
        }, expected_state_version=records["state"]["version"],
    )
    stored_receipt, operation_receipt = _single_output_challenge_transaction(
        task, intent=intent, output_path=directory / "CR.json", output=receipt,
        output_id=receipt["challenge_receipt_id"], affected=request_id,
    )
    context = replace(
        relationship, challenge_request=persisted_request,
        challenge_evidence=checked_evidence, challenge_receipt=stored_receipt,
    )
    return {
        "request": persisted_request, "evidence": checked_evidence, "receipt": stored_receipt,
        "operation_receipt": operation_receipt, "context": context,
    }


def observed_reviewer_attestation(
    runtime_receipt: Mapping[str, object], review_policy: Mapping[str, object] | None = None,
    behavioral_window: Mapping[str, object] | None = None,
) -> dict[str, object]:
    required = {"thread_id", "agent_role", "model", "effort", "sandbox_policy_type"}
    allowed = required | {
        "parent_thread_id", "context_id", "agent_path", "model_provider",
        "permission_profile_type", "prompt_digest",
        "cwd", "task_id", "stage_key",
    }
    if not set(runtime_receipt).issubset(allowed):
        raise workflow.WorkflowError(
            "review-invalid", "reviewer runtime receipt contains unsupported fields",
            affected=str(runtime_receipt.get("thread_id", "reviewer")),
            recovery="use-the-redacted-native-runtime-receipt",
        )
    if not required.issubset(runtime_receipt) or any(
        not isinstance(runtime_receipt[key], str) or not runtime_receipt[key]
        for key in required
    ):
        raise workflow.WorkflowError(
            "runtime-unavailable", "reviewer runtime receipt is incomplete",
            affected="reviewer-runtime", recovery="rerun-native-runtime-inspection",
        )
    if (
        runtime_receipt["agent_role"] != "sol_advisor_sol_reviewer"
        or runtime_receipt["model"] != "gpt-5.6-sol"
        or runtime_receipt["effort"] != "high"
    ):
        raise workflow.WorkflowError(
            "review-invalid", "runtime receipt is not the required read-only Sol reviewer",
            affected=str(runtime_receipt.get("thread_id", "reviewer")),
            recovery="start-a-fresh-correct-reviewer",
        )
    legacy = {
        "context_id": runtime_receipt.get("context_id", runtime_receipt["thread_id"]),
        "thread_id": runtime_receipt["thread_id"],
        "role": runtime_receipt["agent_role"],
        "model": runtime_receipt["model"],
        "effort": runtime_receipt["effort"],
        "observed_attestation": {
            "runtime_receipt_digest": full_protocol.canonical_digest(runtime_receipt),
            "sandbox_policy_type": runtime_receipt["sandbox_policy_type"],
        },
    }
    if not review_policy or review_policy.get("review_identity_schema") not in {"SA-REVIEW-ATTESTATION-1", "SA-REVIEW-ATTESTATION-2"}:
        return legacy
    context_value = runtime_receipt.get("context_id")
    if context_value is None:
        context_id = runtime_receipt["thread_id"]
        context_source = "verified-thread-id"
    elif isinstance(context_value, str) and context_value:
        context_id = context_value
        context_source = "observed-context"
    else:
        raise workflow.WorkflowError("runtime-unavailable", "reviewer context is unavailable", affected="reviewer-runtime")
    permission_profile = runtime_receipt.get("permission_profile_type")
    prompt_digest = runtime_receipt.get("prompt_digest")
    if not isinstance(permission_profile, str) or not permission_profile or not isinstance(prompt_digest, str) or not prompt_digest:
        raise workflow.WorkflowError("runtime-unavailable", "reviewer permission or prompt fact is unavailable", affected="reviewer-runtime")
    mode = "hard-read-only" if runtime_receipt["sandbox_policy_type"] == "read-only" else "behavioral-window"
    schema = review_policy["review_identity_schema"]
    if mode == "behavioral-window" and schema == "SA-REVIEW-ATTESTATION-1":
        raise workflow.WorkflowError(
            "runtime-unavailable",
            "behavioral reviewer admission is unavailable on this host without a Root-controlled lifecycle window",
            affected=str(runtime_receipt["thread_id"]),
            recovery="use-an-observed-hard-read-only-reviewer-or-a-host-with-the-root-window-capability",
        )
    if mode == "behavioral-window":
        if behavioral_window is None:
            raise workflow.WorkflowError("runtime-unavailable", "behavioral reviewer admission requires a Root begin/end lifecycle window", affected=str(runtime_receipt["thread_id"]))
        if behavioral_window.get("context_id") != context_id or behavioral_window.get("reviewer_thread_id") != runtime_receipt["thread_id"]:
            raise workflow.WorkflowError("review-invalid", "behavioral window does not bind the observed reviewer identity", affected=str(runtime_receipt["thread_id"]))
        windows = [dict(behavioral_window)]
    else:
        windows = []
    value: dict[str, object] = {
        "schema": schema, "mode": mode,
        "reviewer": {
            "thread_id": runtime_receipt["thread_id"], "context_id": context_id,
            "context_source": context_source, "role": runtime_receipt["agent_role"],
            "model": runtime_receipt["model"], "effort": runtime_receipt["effort"],
            "runtime_receipt_digest": full_protocol.canonical_digest(runtime_receipt),
        },
        "observed": {
            "sandbox_policy_type": runtime_receipt["sandbox_policy_type"],
            "permission_profile": permission_profile, "prompt_digest": prompt_digest,
        },
        "windows": windows,
    }
    value["attestation_digest"] = full_protocol.canonical_digest(value)
    return value


def _controlled_behavioral_window(
    task: Path, relationship: full_protocol.RelationshipContext, attestation: dict[str, object],
) -> dict[str, object]:
    """Historical P1 helper retained for old fixtures; it admits no broad host."""
    if attestation.get("mode") != "behavioral-window":
        return attestation
    candidate = {"candidate_id": relationship.candidate_bridge["candidate_id"], "manifest_sha256": hashlib.sha256(relationship.manifest_bytes).hexdigest()}
    with workflow.reviewer_window(task) as observed:
        pass
    attestation["windows"] = [{"candidate_before": candidate, "candidate_after": dict(candidate), "task_tree_before": observed["before_tree_digest"], "task_tree_after": observed["after_tree_digest"]}]
    attestation["attestation_digest"] = full_protocol.canonical_digest({key: item for key, item in attestation.items() if key != "attestation_digest"})
    return attestation


def record_review(
    task_dir: Path | str, *, op_id: str, expected_state_version: int,
    relationship: full_protocol.RelationshipContext,
    verdict: Mapping[str, object], reviewer_runtime_receipt: Mapping[str, object],
    pre_ship_evidence: list[Mapping[str, object]] | None = None,
    behavioral_window_id: str | None = None,
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    records = workflow.read_task(task)
    state = records["state"]
    schema = records["contract"]["review_policy"].get("review_identity_schema")
    if schema not in {"SA-REVIEW-ATTESTATION-1", "SA-REVIEW-ATTESTATION-2"}:
        raise workflow.WorkflowError(
            "review-invalid", "legacy review policy is historical-read-only and cannot publish a new review",
            affected=op_id, recovery="create-a-tagged-hard-read-only-task-contract",
        )
    late = list(pre_ship_evidence or [])
    for evidence in [*(relationship.candidate_evidence or []), *late, *([relationship.challenge_evidence] if relationship.challenge_evidence is not None else [])]:
        _require_persisted_evidence(task, evidence, affected=op_id)
    candidate_identity = {"candidate_id": relationship.candidate_bridge["candidate_id"], "manifest_hash": relationship.candidate_bridge["manifest_hash"], "verify_receipt_digest": full_protocol.canonical_digest(relationship.candidate_verify_receipt)}
    window = None
    if behavioral_window_id is not None:
        window = workflow.end_reviewer_window(task, window_id=behavioral_window_id, candidate_identity=candidate_identity, runtime_receipt=reviewer_runtime_receipt)
    attestation = observed_reviewer_attestation(reviewer_runtime_receipt, records["contract"]["review_policy"], behavioral_window=window)
    _require_current_relationship(relationship, affected=op_id)
    try:
        roots = list(relationship.packet["rejection_roots"])
        closure = full_protocol._validate_predecessor_closure(
            roots, relationship.predecessor_verdicts or {},
        )
    except (KeyError, TypeError, full_protocol.ProtocolValidationError) as error:
        raise _protocol_error(
            error, category="review-invalid", affected=op_id,
            recovery="reload-persisted-predecessor-reviews",
        ) from error
    workflow.require_persisted_p2_predecessor_closure(
        task, contract=records["contract"], closure=closure,
        predecessor_verdicts=relationship.predecessor_verdicts or {}, affected=op_id,
    )
    if schema == "SA-REVIEW-ATTESTATION-2":
        for path in (task / "design-reviews").glob("*/DR.json"):
            design, _ = workflow._json_bytes(path)
            if design.get("contract_digest") == records["contract"]["contract_digest"] and (design.get("reviewer_thread_id") == reviewer_runtime_receipt["thread_id"] or design.get("reviewer_context_id") == attestation["reviewer"]["context_id"]):
                raise workflow.WorkflowError("review-invalid", "implementation review needs a context independent of design review", affected=op_id)
    normalized_verdict = dict(verdict)
    bound = {
        "observed_attestation_digest": full_protocol.canonical_digest(attestation),
        "reviewer_thread_id": attestation.get("reviewer", {}).get("thread_id"),
        "reviewer_context_id": attestation.get("reviewer", {}).get("context_id"),
    }
    if records["contract"]["protocol"] == full_protocol.STAGED_PROTOCOL_VERSION:
        bound.update(stage_key=relationship.packet["stage_key"], review_scope=relationship.packet["review_scope"])
    for key, value in bound.items():
        if value is not None and key in normalized_verdict and normalized_verdict[key] != value:
            raise workflow.WorkflowError("review-invalid", "review verdict conflicts with Root-observed reviewer metadata", affected=op_id)
        if value is not None:
            normalized_verdict[key] = value
    context = replace(relationship, verdict=normalized_verdict, observed_attestation=attestation, pre_ship_evidence=late)
    try:
        checked_verdict = full_protocol.validate_relationship_context(context, target="review")
        after = full_protocol.validate_record_review_transition(state, checked_verdict, context=context)
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="review-invalid", affected=op_id,
            recovery="obtain-a-fresh-valid-review-response",
        ) from error
    existing_intent_path = task / "operation-intent" / f"{op_id}.json"
    if not (existing_intent_path.exists() or existing_intent_path.is_symlink()) and state["version"] != expected_state_version:
        raise workflow.WorkflowError(
            "stale-baseline", "record-review expected state is stale", affected=op_id,
            recovery="reload-state-and-use-a-new-operation",
        )
    if (
        relationship.packet is None
        or state["current_ids"].get("review_packet") != relationship.packet["packet_id"]
        or state["current_ids"].get("candidate_binding") != relationship.candidate_bridge["bridge_id"]
    ):
        raise workflow.WorkflowError(
            "candidate-changed", "state no longer identifies the reviewed P/CB",
            affected=op_id,
        )
    request_digest = full_protocol.canonical_digest(
        {
            "relationship": workflow._relationship_identity(context),
            "verdict": full_protocol.canonical_digest(checked_verdict),
            "reviewer_runtime": full_protocol.canonical_digest(reviewer_runtime_receipt),
        }
    )
    verdict_id = checked_verdict.get("verdict_id")
    if not isinstance(verdict_id, str) or not verdict_id:
        raise workflow.WorkflowError("review-invalid", "verdict ID is missing", affected=op_id)
    directory = task / "reviews" / verdict_id
    output_paths = {"V": directory / "V.json", "reviewer-runtime": directory / "reviewer-runtime.json", "context": directory / "context.json"}
    intent = {
        "record_type": "operation-intent", "op_id": op_id, "command_kind": "record-review",
        "request_digest": request_digest, "contract_digest": records["contract"]["contract_digest"],
        "expected_state_version": expected_state_version,
        "planned_output_types": list(output_paths),
        "planned_output_paths": [os.fspath(path) for path in output_paths.values()],
    }
    status, completed = workflow._operation_status(task, intent)
    if completed is not None:
        return {"verdict": checked_verdict, "context": context, "receipt": completed}
    payloads = {
        "V": full_protocol.canonical_json_bytes(checked_verdict),
        "reviewer-runtime": full_protocol.canonical_json_bytes(reviewer_runtime_receipt),
        "context": full_protocol.canonical_json_bytes(relationship_to_package(context)),
    }
    existing = [path.exists() or path.is_symlink() for path in output_paths.values()]
    if status == "recover":
        if not all(existing):
            receipt = workflow.publish_operation_receipt(
                task,
                workflow._operation_receipt(
                    intent, outcome="ambiguous" if any(existing) else "failure",
                    side_effect="unknown" if any(existing) else "none", actual_output_ids=[],
                    state_before=expected_state_version, state_after=expected_state_version,
                ),
            )
            raise workflow.WorkflowError(
                "execution-incomplete", "review publication was incomplete", affected=op_id,
                side_effect=receipt["side_effect"], recovery="preserve-and-root-reconcile",
            )
        for key, path in output_paths.items():
            if workflow._regular_bytes(path, category="candidate-changed") != payloads[key]:
                raise workflow.WorkflowError(
                    "candidate-changed", "review output drifted", affected=os.fspath(path),
                    side_effect="unknown", recovery="preserve-and-root-reconcile",
                )
    else:
        for key, path in output_paths.items():
            workflow.publish_task_path_bytes(task, path, payloads[key])
    after["last_operation_receipt"] = op_id
    updates = {key: after[key] for key in after if key != "version"}
    current = workflow.read_task(task)["state"]
    if current["version"] == expected_state_version:
        try:
            workflow.update_state_cas(task, expected_version=expected_state_version, updates=updates)
        except workflow.WorkflowError:
            observed = workflow.read_task(task)["state"]["version"]
            receipt = workflow.publish_operation_receipt(
                task,
                workflow._operation_receipt(
                    intent, outcome="ambiguous", side_effect="unknown",
                    actual_output_ids=[verdict_id, full_protocol.canonical_digest(reviewer_runtime_receipt)],
                    state_before=expected_state_version, state_after=observed,
                ),
            )
            return {"verdict": checked_verdict, "context": context, "receipt": receipt}
    elif not (
        current["version"] == expected_state_version + 1
        and current["last_operation_receipt"] == op_id
        and (
            checked_verdict["status"] in {"unavailable", "invalid"}
            or current["current_ids"].get("verdict") == verdict_id
        )
    ):
        receipt = workflow.publish_operation_receipt(
            task,
            workflow._operation_receipt(
                intent, outcome="ambiguous", side_effect="unknown",
                actual_output_ids=[verdict_id, full_protocol.canonical_digest(reviewer_runtime_receipt)],
                state_before=expected_state_version, state_after=current["version"],
            ),
        )
        return {"verdict": checked_verdict, "context": context, "receipt": receipt}
    receipt = workflow.publish_operation_receipt(
        task,
        workflow._operation_receipt(
            intent, outcome="success", side_effect="durable",
            actual_output_ids=[verdict_id, full_protocol.canonical_digest(reviewer_runtime_receipt)],
            state_before=expected_state_version, state_after=expected_state_version + 1,
        ),
    )
    return {"verdict": checked_verdict, "context": context, "receipt": receipt}


def record_design_review(
    task_dir: Path | str, *, review: Mapping[str, object],
    reviewer_runtime_receipt: Mapping[str, object], design_input: Mapping[str, object] | None = None,
    behavioral_window_id: str | None = None,
) -> dict[str, Any]:
    task = Path(task_dir).absolute()
    records = workflow.read_task(task)
    policy = records["contract"]["review_policy"]
    if policy.get("review_identity_schema") not in {"SA-REVIEW-ATTESTATION-1", "SA-REVIEW-ATTESTATION-2"}:
        raise workflow.WorkflowError(
            "review-invalid", "legacy review policy is historical-read-only and cannot publish a new design review",
            affected=str(review.get("review_id", "DR")), recovery="create-a-tagged-hard-read-only-task-contract",
        )
    window = None
    if behavioral_window_id is not None:
        if design_input is None:
            raise workflow.WorkflowError("missing-evidence", "design observation needs its input", affected="design-input")
        window = workflow.end_reviewer_window(task, window_id=behavioral_window_id,
            candidate_identity={"design_input_digest": full_protocol.canonical_digest(dict(design_input))},
            runtime_receipt=reviewer_runtime_receipt)
    attestation = observed_reviewer_attestation(reviewer_runtime_receipt, policy, behavioral_window=window)
    review_value = dict(review)
    modern = "review_identity_schema" in policy
    input_payload: bytes | None = None
    if modern:
        if design_input is None:
            raise workflow.WorkflowError("missing-evidence", "tagged design review requires canonical design input", affected="design-input")
        input_payload = full_protocol.canonical_json_bytes(dict(design_input))
        reviewer = attestation["reviewer"]
        review_value.update({
            "design_input_digest": full_protocol.canonical_digest(dict(design_input)),
            "observed_attestation_digest": full_protocol.canonical_digest(attestation),
            "reviewer_thread_id": reviewer["thread_id"],
            "reviewer_context_id": reviewer["context_id"],
        })
    try:
        checked = full_protocol.validate_design_review(review_value)
    except full_protocol.ProtocolValidationError as error:
        raise _protocol_error(
            error, category="review-invalid", affected=str(review.get("review_id", "DR")),
            recovery="obtain-a-valid-design-only-review",
        ) from error
    if checked.get("contract_digest") != records["contract"]["contract_digest"]:
        raise workflow.WorkflowError(
            "review-invalid", "design review uses another task contract",
            affected=str(review.get("review_id", "DR")),
        )
    if modern:
        full_protocol.validate_review_attestation(attestation, records["contract"])
        reviewer = attestation["reviewer"]
        if (
            checked.get("design_input_digest") != full_protocol.canonical_digest(dict(design_input or {}))
            or checked.get("observed_attestation_digest") != full_protocol.canonical_digest(attestation)
            or checked.get("reviewer_thread_id") != reviewer["thread_id"]
            or checked.get("reviewer_context_id") != reviewer["context_id"]
        ):
            raise workflow.WorkflowError("review-invalid", "design review does not bind its tagged input and reviewer", affected=str(review.get("review_id", "DR")))
    review_id = checked.get("review_id")
    if not isinstance(review_id, str) or not review_id:
        raise workflow.WorkflowError("review-invalid", "design review ID is missing", affected="DR")
    directory = task / "design-reviews" / review_id
    output_paths = {
        "DR": directory / "DR.json",
        "reviewer-runtime": directory / "reviewer-runtime.json",
    }
    if input_payload is not None:
        output_paths["design-input"] = directory / "design-input.json"
    current_version = records["state"]["version"]
    intent = {
        "record_type": "operation-intent", "op_id": review_id,
        "command_kind": "design-review",
        "request_digest": full_protocol.canonical_digest(
            {
                "review": full_protocol.canonical_digest(checked),
                "runtime": full_protocol.canonical_digest(reviewer_runtime_receipt),
                "attestation": full_protocol.canonical_digest(attestation),
                "design_input": None if design_input is None else full_protocol.canonical_digest(dict(design_input)),
            }
        ),
        "contract_digest": records["contract"]["contract_digest"],
        "expected_state_version": current_version,
        "planned_output_types": list(output_paths),
        "planned_output_paths": [os.fspath(path) for path in output_paths.values()],
    }
    intent_path = task / "operation-intent" / f"{review_id}.json"
    if intent_path.exists() or intent_path.is_symlink():
        existing_intent, _ = workflow._json_bytes(intent_path)
        intent["expected_state_version"] = existing_intent["expected_state_version"]
    status, completed = workflow._operation_status(task, intent)
    if completed is not None:
        return checked
    payloads = {
        "DR": full_protocol.canonical_json_bytes(checked),
        "reviewer-runtime": full_protocol.canonical_json_bytes(reviewer_runtime_receipt),
    }
    if input_payload is not None:
        payloads["design-input"] = input_payload
    existing = [path.exists() or path.is_symlink() for path in output_paths.values()]
    if status == "recover" and not all(existing):
        receipt = workflow.publish_operation_receipt(
            task,
            workflow._operation_receipt(
                intent, outcome="ambiguous" if any(existing) else "failure",
                side_effect="unknown" if any(existing) else "none", actual_output_ids=[],
                state_before=intent["expected_state_version"],
                state_after=intent["expected_state_version"],
            ),
        )
        raise workflow.WorkflowError(
            "execution-incomplete", "design review publication was incomplete",
            affected=review_id, side_effect=receipt["side_effect"],
            recovery="preserve-and-root-reconcile",
        )
    for key, path in output_paths.items():
        workflow.publish_task_path_bytes(task, path, payloads[key])
    workflow.publish_operation_receipt(
        task,
        workflow._operation_receipt(
            intent, outcome="success", side_effect="durable",
            actual_output_ids=[review_id, full_protocol.canonical_digest(reviewer_runtime_receipt)],
            state_before=intent["expected_state_version"],
            state_after=intent["expected_state_version"],
        ),
    )
    return checked


def _read_json_value(path: str) -> object:
    raw = workflow._regular_bytes(Path(path).absolute())
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise workflow.WorkflowError(
            "invalid-input", f"invalid JSON input: {error}", affected=path
        ) from error


def relationship_from_package(value: object) -> full_protocol.RelationshipContext:
    if not isinstance(value, Mapping):
        raise workflow.WorkflowError(
            "invalid-input", "relationship package must be an object", affected="relationship"
        )
    required = {
        "task_contract", "candidate_bridge", "manifest", "manifest_bytes_base64",
        "candidate_verify_receipt", "assembly", "deliveries", "materials",
        "delivery_evidence",
    }
    optional = {
        "packet", "candidate_evidence", "applicable_rejection_roots",
        "predecessor_verdicts", "expected_coverage", "pre_ship_evidence", "challenge_request",
        "challenge_evidence", "challenge_receipt", "verdict", "observed_attestation",
    }
    if not required.issubset(value) or not set(value).issubset(required | optional):
        raise workflow.WorkflowError(
            "invalid-input", "relationship package fields are missing or unsupported",
            affected="relationship",
        )
    try:
        manifest_bytes = base64.b64decode(value["manifest_bytes_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise workflow.WorkflowError(
            "invalid-input", "manifest_bytes_base64 is invalid", affected="relationship"
        ) from error
    arguments = {key: value.get(key) for key in required | optional if key != "manifest_bytes_base64"}
    arguments["manifest_bytes"] = manifest_bytes
    try:
        return full_protocol.RelationshipContext(**arguments)
    except TypeError as error:
        raise workflow.WorkflowError(
            "invalid-input", f"relationship package shape is invalid: {error}",
            affected="relationship",
        ) from error


def relationship_to_package(context: full_protocol.RelationshipContext) -> dict[str, object]:
    """Canonical persisted form used by final-accept reconstruction."""
    return {
        "task_contract": context.task_contract,
        "candidate_bridge": context.candidate_bridge,
        "manifest": context.manifest,
        "manifest_bytes_base64": base64.b64encode(context.manifest_bytes).decode("ascii"),
        "candidate_verify_receipt": context.candidate_verify_receipt,
        "assembly": context.assembly,
        "deliveries": context.deliveries,
        "materials": context.materials,
        "delivery_evidence": context.delivery_evidence,
        "packet": context.packet,
        "candidate_evidence": context.candidate_evidence,
        "pre_ship_evidence": context.pre_ship_evidence,
        "applicable_rejection_roots": context.applicable_rejection_roots,
        "predecessor_verdicts": context.predecessor_verdicts,
        "expected_coverage": context.expected_coverage,
        "challenge_request": context.challenge_request,
        "challenge_evidence": context.challenge_evidence,
        "challenge_receipt": context.challenge_receipt,
        "verdict": context.verdict,
        "observed_attestation": context.observed_attestation,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build and validate full-route review records")
    commands = result.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--task-dir", required=True)
    bundle = commands.add_parser("bundle")
    bundle.add_argument("--task-dir", required=True)
    bundle.add_argument("--op-id", required=True)
    bundle.add_argument("--expected-state-version", required=True, type=int)
    bundle.add_argument("--relationship", required=True)
    bundle.add_argument("--candidate-evidence", required=True)
    bundle.add_argument("--expected-coverage", required=True)
    bundle.add_argument("--predecessor-verdicts", required=True)
    challenge = commands.add_parser("prepare-challenge")
    challenge.add_argument("--task-dir", required=True)
    challenge.add_argument("--relationship", required=True)
    challenge.add_argument("--request-id", required=True)
    challenge.add_argument("--check-key", required=True)
    challenge.add_argument("--authority-decision", required=True)
    challenge.add_argument("--arg", action="append", default=[])
    probe = commands.add_parser("register-probe")
    probe.add_argument("--task-dir", required=True)
    probe.add_argument("--relationship", required=True)
    probe.add_argument("--request-id", required=True)
    probe.add_argument("--source", required=True)
    probe.add_argument("--timeout-seconds", type=int, required=True)
    challenge_evidence = commands.add_parser("record-challenge")
    challenge_evidence.add_argument("--task-dir", required=True)
    challenge_evidence.add_argument("--relationship", required=True)
    challenge_evidence.add_argument("--request", required=True)
    challenge_evidence.add_argument("--evidence", required=True)
    review = commands.add_parser("record-review")
    review.add_argument("--task-dir", required=True)
    review.add_argument("--op-id", required=True)
    review.add_argument("--expected-state-version", required=True, type=int)
    review.add_argument("--relationship", required=True)
    review.add_argument("--verdict", required=True)
    review.add_argument("--reviewer-runtime", required=True)
    review.add_argument("--pre-ship-evidence")
    review.add_argument("--behavioral-window-id")
    window = commands.add_parser("begin-behavioral-window")
    window.add_argument("--task-dir", required=True)
    window.add_argument("--relationship", required=True)
    window.add_argument("--window-id", required=True)
    close_window = commands.add_parser("end-behavioral-window")
    close_window.add_argument("--task-dir", required=True)
    close_window.add_argument("--relationship", required=True)
    close_window.add_argument("--window-id", required=True)
    close_window.add_argument("--reviewer-runtime", required=True)
    design = commands.add_parser("record-design-review")
    design.add_argument("--task-dir", required=True)
    design.add_argument("--review", required=True)
    design.add_argument("--reviewer-runtime", required=True)
    design.add_argument("--design-input")
    design.add_argument("--behavioral-window-id")
    design_window = commands.add_parser("begin-design-window")
    design_window.add_argument("--task-dir", required=True)
    design_window.add_argument("--window-id", required=True)
    design_window.add_argument("--design-input", required=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "inspect":
            output = inspect_task(arguments.task_dir)
        elif arguments.command == "bundle":
            relationship = relationship_from_package(_read_json_value(arguments.relationship))
            evidence = _read_json_value(arguments.candidate_evidence)
            coverage = _read_json_value(arguments.expected_coverage)
            predecessors = _read_json_value(arguments.predecessor_verdicts)
            if not isinstance(evidence, list) or not isinstance(coverage, list) or not isinstance(predecessors, Mapping):
                raise workflow.WorkflowError(
                    "invalid-input", "bundle list/map inputs have wrong shape", affected=arguments.op_id
                )
            result = bundle_review_packet(
                arguments.task_dir, op_id=arguments.op_id,
                expected_state_version=arguments.expected_state_version,
                context=relationship, candidate_evidence=evidence,
                expected_coverage=coverage, predecessor_verdicts=predecessors,
            )
            output = {"packet": result["packet"], "receipt": result["receipt"]}
        elif arguments.command == "prepare-challenge":
            output = prepare_challenge(
                arguments.task_dir,
                relationship=relationship_from_package(_read_json_value(arguments.relationship)),
                request_id=arguments.request_id, check_key=arguments.check_key,
                authority_decision=arguments.authority_decision, argv_suffix=arguments.arg,
            )
        elif arguments.command == "register-probe":
            output = register_probe(
                arguments.task_dir,
                relationship=relationship_from_package(_read_json_value(arguments.relationship)),
                request_id=arguments.request_id,
                source_bytes=workflow._regular_bytes(Path(arguments.source).absolute()),
                timeout_seconds=arguments.timeout_seconds,
            )
        elif arguments.command == "record-challenge":
            result = record_challenge_evidence(
                arguments.task_dir,
                relationship=relationship_from_package(_read_json_value(arguments.relationship)),
                request=_read_json_value(arguments.request),
                evidence=_read_json_value(arguments.evidence),
            )
            output = {
                "request": result["request"], "evidence": result["evidence"],
                "receipt": result["receipt"], "operation_receipt": result["operation_receipt"],
            }
        elif arguments.command == "begin-behavioral-window":
            relationship = relationship_from_package(_read_json_value(arguments.relationship))
            _require_current_relationship(relationship, affected=arguments.window_id)
            candidate_identity = {"candidate_id": relationship.candidate_bridge["candidate_id"], "manifest_hash": relationship.candidate_bridge["manifest_hash"], "verify_receipt_digest": full_protocol.canonical_digest(relationship.candidate_verify_receipt)}
            output = workflow.begin_reviewer_window(arguments.task_dir, window_id=arguments.window_id, candidate_identity=candidate_identity)
        elif arguments.command == "begin-design-window":
            design_input = _read_json_value(arguments.design_input)
            if not isinstance(design_input, Mapping):
                raise workflow.WorkflowError("invalid-input", "design input must be an object", affected="design-input")
            output = workflow.begin_reviewer_window(arguments.task_dir, window_id=arguments.window_id, candidate_identity={"design_input_digest": full_protocol.canonical_digest(dict(design_input))})
        elif arguments.command == "end-behavioral-window":
            relationship = relationship_from_package(_read_json_value(arguments.relationship))
            _require_current_relationship(relationship, affected=arguments.window_id)
            candidate_identity = {"candidate_id": relationship.candidate_bridge["candidate_id"], "manifest_hash": relationship.candidate_bridge["manifest_hash"], "verify_receipt_digest": full_protocol.canonical_digest(relationship.candidate_verify_receipt)}
            output = workflow.end_reviewer_window(arguments.task_dir, window_id=arguments.window_id, candidate_identity=candidate_identity, runtime_receipt=_read_json_value(arguments.reviewer_runtime))
        elif arguments.command == "record-review":
            late = [] if arguments.pre_ship_evidence is None else _read_json_value(arguments.pre_ship_evidence)
            if not isinstance(late, list):
                raise workflow.WorkflowError("invalid-input", "pre-ship evidence must be a JSON list", affected=arguments.op_id)
            result = record_review(
                arguments.task_dir, op_id=arguments.op_id,
                expected_state_version=arguments.expected_state_version,
                relationship=relationship_from_package(_read_json_value(arguments.relationship)),
                verdict=_read_json_value(arguments.verdict),
                reviewer_runtime_receipt=_read_json_value(arguments.reviewer_runtime),
                pre_ship_evidence=late, behavioral_window_id=arguments.behavioral_window_id,
            )
            output = {"verdict": result["verdict"], "receipt": result["receipt"]}
        else:
            design_input = None if arguments.design_input is None else _read_json_value(arguments.design_input)
            if design_input is not None and not isinstance(design_input, Mapping):
                raise workflow.WorkflowError("invalid-input", "design input must be an object", affected="design-input")
            output = record_design_review(
                arguments.task_dir, review=_read_json_value(arguments.review),
                reviewer_runtime_receipt=_read_json_value(arguments.reviewer_runtime),
                design_input=design_input, behavioral_window_id=arguments.behavioral_window_id,
            )
        print(json.dumps(output, sort_keys=True))
        return 0
    except workflow.WorkflowError as error:
        print(json.dumps(error.as_dict(), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
