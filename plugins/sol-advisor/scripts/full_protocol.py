"""Pure validation helpers for the full-route protocol contract.

This is deliberately an import seam for P2/P3, not a command runner.  It only
canonicalizes or validates caller-supplied values and returns copies; callers own
filesystem publication, locking, CAS writes, command execution, and verdict choice.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import candidate as candidate_tool


PROTOCOL_VERSION = "SA-FULL-V2-P1"
STAGED_PROTOCOL_VERSION = "SA-FULL-V2-P2"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({PROTOCOL_VERSION, STAGED_PROTOCOL_VERSION})
ROUTES = frozenset({"solo", "delegate", "audit", "full"})
VERDICTS = frozenset({"ship", "fix-first", "rethink"})
REVIEW_STATUSES = frozenset(
    {
        "reviewing",
        "needs-fix",
        "needs-decision",
        "reviewed-awaiting-final-accept",
        "blocked-unavailable",
    }
)
REVIEW_AVAILABILITY = frozenset({"valid", "unavailable", "invalid"})
DESIGN_VERDICTS = frozenset({"design-approved", "fix-first", "rethink"})
EVIDENCE_SCOPES = frozenset({"delivery", "candidate", "challenge"})
ASSEMBLE_OUTPUT_TYPES = frozenset({"I", "output-identity", "schema2-manifest", "CB"})
SUPPORTED_RECORD_TYPES = frozenset(
    {
        "D",
        "M",
        "I",
        "CB",
        "E",
        "P",
        "DR",
        "CR",
        "V",
        "A",
        "challenge-request",
        "run-check-receipt",
        "operation-intent",
        "operation-receipt",
    }
)
_FILENAME_COMPONENTS_BY_RECORD = {
    "M": ("material_id",),
    "D": ("delivery_id",),
    "I": ("assembly_id",),
    "CB": ("bridge_id",),
    "E": ("evidence_id",),
    "P": ("packet_id",),
    "DR": ("review_id",),
    "V": ("verdict_id",),
    "A": ("acceptance_id",),
    "CR": ("challenge_receipt_id",),
    "challenge-request": ("request_id",),
    "operation-intent": ("op_id",),
    "operation-receipt": ("op_id",),
}


class ProtocolValidationError(ValueError):
    """Base class for malformed full-route protocol inputs."""


class UnsupportedProtocolError(ProtocolValidationError):
    """The supplied contract does not opt in to this protocol version."""


class UnsupportedRecordError(ProtocolValidationError):
    """A caller requested validation for an unknown immutable record kind."""


class ContractValidationError(ProtocolValidationError):
    """An immutable task contract contains an invalid or mutable field."""


class StateValidationError(ProtocolValidationError):
    """The mutable progress state has an invalid shape."""


class RouteCompatibilityError(ProtocolValidationError):
    """A non-full route was supplied full-only progress state."""


class RelationshipValidationError(ProtocolValidationError):
    """Immutable records do not bind the required predecessor relationship."""


class VerdictValidationError(RelationshipValidationError):
    """A review-status/verdict combination violates the verdict split."""


class StateTransitionError(StateValidationError):
    """A pure record-review transition would lose or invent rejection roots."""


class EnvironmentPolicyError(ProtocolValidationError):
    """A child environment violates the exact non-secret environment policy."""


class OperationConflictError(ProtocolValidationError):
    """One operation ID was reused with a different request."""


_CONTRACT_REQUIRED = frozenset(
    {
        "protocol",
        "contract_digest",
        "goal",
        "authority",
        "preserved_behavior",
        "excluded_behavior",
        "stages",
        "work_items",
        "checks",
        "environment_policy",
        "required_coverage",
        "review_policy",
    }
)
_CONTRACT_MUTABLE_OR_RUNTIME = frozenset(
    {
        "state",
        "stage_status",
        "work_status",
        "selected_attempts",
        "current_ids",
        "applicable_rejection_roots",
        "last_operation_receipt",
        "artifact_ids",
        "attempts",
        "progress",
        "future_artifact_ids",
    }
)
_STATE_REQUIRED = frozenset(
    {
        "version",
        "contract_digest",
        "stage_status",
        "work_status",
        "selected_attempts",
        "current_ids",
        "applicable_rejection_roots",
        "last_operation_receipt",
    }
)
_NON_FULL_STATE_KEYS = _STATE_REQUIRED | frozenset({"contract_digest", "state"})


@dataclass(frozen=True)
class RelationshipContext:
    """The only trusted bundle for cross-artifact full-route validation.

    Each public stage validator receives this bundle rather than accepting a prior
    shape check as evidence.  Fields needed by a later stage are intentionally
    required by that stage's wrapper, never inferred from IDs.
    """

    task_contract: Mapping[str, object]
    candidate_bridge: Mapping[str, object]
    manifest: Mapping[str, object]
    manifest_bytes: bytes
    candidate_verify_receipt: Mapping[str, object]
    assembly: Mapping[str, object]
    deliveries: list[Mapping[str, object]]
    materials: list[Mapping[str, object]]
    delivery_evidence: list[Mapping[str, object]]
    packet: Mapping[str, object] | None = None
    candidate_evidence: list[Mapping[str, object]] | None = None
    pre_ship_evidence: list[Mapping[str, object]] | None = None
    applicable_rejection_roots: list[str] | None = None
    predecessor_verdicts: Mapping[str, Mapping[str, object]] | None = None
    expected_coverage: list[str] | None = None
    challenge_request: Mapping[str, object] | None = None
    challenge_evidence: Mapping[str, object] | None = None
    challenge_receipt: Mapping[str, object] | None = None
    verdict: Mapping[str, object] | None = None
    observed_attestation: Mapping[str, object] | None = None


@dataclass(frozen=True)
class AcceptanceContext:
    """Complete evidence for one accepted stage, including its dependencies.

    Acceptance cannot rely on an ID-shaped prior A.  Each dependency carries the
    full relationship context that independently proves its own final authority.
    """

    acceptance: Mapping[str, object]
    relationship: RelationshipContext
    final_candidate_evidence: Mapping[str, object]
    root_authority: Mapping[str, object]
    candidate_verify_receipt: Mapping[str, object]
    dependency_acceptance_contexts: Mapping[str, "AcceptanceContext"]


@dataclass(frozen=True)
class AssembleRecoveryContext:
    relationship: RelationshipContext
    intent: Mapping[str, object]
    assembly: Mapping[str, object]
    output_identity: Mapping[str, object]
    receipt: Mapping[str, object] | None
    observed_state_version: int
    expected_state_before: int
    expected_state_after: int
    observed_outputs: Mapping[str, bool] | None = None


@dataclass(frozen=True)
class ChallengeRecoveryContext:
    """All facts required to recover one challenge without rerunning it."""

    relationship: RelationshipContext
    request: Mapping[str, object]
    evidence: Mapping[str, object] | None
    challenge_receipt: Mapping[str, object] | None
    nested_run_receipt: Mapping[str, object] | None


def _mapping(value: object, label: str, exc: type[ProtocolValidationError] = ProtocolValidationError) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise exc(f"{label} must be an object")
    return value


def _string(value: object, label: str, exc: type[ProtocolValidationError] = ProtocolValidationError) -> str:
    if not isinstance(value, str) or not value:
        raise exc(f"{label} must be a non-empty string")
    return value


def _string_list(value: object, label: str, exc: type[ProtocolValidationError] = ProtocolValidationError) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise exc(f"{label} must be a list of non-empty strings")
    return list(value)


def canonical_component(value: object, label: str) -> str:
    """Require one portable, canonical filename component without normalizing it."""

    if not isinstance(value, str) or not value or "\0" in value:
        raise ProtocolValidationError(f"{label} must be a non-empty filename component")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ProtocolValidationError(f"{label} must not contain a path traversal or separator")
    windows = PureWindowsPath(value)
    if windows.is_absolute() or windows.drive:
        raise ProtocolValidationError(f"{label} must not be an absolute or drive path")
    if unicodedata.normalize("NFC", value) != value:
        raise ProtocolValidationError(f"{label} must use NFC canonical Unicode")
    return value


def _required(record: Mapping[str, Any], keys: Sequence[str], exc: type[ProtocolValidationError]) -> None:
    missing = [key for key in keys if key not in record]
    if missing:
        raise exc("missing required fields: " + ", ".join(missing))


def canonical_json_bytes(value: object) -> bytes:
    """Return the sole JSON byte representation used for full-record hashes."""

    def reject_non_finite(item: object) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ProtocolValidationError("canonical JSON cannot contain non-finite numbers")
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ProtocolValidationError("canonical JSON object keys must be strings")
                reject_non_finite(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                reject_non_finite(child)

    reject_non_finite(value)
    try:
        return json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ProtocolValidationError("value is not canonical JSON") from error


def canonical_digest(value: object) -> str:
    """Hash a canonical JSON value without reading or writing external state."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_task_contract(value: object) -> dict[str, Any]:
    contract = _mapping(value, "task contract", ContractValidationError)
    _required(contract, sorted(_CONTRACT_REQUIRED), ContractValidationError)
    if contract["protocol"] not in SUPPORTED_PROTOCOL_VERSIONS:
        raise UnsupportedProtocolError(f"unsupported protocol: {contract['protocol']!r}")
    staged = contract["protocol"] == STAGED_PROTOCOL_VERSION
    if contract["contract_digest"] != canonical_digest(
        {key: item for key, item in contract.items() if key != "contract_digest"}
    ):
        raise ContractValidationError("contract_digest does not bind the canonical contract preimage")
    forbidden = sorted(_CONTRACT_MUTABLE_OR_RUNTIME.intersection(contract))
    if forbidden:
        raise ContractValidationError("task contract contains mutable/runtime fields: " + ", ".join(forbidden))
    _string(contract["contract_digest"], "contract_digest", ContractValidationError)
    _mapping(contract["authority"], "authority", ContractValidationError)
    stages = _mapping(contract["stages"], "stages", ContractValidationError)
    if not stages:
        raise ContractValidationError("stages must not be empty")
    for stage_key, stage in stages.items():
        _string(stage_key, "stage key", ContractValidationError)
        stage_value = _mapping(stage, f"stage {stage_key}", ContractValidationError)
        dependencies = _string_list(stage_value.get("depends_on"), f"stage {stage_key}.depends_on", ContractValidationError)
        if len(set(dependencies)) != len(dependencies) or stage_key in dependencies:
            raise ContractValidationError(f"stage {stage_key} has invalid dependencies")
        if staged:
            review_scope = stage_value.get("review_scope")
            if review_scope not in {"stage", "stage+final"}:
                raise ContractValidationError(f"stage {stage_key} must declare stage or stage+final review_scope")
    work_items = _mapping(contract["work_items"], "work_items", ContractValidationError)
    if not work_items:
        raise ContractValidationError("work_items must not be empty")
    for work_key, work in work_items.items():
        _string(work_key, "work key", ContractValidationError)
        item = _mapping(work, f"work item {work_key}", ContractValidationError)
        if staged:
            stage_key = _string(item.get("stage_key"), f"work item {work_key}.stage_key", ContractValidationError)
            if stage_key not in stages:
                raise ContractValidationError(f"work item {work_key} belongs to an unknown stage")
        if "paths" in item:
            if not _string_list(item["paths"], f"work item {work_key}.paths", ContractValidationError):
                raise ContractValidationError(f"work item {work_key}.paths must not be empty")
    checks = _mapping(contract["checks"], "checks", ContractValidationError)
    for check_key, check in checks.items():
        _string(check_key, "check key", ContractValidationError)
        scope = _mapping(check, f"check {check_key}", ContractValidationError).get("scope")
        if scope not in EVIDENCE_SCOPES:
            raise ContractValidationError(f"check {check_key} has unsupported scope")
        if staged:
            if "stage_key" in check and check["stage_key"] not in stages:
                raise ContractValidationError(f"check {check_key} names an unknown stage")
            phase = check.get("phase")
            if phase not in {"pre-review", "pre-ship"}:
                raise ContractValidationError(f"check {check_key} must declare pre-review or pre-ship phase")
            if not isinstance(check.get("required"), bool):
                raise ContractValidationError(f"check {check_key} must declare whether it is required")
            if "final_candidate_verify" in check and not isinstance(check["final_candidate_verify"], bool):
                raise ContractValidationError(f"check {check_key} final_candidate_verify must be boolean")
            if check.get("final_candidate_verify") is True and (scope != "candidate" or phase != "pre-ship"):
                raise ContractValidationError(f"check {check_key} final verification must be candidate/pre-ship")
    if staged:
        for stage_key in stages:
            if not any(check.get("final_candidate_verify") is True and check.get("stage_key", stage_key) == stage_key for check in checks.values()):
                raise ContractValidationError(f"stage {stage_key} needs an applicable final candidate verification check")
    review_policy = _mapping(contract["review_policy"], "review_policy", ContractValidationError)
    allowed_verdicts = _string_list(review_policy.get("allowed_verdicts"), "review_policy.allowed_verdicts", ContractValidationError)
    if set(allowed_verdicts) != VERDICTS or len(allowed_verdicts) != len(VERDICTS):
        raise ContractValidationError("review_policy.allowed_verdicts must contain the verdict triad")
    schema = review_policy.get("review_identity_schema")
    if schema is not None:
        allowed_schema = "SA-REVIEW-ATTESTATION-2" if staged else "SA-REVIEW-ATTESTATION-1"
        if schema != allowed_schema:
            raise ContractValidationError("review policy has an unsupported identity schema")
        admission = review_policy.get("isolation_admission")
        if admission not in {"hard-read-only", "hard-or-behavioral"}:
            raise ContractValidationError("review policy has an unsupported isolation admission")
        prompt_digest = review_policy.get("behavioral_read_only_prompt_digest")
        if admission == "hard-or-behavioral" and (not isinstance(prompt_digest, str) or not prompt_digest.startswith("sha256:") or len(prompt_digest) != 71):
            raise ContractValidationError("behavioral review policy requires an exact prompt digest")
        allowed = {"allowed_verdicts", "review_identity_schema", "isolation_admission"}
        if admission == "hard-or-behavioral":
            allowed.add("behavioral_read_only_prompt_digest")
        if set(review_policy) != allowed:
            raise ContractValidationError("review policy fields are invalid for its isolation admission")
    elif set(review_policy) != {"allowed_verdicts"}:
        raise ContractValidationError("legacy review policy has unsupported fields")
    probe_policy = contract.get("probe_policy")
    if staged and probe_policy is not None:
        policy = _mapping(probe_policy, "probe_policy", ContractValidationError)
        required_policy = {"scratch_root", "allowed_argv_prefixes", "allowed_cwd", "allowed_environment", "read_paths", "max_timeout_seconds", "network"}
        if set(policy) != required_policy:
            raise ContractValidationError("probe policy fields are invalid")
        canonical_component(policy["scratch_root"], "probe policy scratch_root")
        if policy["allowed_cwd"] != "." or policy["network"] != "forbidden":
            raise ContractValidationError("probe policy must use task root cwd and forbid network")
        prefixes = policy["allowed_argv_prefixes"]
        if not isinstance(prefixes, list) or not prefixes or any(not isinstance(prefix, list) or not prefix or any(not isinstance(part, str) or not part for part in prefix) for prefix in prefixes):
            raise ContractValidationError("probe policy argv prefixes are invalid")
        if not isinstance(policy["allowed_environment"], list) or any(not isinstance(name, str) or not name for name in policy["allowed_environment"]):
            raise ContractValidationError("probe policy environment allowlist is invalid")
        if not isinstance(policy["read_paths"], list) or not policy["read_paths"] or any(not isinstance(path, str) or not path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts or path.startswith((".env", "credentials", "secrets")) for path in policy["read_paths"]):
            raise ContractValidationError("probe policy read paths are invalid or sensitive")
        if not isinstance(policy["max_timeout_seconds"], int) or isinstance(policy["max_timeout_seconds"], bool) or policy["max_timeout_seconds"] <= 0:
            raise ContractValidationError("probe policy timeout is invalid")
    elif not staged and probe_policy is not None:
        raise ContractValidationError("legacy protocol must not carry a probe policy")
    if staged:
        unknown_dependencies = {dependency for stage in stages.values() for dependency in stage["depends_on"] if dependency not in stages}
        if unknown_dependencies:
            raise ContractValidationError("stage dependencies name an unknown stage")
        visiting: set[str] = set()
        completed: set[str] = set()
        def visit(stage_key: str) -> None:
            if stage_key in visiting:
                raise ContractValidationError("stage dependencies contain a cycle")
            if stage_key in completed:
                return
            visiting.add(stage_key)
            for dependency in stages[stage_key]["depends_on"]:
                visit(dependency)
            visiting.remove(stage_key)
            completed.add(stage_key)
        for stage_key in stages:
            visit(stage_key)
        final_stages = [key for key, stage in stages.items() if stage["review_scope"] == "stage+final"]
        terminals = [key for key in stages if not any(key in stage["depends_on"] for stage in stages.values())]
        if len(final_stages) != 1 or final_stages != terminals:
            raise ContractValidationError("staged contract requires its sole terminal stage to cover stage+final")
    return copy.deepcopy(dict(contract))


