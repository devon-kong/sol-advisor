from __future__ import annotations

import importlib
import hashlib
import json
import os
import re
import subprocess
import sys
from fixture_support import fixture_directory
from dataclasses import replace
from pathlib import Path
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CANDIDATE_SCRIPT = SCRIPTS / "candidate.py"
RUN_CHECK_SCRIPT = SCRIPTS / "run-check.py"
TEST_ARTIFACTS = Path(__file__).resolve().parents[3] / ".agent-artifacts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

try:
    full_protocol = importlib.import_module("full_protocol")
except ModuleNotFoundError:
    full_protocol = None


CB_ID = "cb-001"
PACKET_ID = "packet-001"
VERDICT_ID = "verdict-001"


def digest(value: object, *, without: tuple[str, ...] = ()) -> str:
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key not in without}
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def contract() -> dict[str, object]:
    value = {
        "protocol": "SA-FULL-V2-P1",
        "goal": "Validate the full-only route.",
        "authority": {"allowed_paths": ["plugins/sol-advisor"]},
        "preserved_behavior": ["solo", "delegate", "audit"],
        "excluded_behavior": ["network", "credentials"],
        "stages": {
            "p1": {"depends_on": []},
            "p2": {"depends_on": ["p1"]},
            "p3": {"depends_on": ["p2"]},
        },
        "work_items": {"p1": {"paths": ["plugins/sol-advisor/scripts/full_protocol.py"]}},
        "checks": {"delivery": {"scope": "delivery"}, "candidate": {"scope": "candidate"}, "challenge": {"scope": "challenge"}},
        "environment_policy": [],
        "required_coverage": ["delivery", "candidate"],
        "review_policy": {"allowed_verdicts": ["ship", "fix-first", "rethink"]},
    }
    value["contract_digest"] = digest(value)
    return value


CONTRACT_DIGEST = contract()["contract_digest"]


def state(roots: list[str] | None = None) -> dict[str, object]:
    return {
        "version": 7,
        "contract_digest": CONTRACT_DIGEST,
        "stage_status": {"review_status": "reviewing"},
        "work_status": {"p1": "ready"},
        "selected_attempts": {"p1": "attempt-1"},
        "current_ids": {"verdict": None},
        "applicable_rejection_roots": list(roots or []),
        "last_operation_receipt": None,
    }


