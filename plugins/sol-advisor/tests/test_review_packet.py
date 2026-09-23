from __future__ import annotations

import importlib.util
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import full_protocol
import workflow
from test_full_protocol import ProtocolFixture, candidate_evidence, digest
from test_run_check import run_check


def load_review_packet():
    path = SCRIPTS / "review-packet.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("sol_advisor_review_packet", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


review_packet = load_review_packet()


class ReviewFixture:
    def __init__(self, *, review_policy: dict[str, object] | None = None, scoped_paths: list[str] | None = None, challenge_allowed_suffixes: list[list[str]] | None = None) -> None:
        self.protocol = ProtocolFixture(
            review_policy=review_policy, scoped_paths=scoped_paths,
            challenge_allowed_suffixes=challenge_allowed_suffixes,
            scoped_check_script="import sys\nprint('recorded evidence')\nraise SystemExit(7 if '--fail' in sys.argv else 0)\n",
        )
        self.task = Path(self.protocol._temporary_repo.name) / "review-task"
        self.bridge_path = self.task.parent / "candidate-bridge.json"
        self.bridge_path.write_bytes(full_protocol.canonical_json_bytes(self.protocol.bridge))
        self.state = {
            "version": 0,
            "contract_digest": self.protocol.contract["contract_digest"],
            "stage_status": {"status": "ready", "review_status": "reviewing"},
            "work_status": {"p1": "ready"},
            "selected_attempts": {"p1": self.protocol.delivery["delivery_id"]},
            "current_ids": {
                "assembly_index": self.protocol.assembly["assembly_id"],
                "candidate_binding": self.protocol.bridge["bridge_id"],
                "review_packet": None,
                "verdict": None,
                "acceptance": None,
            },
            "applicable_rejection_roots": [],
            "last_operation_receipt": None,
        }
        workflow.initialize_task(self.task, self.protocol.contract, self.state)
        self.base_context = self.protocol.context()

    def cleanup(self) -> None:
        self.protocol._temporary_repo.cleanup()

    def runtime(self, **updates: object) -> dict[str, object]:
        value = {
            "thread_id": "sol-thread-1",
            "context_id": "sol-context-1",
            "agent_role": "sol_advisor_sol_reviewer",
            "model": "gpt-6-sol",
            "effort": "xhigh",
            "sandbox_policy_type": "read-only",
            "permission_profile_type": "disabled",
            "prompt_digest": "sha256:" + "3" * 64,
            "task_id": "fixture-task",
            "stage_key": "p1",
        }
        value.update(updates)
        return value

    def bundle(self, evidence: list[dict[str, object]] | None = None):
        evidence = evidence or [candidate_evidence(self.protocol)]
        evidence = [self.persist_evidence(item) for item in evidence]
        return review_packet.bundle_review_packet(
            self.task,
            op_id="bundle-1",
            expected_state_version=0,
            context=self.base_context,
            candidate_evidence=evidence,
            expected_coverage=["delivery", "candidate"],
            predecessor_verdicts={},
        )

    def challenge(self, bundled):
        request = review_packet.prepare_challenge(
            self.task,
            relationship=bundled["context"],
            request_id="Q-1",
            check_key="challenge",
            authority_decision="allowed-by-task-contract",
        )
        evidence = self.challenge_evidence(request)
        return review_packet.record_challenge_evidence(
            self.task, relationship=bundled["context"], request=request, evidence=evidence
        )

    def challenge_evidence(self, request):
        return run_check.execute_check(
            self.task, run_id=f"challenge-{request['request_id']}",
            check_key="challenge", subject_id=f"{request['packet_id']}:{request['candidate_bridge_id']}",
            argv_suffix=request.get("argv_suffix", []), challenge_request=request,
        )["evidence"]

    def persist_evidence(self, evidence: dict[str, object]) -> dict[str, object]:
        run_id = str(evidence["evidence_id"])[2:]
        return run_check.execute_check(
            self.task, run_id=run_id, check_key="candidate",
            subject_id=self.protocol.bridge["bridge_id"],
            argv_suffix=["--fail"] if evidence["result"] == "fail" else [],
            candidate_manifest_path=self.protocol.bridge["manifest_path"],
            candidate_bridge_path=self.bridge_path,
        )["evidence"]

    def ship_verdict(self, context, runtime: dict[str, object] | None = None):
        runtime = runtime or self.runtime()
        attestation = review_packet.observed_reviewer_attestation(runtime, self.protocol.contract["review_policy"])
        verdict = {
            "record_type": "V", "verdict_id": "V-1",
            "contract_digest": self.protocol.contract["contract_digest"],
            "status": "valid", "verdict": "ship",
            "packet_id": context.packet["packet_id"],
            "candidate_bridge_id": self.protocol.bridge["bridge_id"],
            "challenge_receipt_id": context.challenge_receipt["challenge_receipt_id"],
            "rejection_closure": [], "coverage_complete": True,
            "rejection_dispositions": {}, "open_rejections": [],
            "observed_attestation_digest": digest(attestation),
        }
        if attestation.get("schema") == "SA-REVIEW-ATTESTATION-1":
            reviewer = attestation["reviewer"]
            verdict.update({"reviewer_thread_id": reviewer["thread_id"], "reviewer_context_id": reviewer["context_id"]})
        return verdict, runtime


class ReviewPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(review_packet, "review-packet.py is missing")

    def fixture(self, **kwargs: object) -> ReviewFixture:
        fixture = ReviewFixture(**kwargs)
        self.addCleanup(fixture.cleanup)
        return fixture

    def test_bundle_freezes_complete_candidate_evidence_and_state(self) -> None:
        fixture = self.fixture()
        bundled = fixture.bundle()
        packet = bundled["packet"]
        self.assertEqual(packet["candidate_bridge_id"], fixture.protocol.bridge["bridge_id"])
        self.assertEqual(packet["candidate_evidence_ids"], ["E-candidate-1"])
        state = workflow.read_task(fixture.task)["state"]
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["current_ids"]["review_packet"], packet["packet_id"])
        self.assertTrue((fixture.task / "review-packets" / packet["packet_id"] / "P.json").is_file())

        replay = fixture.bundle()
        self.assertEqual(replay["packet"], packet)
        self.assertEqual(workflow.read_task(fixture.task)["state"]["version"], 1)

    def test_bundle_rejects_missing_duplicate_nonpass_and_changed_candidate(self) -> None:
        fixture = self.fixture()
        with self.assertRaises(workflow.WorkflowError) as missing:
            review_packet.bundle_review_packet(
                fixture.task, op_id="missing", expected_state_version=0,
                context=fixture.base_context, candidate_evidence=[],
                expected_coverage=["delivery", "candidate"], predecessor_verdicts={},
            )
        self.assertEqual(missing.exception.category, "missing-evidence")
        self.assertFalse((fixture.task / "operation-intent" / "missing.json").exists())

        unrecorded = candidate_evidence(fixture.protocol)
        with self.assertRaises(workflow.WorkflowError) as no_run:
            review_packet.bundle_review_packet(
                fixture.task, op_id="unrecorded", expected_state_version=0,
                context=fixture.base_context, candidate_evidence=[unrecorded],
                expected_coverage=["delivery", "candidate"], predecessor_verdicts={},
            )
        self.assertEqual(no_run.exception.category, "missing-evidence")

        evidence = fixture.persist_evidence(candidate_evidence(fixture.protocol))
        duplicate = dict(evidence, evidence_id="E-candidate-2")
        duplicate["evidence_digest"] = digest(duplicate, without=("evidence_digest",))
        duplicate = fixture.persist_evidence(duplicate)
        with self.assertRaises(workflow.WorkflowError):
            review_packet.bundle_review_packet(
                fixture.task, op_id="duplicate", expected_state_version=0,
                context=fixture.base_context, candidate_evidence=[evidence, duplicate],
                expected_coverage=["delivery", "candidate"], predecessor_verdicts={},
            )

        nonpass = dict(evidence, evidence_id="E-candidate-failed", result="fail")
        nonpass["evidence_digest"] = digest(nonpass, without=("evidence_digest",))
        nonpass = fixture.persist_evidence(nonpass)
        with self.assertRaises(workflow.WorkflowError) as failed:
            review_packet.bundle_review_packet(
                fixture.task, op_id="nonpass", expected_state_version=0,
                context=fixture.base_context, candidate_evidence=[nonpass],
                expected_coverage=["delivery", "candidate"], predecessor_verdicts={},
            )
        self.assertEqual(failed.exception.category, "missing-evidence")

        repo = Path(fixture.protocol.manifest["repo"])
        (repo / "README.md").write_text("changed before bundle\n", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as changed:
            fixture.bundle()
        self.assertEqual(changed.exception.category, "candidate-changed")

    def test_packet_and_challenge_reject_passing_truncated_evidence(self) -> None:
        fixture = self.fixture()
        forged = candidate_evidence(fixture.protocol)
        forged = fixture.persist_evidence(forged)
        forged["logs"][0]["truncated"] = True
        forged["evidence_digest"] = digest(forged, without=("evidence_digest",))
        with self.assertRaises(workflow.WorkflowError):
            review_packet.bundle_review_packet(fixture.task, op_id="truncated-p", expected_state_version=0, context=fixture.base_context, candidate_evidence=[forged], expected_coverage=["delivery", "candidate"], predecessor_verdicts={})
        challenged = fixture.challenge(fixture.bundle())
        bad = dict(challenged["context"].challenge_evidence)
        bad["logs"] = [dict(item) for item in bad["logs"]]
        bad["logs"][0]["truncated"] = True
        bad["evidence_digest"] = digest(bad, without=("evidence_digest",))
        with self.assertRaises(workflow.WorkflowError):
            review_packet.record_challenge_evidence(fixture.task, relationship=fixture.bundle()["context"], request=challenged["context"].challenge_request, evidence=bad)

    def test_prepare_challenge_cli_binds_exact_suffixes_and_legacy_empty(self) -> None:
        def package(context):
            return {"task_contract": context.task_contract, "candidate_bridge": context.candidate_bridge, "manifest": context.manifest, "manifest_bytes_base64": base64.b64encode(context.manifest_bytes).decode(), "candidate_verify_receipt": context.candidate_verify_receipt, "assembly": context.assembly, "deliveries": context.deliveries, "materials": context.materials, "delivery_evidence": context.delivery_evidence, "packet": context.packet, "candidate_evidence": context.candidate_evidence, "applicable_rejection_roots": context.applicable_rejection_roots, "predecessor_verdicts": context.predecessor_verdicts, "expected_coverage": context.expected_coverage}
        allowed = self.fixture(challenge_allowed_suffixes=[["a b", "x\ny"]])
        allowed_context = allowed.bundle()["context"]
        relationship = allowed.task.parent / "relationship.json"
        relationship.write_text(json.dumps(package(allowed_context)), encoding="utf-8")
        script = SCRIPTS / "review-packet.py"
        command = [sys.executable, str(script), "prepare-challenge", "--task-dir", str(allowed.task), "--relationship", str(relationship), "--request-id", "cli-ok", "--check-key", "challenge", "--authority-decision", "allowed", "--arg", "a b", "--arg", "x\ny"]
        ok = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        request = json.loads((allowed.task / "challenges" / "cli-ok" / "request.json").read_text())
        self.assertEqual(request["argv_suffix"], ["a b", "x\ny"])
        bad = subprocess.run([*command[:command.index("--request-id")], "--request-id", "cli-bad", *command[command.index("--check-key"):], "--arg", "no"], text=True, capture_output=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse((allowed.task / "operation-intent" / "cli-bad.json").exists())
        legacy = self.fixture()
        legacy_context = legacy.bundle()["context"]
        legacy_path = legacy.task.parent / "legacy-relationship.json"
        legacy_path.write_text(json.dumps(package(legacy_context)), encoding="utf-8")
        empty = subprocess.run([sys.executable, str(script), "prepare-challenge", "--task-dir", str(legacy.task), "--relationship", str(legacy_path), "--request-id", "cli-empty", "--check-key", "challenge", "--authority-decision", "allowed"], text=True, capture_output=True)
        self.assertEqual(empty.returncode, 0, empty.stderr)

    def test_challenge_request_evidence_and_receipt_bind_without_self_review_loop(self) -> None:
        fixture = self.fixture()
        bundled = fixture.bundle()
        challenged = fixture.challenge(bundled)
        context = challenged["context"]
        self.assertEqual(context.challenge_receipt["evidence_id"], context.challenge_evidence["evidence_id"])
        self.assertEqual(context.challenge_request["request_digest"], context.challenge_receipt["challenge_request_digest"])
        self.assertTrue((fixture.task / "challenges" / "Q-1" / "CR.json").is_file())
        self.assertFalse(any((fixture.task / "operation-intent").glob("*review-challenge*")))

        bad = dict(context.challenge_evidence, challenge_request_digest="sha256:" + "0" * 64)
        bad["evidence_digest"] = digest(bad, without=("evidence_digest",))
        with self.assertRaises(workflow.WorkflowError):
            review_packet.record_challenge_evidence(
                fixture.task, relationship=bundled["context"],
                request=context.challenge_request, evidence=bad,
            )

        unrecorded = dict(context.challenge_evidence, evidence_id="E-challenge-unrecorded")
        unrecorded["evidence_digest"] = digest(unrecorded, without=("evidence_digest",))
        with self.assertRaises(workflow.WorkflowError) as no_run:
            review_packet.record_challenge_evidence(
                fixture.task, relationship=bundled["context"],
                request=context.challenge_request, evidence=unrecorded,
            )
        self.assertEqual(no_run.exception.category, "missing-evidence")

    def test_prepare_challenge_fails_closed_for_intent_only_and_request_only(self) -> None:
        intent_only = self.fixture()
        bundle = intent_only.bundle()
        request = review_packet.prepare_challenge(
            intent_only.task, relationship=bundle["context"], request_id="Q-1",
            check_key="challenge", authority_decision="allowed-by-task-contract",
        )
        request_path = intent_only.task / "challenges" / request["request_id"] / "request.json"
        request_path.unlink()
        for receipt in (intent_only.task / "operation-receipt").glob("*Q-1.json"):
            receipt.unlink()
        with self.assertRaises(workflow.WorkflowError) as rejected:
            review_packet.prepare_challenge(
                intent_only.task, relationship=bundle["context"], request_id="Q-1",
                check_key="challenge", authority_decision="allowed-by-task-contract",
            )
        self.assertEqual(rejected.exception.category, "execution-incomplete")
        self.assertFalse(request_path.exists())

        request_only = self.fixture()
        bundle = request_only.bundle()
        request = review_packet.prepare_challenge(
            request_only.task, relationship=bundle["context"], request_id="Q-1",
            check_key="challenge", authority_decision="allowed-by-task-contract",
        )
        request_path = request_only.task / "challenges" / request["request_id"] / "request.json"
        for intent in (request_only.task / "operation-intent").glob("*Q-1.json"):
            intent.unlink()
        for receipt in (request_only.task / "operation-receipt").glob("*Q-1.json"):
            receipt.unlink()
        with self.assertRaises(workflow.WorkflowError) as rejected:
            review_packet.prepare_challenge(
                request_only.task, relationship=bundle["context"], request_id="Q-1",
                check_key="challenge", authority_decision="allowed-by-task-contract",
            )
        self.assertEqual(rejected.exception.category, "execution-incomplete")
        self.assertTrue(request_path.exists())

    def test_record_requires_completed_prepare_before_new_record_writes(self) -> None:
        fixture = self.fixture()
        bundled = fixture.bundle()
        request = review_packet.prepare_challenge(
            fixture.task, relationship=bundled["context"], request_id="Q-1",
            check_key="challenge", authority_decision="allowed-by-task-contract",
        )
        evidence = fixture.challenge_evidence(request)
        for receipt in (fixture.task / "operation-receipt").glob("*Q-1.json"):
            receipt.unlink()
        with self.assertRaises(workflow.WorkflowError) as rejected:
            review_packet.record_challenge_evidence(
                fixture.task, relationship=bundled["context"], request=request, evidence=evidence,
            )
        self.assertEqual(rejected.exception.category, "missing-evidence")
        self.assertFalse((fixture.task / "challenges" / "Q-1" / "CR.json").exists())
        self.assertFalse(any((fixture.task / "operation-intent").glob("record-challenge-*.json")))

    def test_prepare_only_recovers_the_missing_receipt_for_an_exact_request(self) -> None:
        fixture = self.fixture()
        bundled = fixture.bundle()
        request = review_packet.prepare_challenge(
            fixture.task, relationship=bundled["context"], request_id="Q-1",
            check_key="challenge", authority_decision="allowed-by-task-contract",
        )
        request_path = fixture.task / "challenges" / "Q-1" / "request.json"
        receipt_path = fixture.task / "operation-receipt" / "prepare-challenge-Q-1.json"
        receipt_path.unlink()
        with mock.patch.object(
            workflow, "publish_task_path_json", wraps=workflow.publish_task_path_json,
        ) as published:
            recovered = review_packet.prepare_challenge(
                fixture.task, relationship=bundled["context"], request_id="Q-1",
                check_key="challenge", authority_decision="allowed-by-task-contract",
            )
        self.assertEqual(recovered, request)
        self.assertTrue(receipt_path.is_file())
        self.assertFalse(any(
            len(call.args) > 1 and Path(call.args[1]) == request_path
            for call in published.call_args_list
        ), "noncreator recovery must not rewrite request.json")

    def test_record_is_single_writer_and_same_operation_is_receipted_idempotently(self) -> None:
        fixture = self.fixture()
        bundled = fixture.bundle()
        request = review_packet.prepare_challenge(
            fixture.task, relationship=bundled["context"], request_id="Q-1",
            check_key="challenge", authority_decision="allowed-by-task-contract",
        )
        evidence = fixture.challenge_evidence(request)
        evidence_path = fixture.task / "evidence" / "E-challenge-Q-1.json"
        with mock.patch.object(
            workflow, "publish_task_path_json", wraps=workflow.publish_task_path_json,
        ) as published:
            first = review_packet.record_challenge_evidence(
                fixture.task, relationship=bundled["context"], request=request, evidence=evidence,
            )
        self.assertFalse(any(
            len(call.args) > 1 and Path(call.args[1]) == evidence_path
            for call in published.call_args_list
        ), "record-challenge must not republish run-check's E")
        self.assertTrue((fixture.task / "operation-intent" / "record-challenge-Q-1.json").is_file())
        self.assertTrue((fixture.task / "operation-receipt" / "record-challenge-Q-1.json").is_file())
        second = review_packet.record_challenge_evidence(
            fixture.task, relationship=bundled["context"], request=request, evidence=evidence,
        )
        self.assertEqual(second["receipt"], first["receipt"])

    def test_record_review_requires_observed_sol_and_applies_ship_transition(self) -> None:
        fixture = self.fixture()
        challenged = fixture.challenge(fixture.bundle())
        verdict, runtime = fixture.ship_verdict(challenged["context"])
        with self.assertRaises(workflow.WorkflowError) as rejected:
            review_packet.record_review(
                fixture.task, op_id="review-1", expected_state_version=1,
                relationship=challenged["context"], verdict=verdict,
                reviewer_runtime_receipt=runtime,
            )
        self.assertEqual(rejected.exception.category, "review-invalid")

    def test_tagged_hard_read_only_review_publishes_valid_v(self) -> None:
        policy = {
            "allowed_verdicts": ["ship", "fix-first", "rethink"],
            "review_identity_schema": "SA-REVIEW-ATTESTATION-1",
            "isolation_admission": "hard-read-only",
        }
        fixture = self.fixture(review_policy=policy)
        challenged = fixture.challenge(fixture.bundle())
        verdict, runtime = fixture.ship_verdict(challenged["context"])
        result = review_packet.record_review(
            fixture.task, op_id="tagged-hard-v", expected_state_version=1,
            relationship=challenged["context"], verdict=verdict,
            reviewer_runtime_receipt=runtime,
        )
        self.assertEqual(result["verdict"]["verdict"], "ship")
        self.assertEqual(workflow.read_task(fixture.task)["state"]["current_ids"]["verdict"], "V-1")

    def test_legacy_contract_cannot_publish_a_new_verdict(self) -> None:
        """Legacy attestations remain readable, but cannot sign current task state."""
        fixture = self.fixture()
        challenged = fixture.challenge(fixture.bundle())
        verdict, runtime = fixture.ship_verdict(challenged["context"])
        with self.assertRaises(workflow.WorkflowError) as rejected:
            review_packet.record_review(
                fixture.task, op_id="legacy-publish", expected_state_version=1,
                relationship=challenged["context"], verdict=verdict,
                reviewer_runtime_receipt=runtime,
            )
        self.assertEqual(rejected.exception.category, "review-invalid")
        self.assertFalse((fixture.task / "operation-intent" / "legacy-publish.json").exists())

    def test_behavioral_runtime_cannot_supply_its_own_window(self) -> None:
        fixture = self.fixture()
        policy = {
            "allowed_verdicts": ["ship", "fix-first", "rethink"],
            "review_identity_schema": "SA-REVIEW-ATTESTATION-1",
            "isolation_admission": "hard-or-behavioral",
            "behavioral_read_only_prompt_digest": "sha256:" + "2" * 64,
        }
        runtime = fixture.runtime(
            sandbox_policy_type="danger-full-access", permission_profile_type="disabled",
            prompt_digest=policy["behavioral_read_only_prompt_digest"],
            reviewer_windows=[{
                "candidate_before": {"candidate_id": "unrelated"}, "candidate_after": {"candidate_id": "unrelated"},
                "task_tree_before": "sha256:before", "task_tree_after": "sha256:before",
            }],
        )
        with self.assertRaises(workflow.WorkflowError) as rejected:
            review_packet.observed_reviewer_attestation(runtime, policy)
        self.assertEqual(rejected.exception.category, "review-invalid")

    def test_controlled_behavioral_window_binds_current_candidate_and_task_tree(self) -> None:
        fixture = self.fixture()
        attestation = {
            "schema": "SA-REVIEW-ATTESTATION-1", "mode": "behavioral-window",
            "reviewer": {"thread_id": "sol-thread-1", "context_id": "sol-context-1", "context_source": "observed-context", "role": "sol_advisor_sol_reviewer", "model": "gpt-6-sol", "effort": "xhigh", "runtime_receipt_digest": "sha256:" + "1" * 64},
            "observed": {"sandbox_policy_type": "danger-full-access", "permission_profile": "disabled", "prompt_digest": "sha256:" + "2" * 64},
            "windows": [], "attestation_digest": "",
        }
        observed = review_packet._controlled_behavioral_window(fixture.task, fixture.base_context, attestation)
        window = observed["windows"][0]
        self.assertEqual(window["candidate_before"], window["candidate_after"])
        self.assertEqual(window["candidate_before"]["candidate_id"], fixture.protocol.bridge["candidate_id"])
        self.assertEqual(window["task_tree_before"], window["task_tree_after"])
        self.assertTrue(observed["attestation_digest"].startswith("sha256:"))

    def test_review_rejects_wrong_identity_invalid_ship_and_candidate_drift_before_intent(self) -> None:
        wrong = self.fixture()
        challenged = wrong.challenge(wrong.bundle())
        verdict, _ = wrong.ship_verdict(challenged["context"])
        runtime = wrong.runtime(model="gpt-6-astra")
        with self.assertRaises(workflow.WorkflowError) as identity:
            review_packet.record_review(
                wrong.task, op_id="wrong-sol", expected_state_version=1,
                relationship=challenged["context"], verdict=verdict,
                reviewer_runtime_receipt=runtime,
            )
        self.assertEqual(identity.exception.category, "review-invalid")
        self.assertFalse((wrong.task / "operation-intent" / "wrong-sol.json").exists())

        invalid = self.fixture()
        challenged = invalid.challenge(invalid.bundle())
        verdict, runtime = invalid.ship_verdict(challenged["context"])
        verdict["coverage_complete"] = False
        with self.assertRaises(workflow.WorkflowError):
            review_packet.record_review(
                invalid.task, op_id="invalid-ship", expected_state_version=1,
                relationship=challenged["context"], verdict=verdict,
                reviewer_runtime_receipt=runtime,
            )

        drifted = self.fixture()
        challenged = drifted.challenge(drifted.bundle())
        verdict, runtime = drifted.ship_verdict(challenged["context"])
        (Path(drifted.protocol.manifest["repo"]) / "README.md").write_text("changed during review\n", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as changed:
            review_packet.record_review(
                drifted.task, op_id="drifted-review", expected_state_version=1,
                relationship=challenged["context"], verdict=verdict,
                reviewer_runtime_receipt=runtime,
            )
        self.assertEqual(changed.exception.category, "review-invalid")
        self.assertFalse((drifted.task / "operation-intent" / "drifted-review.json").exists())

    def test_design_review_is_separate_and_cannot_carry_product_authority(self) -> None:
        fixture = self.fixture()
        runtime = fixture.runtime()
        review = {
            "record_type": "DR", "review_id": "DR-1", "status": "valid",
            "design_verdict": "design-approved",
            "contract_digest": fixture.protocol.contract["contract_digest"],
        }
        with self.assertRaises(workflow.WorkflowError) as legacy:
            review_packet.record_design_review(
                fixture.task, review=review, reviewer_runtime_receipt=runtime
            )
        self.assertEqual(legacy.exception.category, "review-invalid")

        elevated = dict(review, candidate_bridge_id=fixture.protocol.bridge["bridge_id"])
        with self.assertRaises(workflow.WorkflowError):
            review_packet.record_design_review(
                fixture.task, review=elevated,
                reviewer_runtime_receipt=runtime,
            )

    def test_tagged_design_review_binds_immutable_input_and_hard_attestation(self) -> None:
        """The new DR relation must not be a re-signed legacy review."""
        fixture = self.fixture()
        contract = json.loads(json.dumps(fixture.protocol.contract))
        contract["review_policy"] = {
            "allowed_verdicts": ["ship", "fix-first", "rethink"],
            "review_identity_schema": "SA-REVIEW-ATTESTATION-1",
            "isolation_admission": "hard-read-only",
        }
        contract["contract_digest"] = digest(contract, without=("contract_digest",))
        state = json.loads(json.dumps(fixture.state))
        state["contract_digest"] = contract["contract_digest"]
        task = fixture.task.parent / "tagged-design-task"
        workflow.initialize_task(task, contract, state)
        review = {
            "record_type": "DR", "review_id": "DR-tagged-1", "status": "valid",
            "design_verdict": "design-approved", "contract_digest": contract["contract_digest"],
        }
        runtime = fixture.runtime(permission_profile_type="read-only-profile", prompt_digest="sha256:" + "1" * 64)
        result = review_packet.record_design_review(
            task, review=review, reviewer_runtime_receipt=runtime,
            design_input={"design": "immutable-source"},
        )
        self.assertEqual(result["design_input_digest"], digest({"design": "immutable-source"}))
        self.assertTrue((task / "design-reviews" / "DR-tagged-1" / "design-input.json").is_file())
        self.assertTrue(result["observed_attestation_digest"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