def validate_state(value: object) -> dict[str, Any]:
    state = _mapping(value, "state", StateValidationError)
    _required(state, sorted(_STATE_REQUIRED), StateValidationError)
    extra = sorted(set(state).difference(_STATE_REQUIRED))
    if extra:
        raise StateValidationError("state contains unsupported fields: " + ", ".join(extra))
    if not isinstance(state["version"], int) or isinstance(state["version"], bool) or state["version"] < 0:
        raise StateValidationError("state.version must be a non-negative integer")
    _string(state["contract_digest"], "state.contract_digest", StateValidationError)
    stage_status = _mapping(state["stage_status"], "state.stage_status", StateValidationError)
    review_status = stage_status.get("review_status")
    if review_status is not None and review_status not in REVIEW_STATUSES:
        raise StateValidationError("state.stage_status.review_status is unsupported")
    _mapping(state["work_status"], "state.work_status", StateValidationError)
    _mapping(state["selected_attempts"], "state.selected_attempts", StateValidationError)
    _mapping(state["current_ids"], "state.current_ids", StateValidationError)
    roots = _string_list(state["applicable_rejection_roots"], "state.applicable_rejection_roots", StateValidationError)
    if roots != sorted(set(roots)):
        raise StateValidationError("state.applicable_rejection_roots must be sorted and unique")
    if state["last_operation_receipt"] is not None:
        _string(state["last_operation_receipt"], "state.last_operation_receipt", StateValidationError)
    return copy.deepcopy(dict(state))


def validate_route_state(route: object, value: object) -> dict[str, Any]:
    route_name = _string(route, "route", RouteCompatibilityError)
    if route_name not in ROUTES:
        raise RouteCompatibilityError(f"unsupported route: {route_name!r}")
    route_state = _mapping(value, "route state", RouteCompatibilityError)
    if route_name != "full":
        forbidden = sorted(_NON_FULL_STATE_KEYS.intersection(route_state))
        if forbidden:
            raise RouteCompatibilityError(
                f"{route_name} route must not carry full-only state: " + ", ".join(forbidden)
            )
        return copy.deepcopy(dict(route_state))
    return validate_state(route_state)


def validate_record(record_type: object, value: object) -> dict[str, Any]:
    kind = _string(record_type, "record_type", UnsupportedRecordError)
    if kind not in SUPPORTED_RECORD_TYPES:
        raise UnsupportedRecordError(f"unsupported record type: {kind!r}")
    record = _mapping(value, f"{kind} record", ProtocolValidationError)
    if record.get("record_type") != kind:
        raise RelationshipValidationError(f"record_type does not match requested {kind}")
    for key in _FILENAME_COMPONENTS_BY_RECORD.get(kind, ()):
        if key in record:
            canonical_component(record[key], f"{kind}.{key}")
    return copy.deepcopy(dict(record))


def validate_material(value: object, task_contract: object, expected_work: Mapping[str, object]) -> dict[str, Any]:
    material = validate_record("M", value)
    contract = validate_task_contract(task_contract)
    _required(
        material,
        ("material_id", "contract_digest", "work_key", "baseline_id", "ready_identity", "bundle", "material_digest"),
        RelationshipValidationError,
    )
    if material["contract_digest"] != contract["contract_digest"]:
        raise RelationshipValidationError("M contract_digest does not bind the task contract")
    if material["work_key"] != expected_work.get("work_key"):
        raise RelationshipValidationError("M work_key does not bind expected work")
    bundle = _mapping(material["bundle"], "M.bundle", RelationshipValidationError)
    paths = _string_list(bundle.get("files"), "M.bundle.files", RelationshipValidationError)
    if paths != expected_work.get("paths"):
        raise RelationshipValidationError("M bundle files do not bind expected work paths")
    if material["material_digest"] != canonical_digest(
        {key: item for key, item in material.items() if key != "material_digest"}
    ):
        raise RelationshipValidationError("M material_digest does not bind canonical material")
    return material


def validate_delivery(
    value: object,
    material_value: object,
    task_contract: object,
    expected_work: Mapping[str, object],
) -> dict[str, Any]:
    delivery = validate_record("D", value)
    material = validate_material(material_value, task_contract, expected_work)
    _required(delivery, ("delivery_id", "contract_digest", "work_key", "baseline_id", "ready_identity", "material_id", "material_digest", "delivery_evidence_id", "attestation", "delivery_digest"), RelationshipValidationError)
    for key in ("delivery_id", "contract_digest", "work_key", "baseline_id", "ready_identity", "material_id", "material_digest", "delivery_evidence_id"):
        _string(delivery[key], f"D.{key}", RelationshipValidationError)
    for key in ("contract_digest", "work_key", "baseline_id", "ready_identity", "material_id", "material_digest"):
        if delivery[key] != material[key]:
            raise RelationshipValidationError(f"D.{key} does not bind the supplied material")
    if not _mapping(delivery["attestation"], "D.attestation", RelationshipValidationError):
        raise RelationshipValidationError("D.attestation must not be empty")
    if delivery["delivery_digest"] != canonical_digest(
        {key: item for key, item in delivery.items() if key != "delivery_digest"}
    ):
        raise RelationshipValidationError("D delivery_digest does not bind canonical delivery")
    return delivery


def validate_evidence(
    value: object,
    task_contract: object,
    expected_scope: str,
    expected_subject_id: str,
) -> dict[str, Any]:
    evidence = validate_record("E", value)
    contract = validate_task_contract(task_contract)
    _required(evidence, ("contract_digest", "scope", "subject_id", "check_key", "harness_identity", "environment_identity", "runtime_identity", "result", "logs"), RelationshipValidationError)
    if evidence["contract_digest"] != contract["contract_digest"]:
        raise RelationshipValidationError("E contract_digest does not bind the task contract")
    check_key = _string(evidence["check_key"], "E.check_key", RelationshipValidationError)
    if contract["protocol"] == STAGED_PROTOCOL_VERSION and check_key == "__new_probe__":
        check = {"scope": "challenge"}
    else:
        check = _mapping(contract["checks"].get(check_key), "E check", RelationshipValidationError)
    if evidence["scope"] != check["scope"]:
        raise RelationshipValidationError("E scope does not match its declared check")
    if evidence["scope"] != expected_scope:
        raise RelationshipValidationError("E scope does not bind the expected scope")
    if evidence["subject_id"] != expected_subject_id:
        raise RelationshipValidationError("E subject_id does not bind the expected subject")
    if evidence["scope"] not in EVIDENCE_SCOPES:
        raise RelationshipValidationError("E scope is unsupported")
    for key in ("subject_id", "check_key", "harness_identity", "environment_identity", "runtime_identity"):
        _string(evidence[key], f"E.{key}", RelationshipValidationError)
    if evidence["result"] not in {"pass", "fail", "incomplete"}:
        raise RelationshipValidationError("E result is unsupported")
    if not isinstance(evidence["logs"], list):
        raise RelationshipValidationError("E.logs must be a list")
    if evidence["result"] == "pass" and any(isinstance(log, Mapping) and log.get("truncated") is True for log in evidence["logs"]):
        raise RelationshipValidationError("passing E must not contain truncated logs")
    _string(evidence.get("evidence_id"), "E.evidence_id", RelationshipValidationError)
    if evidence.get("evidence_digest") != canonical_digest(
        {key: item for key, item in evidence.items() if key != "evidence_digest"}
    ):
        raise RelationshipValidationError("E evidence_digest does not bind canonical evidence")
    return evidence


def _validate_candidate_bridge_shape(value: object) -> dict[str, Any]:
    bridge = validate_record("CB", value)
    _required(bridge, ("contract_digest", "manifest_schema_version", "candidate_id", "manifest_candidate_id", "selection_policy", "assembly_id", "delivery_ids", "material_ids", "explicit_inputs", "correspondence_digest"), RelationshipValidationError)
    if bridge["manifest_schema_version"] != 2:
        raise RelationshipValidationError("CB must bind candidate schema version 2")
    if bridge["candidate_id"] != bridge["manifest_candidate_id"]:
        raise RelationshipValidationError("CB candidate_id does not match manifest_candidate_id")
    for key in ("contract_digest", "candidate_id", "manifest_candidate_id", "selection_policy", "assembly_id", "correspondence_digest"):
        _string(bridge[key], f"CB.{key}", RelationshipValidationError)
    for key in ("delivery_ids", "material_ids"):
        ids = _string_list(bridge[key], f"CB.{key}", RelationshipValidationError)
        if not ids or len(set(ids)) != len(ids):
            raise RelationshipValidationError(f"CB.{key} must be non-empty and unique")
    return bridge


def _validate_schema2_manifest(
    manifest: Mapping[str, object], manifest_bytes: bytes,
) -> dict[str, Any]:
    if not isinstance(manifest_bytes, bytes):
        raise RelationshipValidationError("CB manifest bytes must be bytes")
    try:
        decoded = json.loads(
            manifest_bytes.decode("utf-8"), object_pairs_hook=candidate_tool.unique_json_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError, candidate_tool.CandidateError) as error:
        raise RelationshipValidationError("CB manifest bytes are not JSON") from error
    if decoded != manifest:
        raise RelationshipValidationError("CB manifest bytes do not decode to supplied manifest")
    try:
        # candidate.py owns schema-2 grammar, including legitimate repository
        # symlink/missing/index shapes.  Do not maintain a narrower copy here.
        return candidate_tool.validate_manifest(decoded)
    except candidate_tool.CandidateError as error:
        raise RelationshipValidationError("CB manifest is not a candidate.py schema-2 manifest") from error