class FullProtocolTests(unittest.TestCase):
    """Contract-level counterexamples for the pure P1 protocol seam.

    Each test names a realistic accidental weakening it must catch; the fixtures are
    deliberately hand-written rather than built by the code under test.
    """

    def protocol(self):
        self.assertIsNotNone(full_protocol, "full_protocol module is missing")
        return full_protocol

    def test_module_exports_stable_protocol_identity(self) -> None:
        protocol = self.protocol()
        self.assertEqual(protocol.PROTOCOL_VERSION, "SA-FULL-V2-P1")
        self.assertEqual(protocol.VERDICTS, frozenset({"ship", "fix-first", "rethink"}))
        self.assertEqual(protocol.REVIEW_STATUSES, frozenset({"reviewing", "needs-fix", "needs-decision", "reviewed-awaiting-final-accept", "blocked-unavailable"}))

    def test_canonical_hash_is_order_independent_and_rejects_non_json_input(self) -> None:
        protocol = self.protocol()
        self.assertEqual(
            protocol.canonical_digest({"b": [2], "a": 1}),
            protocol.canonical_digest({"a": 1, "b": [2]}),
        )
        with self.assertRaises(protocol.ProtocolValidationError):
            protocol.canonical_digest({"bad": {1, 2}})

    def test_canonical_component_rejects_path_aliases_and_keeps_valid_identifier(self) -> None:
        protocol = self.protocol()
        self.assertEqual(protocol.canonical_component("run-01", "run_id"), "run-01")
        for value in ("", ".", "..", "../escape", "/tmp/escape", "a/b", "a\\b", "C:\\escape", "//server/share", "a\x00b", "e\u0301"):
            with self.subTest(value=value):
                with self.assertRaises(protocol.ProtocolValidationError):
                    protocol.canonical_component(value, "run_id")

    def test_rejects_unsupported_protocol_and_record_type(self) -> None:
        protocol = self.protocol()
        bad_contract = contract()
        bad_contract["protocol"] = "SA-FULL-V1"
        with self.assertRaises(protocol.UnsupportedProtocolError):
            protocol.validate_task_contract(bad_contract)
        with self.assertRaises(protocol.UnsupportedRecordError):
            protocol.validate_record("report", {})
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record("D", {})

    def test_non_full_route_cannot_carry_full_progress_state(self) -> None:
        protocol = self.protocol()
        with self.assertRaises(protocol.RouteCompatibilityError):
            protocol.validate_route_state("solo", state())
        self.assertEqual(protocol.validate_route_state("solo", {"route": "solo"})["route"], "solo")

    def test_contract_and_progress_are_strictly_separate(self) -> None:
        protocol = self.protocol()
        self.assertEqual(protocol.validate_task_contract(contract())["contract_digest"], CONTRACT_DIGEST)
        polluted = contract()
        polluted["state"] = state()
        with self.assertRaises(protocol.ContractValidationError):
            protocol.validate_task_contract(polluted)
        with self.assertRaises(protocol.StateValidationError):
            protocol.validate_state({"version": 1, "contract_digest": CONTRACT_DIGEST, "candidate_binding": CB_ID})

    def test_new_behavioral_contract_requires_tag_and_prompt_discriminator(self) -> None:
        protocol = self.protocol()
        value = contract()
        value["review_policy"] = {
            "allowed_verdicts": ["ship", "fix-first", "rethink"],
            "review_identity_schema": "SA-REVIEW-ATTESTATION-1",
            "isolation_admission": "hard-or-behavioral",
        }
        value["contract_digest"] = digest({key: item for key, item in value.items() if key != "contract_digest"})
        with self.assertRaises(protocol.ContractValidationError):
            protocol.validate_task_contract(value)

    def test_tagged_hard_attestation_recomputes_its_own_digest(self) -> None:
        protocol = self.protocol()
        value = contract()
        value["review_policy"] = {
            "allowed_verdicts": ["ship", "fix-first", "rethink"],
            "review_identity_schema": "SA-REVIEW-ATTESTATION-1",
            "isolation_admission": "hard-read-only",
        }
        value["contract_digest"] = digest({key: item for key, item in value.items() if key != "contract_digest"})
        attestation = {
            "schema": "SA-REVIEW-ATTESTATION-1", "mode": "hard-read-only",
            "reviewer": {
                "thread_id": "sol-1", "context_id": "sol-context-1", "context_source": "observed-context",
                "role": "sol_advisor_sol_reviewer", "model": "gpt-6-sol", "effort": "xhigh",
                "runtime_receipt_digest": "sha256:" + "1" * 64,
            },
            "observed": {"sandbox_policy_type": "read-only", "permission_profile": "disabled", "prompt_digest": "sha256:" + "2" * 64},
            "windows": [],
        }
        attestation["attestation_digest"] = digest(attestation)
        self.assertEqual(protocol.validate_review_attestation(attestation, value)["attestation_digest"], attestation["attestation_digest"])
        attestation["observed"]["permission_profile"] = "broader"
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_review_attestation(attestation, value)

    def test_behavioral_tag_requires_stable_candidate_and_tree_windows(self) -> None:
        protocol = self.protocol()
        value = contract()
        prompt = "sha256:" + "3" * 64
        value["review_policy"] = {
            "allowed_verdicts": ["ship", "fix-first", "rethink"],
            "review_identity_schema": "SA-REVIEW-ATTESTATION-1",
            "isolation_admission": "hard-or-behavioral",
            "behavioral_read_only_prompt_digest": prompt,
        }
        value["contract_digest"] = digest({key: item for key, item in value.items() if key != "contract_digest"})
        candidate_identity = {"candidate_id": "sha256:" + "4" * 64, "manifest_hash": "sha256:" + "5" * 64, "verify_receipt_digest": "sha256:" + "6" * 64}
        attestation = {
            "schema": "SA-REVIEW-ATTESTATION-1", "mode": "behavioral-window",
            "reviewer": {"thread_id": "sol-1", "context_id": "sol-1", "context_source": "verified-thread-id", "role": "sol_advisor_sol_reviewer", "model": "gpt-6-sol", "effort": "xhigh", "runtime_receipt_digest": "sha256:" + "7" * 64},
            "observed": {"sandbox_policy_type": "danger-full-access", "permission_profile": "disabled", "prompt_digest": prompt},
            "windows": [{"candidate_before": candidate_identity, "candidate_after": candidate_identity, "task_tree_before": "sha256:" + "8" * 64, "task_tree_after": "sha256:" + "8" * 64}],
        }
        attestation["attestation_digest"] = digest(attestation)
        protocol.validate_review_attestation(attestation, value)
        attestation["windows"][0]["task_tree_after"] = "sha256:" + "9" * 64
        attestation["attestation_digest"] = digest(attestation)
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_review_attestation(attestation, value)

    def test_delivery_rejects_material_drift_and_resource_overlap(self) -> None:
        protocol = self.protocol()
        material = {
            "record_type": "M",
            "material_id": "M-1",
            "contract_digest": CONTRACT_DIGEST,
            "work_key": "p1",
            "baseline_id": "base",
            "ready_identity": "ready-1",
            "bundle": {"files": ["plugins/sol-advisor/scripts/full_protocol.py"]},
        }
        material["material_digest"] = digest(material)
        delivery = {
            "record_type": "D",
            "delivery_id": "D-1",
            "contract_digest": CONTRACT_DIGEST,
            "work_key": "p1",
            "baseline_id": "base",
            "ready_identity": "ready-1",
            "material_id": "M-1",
            "material_digest": "sha256:" + "2" * 64,
            "delivery_evidence_id": "E-delivery-1",
            "attestation": {"self_review": "complete"},
        }
        delivery["delivery_digest"] = digest(delivery)
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_delivery(delivery, material, contract(), {"work_key": "p1", "paths": ["plugins/sol-advisor/scripts/full_protocol.py"]})
        delivery["material_digest"] = material["material_digest"]
        delivery["delivery_digest"] = digest(delivery)
        material["bundle"]["files"] = ["plugins/sol-advisor/scripts/candidate.py"]
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_delivery(delivery, material, contract(), {"work_key": "p1", "paths": ["plugins/sol-advisor/scripts/full_protocol.py"]})

    def test_evidence_scope_cannot_be_swapped(self) -> None:
        protocol = self.protocol()
        evidence = {
            "record_type": "E",
            "evidence_id": "E-1",
            "contract_digest": CONTRACT_DIGEST,
            "scope": "candidate",
            "subject_id": CB_ID,
            "check_key": "candidate",
            "harness_identity": "harness-1",
            "environment_identity": "env-1",
            "runtime_identity": "runtime-1",
            "result": "pass",
            "logs": [],
        }
        evidence["evidence_digest"] = digest(evidence)
        self.assertEqual(
            protocol.validate_evidence(evidence, contract(), "candidate", CB_ID)["subject_id"],
            CB_ID,
        )
        evidence["subject_id"] = "material-1"
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_evidence(evidence, contract(), "candidate", CB_ID)
        evidence["subject_id"] = CB_ID
        evidence["check_key"] = ["candidate"]
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_evidence(evidence, contract(), "candidate", CB_ID)

    def test_schema_two_candidate_bridge_must_match_manifest_and_inputs(self) -> None:
        protocol = self.protocol()
        bridge = {
            "record_type": "CB",
            "contract_digest": CONTRACT_DIGEST,
            "manifest_schema_version": 2,
            "candidate_id": "sha256:" + "4" * 64,
            "manifest_candidate_id": "sha256:" + "5" * 64,
            "selection_policy": "retained",
            "assembly_id": "I-1",
            "delivery_ids": ["D-1"],
            "material_ids": ["M-1"],
            "explicit_inputs": {"I": "/I.json", "D": "/D.json", "M": "/M.json", "bundle": "/bundle.json"},
            "correspondence_digest": "sha256:" + "6" * 64,
        }
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol._validate_candidate_bridge_shape(bridge)
        bridge["manifest_candidate_id"] = bridge["candidate_id"]
        self.assertEqual(protocol._validate_candidate_bridge_shape(bridge)["candidate_id"], bridge["candidate_id"])

    def test_assembly_index_rejects_duplicate_delivery_or_material_attempts(self) -> None:
        protocol = self.protocol()
        assembly = {
            "record_type": "I",
            "assembly_id": "I-1",
            "contract_digest": CONTRACT_DIGEST,
            "baseline_id": "base-1",
            "delivery_ids": ["D-1"],
            "material_ids": ["M-1"],
            "output_identity_id": "output-1",
            "schema2_manifest_id": "manifest-1",
            "candidate_bridge_id": CB_ID,
        }
        self.assertEqual(protocol.validate_assembly_index(assembly)["assembly_id"], "I-1")
        assembly["delivery_ids"] = ["D-1", "D-1"]
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_assembly_index(assembly)

    def test_review_packet_rejects_self_binding_and_design_review_is_not_verdict(self) -> None:
        protocol = self.protocol()
        packet = {
            "record_type": "P",
            "packet_id": PACKET_ID,
            "contract_digest": CONTRACT_DIGEST,
            "candidate_bridge_id": CB_ID,
            "assembly_id": "I-1",
            "delivery_ids": ["D-1"],
            "candidate_evidence_ids": ["E-1"],
            "coverage": {"complete": True},
            "rejection_roots": [],
        }
        self.assertEqual(protocol._validate_review_packet_shape(packet)["packet_id"], PACKET_ID)
        packet["candidate_bridge_id"] = PACKET_ID
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol._validate_review_packet_shape(packet)
        with self.assertRaises(protocol.VerdictValidationError):
            protocol._validate_verdict_shape({"record_type": "V", "status": "valid", "verdict": "design-approved"})

    def test_valid_verdict_requires_challenge_receipt_but_unavailable_keeps_verdict_null(self) -> None:
        protocol = self.protocol()
        verdict = {
            "record_type": "V",
            "verdict_id": VERDICT_ID,
            "contract_digest": CONTRACT_DIGEST,
            "status": "valid",
            "verdict": "ship",
            "packet_id": PACKET_ID,
            "candidate_bridge_id": CB_ID,
            "challenge_receipt_id": None,
            "rejection_closure": [],
            "coverage_complete": True,
        }
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol._validate_verdict_shape(verdict)
        verdict["challenge_receipt_id"] = "CR-1"
        self.assertEqual(protocol._validate_verdict_shape(verdict)["verdict"], "ship")
        unavailable = dict(verdict, status="unavailable", verdict=None, challenge_receipt_id=None)
        self.assertIsNone(protocol._validate_verdict_shape(unavailable)["verdict"])

    def test_design_review_is_separate_and_challenge_receipt_binds_request_packet_cb_and_evidence(self) -> None:
        protocol = self.protocol()
        design_review = {
            "record_type": "DR",
            "status": "valid",
            "design_verdict": "design-approved",
            "contract_digest": CONTRACT_DIGEST,
        }
        self.assertEqual(protocol.validate_design_review(design_review)["design_verdict"], "design-approved")
        design_review["candidate_bridge_id"] = CB_ID
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_design_review(design_review)
        request = {
            "record_type": "challenge-request",
            "request_id": "challenge-1",
            "request_digest": "",
            "contract_digest": CONTRACT_DIGEST,
            "packet_id": PACKET_ID,
            "candidate_bridge_id": CB_ID,
            "check_key": "challenge",
            "authority_decision": "allowed",
        }
        request["request_digest"] = digest(request, without=("request_digest",))
        self.assertEqual(protocol.validate_challenge_request(request, contract())["request_id"], "challenge-1")
        receipt = {
            "record_type": "CR",
            "challenge_receipt_id": "CR-1",
            "challenge_request_id": "challenge-1",
            "packet_id": PACKET_ID,
            "candidate_bridge_id": CB_ID,
            "evidence_id": "E-challenge-1",
            "challenge_request_digest": request["request_digest"],
        }
        self.assertEqual(protocol.validate_challenge_receipt(receipt, request)["evidence_id"], "E-challenge-1")
        receipt["packet_id"] = "packet-other"
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_challenge_receipt(receipt, request)

    def test_dependency_closure_is_transitive_and_cycle_safe(self) -> None:
        protocol = self.protocol()
        self.assertEqual(protocol._dependency_closure(contract(), "p3"), ("p1", "p2"))
        cyclic = contract()
        cyclic["stages"] = {"p1": {"depends_on": ["p2"]}, "p2": {"depends_on": ["p1"]}}
        cyclic["contract_digest"] = digest({key: value for key, value in cyclic.items() if key != "contract_digest"})
        with self.assertRaises(protocol.ProtocolValidationError):
            protocol._dependency_closure(cyclic, "p1")

    def test_acceptance_requires_final_candidate_review_and_root_authority_bindings(self) -> None:
        protocol = self.protocol()
        acceptance = {
            "record_type": "A",
            "acceptance_id": "A-p3",
            "status": "accepted",
            "contract_digest": CONTRACT_DIGEST,
            "accepted_stage_key": "p3",
            "candidate_bridge_id": CB_ID,
            "packet_id": PACKET_ID,
            "verdict_id": VERDICT_ID,
            "final_candidate_evidence_id": "E-final-1",
            "root_authority_id": "root-auth-1",
            "root_authority_scope": {"action": "final-accept"},
            "root_authority_expiry": "2099-01-01T00:00:00Z",
            "candidate_verify_receipt_id": "verify-1",
            "dependency_acceptance_ids": {"p1": "A-p1", "p2": "A-p2"},
        }
        self.assertEqual(protocol._validate_acceptance_shape(acceptance)["acceptance_id"], "A-p3")
        acceptance["root_authority_id"] = None
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol._validate_acceptance_shape(acceptance)

    def test_record_review_transitions_preserve_and_close_only_declared_roots(self) -> None:
        protocol = self.protocol()
        f = ProtocolFixture()
        before = state(["V-old", "V-other"])
        fix_first = {"record_type": "V", "status": "valid", "verdict": "fix-first", "verdict_id": VERDICT_ID, "contract_digest": CONTRACT_DIGEST, "packet_id": "P-1", "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-1", "rejection_closure": ["V-old", "V-other"], "rejection_dispositions": {"V-old": "open", "V-other": "open"}, "coverage_complete": True, "blocking_findings": ["F-1"]}
        after_fix = protocol.validate_record_review_transition(
            before, fix_first, context=complete_review_context(f, fix_first, ["V-old", "V-other"])
        )
        self.assertEqual(after_fix["applicable_rejection_roots"], ["V-old", "V-other", VERDICT_ID])
        self.assertEqual(after_fix["stage_status"]["review_status"], "needs-fix")
        ship = {"record_type": "V", "status": "valid", "verdict": "ship", "verdict_id": "V-ship", "contract_digest": CONTRACT_DIGEST, "packet_id": "P-1", "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-1", "rejection_closure": ["V-old", "V-other"], "rejection_dispositions": {"V-old": "resolved", "V-other": "resolved"}, "coverage_complete": True, "open_rejections": []}
        after_ship = protocol.validate_record_review_transition(
            before, ship, context=complete_review_context(f, ship, ["V-old", "V-other"])
        )
        self.assertEqual(after_ship["applicable_rejection_roots"], [])
        invalid_ship = dict(ship, rejection_closure=["V-unrelated"])
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(
                before, invalid_ship,
                context=complete_review_context(f, invalid_ship, ["V-old", "V-other"]),
            )

    def test_ship_closes_active_root_through_ancestor_without_removing_unrelated_root(self) -> None:
        protocol = self.protocol()
        f = ProtocolFixture()
        before = state(["V-root", "V-unrelated"])
        predecessors = {
            "V-root": {
                "record_type": "V", "verdict_id": "V-root", "contract_digest": CONTRACT_DIGEST,
                "status": "valid", "verdict": "fix-first", "packet_id": "P-prior",
                "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-prior",
                "rejection_closure": ["V-old"], "coverage_complete": True,
            },
            "V-old": {
                "record_type": "V", "verdict_id": "V-old", "contract_digest": CONTRACT_DIGEST,
                "status": "valid", "verdict": "fix-first", "packet_id": "P-prior",
                "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-prior",
                "rejection_closure": [], "coverage_complete": True,
            },
            "V-unrelated": {
                "record_type": "V", "verdict_id": "V-unrelated", "contract_digest": CONTRACT_DIGEST,
                "status": "valid", "verdict": "fix-first", "packet_id": "P-prior",
                "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-prior",
                "rejection_closure": [], "coverage_complete": True,
            },
        }
        packet = {
            "record_type": "P", "packet_id": "P-1", "contract_digest": CONTRACT_DIGEST,
            "candidate_bridge_id": f.bridge["bridge_id"], "assembly_id": f.assembly["assembly_id"],
            "delivery_ids": [f.delivery["delivery_id"]], "candidate_evidence_ids": ["E-candidate-1"],
            "coverage": {"complete": True, "checks": ["candidate"], "required_scopes": ["delivery", "candidate"]},
            "rejection_roots": ["V-root"],
            "rejection_closure": ["V-old", "V-root"],
        }
        ship = {
            "record_type": "V", "verdict_id": "V-ship", "contract_digest": CONTRACT_DIGEST,
            "status": "valid", "verdict": "ship", "packet_id": "P-1",
            "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-1",
            "rejection_closure": ["V-old", "V-root"], "coverage_complete": True,
            "rejection_dispositions": {"V-old": "resolved", "V-root": "resolved"},
            "open_rejections": [],
        }
        request = challenge_request(f, packet)
        evidence = challenge_evidence(request)
        receipt = challenge_receipt(request, evidence)
        attestation = {
            "context_id": "context-1", "thread_id": "thread-1", "role": "sol_advisor_sol_reviewer",
            "model": "gpt-6-sol", "effort": "xhigh", "observed_attestation": {"observed": True},
        }
        ship["observed_attestation_digest"] = digest(attestation)
        context = f.context(
            packet=packet, candidate_evidence=[candidate_evidence(f)],
            applicable_rejection_roots=["V-root"], predecessor_verdicts={key: predecessors[key] for key in ("V-root", "V-old")},
            expected_coverage=["delivery", "candidate"], challenge_request=request,
            challenge_evidence=evidence, challenge_receipt=receipt, verdict=ship,
            observed_attestation=attestation,
        )
        after = protocol.validate_record_review_transition(before, ship, context=context)
        self.assertEqual(after["stage_status"]["review_status"], "reviewed-awaiting-final-accept")
        self.assertEqual(after["applicable_rejection_roots"], ["V-unrelated"])

        omitted_root = dict(ship, rejection_closure=["V-old"])
        omitted_root["observed_attestation_digest"] = digest(attestation)
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(
                before, omitted_root,
                context=f.context(
                    packet=packet, candidate_evidence=[candidate_evidence(f)],
                    applicable_rejection_roots=["V-root"], predecessor_verdicts={key: predecessors[key] for key in ("V-root", "V-old")},
                    expected_coverage=["delivery", "candidate"], challenge_request=request,
                    challenge_evidence=evidence, challenge_receipt=receipt, verdict=omitted_root,
                    observed_attestation=attestation,
                ),
            )

    def test_environment_policy_rejects_sensitive_and_extra_variables(self) -> None:
        protocol = self.protocol()
        policy = [{"name": "SAFE", "present": True, "classification": "non-sensitive", "value_bytes_base64": "b2s="}]
        self.assertEqual(protocol.validate_environment_policy(policy, {"SAFE": "ok"})["SAFE"], "ok")
        with self.assertRaises(protocol.EnvironmentPolicyError):
            protocol.validate_environment_policy(policy, {"SAFE": "ok", "EXTRA": "no"})
        sensitive = [{"name": "TOKEN", "present": True, "classification": "sensitive"}]
        with self.assertRaises(protocol.EnvironmentPolicyError):
            protocol.validate_environment_policy(sensitive, {"TOKEN": "secret"})

    def test_same_operation_cannot_change_request_and_partial_assemble_is_ambiguous(self) -> None:
        protocol = self.protocol()
        f = ProtocolFixture()
        intent = {"record_type": "operation-intent", "op_id": "op-1", "command_kind": "assemble", "request_digest": "sha256:" + "7" * 64, "contract_digest": CONTRACT_DIGEST, "expected_state_version": 1, "planned_output_types": ["I", "output-identity", "schema2-manifest", "CB"], "planned_output_paths": ["i.json", "output.json", "manifest.json", "cb.json"]}
        self.assertEqual(protocol.validate_operation_intent(intent)["op_id"], "op-1")
        receipt = {"record_type": "operation-receipt", "op_id": "op-1", "request_digest": intent["request_digest"], "command_kind": "assemble", "outcome": "success", "side_effect": "durable", "actual_output_ids": ["I-1", "output-1", "manifest-1", CB_ID], "state_version_before": 1, "state_version_after": 2}
        self.assertEqual(protocol.validate_operation_receipt(receipt, intent)["outcome"], "success")
        receipt["request_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(protocol.OperationConflictError):
            protocol.validate_operation_receipt(receipt, intent)
        with self.assertRaises(protocol.OperationConflictError):
            protocol.assert_same_operation(intent, dict(intent, request_digest="sha256:" + "8" * 64))
        recovery = protocol.classify_assemble_recovery(protocol.AssembleRecoveryContext(
            relationship=f.context(), intent=intent, assembly=f.assembly,
            output_identity={"assembly_id": f.assembly["assembly_id"]}, receipt=None,
            observed_state_version=1, expected_state_before=1, expected_state_after=2,
        ))
        self.assertEqual(recovery, "ambiguous")


class ReviewerCounterexampleTests(unittest.TestCase):
    """Wrong/valid neighbors from review-1; these must exercise real relationships."""

    def protocol(self):
        self.assertIsNotNone(full_protocol, "full_protocol module is missing")
        return full_protocol

    def test_contract_digest_is_the_canonical_preimage_not_a_digest_shaped_string(self) -> None:
        protocol = self.protocol()
        valid = contract()
        self.assertEqual(protocol.validate_task_contract(valid)["contract_digest"], valid["contract_digest"])
        tampered = contract()
        tampered["goal"] = "A different authorized goal."
        with self.assertRaises(protocol.ContractValidationError):
            protocol.validate_task_contract(tampered)

    def test_delivery_and_evidence_require_actual_context_not_self_reported_strings(self) -> None:
        protocol = self.protocol()
        material = {
            "record_type": "M",
            "material_id": "M-1",
            "contract_digest": CONTRACT_DIGEST,
            "work_key": "p1",
            "baseline_id": "base-1",
            "ready_identity": "ready-1",
            "bundle": {"files": ["plugins/sol-advisor/scripts/full_protocol.py"]},
        }
        material["material_digest"] = digest(material)
        delivery = {
            "record_type": "D",
            "delivery_id": "D-1",
            "contract_digest": CONTRACT_DIGEST,
            "work_key": "p1",
            "baseline_id": "base-1",
            "ready_identity": "ready-1",
            "material_id": "M-1",
            "material_digest": material["material_digest"],
            "delivery_evidence_id": "E-delivery-1",
            "attestation": {"self_review": "complete"},
        }
        delivery["delivery_digest"] = digest(delivery)
        expected_work = {"work_key": "p1", "paths": ["plugins/sol-advisor/scripts/full_protocol.py"]}
        self.assertEqual(protocol.validate_delivery(delivery, material, contract(), expected_work)["delivery_id"], "D-1")
        missing_delivery_evidence = dict(delivery)
        missing_delivery_evidence.pop("delivery_evidence_id")
        missing_delivery_evidence["delivery_digest"] = digest(
            missing_delivery_evidence, without=("delivery_digest",)
        )
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_delivery(missing_delivery_evidence, material, contract(), expected_work)
        material["bundle"]["files"] = ["plugins/sol-advisor/scripts/candidate.py"]
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_delivery(delivery, material, contract(), expected_work)

        evidence = {
            "record_type": "E",
            "evidence_id": "E-candidate-1",
            "contract_digest": CONTRACT_DIGEST,
            "scope": "candidate",
            "subject_id": CB_ID,
            "check_key": "candidate",
            "harness_identity": "harness-1",
            "environment_identity": "env-1",
            "runtime_identity": "runtime-1",
            "result": "pass",
            "logs": [],
        }
        evidence["evidence_digest"] = digest(evidence)
        self.assertEqual(protocol.validate_evidence(evidence, contract(), "candidate", CB_ID)["evidence_id"], "E-candidate-1")
        evidence["subject_id"] = "self-reported-other"
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_evidence(evidence, contract(), "candidate", CB_ID)

    def test_transition_rejects_incomplete_or_unavailable_verdict_before_mutating_roots(self) -> None:
        protocol = self.protocol()
        f = ProtocolFixture()
        before = state(["V-old"])
        unavailable = {"record_type": "V", "status": "unavailable", "verdict": "ship"}
        with self.assertRaises(protocol.VerdictValidationError):
            protocol.validate_record_review_transition(
                before, unavailable, context=complete_review_context(f, unavailable, ["V-old"])
            )

    def test_unavailable_and_invalid_review_transitions_keep_valid_verdict_and_roots(self) -> None:
        protocol = self.protocol()
        f = ProtocolFixture()
        before = state(["V-existing"])
        before["current_ids"]["verdict"] = "V-existing"

        def context_for(status: str, *, verdict_override=None, attestation_override=None):
            attestation = attestation_override or {
                "context_id": "context-unavailable", "thread_id": "thread-unavailable",
                "role": "sol_advisor_sol_reviewer", "model": "gpt-6-sol", "effort": "xhigh",
                "observed_attestation": {"observed": True},
            }
            verdict = verdict_override or {
                "record_type": "V", "verdict_id": "V-" + status,
                "contract_digest": CONTRACT_DIGEST, "candidate_bridge_id": f.bridge["bridge_id"],
                "status": status, "verdict": None,
                "observed_attestation_digest": digest(attestation),
            }
            return verdict, f.context(verdict=verdict, observed_attestation=attestation)

        for status in ("unavailable", "invalid"):
            with self.subTest(status=status):
                verdict, context = context_for(status)
                after = protocol.validate_record_review_transition(before, verdict, context=context)
                self.assertEqual(after["stage_status"]["review_status"], "blocked-unavailable")
                self.assertEqual(after["current_ids"]["verdict"], "V-existing")
                self.assertEqual(after["applicable_rejection_roots"], ["V-existing"])

        verdict, context = context_for("unavailable")
        missing_attestation = dict(verdict)
        missing_attestation.pop("observed_attestation_digest")
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(before, missing_attestation, context=f.context(verdict=missing_attestation, observed_attestation=context.observed_attestation))

        wrong_reviewer = dict(context.observed_attestation, role="sol_advisor_sol_implementer")
        wrong_reviewer["observed_attestation"] = {"observed": True}
        wrong_verdict, _ = context_for(
            "unavailable", attestation_override=wrong_reviewer,
        )
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(before, wrong_verdict, context=f.context(verdict=wrong_verdict, observed_attestation=wrong_reviewer))

        missing_model = dict(context.observed_attestation)
        missing_model.pop("model")
        missing_model_verdict, _ = context_for("invalid", attestation_override=missing_model)
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(before, missing_model_verdict, context=f.context(verdict=missing_model_verdict, observed_attestation=missing_model))

        wrong_effort = dict(context.observed_attestation, effort="medium")
        wrong_effort_verdict, _ = context_for(
            "unavailable", attestation_override=wrong_effort
        )
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(
                before,
                wrong_effort_verdict,
                context=f.context(
                    verdict=wrong_effort_verdict,
                    observed_attestation=wrong_effort,
                ),
            )

        wrong_contract = dict(verdict, contract_digest="sha256:" + "0" * 64)
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(
                before,
                wrong_contract,
                context=f.context(
                    verdict=wrong_contract,
                    observed_attestation=context.observed_attestation,
                ),
            )

        wrong_bridge = dict(f.bridge, bridge_id="CB-other")
        with self.assertRaises(protocol.RelationshipValidationError):
            protocol.validate_record_review_transition(before, verdict, context=f.context(candidate_bridge=wrong_bridge, verdict=verdict, observed_attestation=context.observed_attestation))

        wrong_state = state(["V-existing"])
        wrong_state["contract_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(protocol.StateTransitionError):
            protocol.validate_record_review_transition(wrong_state, verdict, context=context)

    def test_assemble_and_challenge_recovery_use_exact_facts_and_never_rerun_uncertain_work(self) -> None:
        protocol = self.protocol()
        f = ProtocolFixture()
        intent = {
            "record_type": "operation-intent",
            "op_id": "assemble-1",
            "command_kind": "assemble",
            "request_digest": "sha256:" + "a" * 64,
            "contract_digest": CONTRACT_DIGEST,
            "expected_state_version": 10,
            "planned_output_types": ["I", "output-identity", "schema2-manifest", "CB"],
            "planned_output_paths": ["i.json", "output.json", "manifest.json", "cb.json"],
        }
        receipt = {
            "record_type": "operation-receipt",
            "op_id": "assemble-1",
            "request_digest": intent["request_digest"],
            "command_kind": "assemble",
            "outcome": "success",
            "side_effect": "durable",
            "actual_output_ids": ["I-1", "out-1", "manifest-1", CB_ID],
            "state_version_before": 10,
            "state_version_after": 11,
        }
        no_outputs = {kind: False for kind in protocol.ASSEMBLE_OUTPUT_TYPES}
        self.assertEqual(
            protocol.classify_assemble_recovery(protocol.AssembleRecoveryContext(
                relationship=f.context(), intent=intent, assembly=f.assembly,
                output_identity={"output_identity_id": f.assembly["output_identity_id"], "assembly_id": f.assembly["assembly_id"]},
                receipt=None, observed_state_version=10, expected_state_before=10,
                expected_state_after=11, observed_outputs=no_outputs,
            )),
            "failure-receipt-new-operation",
        )
        partial_outputs = dict(no_outputs, I=True)
        self.assertEqual(
            protocol.classify_assemble_recovery(protocol.AssembleRecoveryContext(
                relationship=f.context(), intent=intent, assembly=f.assembly,
                output_identity={"output_identity_id": f.assembly["output_identity_id"], "assembly_id": f.assembly["assembly_id"]},
                receipt=None, observed_state_version=10, expected_state_before=10,
                expected_state_after=11, observed_outputs=partial_outputs,
            )),
            "ambiguous",
        )
        self.assertEqual(
            protocol.classify_assemble_recovery(protocol.AssembleRecoveryContext(
                relationship=f.context(), intent=intent, assembly=f.assembly,
                output_identity={"output_identity_id": "out-1", "assembly_id": f.assembly["assembly_id"]},
                receipt=receipt, observed_state_version=10, expected_state_before=10,
                expected_state_after=11,
            )),
            "ambiguous",
        )
        complete_receipt = dict(
            receipt,
            actual_output_ids=[
                f.assembly["assembly_id"], f.assembly["output_identity_id"],
                f.assembly["schema2_manifest_id"], f.bridge["bridge_id"],
            ],
        )
        self.assertEqual(
            protocol.classify_assemble_recovery(protocol.AssembleRecoveryContext(
                relationship=f.context(), intent=intent, assembly=f.assembly,
                output_identity={
                    "output_identity_id": f.assembly["output_identity_id"],
                    "assembly_id": f.assembly["assembly_id"],
                }, receipt=complete_receipt, observed_state_version=11,
                expected_state_before=10, expected_state_after=11,
            )),
            "complete",
        )
        wrong_identity = dict(f.assembly, output_identity_id="out-other")
        self.assertEqual(
            protocol.classify_assemble_recovery(protocol.AssembleRecoveryContext(
                relationship=f.context(), intent=intent, assembly=wrong_identity,
                output_identity={"output_identity_id": "out-other", "assembly_id": f.assembly["assembly_id"]},
                receipt=complete_receipt, observed_state_version=11,
                expected_state_before=10, expected_state_after=11,
            )),
            "ambiguous",
        )
        wrong_manifest_receipt = dict(complete_receipt, actual_output_ids=[
            f.assembly["assembly_id"], f.assembly["output_identity_id"], f.bridge["candidate_id"],
            f.bridge["bridge_id"],
        ])
        self.assertEqual(
            protocol.classify_assemble_recovery(protocol.AssembleRecoveryContext(
                relationship=f.context(), intent=intent, assembly=f.assembly,
                output_identity={
                    "output_identity_id": f.assembly["output_identity_id"],
                    "assembly_id": f.assembly["assembly_id"],
                }, receipt=wrong_manifest_receipt, observed_state_version=11,
                expected_state_before=10, expected_state_after=11,
            )),
            "ambiguous",
        )
        packet_context = complete_packet_context(f)
        request = challenge_request(f, packet_context.packet)
        self.assertEqual(
            protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                relationship=packet_context, request=request, evidence=None, challenge_receipt=None,
                nested_run_receipt=not_started_receipt(request),
            )),
            "start-probe-once",
        )

    def test_challenge_recovery_requires_complete_context_and_exact_bound_records(self) -> None:
        protocol = self.protocol()
        f = ProtocolFixture()
        packet_context = complete_packet_context(f)
        request = challenge_request(f, packet_context.packet)
        start = protocol.ChallengeRecoveryContext(
            relationship=packet_context, request=request, evidence=None, challenge_receipt=None,
            nested_run_receipt=not_started_receipt(request),
        )
        self.assertEqual(protocol.classify_challenge_recovery(start), "start-probe-once")
        self.assertEqual(
            protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                relationship=f.context(), request=request, evidence=None, challenge_receipt=None,
                nested_run_receipt=not_started_receipt(request),
            )),
            "ambiguous",
        )
        for receipt in (None, dict(not_started_receipt(request), outcome="unknown")):
            with self.subTest(nested_receipt=receipt):
                self.assertEqual(
                    protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                        relationship=packet_context, request=request, evidence=None,
                        challenge_receipt=None, nested_run_receipt=receipt,
                    )),
                    "ambiguous",
                )
        bad_contract = dict(request, contract_digest="sha256:" + "0" * 64)
        bad_contract["request_digest"] = digest(bad_contract, without=("request_digest",))
        bad_check = dict(request, check_key="candidate")
        bad_check["request_digest"] = digest(bad_check, without=("request_digest",))
        for bad_request in (
            dict(request, request_digest="sha256:" + "0" * 64), bad_contract, bad_check,
        ):
            with self.subTest(request=bad_request):
                self.assertEqual(
                    protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                        relationship=packet_context, request=bad_request, evidence=None,
                        challenge_receipt=None, nested_run_receipt=not_started_receipt(request),
                    )),
                    "ambiguous",
                )
        evidence = challenge_evidence(request)
        self.assertEqual(
            protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                relationship=packet_context, request=request, evidence=evidence,
                challenge_receipt=None, nested_run_receipt=None,
            )),
            "publish-cr-only",
        )
        bad_subject = dict(evidence, subject_id="P-other:CB-other")
        bad_subject["evidence_digest"] = digest(bad_subject, without=("evidence_digest",))
        self.assertEqual(
            protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                relationship=packet_context, request=request, evidence=bad_subject,
                challenge_receipt=None, nested_run_receipt=None,
            )),
            "ambiguous",
        )
        receipt = challenge_receipt(request, evidence)
        self.assertEqual(
            protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                relationship=packet_context, request=request, evidence=evidence,
                challenge_receipt=receipt, nested_run_receipt=None,
            )),
            "complete",
        )
        bad_receipt = dict(receipt, evidence_id="E-other")
        self.assertEqual(
            protocol.classify_challenge_recovery(protocol.ChallengeRecoveryContext(
                relationship=packet_context, request=request, evidence=evidence,
                challenge_receipt=bad_receipt, nested_run_receipt=None,
            )),
            "ambiguous",
        )

    def test_reviewer_return_schema_has_valid_and_unavailable_forms(self) -> None:
        root = Path(__file__).resolve().parents[1]
        toml_text = (root / "agents/sol-advisor-sol-reviewer.toml").read_text(encoding="utf-8")
        reference_text = (root / "skills/orchestration/references/role-contracts.md").read_text(encoding="utf-8")
        for text in (toml_text, reference_text):
            self.assertIn("REVIEW_STATUS: valid | unavailable | invalid", text)
            self.assertIn("valid => VERDICT: ship | fix-first | rethink", text)
            self.assertIn("unavailable | invalid => VERDICT: null", text)

    def test_documented_design_outputs_are_accepted_without_product_authority(self) -> None:
        """Consume each advertised design verdict through the real DR validator."""
        root = Path(__file__).resolve().parents[1]
        for path in (root / "agents/sol-advisor-sol-reviewer.toml",
                     root / "skills/orchestration/references/role-contracts.md"):
            with self.subTest(path=path.name):
                match = re.search(r"design \+ valid => DESIGN_VERDICT: ([^\n]+)", path.read_text())
                self.assertIsNotNone(match, "design reviews lack their own output contract")
                choices = {item.strip() for item in match[1].split("|")}
                self.assertEqual(choices, {"design-approved", "fix-first", "rethink"})
                for verdict in choices:
                    self.protocol().validate_design_review({
                        "record_type": "DR", "status": "valid", "design_verdict": verdict,
                        "contract_digest": CONTRACT_DIGEST,
                    })
                for status in ("unavailable", "invalid"):
                    self.protocol().validate_design_review({
                        "record_type": "DR", "status": status, "design_verdict": None,
                    })
                with self.assertRaises(self.protocol().VerdictValidationError):
                    self.protocol().validate_design_review({
                        "record_type": "DR", "status": "valid", "design_verdict": "ship",
                        "contract_digest": CONTRACT_DIGEST,
                    })

    def test_four_relationship_validators_reject_context_free_calls(self) -> None:
        protocol = self.protocol()
        samples = (
            (protocol.validate_candidate_bridge, {"record_type": "CB"}),
            (protocol.validate_review_packet, {"record_type": "P"}),
            (protocol.validate_verdict, {"record_type": "V", "status": "unavailable", "verdict": None}),
            (protocol.validate_acceptance, {"record_type": "A"}),
        )
        for validator, record in samples:
            with self.subTest(validator=validator.__name__):
                with self.assertRaises(TypeError):
                    validator(record)

    def test_state_changing_consumers_reject_missing_contexts(self) -> None:
        protocol = self.protocol()
        with self.assertRaises(protocol.StateTransitionError):
            protocol.validate_record_review_transition(state(), {"record_type": "V"}, context=None)
        with self.assertRaises(protocol.ProtocolValidationError):
            protocol.classify_assemble_recovery(None)
        with self.assertRaises(protocol.ProtocolValidationError):
            protocol.classify_challenge_recovery(None)


