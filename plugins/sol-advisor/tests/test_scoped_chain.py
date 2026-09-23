from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import workflow
from test_full_protocol import ProtocolFixture, digest
from test_review_packet import load_review_packet
from test_run_check import load_run_check


review_packet = load_review_packet()
run_check = load_run_check()

TAGGED_HARD_POLICY = {
    "allowed_verdicts": ["ship", "fix-first", "rethink"],
    "review_identity_schema": "SA-REVIEW-ATTESTATION-1",
    "isolation_admission": "hard-read-only",
}


class ScopedChainTests(unittest.TestCase):
    """Real-run regression coverage for the scoped full-route evidence chain."""

    def setUp(self) -> None:
        self.assertIsNotNone(review_packet, "review-packet.py is missing")
        self.assertIsNotNone(run_check, "run-check.py is missing")

    def test_scoped_candidate_run_persists_real_evidence_before_packet(self) -> None:
        fixture = self._fixture()
        self.addCleanup(fixture.cleanup)

        task = self._initialize_task(fixture)
        candidate = self._run_candidate_check(fixture, task, "candidate-pre")

        self.assertEqual(candidate["evidence"]["result"], "pass")
        self.assertEqual(candidate["evidence"]["scope"], "candidate")
        self.assertTrue((task / "runs" / "candidate-pre" / "stdout.log").is_file())
        self.assertTrue((task / "runs" / "candidate-pre" / "run-record.json").is_file())
        self.assertTrue((task / "operation-intent" / "candidate-pre.json").is_file())
        self.assertTrue((task / "operation-receipt" / "candidate-pre.json").is_file())

    def test_scoped_chain_records_packet_challenge_and_tagged_hard_review_from_real_runs(self) -> None:
        fixture = self._fixture()
        self.addCleanup(fixture.cleanup)
        task = self._initialize_task(fixture)
        relationship = self._bundle_and_challenge(fixture, task)
        reviewed = self._record_hard_ship(fixture, task, relationship)

        self.assertEqual(reviewed["verdict"]["verdict"], "ship")
        self.assertEqual(workflow.read_task(task)["state"]["stage_status"]["review_status"], "reviewed-awaiting-final-accept")
        self.assertEqual(relationship.packet["candidate_evidence_ids"], ["E-candidate-pre"])
        self.assertTrue((task / "runs" / "candidate-pre" / "run-record.json").is_file())
        self.assertTrue((task / "runs" / "challenge-Q-scoped" / "run-record.json").is_file())
        self.assertTrue((task / "challenges" / "Q-scoped" / "CR.json").is_file())
        self.assertTrue((task / "reviews" / "V-scoped" / "V.json").is_file())

    def test_scoped_readme_byte_drift_rejects_review_before_its_intent(self) -> None:
        fixture = self._fixture()
        self.addCleanup(fixture.cleanup)
        task = self._initialize_task(fixture)
        relationship = self._bundle_and_challenge(fixture, task)
        verdict, runtime = self._ship_verdict(fixture, relationship)
        (Path(fixture.manifest["repo"]) / "README.md").write_text("drift before review\n", encoding="utf-8")

        with self.assertRaises(workflow.WorkflowError):
            review_packet.record_review(
                task,
                op_id="review-scoped-drift",
                expected_state_version=1,
                relationship=relationship,
                verdict=verdict,
                reviewer_runtime_receipt=runtime,
            )
        self.assertFalse((task / "operation-intent" / "review-scoped-drift.json").exists())

    def test_scoped_chain_accepts_after_runner_persists_distinct_final_candidate_evidence(self) -> None:
        fixture = self._fixture()
        self.addCleanup(fixture.cleanup)
        task = self._initialize_task(fixture)
        relationship = self._bundle_and_challenge(fixture, task)
        reviewed = self._record_hard_ship(fixture, task, relationship)
        final_run = self._run_final_candidate_check(fixture, task, "candidate-final")
        acceptance, authority = self._acceptance_inputs(fixture, reviewed["context"], final_run["evidence"])

        receipt = workflow.final_accept(
            task,
            op_id="accept-scoped",
            expected_state_version=2,
            acceptance=acceptance,
            relationship=reviewed["context"],
            final_candidate_evidence=final_run["evidence"],
            root_authority=authority,
            candidate_verify_receipt=fixture.candidate_verify_receipt,
            dependency_acceptance_contexts={},
            trusted_observation_time=final_run["evidence"]["observed_at"],
        )

        self.assertEqual(receipt["outcome"], "success")
        self.assertNotEqual(final_run["evidence"]["evidence_id"], relationship.packet["candidate_evidence_ids"][0])
        self.assertEqual(final_run["evidence"]["phase"], "final-candidate-verify")
        self.assertTrue((task / "runs" / "candidate-final" / "run-record.json").is_file())
        replay = workflow.final_accept(
            task, op_id="accept-scoped", expected_state_version=2,
            acceptance=acceptance, relationship=reviewed["context"],
            final_candidate_evidence=final_run["evidence"], root_authority=authority,
            candidate_verify_receipt=fixture.candidate_verify_receipt,
            dependency_acceptance_contexts={},
            trusted_observation_time=final_run["evidence"]["observed_at"],
        )
        self.assertEqual(replay, receipt)
        self.assertEqual(workflow.read_task(task)["state"]["version"], 3)

        altered = dict(final_run["evidence"], result="fail")
        altered["evidence_digest"] = digest({key: value for key, value in altered.items() if key != "evidence_digest"})
        with self.assertRaises(workflow.WorkflowError) as rejected:
            workflow.final_accept(
                task, op_id="accept-altered", expected_state_version=3,
                acceptance=acceptance, relationship=reviewed["context"],
                final_candidate_evidence=altered, root_authority=authority,
                candidate_verify_receipt=fixture.candidate_verify_receipt,
                dependency_acceptance_contexts={},
                trusted_observation_time=final_run["evidence"]["observed_at"],
            )
        self.assertEqual(rejected.exception.category, "candidate-changed")
        self.assertFalse((task / "operation-intent" / "accept-altered.json").exists())

    def test_scoped_readme_byte_drift_rejects_final_acceptance_before_its_intent(self) -> None:
        fixture = self._fixture()
        self.addCleanup(fixture.cleanup)
        task = self._initialize_task(fixture)
        relationship = self._bundle_and_challenge(fixture, task)
        reviewed = self._record_hard_ship(fixture, task, relationship)
        final_run = self._run_final_candidate_check(fixture, task, "candidate-final-drift")
        acceptance, authority = self._acceptance_inputs(fixture, reviewed["context"], final_run["evidence"])
        (Path(fixture.manifest["repo"]) / "README.md").write_text("drift before final acceptance\n", encoding="utf-8")

        with self.assertRaises(workflow.WorkflowError):
            workflow.final_accept(
                task,
                op_id="accept-scoped-drift",
                expected_state_version=2,
                acceptance=acceptance,
                relationship=reviewed["context"],
                final_candidate_evidence=final_run["evidence"],
                root_authority=authority,
                candidate_verify_receipt=fixture.candidate_verify_receipt,
                dependency_acceptance_contexts={},
                trusted_observation_time=final_run["evidence"]["observed_at"],
            )
        self.assertFalse((task / "operation-intent" / "accept-scoped-drift.json").exists())

    def _fixture(self) -> ProtocolFixture:
        return ProtocolFixture(
            review_policy=TAGGED_HARD_POLICY,
            scoped_paths=["README.md", "candidate-check.py"],
            scoped_check_script="print('candidate check ran')\n",
        )

    def _initialize_task(self, fixture: ProtocolFixture) -> Path:
        task = Path(fixture._temporary_repo.name) / "scoped-chain-task"
        state = {
            "version": 0,
            "contract_digest": fixture.contract["contract_digest"],
            "stage_status": {"status": "ready", "review_status": "reviewing"},
            "work_status": {"p1": "ready"},
            "selected_attempts": {"p1": fixture.delivery["delivery_id"]},
            "current_ids": {
                "assembly_index": fixture.assembly["assembly_id"],
                "candidate_binding": fixture.bridge["bridge_id"],
                "review_packet": None,
                "verdict": None,
                "acceptance": None,
            },
            "applicable_rejection_roots": [],
            "last_operation_receipt": None,
        }
        workflow.initialize_task(task, fixture.contract, state)
        return task

    def _run_candidate_check(self, fixture: ProtocolFixture, task: Path, run_id: str):
        bridge_path = task / "candidate-bridge.json"
        workflow.publish_task_path_json(task, bridge_path, fixture.bridge)
        return run_check.execute_check(
            task,
            run_id=run_id,
            check_key="candidate",
            subject_id=fixture.bridge["bridge_id"],
            candidate_manifest_path=fixture.bridge["manifest_path"],
            candidate_bridge_path=bridge_path,
        )

    def _run_final_candidate_check(self, fixture: ProtocolFixture, task: Path, run_id: str):
        bridge_path = task / "candidate-bridge.json"
        workflow.publish_task_path_json(task, bridge_path, fixture.bridge)
        return run_check.execute_check(
            task,
            run_id=run_id,
            check_key="candidate-final",
            subject_id=fixture.bridge["bridge_id"],
            candidate_manifest_path=fixture.bridge["manifest_path"],
            candidate_bridge_path=bridge_path,
        )

    def _bundle_and_challenge(self, fixture: ProtocolFixture, task: Path):
        candidate = self._run_candidate_check(fixture, task, "candidate-pre")
        bundled = review_packet.bundle_review_packet(
            task,
            op_id="bundle-scoped",
            expected_state_version=0,
            context=fixture.context(),
            candidate_evidence=[candidate["evidence"]],
            expected_coverage=["delivery", "candidate"],
            predecessor_verdicts={},
        )
        request = review_packet.prepare_challenge(
            task,
            relationship=bundled["context"],
            request_id="Q-scoped",
            check_key="challenge",
            authority_decision="allowed-by-task-contract",
        )
        challenge = run_check.execute_check(
            task,
            run_id="challenge-Q-scoped",
            check_key="challenge",
            subject_id=f"{request['packet_id']}:{request['candidate_bridge_id']}",
            challenge_request=request,
        )
        return review_packet.record_challenge_evidence(
            task,
            relationship=bundled["context"],
            request=request,
            evidence=challenge["evidence"],
        )["context"]

    def _reviewer_runtime(self) -> dict[str, object]:
        return {
            "thread_id": "sol-thread-scoped",
            "context_id": "sol-context-scoped",
            "agent_role": "sol_advisor_sol_reviewer",
            "model": "gpt-6-sol",
            "effort": "xhigh",
            "sandbox_policy_type": "read-only",
            "permission_profile_type": "disabled",
            "prompt_digest": "sha256:" + "3" * 64,
            "task_id": "scoped-chain-fixture",
            "stage_key": "p1",
        }

    def _ship_verdict(self, fixture: ProtocolFixture, relationship):
        runtime = self._reviewer_runtime()
        attestation = review_packet.observed_reviewer_attestation(runtime, fixture.contract["review_policy"])
        reviewer = attestation["reviewer"]
        verdict = {
            "record_type": "V",
            "verdict_id": "V-scoped",
            "contract_digest": fixture.contract["contract_digest"],
            "status": "valid",
            "verdict": "ship",
            "packet_id": relationship.packet["packet_id"],
            "candidate_bridge_id": fixture.bridge["bridge_id"],
            "challenge_receipt_id": relationship.challenge_receipt["challenge_receipt_id"],
            "rejection_closure": [],
            "coverage_complete": True,
            "rejection_dispositions": {},
            "open_rejections": [],
            "observed_attestation_digest": digest(attestation),
            "reviewer_thread_id": reviewer["thread_id"],
            "reviewer_context_id": reviewer["context_id"],
            "reviewed_at": "2026-01-01T00:00:00Z",
            "review_sequence": 1,
        }
        return verdict, runtime

    def _record_hard_ship(self, fixture: ProtocolFixture, task: Path, relationship):
        verdict, runtime = self._ship_verdict(fixture, relationship)
        return review_packet.record_review(
            task,
            op_id="review-scoped",
            expected_state_version=1,
            relationship=relationship,
            verdict=verdict,
            reviewer_runtime_receipt=runtime,
        )

    def _acceptance_inputs(self, fixture: ProtocolFixture, relationship, final_evidence):
        verify_id = digest(fixture.candidate_verify_receipt)
        self.assertEqual(final_evidence["candidate_verify_receipt_id"], verify_id)
        scope = {
            "route": "full",
            "action": "final-accept",
            "stage_key": "p1",
            "candidate_bridge_id": fixture.bridge["bridge_id"],
        }
        observed_at = final_evidence["observed_at"]
        observed = {
            "context_id": "root-context-scoped",
            "thread_id": "root-thread-scoped",
            "role": "root",
            "model": "gpt-6-astra",
            "effort": "high",
            "observed_attestation": {"scope": scope, "observed_at": observed_at},
        }
        authority = {
            "root_authority_id": "root-scoped",
            "contract_digest": fixture.contract["contract_digest"],
            "scope": scope,
            "observed_at": observed_at,
            "expires_at": "2099-01-01T00:00:00Z",
            "candidate_verify_receipt_id": verify_id,
            "candidate_verify_receipt_digest": verify_id,
            "issuer": {"role": "root", "model": "gpt-6-astra"},
            "observed_attestation": observed,
            "observed_attestation_digest": digest(observed),
        }
        acceptance = {
            "record_type": "A",
            "acceptance_id": "A-scoped",
            "status": "accepted",
            "contract_digest": fixture.contract["contract_digest"],
            "accepted_stage_key": "p1",
            "candidate_bridge_id": fixture.bridge["bridge_id"],
            "packet_id": relationship.packet["packet_id"],
            "verdict_id": relationship.verdict["verdict_id"],
            "final_candidate_evidence_id": final_evidence["evidence_id"],
            "root_authority_id": authority["root_authority_id"],
            "root_authority_scope": scope,
            "root_authority_expiry": authority["expires_at"],
            "candidate_verify_receipt_id": verify_id,
            "dependency_acceptance_ids": {},
        }
        return acceptance, authority



if __name__ == "__main__":
    unittest.main()