def _validate_selected_records(
    *, bridge: Mapping[str, object], assembly: object, deliveries: list[Mapping[str, object]],
    materials: list[Mapping[str, object]], contract: Mapping[str, object],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Validate each retained I/D/M before CB can trust its identifiers."""

    index = validate_assembly_index(assembly)
    if index["contract_digest"] != contract["contract_digest"] or index["assembly_id"] != bridge["assembly_id"]:
        raise RelationshipValidationError("CB I does not bind its task contract and assembly")
    checked_materials: dict[str, dict[str, Any]] = {}
    for material in materials:
        raw = validate_record("M", material)
        work_key = _string(raw.get("work_key"), "M.work_key", RelationshipValidationError)
        work = _mapping(contract["work_items"].get(work_key), "M expected work", RelationshipValidationError)
        checked = validate_material(raw, contract, {"work_key": work_key, "paths": work.get("paths")})
        material_id = checked["material_id"]
        if material_id in checked_materials:
            raise RelationshipValidationError("CB supplied M records must have unique IDs")
        checked_materials[material_id] = checked
    checked_deliveries: dict[str, dict[str, Any]] = {}
    for delivery in deliveries:
        raw = validate_record("D", delivery)
        material_id = _string(raw.get("material_id"), "D.material_id", RelationshipValidationError)
        if material_id not in checked_materials:
            raise RelationshipValidationError("CB D references a missing supplied material")
        work_key = _string(raw.get("work_key"), "D.work_key", RelationshipValidationError)
        work = _mapping(contract["work_items"].get(work_key), "D expected work", RelationshipValidationError)
        checked = validate_delivery(raw, checked_materials[material_id], contract, {"work_key": work_key, "paths": work.get("paths")})
        delivery_id = checked["delivery_id"]
        if delivery_id in checked_deliveries:
            raise RelationshipValidationError("CB supplied D records must have unique IDs")
        checked_deliveries[delivery_id] = checked
    if (
        set(index["delivery_ids"]) != set(checked_deliveries)
        or set(index["material_ids"]) != set(checked_materials)
        or set(bridge["delivery_ids"]) != set(checked_deliveries)
        or set(bridge["material_ids"]) != set(checked_materials)
    ):
        raise RelationshipValidationError("CB I/D/M retained-record correspondence mismatch")
    if contract["protocol"] == STAGED_PROTOCOL_VERSION:
        stage = index.get("stage_key")
        if stage not in contract["stages"] or index.get("review_scope") != contract["stages"][stage]["review_scope"]:
            raise RelationshipValidationError("assembly must bind its stage and review scope")
        included_stages = set(_dependency_closure(contract, stage)) | {stage}
        expected_work = {key for key, work in contract["work_items"].items() if work["stage_key"] in included_stages}
        actual_work = [delivery["work_key"] for delivery in checked_deliveries.values()]
        if len(actual_work) != len(set(actual_work)) or set(actual_work) != expected_work:
            raise RelationshipValidationError("assembly does not contain the exact cumulative stage work")
    return index, checked_deliveries, checked_materials


def _validate_delivery_evidence_chain(
    delivery_evidence: list[Mapping[str, object]], *, deliveries: Mapping[str, Mapping[str, object]],
    materials: Mapping[str, Mapping[str, object]], contract: Mapping[str, object],
) -> dict[str, dict[str, Any]]:
    """Require one passing delivery E for every selected material/D pair."""

    expected_material_ids = set(materials)
    deliveries_by_material = {
        delivery["material_id"]: delivery for delivery in deliveries.values()
    }
    if (
        len(deliveries) != len(materials)
        or len(deliveries_by_material) != len(deliveries)
        or set(deliveries_by_material) != expected_material_ids
    ):
        raise RelationshipValidationError("CB selected D/M records are not one-to-one for delivery evidence")
    checked: dict[str, dict[str, Any]] = {}
    evidence_ids: set[str] = set()
    for evidence in delivery_evidence:
        subject_id = _string(evidence.get("subject_id"), "delivery E.subject_id", RelationshipValidationError)
        if subject_id not in expected_material_ids:
            raise RelationshipValidationError("delivery E references an unselected material")
        item = validate_evidence(evidence, contract, "delivery", subject_id)
        if item["result"] != "pass":
            raise RelationshipValidationError("selected delivery E must pass")
        if deliveries_by_material[subject_id]["delivery_evidence_id"] != item["evidence_id"]:
            raise RelationshipValidationError("selected D does not bind its own delivery E")
        if subject_id in checked or item["evidence_id"] in evidence_ids:
            raise RelationshipValidationError("delivery E records must be unique per selected material")
        checked[subject_id] = item
        evidence_ids.add(item["evidence_id"])
    if set(checked) != expected_material_ids or len(checked) != len(deliveries):
        raise RelationshipValidationError("delivery E records are missing or extra for selected D/M records")
    return checked


def _normalize_explicit_inputs(
    value: object, *, assembly_id: str, delivery_ids: set[str], material_ids: set[str],
) -> dict[str, dict[str, str]]:
    explicit = _mapping(value, "CB.explicit_inputs", RelationshipValidationError)
    if set(explicit) != {"I", "D", "M", "bundle"}:
        raise RelationshipValidationError("CB explicit inputs must name I/D/M/bundle groups")
    if all(isinstance(item, str) and item for item in explicit.values()):
        if len(delivery_ids) != 1 or len(material_ids) != 1:
            raise RelationshipValidationError("CB scalar explicit inputs cannot bind multiple D/M records")
        return {
            "I": {assembly_id: explicit["I"]},
            "D": {next(iter(delivery_ids)): explicit["D"]},
            "M": {next(iter(material_ids)): explicit["M"]},
            "bundle": {next(iter(material_ids)): explicit["bundle"]},
        }
    normalized: dict[str, dict[str, str]] = {}
    expected_ids = {"I": {assembly_id}, "D": delivery_ids, "M": material_ids, "bundle": material_ids}
    for kind, identifiers in expected_ids.items():
        group = _mapping(explicit[kind], f"CB.explicit_inputs.{kind}", RelationshipValidationError)
        if set(group) != identifiers or any(not isinstance(path, str) or not path for path in group.values()):
            raise RelationshipValidationError(f"CB explicit {kind} inputs are missing, extra, or invalid")
        normalized[kind] = dict(group)
    return normalized


def _validate_explicit_input_correspondence(
    *, explicit_inputs: object, strict_manifest: Mapping[str, object], assembly: Mapping[str, object],
    deliveries: Mapping[str, Mapping[str, object]], materials: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, str]]:
    normalized = _normalize_explicit_inputs(
        explicit_inputs, assembly_id=assembly["assembly_id"], delivery_ids=set(deliveries), material_ids=set(materials),
    )
    input_entries = {
        entry["path"]: entry for entry in strict_manifest["entries"] if entry["scope"] == "input"
    }
    paths = [path for group in normalized.values() for path in group.values()]
    if len(paths) != len(set(paths)):
        raise RelationshipValidationError("CB explicit inputs must not substitute one input for another")
    if not set(paths).issubset(input_entries):
        raise RelationshipValidationError("CB relevant explicit inputs are not selected by the manifest")

    expected_hashes: dict[str, str] = {
        normalized["I"][assembly["assembly_id"]]: hashlib.sha256(canonical_json_bytes(assembly)).hexdigest(),
    }
    for delivery_id, delivery in deliveries.items():
        expected_hashes[normalized["D"][delivery_id]] = hashlib.sha256(canonical_json_bytes(delivery)).hexdigest()
    for material_id, material in materials.items():
        expected_hashes[normalized["M"][material_id]] = hashlib.sha256(canonical_json_bytes(material)).hexdigest()
        bundle = _mapping(material["bundle"], "M.bundle", RelationshipValidationError)
        bundle_hash = bundle.get("sha256")
        if not isinstance(bundle_hash, str) or re.fullmatch(r"[0-9a-f]{64}", bundle_hash) is None:
            raise RelationshipValidationError("CB material bundle has no candidate-bindable SHA-256")
        expected_hashes[normalized["bundle"][material_id]] = bundle_hash
    for path, expected_hash in expected_hashes.items():
        entry = input_entries[path]
        if entry.get("type") != "file" or entry.get("sha256") != expected_hash:
            raise RelationshipValidationError("CB explicit input does not bind its retained I/D/M/bundle bytes")
    return normalized


def _validate_candidate_verify_receipt(value: object, candidate_id: str) -> dict[str, Any]:
    receipt = _mapping(value, "candidate verify receipt", RelationshipValidationError)
    required = {"status", "candidate_id", "current_candidate_id", "head_changed", "changes", "expected_candidate_id", "expected_candidate_id_match"}
    if set(receipt) != required:
        raise RelationshipValidationError("candidate verify receipt is not the actual candidate.py format")
    if receipt["status"] != "match" or receipt["expected_candidate_id_match"] is not True or receipt["changes"] != [] or receipt["head_changed"] is not False:
        raise RelationshipValidationError("candidate verify receipt is not an exact clean match")
    if any(receipt[key] != candidate_id for key in ("candidate_id", "current_candidate_id", "expected_candidate_id")):
        raise RelationshipValidationError("candidate verify receipt candidate IDs do not match")
    return dict(receipt)


def _validate_candidate_bridge_context(value: object, *, manifest: Mapping[str, object], manifest_bytes: bytes, candidate_verify_receipt: Mapping[str, object], assembly: Mapping[str, object], deliveries: list[Mapping[str, object]], materials: list[Mapping[str, object]], delivery_evidence: list[Mapping[str, object]], task_contract: object) -> dict[str, Any]:
    bridge = _validate_candidate_bridge_shape(value)
    contract = validate_task_contract(task_contract)
    strict_manifest = _validate_schema2_manifest(manifest, manifest_bytes)
    if bridge["contract_digest"] != contract["contract_digest"]:
        raise RelationshipValidationError("CB contract/schema relationship is invalid")
    if bridge.get("manifest_hash") != "sha256:" + hashlib.sha256(manifest_bytes).hexdigest():
        raise RelationshipValidationError("CB manifest hash mismatch")
    if bridge["candidate_id"] != strict_manifest.get("candidate_id") or bridge["manifest_candidate_id"] != strict_manifest.get("candidate_id"):
        raise RelationshipValidationError("CB candidate identity mismatch")
    if bridge["selection_policy"] != strict_manifest["selection"]["repo_inventory"]:
        raise RelationshipValidationError("CB selection_policy does not bind the schema-2 manifest selection")
    index, checked_deliveries, checked_materials = _validate_selected_records(
        bridge=bridge, assembly=assembly, deliveries=deliveries, materials=materials, contract=contract,
    )
    _validate_delivery_evidence_chain(
        delivery_evidence, deliveries=checked_deliveries, materials=checked_materials, contract=contract,
    )
    _validate_explicit_input_correspondence(
        explicit_inputs=bridge["explicit_inputs"], strict_manifest=strict_manifest, assembly=index,
        deliveries=checked_deliveries, materials=checked_materials,
    )
    expected = canonical_digest({"manifest": manifest, "assembly": assembly, "deliveries": deliveries, "materials": materials, "delivery_evidence": delivery_evidence, "explicit_inputs": bridge["explicit_inputs"]})
    if bridge["correspondence_digest"] != expected:
        raise RelationshipValidationError("CB correspondence digest mismatch")
    _validate_candidate_verify_receipt(candidate_verify_receipt, bridge["candidate_id"])
    return bridge


def validate_candidate_bridge(value: object, *, context: RelationshipContext) -> dict[str, Any]:
    if not isinstance(context, RelationshipContext) or value != context.candidate_bridge:
        raise RelationshipValidationError("CB requires its complete RelationshipContext")
    return validate_relationship_context(context, target="candidate")


def validate_assembly_index(value: object) -> dict[str, Any]:
    assembly = validate_record("I", value)
    _required(
        assembly,
        (
            "assembly_id",
            "contract_digest",
            "baseline_id",
            "delivery_ids",
            "material_ids",
            "output_identity_id",
            "schema2_manifest_id",
            "candidate_bridge_id",
        ),
        RelationshipValidationError,
    )
    for key in (
        "assembly_id",
        "contract_digest",
        "baseline_id",
        "output_identity_id",
        "schema2_manifest_id",
        "candidate_bridge_id",
    ):
        _string(assembly[key], f"I.{key}", RelationshipValidationError)
    for key in ("delivery_ids", "material_ids"):
        ids = _string_list(assembly[key], f"I.{key}", RelationshipValidationError)
        if not ids or len(set(ids)) != len(ids):
            raise RelationshipValidationError(f"I.{key} must be non-empty and unique")
    return assembly


def _validate_review_packet_shape(value: object) -> dict[str, Any]:
    packet = validate_record("P", value)
    _required(packet, ("packet_id", "contract_digest", "candidate_bridge_id", "assembly_id", "delivery_ids", "candidate_evidence_ids", "coverage", "rejection_roots"), RelationshipValidationError)
    for key in ("packet_id", "contract_digest", "candidate_bridge_id", "assembly_id"):
        _string(packet[key], f"P.{key}", RelationshipValidationError)
    if packet["packet_id"] == packet["candidate_bridge_id"]:
        raise RelationshipValidationError("P packet_id must not self-bind as candidate_bridge_id")
    for key in ("delivery_ids", "candidate_evidence_ids", "rejection_roots"):
        ids = _string_list(packet[key], f"P.{key}", RelationshipValidationError)
        if len(set(ids)) != len(ids) or packet["packet_id"] in ids:
            raise RelationshipValidationError(f"P.{key} has duplicate or self-bound IDs")
    coverage = _mapping(packet["coverage"], "P.coverage", RelationshipValidationError)
    if coverage.get("complete") is not True:
        raise RelationshipValidationError("P coverage must be complete before review")
    return packet


def _validate_predecessor_closure(
    roots: list[str], predecessor_verdicts: Mapping[str, Mapping[str, object]]
) -> list[str]:
    """Return the exact transitive predecessor closure, including active roots."""

    supplied = _mapping(predecessor_verdicts, "predecessor verdicts", RelationshipValidationError)
    closure: set[str] = set()
    visiting: set[str] = set()

    def visit(verdict_id: str) -> None:
        if verdict_id in visiting:
            raise RelationshipValidationError("predecessor verdict closure contains a cycle")
        record = _validate_verdict_shape(supplied.get(verdict_id))
        if record.get("status") != "valid" or record.get("verdict_id") != verdict_id:
            raise RelationshipValidationError("predecessor verdict does not bind its supplied ID")
        closure.add(verdict_id)
        visiting.add(verdict_id)
        for predecessor_id in _string_list(
            record.get("rejection_closure"), "predecessor rejection_closure", RelationshipValidationError
        ):
            if predecessor_id == verdict_id:
                raise RelationshipValidationError("predecessor verdict cannot close itself")
            visit(predecessor_id)
        visiting.remove(verdict_id)

    for root in roots:
        visit(root)
    if set(supplied) != closure:
        raise RelationshipValidationError("predecessor verdict records are missing or extra")
    return sorted(closure)


def _validate_corrected_p2_reviewer_freshness(
    *, contract: Mapping[str, Any], bridge: Mapping[str, object],
    attestation: Mapping[str, object], closure: list[str],
    predecessor_verdicts: Mapping[str, Mapping[str, object]],
) -> None:
    """Require a new observed reviewer identity after a P2 candidate correction."""

    if contract["protocol"] != STAGED_PROTOCOL_VERSION:
        return
    differing = [
        verdict_id for verdict_id in closure
        if predecessor_verdicts[verdict_id].get("candidate_bridge_id") != bridge["bridge_id"]
    ]
    if not differing:
        return
    reviewer = attestation.get("reviewer")
    if not isinstance(reviewer, Mapping):
        raise RelationshipValidationError(
            "corrected P2 review cannot prove reviewer independence without tagged identity"
        )
    current_thread = _string(
        reviewer.get("thread_id"), "corrected P2 reviewer thread_id", RelationshipValidationError
    )
    current_context = _string(
        reviewer.get("context_id"), "corrected P2 reviewer context_id", RelationshipValidationError
    )
    for verdict_id in differing:
        predecessor = predecessor_verdicts[verdict_id]
        predecessor_thread = _string(
            predecessor.get("reviewer_thread_id"),
            f"predecessor V.{verdict_id}.reviewer_thread_id",
            RelationshipValidationError,
        )
        predecessor_context = _string(
            predecessor.get("reviewer_context_id"),
            f"predecessor V.{verdict_id}.reviewer_context_id",
            RelationshipValidationError,
        )
        if current_thread == predecessor_thread or current_context == predecessor_context:
            raise RelationshipValidationError(
                f"corrected P2 review reuses predecessor reviewer identity: {verdict_id}"
            )


def _validate_review_packet_context(value: object, *, candidate_bridge: Mapping[str, object], manifest: Mapping[str, object], manifest_bytes: bytes, candidate_verify_receipt: Mapping[str, object], assembly: Mapping[str, object], deliveries: list[Mapping[str, object]], materials: list[Mapping[str, object]], delivery_evidence: list[Mapping[str, object]], candidate_evidence: list[Mapping[str, object]], task_contract: object, applicable_rejection_roots: list[str], predecessor_verdicts: Mapping[str, Mapping[str, object]], expected_coverage: list[str]) -> dict[str, Any]:
    packet = _validate_review_packet_shape(value)
    contract = validate_task_contract(task_contract)
    bridge = _validate_candidate_bridge_context(
        candidate_bridge, manifest=manifest, manifest_bytes=manifest_bytes, candidate_verify_receipt=candidate_verify_receipt, assembly=assembly,
        deliveries=deliveries, materials=materials, delivery_evidence=delivery_evidence, task_contract=contract,
    )
    index = validate_assembly_index(assembly)
    if index["contract_digest"] != contract["contract_digest"]:
        raise RelationshipValidationError("I does not bind the task contract")
    delivery_ids: set[str] = set()
    material_ids: set[str] = set()
    materials_by_id: dict[str, Mapping[str, object]] = {}
    for material in materials:
        record = validate_record("M", material)
        work_key = _string(record.get("work_key"), "M.work_key", RelationshipValidationError)
        work = _mapping(contract["work_items"].get(work_key), "M expected work", RelationshipValidationError)
        materials_by_id[_string(record.get("material_id"), "M.material_id", RelationshipValidationError)] = validate_material(
            record, contract, {"work_key": work_key, "paths": work.get("paths")}
        )
    for delivery in deliveries:
        record = validate_record("D", delivery)
        material_id = _string(record.get("material_id"), "D.material_id", RelationshipValidationError)
        if material_id not in materials_by_id:
            raise RelationshipValidationError("D references a missing supplied material")
        work_key = _string(record.get("work_key"), "D.work_key", RelationshipValidationError)
        work = _mapping(contract["work_items"].get(work_key), "D expected work", RelationshipValidationError)
        checked = validate_delivery(record, materials_by_id[material_id], contract, {"work_key": work_key, "paths": work.get("paths")})
        delivery_ids.add(checked["delivery_id"])
    material_ids = set(materials_by_id)
    if len(delivery_ids) != len(deliveries) or len(material_ids) != len(materials):
        raise RelationshipValidationError("P supplied D/M records must have unique IDs")
    if delivery_ids != set(index["delivery_ids"]) or material_ids != set(index["material_ids"]):
        raise RelationshipValidationError("P I does not bind the supplied D/M records")
    if packet["contract_digest"] != contract["contract_digest"] or packet["candidate_bridge_id"] != bridge.get("bridge_id") or packet["assembly_id"] != index.get("assembly_id"):
        raise RelationshipValidationError("P does not bind supplied CB/I context")
    if set(packet["delivery_ids"]) != delivery_ids:
        raise RelationshipValidationError("P delivery/evidence correspondence mismatch")
    evidence_ids: set[str] = set()
    check_keys: set[str] = set()
    for evidence in candidate_evidence:
        checked = validate_evidence(evidence, contract, "candidate", bridge["bridge_id"])
        if checked["result"] != "pass":
            raise RelationshipValidationError("complete P requires passing candidate evidence")
        evidence_ids.add(checked["evidence_id"])
        check_keys.add(checked["check_key"])
    if contract["protocol"] == STAGED_PROTOCOL_VERSION:
        required_checks = {
            key for key, check in contract["checks"].items()
            if check.get("scope") == "candidate" and check.get("phase") == "pre-review" and check.get("required") is True and check.get("stage_key", index.get("stage_key")) == index.get("stage_key")
        }
    else:
        required_checks = {
            key for key, check in contract["checks"].items()
            if check.get("scope") == "candidate" and check.get("final_candidate_verify") is not True
        }
    staged = contract["protocol"] == STAGED_PROTOCOL_VERSION
    if staged and (packet.get("stage_key") != index["stage_key"] or packet.get("review_scope") != index["review_scope"]):
        raise RelationshipValidationError("packet stage/scope does not bind its assembly")
    if staged and any(contract["checks"][key].get("phase") != "pre-review" or contract["checks"][key].get("stage_key", index["stage_key"]) != index["stage_key"] for key in check_keys):
        raise RelationshipValidationError("P must not absorb pre-ship E")
    checks_complete = required_checks.issubset(check_keys) if staged else check_keys == required_checks
    if len(evidence_ids) != len(candidate_evidence) or len(check_keys) != len(candidate_evidence) or set(packet["candidate_evidence_ids"]) != evidence_ids or not checks_complete:
        raise RelationshipValidationError("P candidate evidence is missing, extra, or has duplicate IDs")
    roots = _string_list(applicable_rejection_roots, "applicable rejection roots", RelationshipValidationError)
    if roots != sorted(set(roots)) or packet["rejection_roots"] != roots:
        raise RelationshipValidationError("P rejection roots mismatch")
    expected_closure = _validate_predecessor_closure(roots, predecessor_verdicts)
    if packet.get("rejection_closure") != expected_closure:
        raise RelationshipValidationError("P rejection closure mismatch")
    required_scopes = _string_list(contract["required_coverage"], "contract required coverage", RelationshipValidationError)
    if set(required_scopes) != set(expected_coverage) or packet["coverage"].get("checks") != sorted(check_keys) or packet["coverage"].get("required_scopes") != required_scopes:
        raise RelationshipValidationError("P roots or coverage mismatch")
    return packet


def validate_review_packet(value: object, *, context: RelationshipContext) -> dict[str, Any]:
    if not isinstance(context, RelationshipContext) or value != context.packet:
        raise RelationshipValidationError("P requires its complete RelationshipContext")
    return validate_relationship_context(context, target="packet")


def _validate_verdict_shape(value: object) -> dict[str, Any]:
    verdict = validate_record("V", value)
    _required(verdict, ("status", "verdict"), VerdictValidationError)
    status = verdict["status"]
    if status not in REVIEW_AVAILABILITY:
        raise VerdictValidationError("V.status is unsupported")
    if status != "valid":
        if verdict["verdict"] is not None:
            raise VerdictValidationError("unavailable/invalid V must have null verdict")
        return verdict
    _required(verdict, ("verdict_id", "contract_digest", "packet_id", "candidate_bridge_id", "challenge_receipt_id", "rejection_closure", "coverage_complete"), VerdictValidationError)
    if verdict["verdict"] not in VERDICTS:
        raise VerdictValidationError("valid V must use the verdict triad")
    for key in ("verdict_id", "contract_digest", "packet_id", "candidate_bridge_id", "challenge_receipt_id"):
        _string(verdict[key], f"V.{key}", RelationshipValidationError)
    roots = _string_list(verdict["rejection_closure"], "V.rejection_closure", RelationshipValidationError)
    if roots != sorted(set(roots)):
        raise RelationshipValidationError("V.rejection_closure must be sorted and unique")
    if not isinstance(verdict["coverage_complete"], bool):
        raise VerdictValidationError("V.coverage_complete must be boolean")
    return verdict


def _validate_observed_attestation(value: object) -> dict[str, Any]:
    attestation = _mapping(value, "observed attestation", RelationshipValidationError)
    required = {"context_id", "thread_id", "role", "model", "effort", "observed_attestation"}
    if set(attestation) != required:
        raise RelationshipValidationError("observed attestation must have exactly its required context fields")
    for key in required.difference({"observed_attestation"}):
        _string(attestation[key], f"observed attestation {key}", RelationshipValidationError)
    if not attestation["observed_attestation"]:
        raise RelationshipValidationError("observed attestation must not be empty")
    return dict(attestation)


def _validate_reviewer_attestation(value: object) -> dict[str, Any]:
    """Validate the observed, pinned Sol identity that may issue a V record."""

    attestation = _validate_observed_attestation(value)
    if (
        attestation["role"] != "sol_advisor_sol_reviewer"
        or attestation["model"] != "gpt-5.6-sol"
        or attestation["effort"] != "high"
    ):
        raise RelationshipValidationError("V observed attestation is not the required Sol reviewer identity")
    return attestation


def validate_review_attestation(value: object, task_contract: object) -> dict[str, Any]:
    """Validate either retained legacy hard evidence or the new tagged identity."""

    contract = validate_task_contract(task_contract)
    policy = contract["review_policy"]
    if "review_identity_schema" not in policy:
        return _validate_reviewer_attestation(value)
    if policy["review_identity_schema"] == "SA-REVIEW-ATTESTATION-2":
        return _validate_v2_review_attestation(value, contract)
    attestation = _mapping(value, "review attestation", RelationshipValidationError)
    required = {"schema", "mode", "reviewer", "observed", "windows", "attestation_digest"}
    if set(attestation) != required or attestation["schema"] != "SA-REVIEW-ATTESTATION-1":
        raise RelationshipValidationError("review attestation has an invalid tagged schema")
    if attestation["attestation_digest"] != canonical_digest({key: item for key, item in attestation.items() if key != "attestation_digest"}):
        raise RelationshipValidationError("review attestation digest does not bind its canonical preimage")
    reviewer = _mapping(attestation["reviewer"], "review attestation reviewer", RelationshipValidationError)
    reviewer_required = {"thread_id", "context_id", "context_source", "role", "model", "effort", "runtime_receipt_digest"}
    if set(reviewer) != reviewer_required:
        raise RelationshipValidationError("review attestation reviewer fields are invalid")
    for key in reviewer_required:
        _string(reviewer[key], f"review attestation reviewer.{key}", RelationshipValidationError)
    if reviewer["context_source"] not in {"observed-context", "verified-thread-id"}:
        raise RelationshipValidationError("review attestation context source is invalid")
    if reviewer["context_source"] == "verified-thread-id" and reviewer["context_id"] != reviewer["thread_id"]:
        raise RelationshipValidationError("verified-thread-id context must equal reviewer thread")
    if (reviewer["role"], reviewer["model"], reviewer["effort"]) != ("sol_advisor_sol_reviewer", "gpt-5.6-sol", "high"):
        raise RelationshipValidationError("review attestation does not bind the Sol reviewer pin")
    observed = _mapping(attestation["observed"], "review attestation observed", RelationshipValidationError)
    if set(observed) != {"sandbox_policy_type", "permission_profile", "prompt_digest"}:
        raise RelationshipValidationError("review attestation observed facts are invalid")
    if any(not isinstance(item, str) or not item for item in observed.values()):
        raise RelationshipValidationError("review attestation observed facts are incomplete")
    mode = attestation["mode"]
    if mode == "hard-read-only":
        if policy["isolation_admission"] not in {"hard-read-only", "hard-or-behavioral"} or observed["sandbox_policy_type"] != "read-only" or attestation["windows"] != []:
            raise RelationshipValidationError("hard review attestation is not observed hard-read-only")
    elif mode == "behavioral-window":
        if policy["isolation_admission"] != "hard-or-behavioral" or observed["prompt_digest"] != policy["behavioral_read_only_prompt_digest"]:
            raise RelationshipValidationError("behavioral review attestation is not allowed by contract")
        if not isinstance(attestation["windows"], list) or not attestation["windows"]:
            raise RelationshipValidationError("behavioral review attestation requires reviewer windows")
        for index, window in enumerate(attestation["windows"]):
            checked_window = _mapping(window, f"reviewer window {index}", RelationshipValidationError)
            required_window = {"candidate_before", "candidate_after", "task_tree_before", "task_tree_after"}
            if set(checked_window) != required_window:
                raise RelationshipValidationError("reviewer window fields are invalid")
            if checked_window["candidate_before"] != checked_window["candidate_after"]:
                raise RelationshipValidationError("reviewer window candidate changed")
            if checked_window["task_tree_before"] != checked_window["task_tree_after"]:
                raise RelationshipValidationError("reviewer window task tree changed")
            if not isinstance(checked_window["candidate_before"], Mapping) or not isinstance(checked_window["task_tree_before"], str):
                raise RelationshipValidationError("reviewer window identities are invalid")
    else:
        raise RelationshipValidationError("review attestation mode is unsupported")
    return copy.deepcopy(dict(attestation))


def _validate_v2_review_attestation(value: object, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate Root-recorded lifecycle evidence for behavioral-only review.

    V2 deliberately records a begin record made before a native reviewer is
    available and an end record made after it returns.  It proves only that the
    observed candidate/task bytes did not drift during that interval; it cannot
    prove that a broad host did not write and restore bytes.
    """

    attestation = _mapping(value, "review attestation", RelationshipValidationError)
    required = {"schema", "mode", "reviewer", "observed", "windows", "attestation_digest"}
    if set(attestation) != required or attestation["schema"] != "SA-REVIEW-ATTESTATION-2":
        raise RelationshipValidationError("review attestation has an invalid V2 tagged schema")
    if attestation["attestation_digest"] != canonical_digest({key: item for key, item in attestation.items() if key != "attestation_digest"}):
        raise RelationshipValidationError("review attestation digest does not bind its canonical preimage")
    reviewer = _mapping(attestation["reviewer"], "review attestation reviewer", RelationshipValidationError)
    reviewer_required = {"thread_id", "context_id", "context_source", "role", "model", "effort", "runtime_receipt_digest"}
    if set(reviewer) != reviewer_required or any(not isinstance(reviewer.get(key), str) or not reviewer[key] for key in reviewer_required):
        raise RelationshipValidationError("review attestation reviewer fields are invalid")
    if reviewer["context_source"] not in {"observed-context", "verified-thread-id"} or (reviewer["context_source"] == "verified-thread-id" and reviewer["context_id"] != reviewer["thread_id"]):
        raise RelationshipValidationError("review attestation context source is invalid")
    if (reviewer["role"], reviewer["model"], reviewer["effort"]) != ("sol_advisor_sol_reviewer", "gpt-5.6-sol", "high"):
        raise RelationshipValidationError("review attestation does not bind the Sol reviewer pin")
    observed = _mapping(attestation["observed"], "review attestation observed", RelationshipValidationError)
    if set(observed) != {"sandbox_policy_type", "permission_profile", "prompt_digest"} or any(not isinstance(item, str) or not item for item in observed.values()):
        raise RelationshipValidationError("review attestation observed facts are invalid")
    mode = attestation["mode"]
    policy = contract["review_policy"]
    if mode == "hard-read-only":
        if policy["isolation_admission"] not in {"hard-read-only", "hard-or-behavioral"} or observed["sandbox_policy_type"] != "read-only" or attestation["windows"] != []:
            raise RelationshipValidationError("hard review attestation is not observed hard-read-only")
        return copy.deepcopy(dict(attestation))
    if mode != "behavioral-window" or policy["isolation_admission"] != "hard-or-behavioral" or observed["prompt_digest"] != policy["behavioral_read_only_prompt_digest"]:
        raise RelationshipValidationError("behavioral review attestation is not allowed by contract")
    windows = attestation["windows"]
    if not isinstance(windows, list) or len(windows) != 1:
        raise RelationshipValidationError("behavioral review attestation requires one lifecycle window")
    window = _mapping(windows[0], "reviewer lifecycle window", RelationshipValidationError)
    fields = {"window_id", "context_id", "reviewer_thread_id", "candidate_before", "candidate_after", "task_tree_before", "task_tree_after", "begin_record_digest", "end_record_digest", "started_at", "ended_at"}
    if set(window) != fields or window["context_id"] != reviewer["context_id"] or window["reviewer_thread_id"] != reviewer["thread_id"]:
        raise RelationshipValidationError("behavioral reviewer window does not bind observed identity")
    if any(not isinstance(window.get(key), str) or not window[key] for key in fields.difference({"candidate_before", "candidate_after"})):
        raise RelationshipValidationError("behavioral reviewer window lifecycle facts are incomplete")
    if not isinstance(window["candidate_before"], Mapping) or window["candidate_before"] != window["candidate_after"]:
        raise RelationshipValidationError("behavioral reviewer window candidate changed")
    if window["task_tree_before"] != window["task_tree_after"]:
        raise RelationshipValidationError("behavioral reviewer window task tree changed")
    if window["started_at"] >= window["ended_at"]:
        raise RelationshipValidationError("behavioral reviewer window order is invalid")
    return copy.deepcopy(dict(attestation))


def _validate_unavailable_verdict_context(
    value: object, *, candidate_bridge: Mapping[str, object], observed_attestation: Mapping[str, object],
    task_contract: object,
) -> dict[str, Any]:
    """Validate an operationally unavailable/invalid V without inventing a challenge chain."""

    verdict = _validate_verdict_shape(value)
    if verdict["status"] not in {"unavailable", "invalid"}:
        raise RelationshipValidationError("unavailable verdict context requires unavailable or invalid V")
    _required(
        verdict,
        ("verdict_id", "contract_digest", "candidate_bridge_id", "observed_attestation_digest"),
        RelationshipValidationError,
    )
    for key in ("verdict_id", "contract_digest", "candidate_bridge_id", "observed_attestation_digest"):
        _string(verdict[key], f"V.{key}", RelationshipValidationError)
    contract = validate_task_contract(task_contract)
    bridge = _validate_candidate_bridge_shape(candidate_bridge)
    if verdict["contract_digest"] != contract["contract_digest"] or verdict["candidate_bridge_id"] != bridge["bridge_id"]:
        raise RelationshipValidationError("unavailable V does not bind task contract and CB")
    attestation = validate_review_attestation(observed_attestation, task_contract)
    if verdict["observed_attestation_digest"] != canonical_digest(attestation):
        raise RelationshipValidationError("unavailable V observed attestation digest mismatch")
    if "review_identity_schema" in contract["review_policy"] and (
        verdict.get("reviewer_thread_id") != attestation["reviewer"]["thread_id"]
        or verdict.get("reviewer_context_id") != attestation["reviewer"]["context_id"]
    ):
        raise RelationshipValidationError("unavailable V does not bind tagged reviewer identity")
    return verdict


def _validate_verdict_context(value: object, *, packet: Mapping[str, object], candidate_bridge: Mapping[str, object], candidate_evidence: list[Mapping[str, object]], challenge_receipt: Mapping[str, object] | None, challenge_request: Mapping[str, object] | None, challenge_evidence: Mapping[str, object] | None, observed_attestation: Mapping[str, object], predecessor_verdicts: Mapping[str, Mapping[str, object]], task_contract: object, applicable_rejection_roots: list[str], pre_ship_evidence: list[Mapping[str, object]] | None = None) -> dict[str, Any]:
    verdict = _validate_verdict_shape(value)
    if verdict["status"] != "valid":
        return verdict
    contract = validate_task_contract(task_contract)
    review_packet = _validate_review_packet_shape(packet)
    bridge = _validate_candidate_bridge_shape(candidate_bridge)
    if review_packet["contract_digest"] != contract["contract_digest"] or bridge["contract_digest"] != contract["contract_digest"]:
        raise RelationshipValidationError("V P/CB records do not bind the task contract")
    if review_packet["candidate_bridge_id"] != bridge.get("bridge_id") or verdict["packet_id"] != review_packet.get("packet_id") or verdict["candidate_bridge_id"] != bridge.get("bridge_id"):
        raise RelationshipValidationError("V does not bind P/CB")
    if challenge_receipt is None or challenge_request is None or challenge_evidence is None:
        raise RelationshipValidationError("valid V requires CR/request/challenge E")
    request = validate_challenge_request(challenge_request, contract)
    if request["packet_id"] != review_packet["packet_id"] or request["candidate_bridge_id"] != bridge["bridge_id"]:
        raise RelationshipValidationError("V challenge request does not bind P/CB")
    receipt = validate_challenge_receipt(challenge_receipt, request)
    evidence = _validate_challenge_evidence(challenge_evidence, request, contract)
    if receipt["evidence_id"] != evidence["evidence_id"] or receipt.get("challenge_request_digest") != request["request_digest"]:
        raise RelationshipValidationError("V CR does not bind canonical request and challenge evidence")
    if verdict["challenge_receipt_id"] != receipt.get("challenge_receipt_id"):
        raise RelationshipValidationError("V challenge receipt mismatch")
    if contract["protocol"] == STAGED_PROTOCOL_VERSION and (verdict.get("stage_key") != review_packet.get("stage_key") or verdict.get("review_scope") != review_packet.get("review_scope")):
        raise RelationshipValidationError("verdict stage/scope does not bind its packet")
    if contract["protocol"] == STAGED_PROTOCOL_VERSION and verdict["verdict"] == "ship":
        required_late = {
            key for key, check in contract["checks"].items()
            if check.get("scope") == "candidate" and check.get("phase") == "pre-ship" and check.get("required") is True and check.get("stage_key", review_packet.get("stage_key")) == review_packet.get("stage_key") and check.get("final_candidate_verify") is not True
        }
        supplied = pre_ship_evidence or []
        ids = _string_list(verdict.get("pre_ship_evidence_ids", []), "V.pre_ship_evidence_ids", RelationshipValidationError)
        if len(ids) != len(set(ids)) or set(ids) != {item.get("evidence_id") for item in supplied}:
            raise RelationshipValidationError("V pre-ship E IDs are missing, duplicate, or do not bind supplied evidence")
        seen: set[str] = set()
        for item in supplied:
            checked = validate_evidence(item, contract, "candidate", bridge["bridge_id"])
            key = checked["check_key"]
            declaration = contract["checks"][key]
            if declaration.get("stage_key", review_packet.get("stage_key")) != review_packet.get("stage_key") or declaration.get("phase") != "pre-ship" or declaration.get("final_candidate_verify") is True or key in seen or checked["result"] == "incomplete" or (key in required_late and checked["result"] != "pass"):
                raise RelationshipValidationError("V pre-ship E is invalid or duplicated")
            seen.add(key)
        if not required_late.issubset(seen):
            raise RelationshipValidationError("V required pre-ship E is missing")
    attestation = validate_review_attestation(observed_attestation, task_contract)
    if verdict.get("observed_attestation_digest") != canonical_digest(attestation):
        raise RelationshipValidationError("V observed attestation digest mismatch")
    if "review_identity_schema" in contract["review_policy"] and (
        verdict.get("reviewer_thread_id") != attestation["reviewer"]["thread_id"]
        or verdict.get("reviewer_context_id") != attestation["reviewer"]["context_id"]
    ):
        raise RelationshipValidationError("V does not bind tagged reviewer identity")
    roots = _string_list(applicable_rejection_roots, "applicable rejection roots", RelationshipValidationError)
    if roots != sorted(set(roots)):
        raise RelationshipValidationError("applicable rejection roots must be sorted and unique")
    expected_closure = _validate_predecessor_closure(roots, predecessor_verdicts)
    if verdict["rejection_closure"] != expected_closure:
        raise RelationshipValidationError("V inherited rejection closure mismatch")
    _validate_corrected_p2_reviewer_freshness(
        contract=contract, bridge=bridge, attestation=attestation,
        closure=expected_closure, predecessor_verdicts=predecessor_verdicts,
    )
    dispositions = _mapping(verdict.get("rejection_dispositions"), "V.rejection_dispositions", RelationshipValidationError)
    if set(dispositions) != set(expected_closure):
        raise RelationshipValidationError("V rejection dispositions are missing or extra")
    for predecessor_id, disposition in dispositions.items():
        if disposition not in {"open", "resolved"}:
            raise RelationshipValidationError(f"V rejection disposition for {predecessor_id} is unsupported")
    if verdict["verdict"] == "ship" and (not verdict["coverage_complete"] or verdict.get("open_rejections") != [] or any(item != "resolved" for item in dispositions.values())):
        raise RelationshipValidationError("ship V requires complete coverage and resolved inherited blockers")
    if verdict["verdict"] == "ship" and (
        any(item.get("result") != "pass" for item in candidate_evidence)
        or evidence["result"] != "pass"
    ):
        raise RelationshipValidationError("ship V requires passing required candidate and challenge evidence")
    return verdict


def validate_verdict(value: object, *, context: RelationshipContext) -> dict[str, Any]:
    if not isinstance(context, RelationshipContext) or value != context.verdict:
        raise RelationshipValidationError("V requires its complete RelationshipContext")
    return validate_relationship_context(context, target="review")


def validate_relationship_context(context: RelationshipContext, *, target: str) -> dict[str, Any]:
    """Validate the complete reachable relationship chain for one protocol stage."""

    if not isinstance(context, RelationshipContext):
        raise RelationshipValidationError("relationship validation requires RelationshipContext")
    if target not in {"candidate", "packet", "review"}:
        raise RelationshipValidationError("unsupported relationship validation target")
    bridge = _validate_candidate_bridge_context(
        context.candidate_bridge, manifest=context.manifest, manifest_bytes=context.manifest_bytes,
        candidate_verify_receipt=context.candidate_verify_receipt, assembly=context.assembly,
        deliveries=context.deliveries, materials=context.materials, delivery_evidence=context.delivery_evidence, task_contract=context.task_contract,
    )
    if target == "candidate":
        return bridge
    if target == "review" and context.verdict is not None:
        status = _validate_verdict_shape(context.verdict)["status"]
        if status in {"unavailable", "invalid"}:
            if context.observed_attestation is None:
                raise RelationshipValidationError("unavailable V requires observed reviewer attestation")
            return _validate_unavailable_verdict_context(
                context.verdict, candidate_bridge=bridge,
                observed_attestation=context.observed_attestation, task_contract=context.task_contract,
            )
    required_packet = (context.packet, context.candidate_evidence, context.applicable_rejection_roots, context.predecessor_verdicts, context.expected_coverage)
    if any(item is None for item in required_packet):
        raise RelationshipValidationError("P requires complete CB/P/E/predecessor context")
    packet = _validate_review_packet_context(
        context.packet, candidate_bridge=context.candidate_bridge, manifest=context.manifest,
        manifest_bytes=context.manifest_bytes, candidate_verify_receipt=context.candidate_verify_receipt,
        assembly=context.assembly, deliveries=context.deliveries, materials=context.materials,
        delivery_evidence=context.delivery_evidence, candidate_evidence=context.candidate_evidence, task_contract=context.task_contract,
        applicable_rejection_roots=context.applicable_rejection_roots,
        predecessor_verdicts=context.predecessor_verdicts, expected_coverage=context.expected_coverage,
    )
    if target == "packet":
        return packet
    required_review = (context.challenge_request, context.challenge_evidence, context.challenge_receipt, context.verdict, context.observed_attestation)
    if any(item is None for item in required_review):
        raise RelationshipValidationError("V requires complete P/CB/request/E/CR/attestation context")
    return _validate_verdict_context(
        context.verdict, packet=packet, candidate_bridge=bridge, candidate_evidence=context.candidate_evidence,
        challenge_receipt=context.challenge_receipt, challenge_request=context.challenge_request,
        challenge_evidence=context.challenge_evidence, observed_attestation=context.observed_attestation,
        predecessor_verdicts=context.predecessor_verdicts, task_contract=context.task_contract,
        applicable_rejection_roots=context.applicable_rejection_roots,
        pre_ship_evidence=context.pre_ship_evidence,
    )


def validate_design_review(value: object) -> dict[str, Any]:
    review = validate_record("DR", value)
    _required(review, ("status", "design_verdict"), VerdictValidationError)
    status = review["status"]
    if status not in REVIEW_AVAILABILITY:
        raise VerdictValidationError("DR.status is unsupported")
    forbidden = sorted(
        set(review).intersection(
            {"candidate_bridge_id", "packet_id", "verdict_id", "acceptance_id", "challenge_receipt_id"}
        )
    )
    if forbidden:
        raise RelationshipValidationError("DR must not carry final-review authority: " + ", ".join(forbidden))
    if status == "valid":
        if review["design_verdict"] not in DESIGN_VERDICTS:
            raise VerdictValidationError("valid DR has an unsupported design verdict")
        _string(review.get("contract_digest"), "DR.contract_digest", RelationshipValidationError)
        tagged = {"design_input_digest", "observed_attestation_digest", "reviewer_thread_id", "reviewer_context_id"}
        present = tagged.intersection(review)
        if present and present != tagged:
            raise RelationshipValidationError("DR tagged review identity is incomplete")
        for key in present:
            _string(review[key], f"DR.{key}", RelationshipValidationError)
    elif review["design_verdict"] is not None:
        raise VerdictValidationError("unavailable/invalid DR must have null design_verdict")
    return review


def validate_challenge_request(value: object, task_contract: object) -> dict[str, Any]:
    request = validate_record("challenge-request", value)
    contract = validate_task_contract(task_contract)
    _required(
        request,
        (
            "request_id",
            "request_digest",
            "contract_digest",
            "packet_id",
            "candidate_bridge_id",
            "check_key",
            "authority_decision",
        ),
        RelationshipValidationError,
    )
    if request["contract_digest"] != contract["contract_digest"]:
        raise RelationshipValidationError("challenge request does not bind the task contract")
    check_key = _string(request["check_key"], "challenge request check_key", RelationshipValidationError)
    staged = contract["protocol"] == STAGED_PROTOCOL_VERSION
    if staged and check_key == "__new_probe__":
        _validate_new_probe_request(request, contract)
    else:
        check = _mapping(contract["checks"].get(check_key), "challenge request check", RelationshipValidationError)
        if check.get("scope") != "challenge":
            raise RelationshipValidationError("challenge request check_key is not a predeclared challenge check")
        suffix = request.get("argv_suffix", [])
        allowed_suffixes = check.get("allowed_argv_suffixes", [[]])
        if not isinstance(suffix, list) or any(not isinstance(item, str) for item in suffix) or suffix not in allowed_suffixes:
            raise RelationshipValidationError("challenge request argv suffix is not contract-authorized")
    for key in (
        "request_id",
        "request_digest",
        "contract_digest",
        "packet_id",
        "candidate_bridge_id",
        "authority_decision",
    ):
        _string(request[key], f"challenge request {key}", RelationshipValidationError)
    if request["request_digest"] != canonical_digest(
        {key: item for key, item in request.items() if key != "request_digest"}
    ):
        raise RelationshipValidationError("challenge request digest does not bind its canonical preimage")
    return request


def _validate_new_probe_request(request: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the intentionally small new-probe admission surface.

    The source is not executable authority: callers must subsequently prove that
    it is the immutable task-owned source selected here.  No shell form, outside
    cwd, network policy, aliases, or unlisted environment are admitted.
    """

    policy = _mapping(contract.get("probe_policy"), "probe policy", RelationshipValidationError)
    probe = _mapping(request.get("probe"), "challenge request probe", RelationshipValidationError)
    required = {"source_path", "source_sha256", "argv", "cwd", "environment", "timeout_seconds", "network"}
    if set(probe) != required:
        raise RelationshipValidationError("new probe fields are invalid")
    source_path = _string(probe["source_path"], "new probe source path", RelationshipValidationError)
    expected_prefix = f"{policy['scratch_root']}/"
    pure = PurePosixPath(source_path)
    if not source_path.startswith(expected_prefix) or pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 2:
        raise RelationshipValidationError("new probe source escapes the task-owned scratch root")
    source_hash = _string(probe["source_sha256"], "new probe source SHA-256", RelationshipValidationError)
    if re.fullmatch(r"[0-9a-f]{64}", source_hash) is None:
        raise RelationshipValidationError("new probe source SHA-256 is invalid")
    argv = probe["argv"]
    if not isinstance(argv, list) or any(not isinstance(item, str) or not item for item in argv):
        raise RelationshipValidationError("new probe argv is invalid")
    prefixes = policy["allowed_argv_prefixes"]
    if not any(argv[:len(prefix)] == prefix for prefix in prefixes) or source_path not in argv:
        raise RelationshipValidationError("new probe argv is not policy-authorized")
    if probe["cwd"] != policy["allowed_cwd"] or probe["network"] != "forbidden":
        raise RelationshipValidationError("new probe cwd or network policy is not authorized")
    environment = probe["environment"]
    if not isinstance(environment, list) or any(not isinstance(item, str) or item not in policy["allowed_environment"] for item in environment) or len(set(environment)) != len(environment):
        raise RelationshipValidationError("new probe environment is not policy-authorized")
    timeout = probe["timeout_seconds"]
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0 or timeout > policy["max_timeout_seconds"]:
        raise RelationshipValidationError("new probe timeout is not policy-authorized")
    return dict(probe)


def validate_challenge_receipt(value: object, request_value: object) -> dict[str, Any]:
    receipt = validate_record("CR", value)
    request = validate_record("challenge-request", request_value)
    _required(receipt, ("challenge_receipt_id", "challenge_request_id", "packet_id", "candidate_bridge_id", "evidence_id", "challenge_request_digest"), RelationshipValidationError)
    expected = {
        "challenge_request_id": request.get("request_id"),
        "packet_id": request.get("packet_id"),
        "candidate_bridge_id": request.get("candidate_bridge_id"),
    }
    for key, expected_value in expected.items():
        if receipt[key] != expected_value:
            raise RelationshipValidationError(f"CR.{key} does not bind its challenge request")
        _string(receipt[key], f"CR.{key}", RelationshipValidationError)
    _string(receipt["evidence_id"], "CR.evidence_id", RelationshipValidationError)
    _string(receipt["challenge_receipt_id"], "CR.challenge_receipt_id", RelationshipValidationError)
    if receipt["challenge_request_digest"] != request.get("request_digest"):
        raise RelationshipValidationError("CR.challenge_request_digest does not bind its request")
    return receipt


def _validate_acceptance_shape(value: object) -> dict[str, Any]:
    acceptance = validate_record("A", value)
    _required(
        acceptance,
        (
            "acceptance_id",
            "contract_digest",
            "accepted_stage_key",
            "candidate_bridge_id",
            "packet_id",
            "verdict_id",
            "final_candidate_evidence_id",
            "root_authority_id",
            "status",
            "root_authority_scope",
            "root_authority_expiry",
            "candidate_verify_receipt_id",
            "dependency_acceptance_ids",
        ),
        RelationshipValidationError,
    )
    for key in (
        "acceptance_id",
        "contract_digest",
        "accepted_stage_key",
        "candidate_bridge_id",
        "packet_id",
        "verdict_id",
        "final_candidate_evidence_id",
        "root_authority_id",
        "root_authority_expiry",
        "candidate_verify_receipt_id",
    ):
        _string(acceptance[key], f"A.{key}", RelationshipValidationError)
    _mapping(acceptance["dependency_acceptance_ids"], "A.dependency_acceptance_ids", RelationshipValidationError)
    _mapping(acceptance["root_authority_scope"], "A.root_authority_scope", RelationshipValidationError)
    if acceptance["status"] != "accepted":
        raise RelationshipValidationError("A.status must be accepted")
    forbidden = sorted(set(acceptance).intersection({"state", "intent", "receipt", "challenge_request_id", "future_id"}))
    if forbidden:
        raise RelationshipValidationError("A contains non-acceptance provenance: " + ", ".join(forbidden))
    return acceptance


def _utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value) is None:
        raise RelationshipValidationError(f"{label} must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise RelationshipValidationError(f"{label} must be RFC3339 UTC") from error
    if parsed.tzinfo != UTC:
        raise RelationshipValidationError(f"{label} must be RFC3339 UTC")
    return parsed


def _trusted_observation_time(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo != UTC:
            raise RelationshipValidationError("trusted_observation_time must be UTC")
        return value
    return _utc_timestamp(value, "trusted_observation_time")


def _validate_final_candidate_evidence(
    value: Mapping[str, object], *, contract: Mapping[str, object], bridge: Mapping[str, object],
    packet: Mapping[str, object], verdict: Mapping[str, object], candidate_verify_receipt: Mapping[str, object],
    trusted_observation_time: datetime,
) -> dict[str, Any]:
    evidence = validate_evidence(value, contract, "candidate", bridge["bridge_id"])
    _required(evidence, ("phase", "observed_at", "sequence", "candidate_verify_receipt_id", "candidate_verify_receipt_digest"), RelationshipValidationError)
    if evidence["phase"] != "final-candidate-verify":
        raise RelationshipValidationError("final E must be final-candidate-verify")
    final_checks = {
        key for key, check in contract["checks"].items()
        if check.get("scope") == "candidate" and check.get("final_candidate_verify") is True
        and (contract["protocol"] != STAGED_PROTOCOL_VERSION or check.get("stage_key", packet["stage_key"]) == packet["stage_key"])
    }
    if final_checks and evidence["check_key"] not in final_checks:
        raise RelationshipValidationError("final E check key is not a contract final-candidate-verify check")
    if evidence["evidence_id"] in packet["candidate_evidence_ids"]:
        raise RelationshipValidationError("final E must not reuse P pre-review evidence")
    observed_at = _utc_timestamp(evidence["observed_at"], "final E.observed_at")
    reviewed_at = _utc_timestamp(verdict.get("reviewed_at", verdict.get("created_at")), "V.reviewed_at/created_at")
    sequence = evidence["sequence"]
    review_sequence = verdict.get("review_sequence", verdict.get("created_sequence", verdict.get("sequence")))
    if isinstance(sequence, bool) or not isinstance(sequence, int) or isinstance(review_sequence, bool) or not isinstance(review_sequence, int):
        raise RelationshipValidationError("final E/V sequences must be integers")
    if observed_at <= reviewed_at or observed_at > trusted_observation_time or sequence <= review_sequence:
        raise RelationshipValidationError("final E must be after V and no later than trusted observation")
    verify = _validate_candidate_verify_receipt(candidate_verify_receipt, bridge["candidate_id"])
    verify_id = canonical_digest(verify)
    if evidence["candidate_verify_receipt_id"] != verify_id or evidence["candidate_verify_receipt_digest"] != verify_id:
        raise RelationshipValidationError("final E does not bind its actual candidate verify receipt")
    return evidence


def _validate_root_authority(
    value: Mapping[str, object], *, acceptance: Mapping[str, object], contract: Mapping[str, object],
    bridge: Mapping[str, object], candidate_verify_receipt: Mapping[str, object], trusted_observation_time: datetime,
) -> dict[str, Any]:
    authority = _mapping(value, "root authority", RelationshipValidationError)
    _required(authority, ("root_authority_id", "contract_digest", "scope", "observed_at", "expires_at", "candidate_verify_receipt_id", "candidate_verify_receipt_digest", "issuer", "observed_attestation", "observed_attestation_digest"), RelationshipValidationError)
    for key in ("root_authority_id", "contract_digest", "candidate_verify_receipt_id", "candidate_verify_receipt_digest", "observed_attestation_digest"):
        _string(authority[key], f"root authority {key}", RelationshipValidationError)
    verify = _validate_candidate_verify_receipt(candidate_verify_receipt, bridge["candidate_id"])
    verify_id = canonical_digest(verify)
    expected_scope = {"route": "full", "action": "final-accept", "stage_key": acceptance["accepted_stage_key"], "candidate_bridge_id": bridge["bridge_id"]}
    if authority["contract_digest"] != contract["contract_digest"] or authority["scope"] != expected_scope or authority["candidate_verify_receipt_id"] != verify_id or authority["candidate_verify_receipt_digest"] != verify_id:
        raise RelationshipValidationError("root authority scope or verify binding mismatch")
    issuer = _mapping(authority["issuer"], "root authority issuer", RelationshipValidationError)
    if set(issuer) != {"role", "model"} or issuer["role"] != "root":
        raise RelationshipValidationError("root authority issuer must be the observed root role")
    model = _string(issuer["model"], "root authority issuer model", RelationshipValidationError)
    attestation = _validate_observed_attestation(authority["observed_attestation"])
    if attestation["role"] != "root" or attestation["model"] != model:
        raise RelationshipValidationError("root authority issuer does not bind observed root identity")
    if authority["observed_attestation_digest"] != canonical_digest(attestation):
        raise RelationshipValidationError("root authority observed attestation digest mismatch")
    observed_control = _mapping(
        attestation["observed_attestation"], "root authority observed control", RelationshipValidationError
    )
    if set(observed_control) != {"scope", "observed_at"}:
        raise RelationshipValidationError("root authority observed control must bind scope and time")
    if observed_control["scope"] != expected_scope or observed_control["observed_at"] != authority["observed_at"]:
        raise RelationshipValidationError("root authority observed control scope/time mismatch")
    _utc_timestamp(observed_control["observed_at"], "root authority observed control observed_at")
    observed_at = _utc_timestamp(authority["observed_at"], "root authority observed_at")
    expires_at = _utc_timestamp(authority["expires_at"], "root authority expires_at")
    if observed_at > trusted_observation_time or trusted_observation_time >= expires_at:
        raise RelationshipValidationError("root authority is not valid at trusted observation time")
    return authority


def validate_acceptance(value: object, *, context: RelationshipContext, candidate_bridge: Mapping[str, object], packet: Mapping[str, object], verdict: Mapping[str, object], final_candidate_evidence: Mapping[str, object], root_authority: Mapping[str, object], candidate_verify_receipt: Mapping[str, object], task_contract: object, dependency_acceptance_contexts: Mapping[str, AcceptanceContext], trusted_observation_time: object) -> dict[str, Any]:
    return _validate_acceptance(
        value, context=context, candidate_bridge=candidate_bridge, packet=packet, verdict=verdict,
        final_candidate_evidence=final_candidate_evidence, root_authority=root_authority,
        candidate_verify_receipt=candidate_verify_receipt, task_contract=task_contract,
        dependency_acceptance_contexts=dependency_acceptance_contexts,
        trusted_observation_time=_trusted_observation_time(trusted_observation_time), active_stages=set(),
    )


def _validate_acceptance(value: object, *, context: RelationshipContext, candidate_bridge: Mapping[str, object], packet: Mapping[str, object], verdict: Mapping[str, object], final_candidate_evidence: Mapping[str, object], root_authority: Mapping[str, object], candidate_verify_receipt: Mapping[str, object], task_contract: object, dependency_acceptance_contexts: Mapping[str, AcceptanceContext], trusted_observation_time: datetime, active_stages: set[str]) -> dict[str, Any]:
    acceptance = _validate_acceptance_shape(value)
    stage_key = acceptance["accepted_stage_key"]
    if stage_key in active_stages:
        raise RelationshipValidationError("dependency acceptance contexts contain a cycle")
    active_stages.add(stage_key)
    try:
        return _validate_acceptance_inner(
            acceptance, context=context, candidate_bridge=candidate_bridge, packet=packet, verdict=verdict,
            final_candidate_evidence=final_candidate_evidence, root_authority=root_authority,
            candidate_verify_receipt=candidate_verify_receipt, task_contract=task_contract,
            dependency_acceptance_contexts=dependency_acceptance_contexts,
            trusted_observation_time=trusted_observation_time, active_stages=active_stages,
        )
    finally:
        active_stages.remove(stage_key)


def _validate_acceptance_inner(acceptance: Mapping[str, Any], *, context: RelationshipContext, candidate_bridge: Mapping[str, object], packet: Mapping[str, object], verdict: Mapping[str, object], final_candidate_evidence: Mapping[str, object], root_authority: Mapping[str, object], candidate_verify_receipt: Mapping[str, object], task_contract: object, dependency_acceptance_contexts: Mapping[str, AcceptanceContext], trusted_observation_time: datetime, active_stages: set[str]) -> dict[str, Any]:
    if not isinstance(context, RelationshipContext) or any((candidate_bridge != context.candidate_bridge, packet != context.packet, verdict != context.verdict, task_contract != context.task_contract)):
        raise RelationshipValidationError("A requires the same complete RelationshipContext")
    review_verdict = validate_relationship_context(context, target="review")
    contract = validate_task_contract(task_contract)
    bridge = _validate_candidate_bridge_context(candidate_bridge, manifest=context.manifest, manifest_bytes=context.manifest_bytes, candidate_verify_receipt=context.candidate_verify_receipt, assembly=context.assembly, deliveries=context.deliveries, materials=context.materials, delivery_evidence=context.delivery_evidence, task_contract=contract)
    review_packet = _validate_review_packet_context(packet, candidate_bridge=candidate_bridge, manifest=context.manifest, manifest_bytes=context.manifest_bytes, candidate_verify_receipt=context.candidate_verify_receipt, assembly=context.assembly, deliveries=context.deliveries, materials=context.materials, delivery_evidence=context.delivery_evidence, candidate_evidence=context.candidate_evidence or [], task_contract=contract, applicable_rejection_roots=context.applicable_rejection_roots or [], predecessor_verdicts=context.predecessor_verdicts or {}, expected_coverage=context.expected_coverage or [])
    if acceptance["contract_digest"] != contract["contract_digest"] or bridge["contract_digest"] != contract["contract_digest"] or review_packet["contract_digest"] != contract["contract_digest"] or review_verdict.get("contract_digest") != contract["contract_digest"]:
        raise RelationshipValidationError("A contract relationship mismatch")
    if acceptance["candidate_bridge_id"] != bridge.get("bridge_id") or acceptance["packet_id"] != review_packet.get("packet_id") or acceptance["verdict_id"] != review_verdict.get("verdict_id") or review_packet.get("candidate_bridge_id") != bridge.get("bridge_id") or review_verdict.get("packet_id") != review_packet.get("packet_id") or review_verdict.get("candidate_bridge_id") != bridge.get("bridge_id"):
        raise RelationshipValidationError("A predecessor relationship mismatch")
    if contract["protocol"] == STAGED_PROTOCOL_VERSION and acceptance["accepted_stage_key"] != context.assembly["stage_key"]:
        raise RelationshipValidationError("acceptance cannot relabel a reviewed stage")
    if review_verdict["status"] != "valid" or review_verdict["verdict"] != "ship" or review_verdict.get("coverage_complete") is not True or review_verdict.get("open_rejections") != []:
        raise RelationshipValidationError("A requires a valid complete ship verdict")
    final_evidence = _validate_final_candidate_evidence(final_candidate_evidence, contract=contract, bridge=bridge, packet=review_packet, verdict=review_verdict, candidate_verify_receipt=candidate_verify_receipt, trusted_observation_time=trusted_observation_time)
    if final_evidence["evidence_id"] != acceptance["final_candidate_evidence_id"] or final_evidence["result"] != "pass":
        raise RelationshipValidationError("A final candidate evidence mismatch")
    authority = _validate_root_authority(root_authority, acceptance=acceptance, contract=contract, bridge=bridge, candidate_verify_receipt=candidate_verify_receipt, trusted_observation_time=trusted_observation_time)
    if authority["root_authority_id"] != acceptance["root_authority_id"] or authority["candidate_verify_receipt_id"] != acceptance["candidate_verify_receipt_id"]:
        raise RelationshipValidationError("A root authority/verify relationship mismatch")
    if authority["scope"] != acceptance["root_authority_scope"] or authority["expires_at"] != acceptance["root_authority_expiry"]:
        raise RelationshipValidationError("A root authority scope or expiry mismatch")
    _validate_dependency_acceptance_contexts(acceptance, contract, dependency_acceptance_contexts, trusted_observation_time, active_stages)
    return dict(acceptance)


def _dependency_closure(task_contract: Mapping[str, Any], stage_key: str) -> tuple[str, ...]:
    stages = _mapping(task_contract["stages"], "stages", ContractValidationError)
    if stage_key not in stages:
        raise RelationshipValidationError(f"unknown accepted stage: {stage_key}")
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ContractValidationError("stage dependencies contain a cycle")
        if key in complete:
            return
        if key not in stages:
            raise ContractValidationError(f"stage dependency {key} is unknown")
        visiting.add(key)
        dependencies = _string_list(_mapping(stages[key], f"stage {key}", ContractValidationError).get("depends_on"), f"stage {key}.depends_on", ContractValidationError)
        for dependency in dependencies:
            visit(dependency)
            complete.add(dependency)
        visiting.remove(key)

    visit(stage_key)
    return tuple(sorted(complete))


def _validate_dependency_acceptance_contexts(acceptance: Mapping[str, Any], contract: Mapping[str, Any], contexts: Mapping[str, AcceptanceContext], trusted_observation_time: datetime, active_stages: set[str]) -> tuple[str, ...]:
    if not isinstance(contexts, Mapping):
        raise RelationshipValidationError("A dependency acceptance contexts must be a mapping")
    expected = _dependency_closure(contract, acceptance["accepted_stage_key"])
    if tuple(sorted(contexts)) != expected:
        raise RelationshipValidationError("A dependency acceptance contexts is not the exact transitive closure")
    references = _mapping(acceptance["dependency_acceptance_ids"], "A.dependency_acceptance_ids", RelationshipValidationError)
    if tuple(sorted(references)) != expected:
        raise RelationshipValidationError("A dependency_acceptance_ids is not the exact transitive closure")
    for stage_key in expected:
        dependency = contexts[stage_key]
        if not isinstance(dependency, AcceptanceContext):
            raise RelationshipValidationError(f"A dependency context for {stage_key} is incomplete")
        checked = _validate_acceptance(
            dependency.acceptance, context=dependency.relationship,
            candidate_bridge=dependency.relationship.candidate_bridge,
            packet=dependency.relationship.packet,
            verdict=dependency.relationship.verdict,
            final_candidate_evidence=dependency.final_candidate_evidence,
            root_authority=dependency.root_authority,
            candidate_verify_receipt=dependency.candidate_verify_receipt,
            task_contract=dependency.relationship.task_contract,
            dependency_acceptance_contexts=dependency.dependency_acceptance_contexts,
            # A prior stage is revalidated at its own accepted observation time.
            # Its short-lived Root authority is historical evidence, never new
            # authority for the current stage, and must not expire retroactively.
            trusted_observation_time=_trusted_observation_time(dependency.root_authority.get("observed_at")), active_stages=active_stages,
        )
        if checked["accepted_stage_key"] != stage_key or checked["acceptance_id"] != references[stage_key]:
            raise RelationshipValidationError(f"A dependency acceptance ID for {stage_key} does not match")
        if dependency.relationship.task_contract != contract:
            raise RelationshipValidationError(f"A dependency acceptance for {stage_key} has another contract")
    return expected


def validate_record_review_transition(
    before_state: object,
    verdict_record: object, *, context: RelationshipContext,
) -> dict[str, Any]:
    if not isinstance(context, RelationshipContext):
        raise StateTransitionError("record-review requires a complete RelationshipContext")
    before = validate_state(before_state)
    contract = validate_task_contract(context.task_contract)
    if before["contract_digest"] != contract["contract_digest"]:
        raise StateTransitionError("record-review state does not bind the task contract")
    if verdict_record != context.verdict:
        raise StateTransitionError("record-review verdict differs from RelationshipContext")
    verdict = validate_relationship_context(context, target="review")
    status = verdict.get("status")
    after = copy.deepcopy(before)
    if status in {"unavailable", "invalid"}:
        after["stage_status"]["review_status"] = "blocked-unavailable"
        return after
    if status != "valid":
        raise StateTransitionError("record-review status is unsupported")
    kind = verdict.get("verdict")
    if kind not in VERDICTS:
        raise StateTransitionError("valid record-review must use the verdict triad")
    verdict_id = _string(verdict.get("verdict_id"), "record-review verdict_id", StateTransitionError)
    roots = list(before["applicable_rejection_roots"])
    if kind == "fix-first":
        if not verdict.get("blocking_findings"):
            raise StateTransitionError("fix-first requires blocking findings")
        after["current_ids"]["verdict"] = verdict_id
        after["stage_status"]["review_status"] = "needs-fix"
        after["applicable_rejection_roots"] = sorted(set(roots + [verdict_id]))
        return after
    if kind == "rethink":
        after["current_ids"]["verdict"] = verdict_id
        after["stage_status"]["review_status"] = "needs-decision"
        after["applicable_rejection_roots"] = sorted(set(roots + [verdict_id]))
        return after
    closure = _string_list(verdict.get("rejection_closure"), "ship rejection_closure", StateTransitionError)
    relevant_roots = _string_list(
        context.applicable_rejection_roots, "ship applicable rejection roots", StateTransitionError
    )
    if closure != sorted(set(closure)) or not set(relevant_roots).issubset(closure):
        raise StateTransitionError("ship closure must contain every applicable active rejection root")
    if verdict.get("coverage_complete") is not True or verdict.get("open_rejections") not in ([], None):
        raise StateTransitionError("ship requires complete coverage and no open rejections")
    after["current_ids"]["verdict"] = verdict_id
    after["stage_status"]["review_status"] = "reviewed-awaiting-final-accept"
    after["applicable_rejection_roots"] = [root for root in roots if root not in set(closure)]
    return after


def validate_environment_policy(policy_value: object, child_environment: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(policy_value, list):
        raise EnvironmentPolicyError("environment policy must be a list")
    declared: dict[str, str] = {}
    for entry in policy_value:
        policy = _mapping(entry, "environment policy entry", EnvironmentPolicyError)
        name = _string(policy.get("name"), "environment name", EnvironmentPolicyError)
        if name in declared:
            raise EnvironmentPolicyError("environment policy names must be unique")
        present = policy.get("present")
        classification = policy.get("classification")
        if not isinstance(present, bool) or classification not in {"non-sensitive", "sensitive", "unclassified"}:
            raise EnvironmentPolicyError("environment policy entry is invalid")
        if present and classification == "non-sensitive":
            encoded = _string(policy.get("value_bytes_base64"), f"environment {name} value", EnvironmentPolicyError)
            try:
                declared[name] = base64.b64decode(encoded, validate=True).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as error:
                raise EnvironmentPolicyError(f"environment {name} value is not UTF-8 base64") from error
        else:
            if "value_bytes_base64" in policy:
                raise EnvironmentPolicyError("absent/sensitive environment entries must not contain bytes")
            if present:
                raise EnvironmentPolicyError("sensitive/unclassified environment is unavailable")
    if set(child_environment) != set(declared):
        raise EnvironmentPolicyError("child environment differs from exact non-secret policy")
    for name, expected in declared.items():
        if child_environment[name] != expected:
            raise EnvironmentPolicyError(f"child environment value differs for {name}")
    return dict(declared)


def validate_operation_intent(value: object) -> dict[str, Any]:
    intent = validate_record("operation-intent", value)
    _required(intent, ("op_id", "command_kind", "request_digest", "contract_digest", "expected_state_version", "planned_output_types", "planned_output_paths"), OperationConflictError)
    for key in ("op_id", "command_kind", "request_digest", "contract_digest"):
        _string(intent[key], f"intent.{key}", OperationConflictError)
    if not isinstance(intent["expected_state_version"], int) or isinstance(intent["expected_state_version"], bool) or intent["expected_state_version"] < 0:
        raise OperationConflictError("intent.expected_state_version must be a non-negative integer")
    output_types = _string_list(intent["planned_output_types"], "intent.planned_output_types", OperationConflictError)
    output_paths = _string_list(intent["planned_output_paths"], "intent.planned_output_paths", OperationConflictError)
    if len(output_types) != len(output_paths) or len(set(output_types)) != len(output_types) or len(set(output_paths)) != len(output_paths):
        raise OperationConflictError("intent planned output types/paths must be unique pairs")
    if intent["command_kind"] == "assemble" and set(output_types) != ASSEMBLE_OUTPUT_TYPES:
        raise OperationConflictError("assemble intent must declare exactly its four outputs")
    return intent


def validate_operation_receipt(value: object, intent_value: object) -> dict[str, Any]:
    receipt = validate_record("operation-receipt", value)
    intent = validate_operation_intent(intent_value)
    _required(
        receipt,
        (
            "op_id",
            "request_digest",
            "command_kind",
            "outcome",
            "side_effect",
            "actual_output_ids",
            "state_version_before",
            "state_version_after",
        ),
        OperationConflictError,
    )
    for key in ("op_id", "request_digest", "command_kind"):
        if receipt[key] != intent[key]:
            raise OperationConflictError(f"receipt {key} does not bind its operation intent")
    if receipt["outcome"] not in {"success", "failure", "ambiguous"}:
        raise OperationConflictError("receipt outcome is unsupported")
    if receipt["side_effect"] not in {"none", "durable", "unknown"}:
        raise OperationConflictError("receipt side_effect is unsupported")
    outputs = _string_list(receipt["actual_output_ids"], "receipt.actual_output_ids", OperationConflictError)
    if len(set(outputs)) != len(outputs):
        raise OperationConflictError("receipt actual_output_ids must be unique")
    if receipt["command_kind"] == "assemble" and receipt["outcome"] == "success" and len(outputs) != 4:
        raise OperationConflictError("successful assemble receipt must bind four outputs")
    for key in ("state_version_before", "state_version_after"):
        version = receipt[key]
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            raise OperationConflictError(f"receipt {key} must be a non-negative integer")
    if receipt["state_version_after"] < receipt["state_version_before"]:
        raise OperationConflictError("receipt state version cannot move backward")
    return receipt


def assert_same_operation(original_intent: object, repeated_intent: object) -> None:
    original = validate_operation_intent(original_intent)
    repeated = validate_operation_intent(repeated_intent)
    if original["op_id"] != repeated["op_id"]:
        raise OperationConflictError("operation IDs differ")
    if original["request_digest"] != repeated["request_digest"]:
        raise OperationConflictError("same operation ID cannot use a different request")
    if original != repeated:
        raise OperationConflictError("same operation ID must have an identical intent")


def classify_assemble_recovery(context: AssembleRecoveryContext) -> str:
    if not isinstance(context, AssembleRecoveryContext):
        raise ProtocolValidationError("assemble recovery requires AssembleRecoveryContext")
    intent = validate_operation_intent(context.intent)
    observed_state_version = context.observed_state_version
    expected_state_before = context.expected_state_before
    expected_state_after = context.expected_state_after
    if intent["command_kind"] != "assemble" or intent["expected_state_version"] != expected_state_before:
        raise ProtocolValidationError("assemble recovery intent does not bind expected-before state")
    if not isinstance(observed_state_version, int) or isinstance(observed_state_version, bool):
        raise ProtocolValidationError("observed state version must be an integer")
    observed = context.observed_outputs
    if observed is not None:
        if not isinstance(observed, Mapping) or set(observed) != ASSEMBLE_OUTPUT_TYPES or any(type(present) is not bool for present in observed.values()):
            raise ProtocolValidationError("assemble recovery must explicitly represent the four output observations")
        if not any(observed.values()):
            if context.receipt is None and observed_state_version == expected_state_before:
                return "failure-receipt-new-operation"
            return "ambiguous"
        if not all(observed.values()):
            return "ambiguous"
    bridge = validate_relationship_context(context.relationship, target="candidate")
    assembly = validate_assembly_index(context.assembly)
    output = _mapping(context.output_identity, "assemble output identity", ProtocolValidationError)
    if (
        assembly != context.relationship.assembly
        or assembly["candidate_bridge_id"] != bridge.get("bridge_id")
        or output.get("assembly_id") != assembly["assembly_id"]
    ):
        return "ambiguous"
    if set(output) != {"output_identity_id", "assembly_id"}:
        return "ambiguous"
    if output["output_identity_id"] != assembly["output_identity_id"]:
        return "ambiguous"
    receipt = None if context.receipt is None else validate_operation_receipt(context.receipt, intent)
    if observed_state_version == expected_state_before:
        if receipt is not None:
            return "ambiguous"
        return "cas-then-receipt"
    if observed_state_version != expected_state_after:
        return "ambiguous"
    if receipt is None:
        return "receipt-only"
    if receipt["state_version_before"] != expected_state_before or receipt["state_version_after"] != expected_state_after:
        return "ambiguous"
    if set(receipt["actual_output_ids"]) != {
        assembly["assembly_id"], output["output_identity_id"],
        assembly["schema2_manifest_id"], bridge["bridge_id"],
    }:
        return "ambiguous"
    return "complete"


def _validate_not_started_run_receipt(value: object, request: Mapping[str, object]) -> dict[str, Any]:
    receipt = validate_record("run-check-receipt", value)
    required = {
        "record_type", "challenge_request_id", "challenge_request_digest", "packet_id",
        "candidate_bridge_id", "outcome",
    }
    if set(receipt) != required:
        raise RelationshipValidationError("nested run-check receipt must have exactly its bound fields")
    if receipt["outcome"] != "not-started":
        raise RelationshipValidationError("nested run-check receipt must prove not-started")
    for key, expected in (
        ("challenge_request_id", request["request_id"]),
        ("challenge_request_digest", request["request_digest"]),
        ("packet_id", request["packet_id"]),
        ("candidate_bridge_id", request["candidate_bridge_id"]),
    ):
        if receipt[key] != expected:
            raise RelationshipValidationError(f"nested run-check receipt {key} does not bind its request")
        _string(receipt[key], f"nested run-check receipt {key}", RelationshipValidationError)
    return receipt


def _validate_challenge_evidence(
    value: object, request: Mapping[str, object], task_contract: object,
) -> dict[str, Any]:
    evidence = validate_evidence(
        value, task_contract, "challenge",
        f"{request['packet_id']}:{request['candidate_bridge_id']}",
    )
    if evidence["check_key"] != request["check_key"]:
        raise RelationshipValidationError("challenge E check_key does not bind its request")
    if evidence.get("challenge_request_id") != request["request_id"]:
        raise RelationshipValidationError("challenge E does not bind its request ID")
    if evidence.get("challenge_request_digest") != request["request_digest"]:
        raise RelationshipValidationError("challenge E does not bind its request digest")
    if evidence["result"] == "incomplete":
        raise RelationshipValidationError("incomplete challenge E cannot be recovered")
    return evidence


def classify_challenge_recovery(context: ChallengeRecoveryContext) -> str:
    """Classify recovery from complete immutable facts; ambiguity never reruns work."""

    if not isinstance(context, ChallengeRecoveryContext):
        raise ProtocolValidationError("challenge recovery requires ChallengeRecoveryContext")
    try:
        packet = validate_relationship_context(context.relationship, target="packet")
        request = validate_challenge_request(context.request, context.relationship.task_contract)
        bridge = context.relationship.candidate_bridge
        if (
            request["packet_id"] != packet["packet_id"]
            or request["candidate_bridge_id"] != bridge["bridge_id"]
        ):
            return "ambiguous"
        if context.evidence is None:
            if context.challenge_receipt is not None:
                return "ambiguous"
            _validate_not_started_run_receipt(context.nested_run_receipt, request)
            return "start-probe-once"
        if context.nested_run_receipt is not None:
            return "ambiguous"
        evidence = _validate_challenge_evidence(
            context.evidence, request, context.relationship.task_contract,
        )
        if context.challenge_receipt is None:
            return "publish-cr-only"
        receipt = validate_challenge_receipt(context.challenge_receipt, request)
        if receipt["evidence_id"] != evidence["evidence_id"]:
            return "ambiguous"
        return "complete"
    except ProtocolValidationError:
        return "ambiguous"