class ProtocolFixture:
    def __init__(self, *, record_count: int = 1, include_repo_symlink_and_missing: bool = False, include_unrelated_explicit_input: bool = False, review_policy: dict[str, object] | None = None, scoped_paths: list[str] | None = None, scoped_check_script: str | None = None, challenge_allowed_suffixes: list[list[str]] | None = None) -> None:
        if record_count < 1:
            raise ValueError("record_count must be positive")
        self.contract = contract()
        if challenge_allowed_suffixes is not None:
            self.contract["checks"]["challenge"]["allowed_argv_suffixes"] = challenge_allowed_suffixes
        if review_policy is not None or challenge_allowed_suffixes is not None:
            if review_policy is not None:
                self.contract["review_policy"] = review_policy
            self.contract["contract_digest"] = digest(self.contract, without=("contract_digest",))
        self._temporary_repo = fixture_directory(TEST_ARTIFACTS)
        repo = Path(self._temporary_repo.name) / "candidate-repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Protocol Tests"], check=True)
        (repo / "README.md").write_text("candidate fixture\n", encoding="utf-8")
        tracked = ["README.md"]
        if scoped_check_script is not None:
            check_script = repo / "candidate-check.py"
            check_script.write_text(scoped_check_script, encoding="utf-8")
            check_script.chmod(0o755)
            tracked.append(check_script.name)
            self.contract["checks"]["candidate"] = {
                "scope": "candidate",
                "argv": [sys.executable, str(check_script)],
                "cwd": str(repo),
                "timeout_seconds": 5,
                "required": True,
                "acceptance_material_paths": [str(check_script)],
                "allowed_argv_suffixes": [["--fail"]],
            }
            self.contract["checks"]["candidate-final"] = {
                "scope": "candidate",
                "argv": [sys.executable, str(check_script)],
                "cwd": str(repo),
                "timeout_seconds": 5,
                "required": True,
                "acceptance_material_paths": [str(check_script)],
                "final_candidate_verify": True,
            }
            self.contract["checks"]["challenge"] = {
                "scope": "challenge",
                "argv": [sys.executable, str(check_script)],
                "cwd": str(repo),
                "timeout_seconds": 5,
                "required": True,
                "acceptance_material_paths": [str(check_script)],
                **({"allowed_argv_suffixes": challenge_allowed_suffixes} if challenge_allowed_suffixes is not None else {}),
            }
            self.contract["contract_digest"] = digest(self.contract, without=("contract_digest",))
        contract_digest = self.contract["contract_digest"]
        if include_repo_symlink_and_missing:
            (repo / "gone.txt").write_text("deleted after commit\n", encoding="utf-8")
            os.symlink("README.md", repo / "repo-link")
            tracked.extend(["gone.txt", "repo-link"])
        subprocess.run(["git", "-C", str(repo), "add", *tracked], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
        if include_repo_symlink_and_missing:
            (repo / "gone.txt").unlink()
        inputs = repo / ".agent-artifacts" / "inputs"
        inputs.mkdir(parents=True)
        self.materials = []
        self.deliveries = []
        self.delivery_evidence = []
        bundle_paths = {}
        delivery_paths = {}
        material_paths = {}
        for number in range(1, record_count + 1):
            suffix = str(number)
            material_id = f"M-{suffix}"
            delivery_id = f"D-{suffix}"
            bundle_path = inputs / f"bundle-{suffix}.json"
            bundle_path.write_bytes(full_protocol.canonical_json_bytes({"bundle": f"actual material bytes {suffix}"}))
            material = {"record_type":"M","material_id":material_id,"contract_digest":contract_digest,"work_key":"p1","baseline_id":"base","ready_identity":"ready","bundle":{"files":["plugins/sol-advisor/scripts/full_protocol.py"],"sha256":hashlib.sha256(bundle_path.read_bytes()).hexdigest()}}
            material["material_digest"] = digest(material)
            delivery = {"record_type":"D","delivery_id":delivery_id,"contract_digest":contract_digest,"work_key":"p1","baseline_id":"base","ready_identity":"ready","material_id":material_id,"material_digest":material["material_digest"],"delivery_evidence_id":f"E-delivery-{suffix}","attestation":{"self_review":"complete"}}
            delivery["delivery_digest"] = digest(delivery)
            self.materials.append(material)
            self.deliveries.append(delivery)
            evidence = {
                "record_type": "E", "evidence_id": f"E-delivery-{suffix}",
                "contract_digest": contract_digest, "scope": "delivery", "subject_id": material_id,
                "check_key": "delivery", "harness_identity": "harness-delivery",
                "environment_identity": "env-delivery", "runtime_identity": "runtime-delivery",
                "result": "pass", "logs": [],
            }
            evidence["evidence_digest"] = digest(evidence)
            self.delivery_evidence.append(evidence)
            bundle_paths[material_id] = bundle_path
            delivery_paths[delivery_id] = inputs / f"{delivery_id}.json"
            material_paths[material_id] = inputs / f"{material_id}.json"
        self.material = self.materials[0]
        self.delivery = self.deliveries[0]
        self.assembly = {"record_type":"I","assembly_id":"I-1","contract_digest":contract_digest,"baseline_id":"base","delivery_ids":[item["delivery_id"] for item in self.deliveries],"material_ids":[item["material_id"] for item in self.materials],"output_identity_id":"out-1","schema2_manifest_id":"manifest-1","candidate_bridge_id":"CB-1"}
        assembly_path = inputs / "I-1.json"
        assembly_path.write_bytes(full_protocol.canonical_json_bytes(self.assembly))
        for delivery in self.deliveries:
            delivery_paths[delivery["delivery_id"]].write_bytes(full_protocol.canonical_json_bytes(delivery))
        for material in self.materials:
            material_paths[material["material_id"]].write_bytes(full_protocol.canonical_json_bytes(material))
        if record_count == 1:
            self.explicit_inputs = {"I": str(assembly_path), "D": str(delivery_paths["D-1"]), "M": str(material_paths["M-1"]), "bundle": str(bundle_paths["M-1"])}
        else:
            self.explicit_inputs = {
                "I": {"I-1": str(assembly_path)},
                "D": {record_id: str(path) for record_id, path in delivery_paths.items()},
                "M": {record_id: str(path) for record_id, path in material_paths.items()},
                "bundle": {record_id: str(path) for record_id, path in bundle_paths.items()},
            }
        input_paths = (
            list(self.explicit_inputs.values()) if record_count == 1 else
            [path for group in self.explicit_inputs.values() for path in group.values()]
        )
        if include_unrelated_explicit_input:
            unrelated_path = inputs / "unrelated.json"
            unrelated_path.write_bytes(full_protocol.canonical_json_bytes({"unrelated": True}))
            input_paths.append(str(unrelated_path))
        if scoped_check_script is not None:
            input_paths.append(str(RUN_CHECK_SCRIPT))
        manifest_path = repo / ".agent-artifacts" / "candidate.json"
        snapshot = subprocess.run(
            [sys.executable, str(CANDIDATE_SCRIPT), "snapshot", "--repo", str(repo), "--output", str(manifest_path), *([] if scoped_paths is None else sum((["--scope", value] for value in scoped_paths), [])), *sum((["--input", str(path)] for path in input_paths), [])],
            check=True, text=True, capture_output=True,
        )
        self.snapshot_receipt = json.loads(snapshot.stdout)
        self.manifest_bytes = manifest_path.read_bytes()
        self.manifest = json.loads(self.manifest_bytes)
        verify = subprocess.run(
            [sys.executable, str(CANDIDATE_SCRIPT), "verify", "--manifest", str(manifest_path), "--expected-candidate-id", self.manifest["candidate_id"]],
            check=True, text=True, capture_output=True,
        )
        self.candidate_verify_receipt = json.loads(verify.stdout)
        self.bridge = {"record_type":"CB","bridge_id":"CB-1","contract_digest":contract_digest,"manifest_schema_version":2,"manifest_path":str(manifest_path),"manifest_hash":"sha256:"+hashlib.sha256(self.manifest_bytes).hexdigest(),"candidate_id":self.manifest["candidate_id"],"manifest_candidate_id":self.manifest["candidate_id"],"selection_policy":self.manifest["selection"]["repo_inventory"],"assembly_id":"I-1","delivery_ids":[item["delivery_id"] for item in self.deliveries],"material_ids":[item["material_id"] for item in self.materials],"explicit_inputs":self.explicit_inputs}
        self.bridge["correspondence_digest"] = digest({"manifest":self.manifest,"assembly":self.assembly,"deliveries":self.deliveries,"materials":self.materials,"delivery_evidence":self.delivery_evidence,"explicit_inputs":self.explicit_inputs})

    def cleanup(self) -> None:
        temporary = getattr(self, "_temporary_repo", None)
        if temporary is not None:
            temporary.cleanup()
            self._temporary_repo = None

    def __del__(self) -> None:
        self.cleanup()

    def context(self, **overrides: object):
        values = {
            "task_contract": self.contract, "candidate_bridge": self.bridge,
            "manifest": self.manifest, "manifest_bytes": self.manifest_bytes,
            "candidate_verify_receipt": self.candidate_verify_receipt,
            "assembly": self.assembly, "deliveries": self.deliveries, "materials": self.materials,
            "delivery_evidence": self.delivery_evidence,
        }
        values.update(overrides)
        return full_protocol.RelationshipContext(**values)


def candidate_evidence(f: ProtocolFixture) -> dict[str, object]:
    evidence = {
        "record_type": "E", "evidence_id": "E-candidate-1",
        "contract_digest": f.contract["contract_digest"], "scope": "candidate",
        "subject_id": f.bridge["bridge_id"], "check_key": "candidate",
        "harness_identity": "harness", "environment_identity": "env",
        "runtime_identity": "runtime", "result": "pass", "logs": [],
    }
    evidence["evidence_digest"] = digest(evidence)
    return evidence


def complete_packet_context(f: ProtocolFixture, roots: list[str] | None = None):
    roots = list(roots or [])
    predecessors = {
        root: {
            "record_type": "V", "verdict_id": root, "contract_digest": CONTRACT_DIGEST,
            "status": "valid", "verdict": "fix-first", "packet_id": "P-prior",
            "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-prior",
            "rejection_closure": [], "coverage_complete": True,
        }
        for root in roots
    }
    packet = {
        "record_type": "P", "packet_id": "P-1", "contract_digest": CONTRACT_DIGEST,
        "candidate_bridge_id": f.bridge["bridge_id"], "assembly_id": f.assembly["assembly_id"],
        "delivery_ids": [f.delivery["delivery_id"]], "candidate_evidence_ids": ["E-candidate-1"],
        "coverage": {"complete": True, "checks": ["candidate"], "required_scopes": ["delivery", "candidate"]},
        "rejection_roots": roots, "rejection_closure": roots,
    }
    return f.context(
        packet=packet, candidate_evidence=[candidate_evidence(f)],
        applicable_rejection_roots=roots, predecessor_verdicts=predecessors,
        expected_coverage=["delivery", "candidate"],
    )


def challenge_request(f: ProtocolFixture, packet: dict[str, object]) -> dict[str, object]:
    request = {
        "record_type": "challenge-request", "request_id": "Q-1", "request_digest": "",
        "contract_digest": CONTRACT_DIGEST, "packet_id": packet["packet_id"],
        "candidate_bridge_id": f.bridge["bridge_id"], "check_key": "challenge",
        "authority_decision": "allowed",
    }
    request["request_digest"] = digest(request, without=("request_digest",))
    return request


def challenge_evidence(request: dict[str, object]) -> dict[str, object]:
    evidence = {
        "record_type": "E", "evidence_id": "E-challenge-1",
        "contract_digest": CONTRACT_DIGEST, "scope": "challenge",
        "subject_id": f"{request['packet_id']}:{request['candidate_bridge_id']}",
        "check_key": "challenge", "challenge_request_id": request["request_id"],
        "challenge_request_digest": request["request_digest"], "harness_identity": "harness",
        "environment_identity": "env", "runtime_identity": "runtime", "result": "pass", "logs": [],
    }
    evidence["evidence_digest"] = digest(evidence)
    return evidence


def challenge_receipt(request: dict[str, object], evidence: dict[str, object]) -> dict[str, object]:
    return {
        "record_type": "CR", "challenge_receipt_id": "CR-1",
        "challenge_request_id": request["request_id"], "packet_id": request["packet_id"],
        "candidate_bridge_id": request["candidate_bridge_id"], "evidence_id": evidence["evidence_id"],
        "challenge_request_digest": request["request_digest"],
    }


def not_started_receipt(request: dict[str, object]) -> dict[str, object]:
    return {
        "record_type": "run-check-receipt", "challenge_request_id": request["request_id"],
        "challenge_request_digest": request["request_digest"], "packet_id": request["packet_id"],
        "candidate_bridge_id": request["candidate_bridge_id"], "outcome": "not-started",
    }


def complete_review_context(f: ProtocolFixture, verdict: dict[str, object], roots: list[str]):
    packet_context = complete_packet_context(f, roots)
    request = challenge_request(f, packet_context.packet)
    evidence = challenge_evidence(request)
    receipt = challenge_receipt(request, evidence)
    attestation = {
        "context_id": "context-1", "thread_id": "thread-1", "role": "sol_advisor_sol_reviewer",
        "model": "gpt-6-sol", "effort": "xhigh", "observed_attestation": {"observed": True},
    }
    verdict["observed_attestation_digest"] = digest(attestation)
    verdict.setdefault("rejection_dispositions", {})
    return f.context(
        packet=packet_context.packet, candidate_evidence=packet_context.candidate_evidence,
        applicable_rejection_roots=roots, predecessor_verdicts=packet_context.predecessor_verdicts,
        expected_coverage=packet_context.expected_coverage, challenge_request=request,
        challenge_evidence=evidence, challenge_receipt=receipt, verdict=verdict,
        observed_attestation=attestation,
    )


class CompleteRelationshipTests(unittest.TestCase):
    def test_corrected_p2_reviewer_freshness_covers_transitive_ancestry(self) -> None:
        contract_value = {"protocol": full_protocol.STAGED_PROTOCOL_VERSION}
        bridge = {"bridge_id": "CB-current"}
        attestation = {"reviewer": {"thread_id": "thread-current", "context_id": "context-current"}}
        predecessors = {
            "V-root": {"candidate_bridge_id": "CB-prior", "reviewer_thread_id": "thread-prior", "reviewer_context_id": "context-prior"},
            "V-ancestor": {"candidate_bridge_id": "CB-older", "reviewer_thread_id": "thread-older", "reviewer_context_id": "context-current"},
        }
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol._validate_corrected_p2_reviewer_freshness(
                contract=contract_value, bridge=bridge, attestation=attestation,
                closure=["V-ancestor", "V-root"], predecessor_verdicts=predecessors,
            )
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol._validate_corrected_p2_reviewer_freshness(
                contract=contract_value, bridge=bridge, attestation={},
                closure=["V-root"], predecessor_verdicts=predecessors,
            )
        full_protocol._validate_corrected_p2_reviewer_freshness(
            contract=contract_value, bridge=bridge,
            attestation={"reviewer": {"thread_id": "thread-fresh", "context_id": "context-fresh"}},
            closure=["V-ancestor", "V-root"], predecessor_verdicts=predecessors,
        )
        full_protocol._validate_corrected_p2_reviewer_freshness(
            contract={"protocol": full_protocol.PROTOCOL_VERSION}, bridge=bridge, attestation={},
            closure=["V-root"], predecessor_verdicts=predecessors,
        )
        full_protocol._validate_corrected_p2_reviewer_freshness(
            contract=contract_value, bridge=bridge, attestation={}, closure=["V-root"],
            predecessor_verdicts={"V-root": {"candidate_bridge_id": "CB-current"}},
        )

    def test_candidate_bridge_requires_actual_manifest_and_retained_records(self) -> None:
        f = ProtocolFixture()
        with self.assertRaises(TypeError):
            full_protocol.validate_candidate_bridge(f.bridge)
        self.assertEqual(full_protocol.validate_candidate_bridge(f.bridge, context=f.context())["bridge_id"], "CB-1")
        f.manifest_bytes = b'{}'
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_candidate_bridge(f.bridge, context=f.context(manifest_bytes=f.manifest_bytes))

    def test_candidate_bridge_binds_manifest_policy_and_each_delivery_evidence(self) -> None:
        f = ProtocolFixture(record_count=2)

        fabricated_policy = dict(f.bridge, selection_policy="fabricated-policy")
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_candidate_bridge(
                fabricated_policy, context=f.context(candidate_bridge=fabricated_policy)
            )

        missing_policy = dict(f.bridge)
        missing_policy.pop("selection_policy")
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_candidate_bridge(
                missing_policy, context=f.context(candidate_bridge=missing_policy)
            )

        wrong_delivery_evidence = [dict(item) for item in f.delivery_evidence]
        wrong_delivery_evidence[0]["evidence_id"] = "E-delivery-substituted"
        wrong_delivery_evidence[0]["evidence_digest"] = digest(
            wrong_delivery_evidence[0], without=("evidence_digest",)
        )
        wrong_bridge = dict(f.bridge)
        wrong_bridge["correspondence_digest"] = digest({
            "manifest": f.manifest,
            "assembly": f.assembly,
            "deliveries": f.deliveries,
            "materials": f.materials,
            "delivery_evidence": wrong_delivery_evidence,
            "explicit_inputs": f.explicit_inputs,
        })
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_candidate_bridge(
                wrong_bridge,
                context=f.context(
                    candidate_bridge=wrong_bridge,
                    delivery_evidence=wrong_delivery_evidence,
                ),
            )

        for result in ("fail", "incomplete"):
            nonpassing = [dict(item) for item in f.delivery_evidence]
            nonpassing[0]["result"] = result
            nonpassing[0]["evidence_digest"] = digest(
                nonpassing[0], without=("evidence_digest",)
            )
            bridge = dict(f.bridge)
            bridge["correspondence_digest"] = digest({
                "manifest": f.manifest,
                "assembly": f.assembly,
                "deliveries": f.deliveries,
                "materials": f.materials,
                "delivery_evidence": nonpassing,
                "explicit_inputs": f.explicit_inputs,
            })
            with self.subTest(delivery_result=result), self.assertRaises(
                full_protocol.RelationshipValidationError
            ):
                full_protocol.validate_candidate_bridge(
                    bridge,
                    context=f.context(
                        candidate_bridge=bridge, delivery_evidence=nonpassing
                    ),
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_candidate_bridge_accepts_every_real_schema_two_repository_entry_shape(self) -> None:
        f = ProtocolFixture(include_repo_symlink_and_missing=True)
        repo_types = {entry["type"] for entry in f.manifest["entries"] if entry["scope"] == "repo"}
        self.assertTrue({"file", "symlink", "missing"}.issubset(repo_types))
        self.assertEqual(
            full_protocol.validate_candidate_bridge(f.bridge, context=f.context())["bridge_id"],
            "CB-1",
        )

    def test_candidate_bridge_validates_full_i_every_d_and_every_m_before_acceptance(self) -> None:
        f = ProtocolFixture()

        def bridge_for(assembly, deliveries, materials):
            bridge = dict(f.bridge)
            bridge["correspondence_digest"] = digest({
                "manifest": f.manifest, "assembly": assembly, "deliveries": deliveries,
                "materials": materials, "delivery_evidence": f.delivery_evidence,
                "explicit_inputs": f.explicit_inputs,
            })
            return bridge

        cases = (
            ({"assembly_id": f.assembly["assembly_id"]}, f.deliveries, f.materials),
            (f.assembly, [{"delivery_id": f.delivery["delivery_id"]}], f.materials),
            (f.assembly, f.deliveries, [{"material_id": f.material["material_id"]}]),
        )
        for assembly, deliveries, materials in cases:
            with self.subTest(assembly=assembly, deliveries=deliveries, materials=materials), self.assertRaises(full_protocol.RelationshipValidationError):
                bridge = bridge_for(assembly, deliveries, materials)
                full_protocol.validate_candidate_bridge(
                    bridge,
                    context=f.context(
                        candidate_bridge=bridge, assembly=assembly,
                        deliveries=deliveries, materials=materials,
                    ),
                )

    def test_candidate_bridge_ignores_unrelated_selected_explicit_input_entries(self) -> None:
        f = ProtocolFixture(include_unrelated_explicit_input=True)
        self.assertEqual(
            full_protocol.validate_candidate_bridge(f.bridge, context=f.context())["bridge_id"],
            "CB-1",
        )

    def test_candidate_bridge_binds_every_selected_delivery_material_and_bundle_input(self) -> None:
        f = ProtocolFixture(record_count=2)
        self.assertEqual(
            full_protocol.validate_candidate_bridge(f.bridge, context=f.context())["bridge_id"],
            "CB-1",
        )

        def bridge_for(explicit_inputs):
            bridge = dict(f.bridge, explicit_inputs=explicit_inputs)
            bridge["correspondence_digest"] = digest({
                "manifest": f.manifest, "assembly": f.assembly, "deliveries": f.deliveries,
                "materials": f.materials, "delivery_evidence": f.delivery_evidence,
                "explicit_inputs": explicit_inputs,
            })
            return bridge

        missing_delivery = {key: dict(value) for key, value in f.explicit_inputs.items()}
        del missing_delivery["D"]["D-2"]
        extra_delivery = {key: dict(value) for key, value in f.explicit_inputs.items()}
        extra_delivery["D"]["D-extra"] = extra_delivery["D"]["D-2"]
        substituted_material = {key: dict(value) for key, value in f.explicit_inputs.items()}
        substituted_material["M"]["M-2"] = substituted_material["D"]["D-2"]
        substituted_bundle = {key: dict(value) for key, value in f.explicit_inputs.items()}
        substituted_bundle["bundle"]["M-2"] = substituted_bundle["bundle"]["M-1"]
        for explicit_inputs in (missing_delivery, extra_delivery, substituted_material, substituted_bundle):
            with self.subTest(explicit_inputs=explicit_inputs), self.assertRaises(full_protocol.RelationshipValidationError):
                bridge = bridge_for(explicit_inputs)
                full_protocol.validate_candidate_bridge(bridge, context=f.context(candidate_bridge=bridge))


class PublicRelationshipClosureTests(unittest.TestCase):
    """P/V/A must derive relationships from supplied records, never their labels."""

    def fixture(self) -> ProtocolFixture:
        return ProtocolFixture()

    def candidate_evidence(self, f: ProtocolFixture) -> dict[str, object]:
        evidence = {
            "record_type": "E", "evidence_id": "E-candidate-1",
            "contract_digest": CONTRACT_DIGEST, "scope": "candidate",
            "subject_id": f.bridge["bridge_id"], "check_key": "candidate",
            "harness_identity": "harness", "environment_identity": "env",
            "runtime_identity": "runtime", "result": "pass", "logs": [],
        }
        evidence["evidence_digest"] = digest(evidence)
        return evidence

    def test_review_packet_recomputes_retained_records_not_just_ids(self) -> None:
        f = self.fixture()
        packet = {
            "record_type": "P", "packet_id": "P-1", "contract_digest": CONTRACT_DIGEST,
            "candidate_bridge_id": f.bridge["bridge_id"], "assembly_id": f.assembly["assembly_id"],
            "delivery_ids": [f.delivery["delivery_id"]], "candidate_evidence_ids": ["E-candidate-1"],
            "coverage": {"complete": True, "checks": ["candidate"], "required_scopes": ["delivery", "candidate"]},
            "rejection_roots": [], "rejection_closure": [],
        }
        forged_delivery = dict(f.delivery, contract_digest="sha256:" + "f" * 64)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_review_packet(packet, context=f.context(deliveries=[forged_delivery], packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"]))
        self.assertEqual(
            full_protocol.validate_review_packet(packet, context=f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"]))["packet_id"],
            "P-1",
        )
        extra_evidence = self.candidate_evidence(f)
        extra_evidence["evidence_id"] = "E-candidate-2"
        extra_evidence["evidence_digest"] = digest(extra_evidence, without=("evidence_digest",))
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_review_packet(packet, context=f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f), extra_evidence], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"]))

        valid_context = f.context(
            packet=packet,
            candidate_evidence=[self.candidate_evidence(f)],
            applicable_rejection_roots=[],
            predecessor_verdicts={},
            expected_coverage=["delivery", "candidate"],
        )
        for result in ("fail", "incomplete"):
            nonpassing = dict(valid_context.candidate_evidence[0], result=result)
            nonpassing["evidence_digest"] = digest(
                nonpassing, without=("evidence_digest",)
            )
            with self.subTest(candidate_result=result), self.assertRaises(
                full_protocol.RelationshipValidationError
            ):
                full_protocol.validate_review_packet(
                    packet,
                    context=replace(valid_context, candidate_evidence=[nonpassing]),
                )

    def test_verdict_recomputes_challenge_request_receipt_and_evidence_relation(self) -> None:
        f = self.fixture()
        packet = {
            "record_type": "P", "packet_id": "P-1", "contract_digest": CONTRACT_DIGEST,
            "candidate_bridge_id": f.bridge["bridge_id"], "assembly_id": f.assembly["assembly_id"],
            "delivery_ids": [f.delivery["delivery_id"]], "candidate_evidence_ids": ["E-candidate-1"],
            "coverage": {"complete": True, "checks": ["candidate"], "required_scopes": ["delivery", "candidate"]}, "rejection_roots": [], "rejection_closure": [],
        }
        request = {
            "record_type": "challenge-request", "request_id": "Q-1",
            "request_digest": "", "contract_digest": CONTRACT_DIGEST,
            "packet_id": "P-1", "candidate_bridge_id": f.bridge["bridge_id"],
            "check_key": "challenge", "authority_decision": "allowed",
        }
        request["request_digest"] = digest(request, without=("request_digest",))
        receipt = {
            "record_type": "CR", "challenge_receipt_id": "CR-1",
            "challenge_request_id": "Q-1", "packet_id": "P-1",
            "candidate_bridge_id": f.bridge["bridge_id"], "evidence_id": "E-other", "challenge_request_digest": request["request_digest"],
        }
        challenge_evidence = {
            "record_type": "E", "evidence_id": "E-challenge-1",
            "contract_digest": CONTRACT_DIGEST, "scope": "challenge",
            "subject_id": "P-1:" + f.bridge["bridge_id"], "check_key": "challenge",
            "challenge_request_id": request["request_id"], "challenge_request_digest": request["request_digest"],
            "harness_identity": "harness", "environment_identity": "env",
            "runtime_identity": "runtime", "result": "pass", "logs": [],
        }
        challenge_evidence["evidence_digest"] = digest(challenge_evidence)
        verdict = {
            "record_type": "V", "verdict_id": "V-1", "contract_digest": CONTRACT_DIGEST,
            "status": "valid", "verdict": "ship", "packet_id": "P-1",
            "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-1",
            "rejection_closure": [], "coverage_complete": True, "rejection_dispositions": {}, "open_rejections": [],
        }
        attestation = {"context_id": "context-1", "thread_id": "thread-1", "role": "sol_advisor_sol_reviewer", "model": "gpt-6-sol", "effort": "xhigh", "observed_attestation": {"observed": True}}
        verdict["observed_attestation_digest"] = digest(attestation)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_verdict(verdict, context=f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"], challenge_request=request, challenge_evidence=challenge_evidence, challenge_receipt=receipt, verdict=verdict, observed_attestation=attestation))
        receipt["evidence_id"] = challenge_evidence["evidence_id"]
        self.assertEqual(
            full_protocol.validate_verdict(verdict, context=f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"], challenge_request=request, challenge_evidence=challenge_evidence, challenge_receipt=receipt, verdict=verdict, observed_attestation=attestation))["verdict_id"],
            "V-1",
        )
        for result in ("fail", "incomplete"):
            nonpassing = dict(challenge_evidence, result=result)
            nonpassing["evidence_digest"] = digest(
                nonpassing, without=("evidence_digest",)
            )
            ship_context = f.context(
                packet=packet, candidate_evidence=[self.candidate_evidence(f)],
                applicable_rejection_roots=[], predecessor_verdicts={},
                expected_coverage=["delivery", "candidate"], challenge_request=request,
                challenge_evidence=nonpassing, challenge_receipt=receipt,
                verdict=verdict, observed_attestation=attestation,
            )
            with self.subTest(ship_challenge_result=result), self.assertRaises(
                full_protocol.RelationshipValidationError
            ):
                full_protocol.validate_verdict(verdict, context=ship_context)

            if result == "fail":
                for outcome in ("fix-first", "rethink"):
                    nonship = dict(verdict, verdict=outcome)
                    if outcome == "fix-first":
                        nonship["blocking_findings"] = [{"finding_id": "F-1"}]
                    self.assertEqual(
                        full_protocol.validate_verdict(
                            nonship, context=replace(ship_context, verdict=nonship)
                        )["verdict"],
                        outcome,
                    )
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_verdict(verdict, context=f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"], challenge_request=request, challenge_evidence=challenge_evidence, challenge_receipt=None, verdict=verdict, observed_attestation=attestation))
        bad_digest_request = dict(request, request_digest="sha256:" + "0" * 64)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_verdict(verdict, context=f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"], challenge_request=bad_digest_request, challenge_evidence=challenge_evidence, challenge_receipt=receipt, verdict=verdict, observed_attestation=attestation))
        predecessor_old = {"record_type": "V", "verdict_id": "V-old", "contract_digest": CONTRACT_DIGEST, "status": "valid", "verdict": "fix-first", "packet_id": "P-old", "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-old", "rejection_closure": [], "coverage_complete": True}
        predecessor_root = dict(predecessor_old, verdict_id="V-root", rejection_closure=["V-old"])
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_verdict(verdict, context=f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=["V-root"], predecessor_verdicts={"V-root": predecessor_root, "V-old": predecessor_old}, expected_coverage=["delivery", "candidate"], challenge_request=request, challenge_evidence=challenge_evidence, challenge_receipt=receipt, verdict=verdict, observed_attestation=attestation))

    def test_acceptance_recomputes_final_evidence_and_root_authority(self) -> None:
        f = self.fixture()
        packet = {"record_type": "P", "packet_id": "P-1", "contract_digest": CONTRACT_DIGEST, "candidate_bridge_id": f.bridge["bridge_id"], "assembly_id": f.assembly["assembly_id"], "delivery_ids": [f.delivery["delivery_id"]], "candidate_evidence_ids": ["E-candidate-1"], "coverage": {"complete": True, "checks": ["candidate"], "required_scopes": ["delivery", "candidate"]}, "rejection_roots": [], "rejection_closure": []}
        verdict = {"record_type": "V", "verdict_id": "V-1", "contract_digest": CONTRACT_DIGEST, "status": "valid", "verdict": "ship", "packet_id": "P-1", "candidate_bridge_id": f.bridge["bridge_id"], "challenge_receipt_id": "CR-1", "rejection_closure": [], "coverage_complete": True, "rejection_dispositions": {}, "open_rejections": [], "reviewed_at": "2026-01-01T00:00:00Z", "review_sequence": 10}
        request = {"record_type": "challenge-request", "request_id": "Q-1", "request_digest": "", "contract_digest": CONTRACT_DIGEST, "packet_id": "P-1", "candidate_bridge_id": f.bridge["bridge_id"], "check_key": "challenge", "authority_decision": "allowed"}
        request["request_digest"] = digest(request, without=("request_digest",))
        challenge = {"record_type": "E", "evidence_id": "E-challenge-1", "contract_digest": CONTRACT_DIGEST, "scope": "challenge", "subject_id": "P-1:" + f.bridge["bridge_id"], "check_key": "challenge", "challenge_request_id": "Q-1", "challenge_request_digest": request["request_digest"], "harness_identity": "harness", "environment_identity": "env", "runtime_identity": "runtime", "result": "pass", "logs": []}
        challenge["evidence_digest"] = digest(challenge)
        receipt = {"record_type": "CR", "challenge_receipt_id": "CR-1", "challenge_request_id": "Q-1", "packet_id": "P-1", "candidate_bridge_id": f.bridge["bridge_id"], "evidence_id": "E-challenge-1", "challenge_request_digest": request["request_digest"]}
        attestation = {"context_id": "context-1", "thread_id": "thread-1", "role": "sol_advisor_sol_reviewer", "model": "gpt-6-sol", "effort": "xhigh", "observed_attestation": {"observed": True}}
        verdict["observed_attestation_digest"] = digest(attestation)
        relationship = f.context(packet=packet, candidate_evidence=[self.candidate_evidence(f)], applicable_rejection_roots=[], predecessor_verdicts={}, expected_coverage=["delivery", "candidate"], challenge_request=request, challenge_evidence=challenge, challenge_receipt=receipt, verdict=verdict, observed_attestation=attestation)
        verify = f.candidate_verify_receipt
        verify_id = digest(verify)

        def build(stage: str, dependency_ids: dict[str, str], root_id: str, model: str = "gpt-6-astra"):
            scope = {"route": "full", "action": "final-accept", "stage_key": stage, "candidate_bridge_id": f.bridge["bridge_id"]}
            observed_attestation = {
                "context_id": "root-context-" + stage, "thread_id": "root-thread-" + stage,
                "role": "root", "model": model, "effort": "high",
                "observed_attestation": {"scope": scope, "observed_at": "2026-01-01T00:00:01Z"},
            }
            authority = {"root_authority_id": root_id, "contract_digest": CONTRACT_DIGEST, "scope": scope, "observed_at": "2026-01-01T00:00:01Z", "expires_at": "2099-01-01T00:00:00Z", "candidate_verify_receipt_id": verify_id, "candidate_verify_receipt_digest": verify_id, "issuer": {"role": "root", "model": model}, "observed_attestation": observed_attestation, "observed_attestation_digest": digest(observed_attestation)}
            final = self.candidate_evidence(f)
            final.update({"evidence_id": "E-final-" + stage, "phase": "final-candidate-verify", "observed_at": "2026-01-01T00:00:01Z", "sequence": 11, "candidate_verify_receipt_id": verify_id, "candidate_verify_receipt_digest": verify_id})
            final["evidence_digest"] = digest(final, without=("evidence_digest",))
            acceptance = {"record_type": "A", "acceptance_id": "A-" + stage, "status": "accepted", "contract_digest": CONTRACT_DIGEST, "accepted_stage_key": stage, "candidate_bridge_id": f.bridge["bridge_id"], "packet_id": "P-1", "verdict_id": "V-1", "final_candidate_evidence_id": final["evidence_id"], "root_authority_id": root_id, "root_authority_scope": authority["scope"], "root_authority_expiry": authority["expires_at"], "candidate_verify_receipt_id": verify_id, "dependency_acceptance_ids": dependency_ids}
            return acceptance, final, authority

        p1, e1, r1 = build("p1", {}, "root-p1")
        p2, e2, r2 = build("p2", {"p1": "A-p1"}, "root-p2")
        p3, e3, r3 = build("p3", {"p1": "A-p1", "p2": "A-p2"}, "root-p3")
        c1 = full_protocol.AcceptanceContext(acceptance=p1, relationship=relationship, final_candidate_evidence=e1, root_authority=r1, candidate_verify_receipt=verify, dependency_acceptance_contexts={})
        c2 = full_protocol.AcceptanceContext(acceptance=p2, relationship=relationship, final_candidate_evidence=e2, root_authority=r2, candidate_verify_receipt=verify, dependency_acceptance_contexts={"p1": c1})
        dependencies = {"p1": c1, "p2": c2}
        kwargs = {"context": relationship, "candidate_bridge": f.bridge, "packet": packet, "verdict": verdict, "final_candidate_evidence": e3, "root_authority": r3, "candidate_verify_receipt": verify, "task_contract": f.contract, "dependency_acceptance_contexts": dependencies, "trusted_observation_time": "2026-01-01T00:00:02Z"}
        self.assertEqual(full_protocol.validate_acceptance(p3, **kwargs)["acceptance_id"], "A-p3")
        truncated = dict(e3, logs=[{"kind": "stdout", "path": "fixture.log", "sha256": "0" * 64, "size": 1, "truncated": True}])
        truncated["evidence_digest"] = digest(truncated, without=("evidence_digest",))
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(p3, **dict(kwargs, final_candidate_evidence=truncated))
        upper_bound = dict(
            e3, observed_at="2026-01-01T00:00:02Z", sequence=12
        )
        upper_bound["evidence_digest"] = digest(
            upper_bound, without=("evidence_digest",)
        )
        self.assertEqual(
            full_protocol.validate_acceptance(
                p3, **dict(kwargs, final_candidate_evidence=upper_bound)
            )["acceptance_id"],
            "A-p3",
        )
        future = dict(e3, observed_at="2098-01-01T00:00:00Z", sequence=12)
        future["evidence_digest"] = digest(future, without=("evidence_digest",))
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(
                p3, **dict(kwargs, final_candidate_evidence=future)
            )
        p3_sol, e3_sol, r3_sol = build("p3", {"p1": "A-p1", "p2": "A-p2"}, "root-p3-sol", "gpt-5.6-sol")
        self.assertEqual(
            full_protocol.validate_acceptance(
                p3_sol,
                **dict(kwargs, root_authority=r3_sol, final_candidate_evidence=e3_sol),
            )["acceptance_id"],
            "A-p3",
        )
        for field, bad_value in (("phase", "candidate"), ("observed_at", "2026-01-01T00:00:00Z"), ("sequence", 10), ("evidence_id", "E-candidate-1")):
            bad = dict(e3, **{field: bad_value})
            bad["evidence_digest"] = digest(bad, without=("evidence_digest",))
            with self.subTest(final_field=field), self.assertRaises(full_protocol.RelationshipValidationError):
                full_protocol.validate_acceptance(p3, **dict(kwargs, final_candidate_evidence=bad))
        for authority in (
            dict(r3, expires_at="2026-01-01T00:00:02Z"),
            dict(r3, observed_at="2026-01-01T00:00:03Z"),
            dict(r3, expires_at="2099-01-01 00:00:00Z"),
            dict(r3, scope=dict(r3["scope"], route="audit")),
            *(
                dict(r3, issuer={"role": role, "model": "gpt-5.6-sol"})
                for role in ("sol_advisor_sol_implementer", "sol_advisor_sol_reviewer", "reviewer")
            ),
        ):
            with self.subTest(authority=authority), self.assertRaises(full_protocol.RelationshipValidationError):
                full_protocol.validate_acceptance(p3, **dict(kwargs, root_authority=authority))
        unobserved = dict(r3)
        unobserved.pop("observed_attestation")
        missing_model = dict(r3, issuer={"role": "root"})
        mismatched_observation = dict(r3, observed_attestation=dict(r3["observed_attestation"], model="gpt-5.6-sol"))
        mismatched_observation["observed_attestation_digest"] = digest(mismatched_observation["observed_attestation"])
        self_reported_scope = dict(r3, observed_attestation=dict(r3["observed_attestation"], observed_attestation={"scope": r3["scope"], "observed_at": "2026-01-01T00:00:02Z"}))
        self_reported_scope["observed_attestation_digest"] = digest(self_reported_scope["observed_attestation"])
        for authority in (unobserved, missing_model, mismatched_observation, self_reported_scope):
            with self.subTest(observed_root_authority=authority), self.assertRaises(full_protocol.RelationshipValidationError):
                full_protocol.validate_acceptance(p3, **dict(kwargs, root_authority=authority))
        forged = dict(verify, status="pass")
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(p3, **dict(kwargs, candidate_verify_receipt=forged))
        head_changed = dict(verify, head_changed=True)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(p3, **dict(kwargs, candidate_verify_receipt=head_changed))
        wrong_candidate = dict(verify, current_candidate_id="sha256:" + "0" * 64)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(p3, **dict(kwargs, candidate_verify_receipt=wrong_candidate))
        unbound_final = dict(e3, candidate_verify_receipt_digest="sha256:" + "0" * 64)
        unbound_final["evidence_digest"] = digest(unbound_final, without=("evidence_digest",))
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(p3, **dict(kwargs, final_candidate_evidence=unbound_final))
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(p3, **dict(kwargs, dependency_acceptance_contexts={"p1": p1, "p2": c2}))
        cyclic_p1 = full_protocol.AcceptanceContext(acceptance=p3, relationship=relationship, final_candidate_evidence=e3, root_authority=r3, candidate_verify_receipt=verify, dependency_acceptance_contexts=dependencies)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_acceptance(p3, **dict(kwargs, dependency_acceptance_contexts={"p1": cyclic_p1, "p2": c2}))


if __name__ == "__main__":
    unittest.main()
