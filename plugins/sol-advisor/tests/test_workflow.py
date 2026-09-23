from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import subprocess
import sys
from fixture_support import fixture_directory
import threading
from pathlib import Path
from unittest import mock
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TEST_ARTIFACTS = Path(__file__).resolve().parents[3] / ".agent-artifacts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import full_protocol

try:
    workflow = importlib.import_module("workflow")
except ModuleNotFoundError:
    workflow = None


def digest(value: object) -> str:
    return full_protocol.canonical_digest(value)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(full_protocol.canonical_json_bytes(value))


class WorkflowFixture:
    def __init__(self, *, overlapping: bool = False, staged: bool = False) -> None:
        self.temp = fixture_directory(TEST_ARTIFACTS)
        self.root = Path(self.temp.name)
        self.baseline = self.root / "baseline"
        self.baseline.mkdir()
        subprocess.run(["git", "init", "-q", str(self.baseline)], check=True)
        subprocess.run(["git", "-C", str(self.baseline), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.baseline), "config", "user.name", "Fixture"], check=True)
        (self.baseline / "a.txt").write_text("a0\n", encoding="utf-8")
        (self.baseline / "b.txt").write_text("b0\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.baseline), "add", "a.txt", "b.txt"], check=True)
        subprocess.run(["git", "-C", str(self.baseline), "commit", "-qm", "baseline"], check=True)
        self.baseline_id = subprocess.run(
            ["git", "-C", str(self.baseline), "rev-parse", "HEAD"],
            check=True, text=True, capture_output=True,
        ).stdout.strip()
        b_paths = ["a.txt"] if overlapping else ["b.txt"]
        self.contract = {
            "protocol": "SA-FULL-V2-P2" if staged else "SA-FULL-V2-P1",
            "goal": "mechanically assemble two independent deliveries",
            "authority": {"allowed_paths": ["a.txt", "b.txt"]},
            "preserved_behavior": ["solo", "delegate", "audit"],
            "excluded_behavior": ["network", "credentials"],
            "stages": ({"s1": {"depends_on": [], "review_scope": "stage"}, "s2": {"depends_on": ["s1"], "review_scope": "stage+final"}} if staged else {"p2": {"depends_on": []}}),
            "work_items": {
                "a": {"paths": ["a.txt"], "baseline_id": self.baseline_id, **({"stage_key": "s1"} if staged else {})},
                "b": {"paths": b_paths, "baseline_id": self.baseline_id, **({"stage_key": "s2"} if staged else {})},
            },
            "checks": {
                "delivery": {"scope": "delivery", **({"phase": "pre-review", "required": True} if staged else {})},
                "candidate": {"scope": "candidate", **({"phase": "pre-review", "required": True} if staged else {})},
                "challenge": {"scope": "challenge", **({"phase": "pre-review", "required": True} if staged else {})},
            },
            "environment_policy": [],
            "required_coverage": ["delivery", "candidate"],
            "review_policy": ({"allowed_verdicts": ["ship", "fix-first", "rethink"], "review_identity_schema": "SA-REVIEW-ATTESTATION-2", "isolation_admission": "hard-or-behavioral", "behavioral_read_only_prompt_digest": "sha256:" + "1" * 64} if staged else {"allowed_verdicts": ["ship", "fix-first", "rethink"]}),
        }
        if staged:
            self.contract["checks"]["final"] = {"scope": "candidate", "phase": "pre-ship", "required": True, "final_candidate_verify": True}
            self.contract["probe_policy"] = {"scratch_root": "review-probes", "allowed_argv_prefixes": [[sys.executable]], "allowed_cwd": ".", "allowed_environment": [], "read_paths": ["review-probes", "assemblies"], "max_timeout_seconds": 30, "network": "forbidden"}
        self.contract["contract_digest"] = digest(self.contract)
        self.state = {
            "version": 0,
            "contract_digest": self.contract["contract_digest"],
            "stage_status": ({"stage_key": "s1", "status": "running", "review_status": "reviewing"} if staged else {"review_status": "reviewing"}),
            "work_status": {"a": "planned", "b": "planned"},
            "selected_attempts": {},
            "current_ids": {
                "assembly_index": None,
                "candidate_binding": None,
                "review_packet": None,
                "verdict": None,
                "acceptance": None,
            },
            "applicable_rejection_roots": [],
            "last_operation_receipt": None,
        }
        self.task = self.root / "task"
        workflow.initialize_task(self.task, self.contract, self.state)
        self.inputs = self.root / "inputs"

    def cleanup(self) -> None:
        self.temp.cleanup()

    def delivery_inputs(
        self, work_key: str, attempt: int = 1, *, baseline_id: str | None = None,
        content: str | None = None, operation: str = "modify",
    ) -> dict[str, Path]:
        path = self.contract["work_items"][work_key]["paths"][0]
        before_path = self.baseline / path
        before = before_path.read_bytes() if before_path.exists() else b""
        after = (content or f"{work_key}{attempt}\n").encode("utf-8")
        change = {
            "path": path,
            "operation": operation,
            "mode": "100644",
            "before_sha256": hashlib.sha256(before).hexdigest() if operation != "add" else None,
            "after_sha256": hashlib.sha256(after).hexdigest() if operation != "delete" else None,
            "content_base64": base64.b64encode(after).decode("ascii") if operation != "delete" else None,
        }
        bundle = {
            "schema_version": 1,
            "baseline_id": baseline_id or self.baseline_id,
            "changes": [change],
        }
        bundle_bytes = full_protocol.canonical_json_bytes(bundle)
        ready_identity = digest({
            "work_key": work_key,
            "attempt": attempt,
            "baseline_id": bundle["baseline_id"],
            "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        })
        material_id = f"M-{work_key}-{attempt}"
        delivery_id = f"D-{work_key}-{attempt}"
        evidence_id = f"E-{work_key}-{attempt}"
        material = {
            "record_type": "M",
            "material_id": material_id,
            "contract_digest": self.contract["contract_digest"],
            "work_key": work_key,
            "baseline_id": bundle["baseline_id"],
            "ready_identity": ready_identity,
            "bundle": {
                "files": [path],
                "sha256": hashlib.sha256(bundle_bytes).hexdigest(),
            },
        }
        material["material_digest"] = digest(material)
        runtime = {
            "thread_id": f"thread-{work_key}",
            "agent_role": "sol_advisor_sol_implementer",
            "model": "gpt-6-sol",
            "effort": "high",
            "task_id": "fixture-task",
            "stage_key": self.contract["work_items"][work_key].get("stage_key", "p2"),
            "work_key": work_key,
        }
        attestation = {
            "thread_id": runtime["thread_id"],
            "role": runtime["agent_role"],
            "model": runtime["model"],
            "effort": runtime["effort"],
            "self_review": "complete",
            "runtime_receipt_digest": digest(runtime),
        }
        delivery = {
            "record_type": "D",
            "delivery_id": delivery_id,
            "contract_digest": self.contract["contract_digest"],
            "work_key": work_key,
            "baseline_id": bundle["baseline_id"],
            "ready_identity": ready_identity,
            "material_id": material_id,
            "material_digest": material["material_digest"],
            "delivery_evidence_id": evidence_id,
            "attestation": attestation,
            "attempt": attempt,
        }
        delivery["delivery_digest"] = digest(delivery)
        evidence = {
            "record_type": "E",
            "evidence_id": evidence_id,
            "contract_digest": self.contract["contract_digest"],
            "scope": "delivery",
            "subject_id": material_id,
            "check_key": "delivery",
            "harness_identity": "workflow-fixture",
            "environment_identity": "offline-empty-env",
            "runtime_identity": digest(runtime),
            "result": "pass",
            "logs": [],
        }
        evidence["evidence_digest"] = digest(evidence)
        directory = self.inputs / f"{work_key}-{attempt}"
        paths = {
            "material": directory / "material.json",
            "delivery": directory / "delivery.json",
            "evidence": directory / "delivery-evidence.json",
            "bundle": directory / "bundle.json",
            "runtime": directory / "runtime.json",
        }
        write_json(paths["material"], material)
        write_json(paths["delivery"], delivery)
        write_json(paths["evidence"], evidence)
        paths["bundle"].write_bytes(bundle_bytes)
        write_json(paths["runtime"], runtime)
        return paths

    def receive(self, work_key: str, attempt: int = 1, *, expected: int, **kwargs: object):
        paths = self.delivery_inputs(work_key, attempt, **kwargs)
        receipt = workflow.receive_delivery(
            self.task,
            op_id=f"receive-{work_key}-{attempt}",
            expected_state_version=expected,
            material_path=paths["material"],
            delivery_path=paths["delivery"],
            delivery_evidence_path=paths["evidence"],
            bundle_path=paths["bundle"],
            runtime_receipt_path=paths["runtime"],
        )
        return paths, receipt


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(workflow, "workflow module is missing")

    def fixture(self, **kwargs: object) -> WorkflowFixture:
        fixture = WorkflowFixture(**kwargs)
        self.addCleanup(fixture.cleanup)
        return fixture

    def test_staged_assembly_rejects_skip_and_carries_accepted_prior_delivery(self) -> None:
        f = self.fixture(staged=True)
        _, first = f.receive("a", expected=0)
        self.assertEqual(first["outcome"], "success")
        with self.assertRaises(workflow.WorkflowError) as skipped:
            workflow.assemble_candidate(
                f.task, op_id="assemble-s2-skip", expected_state_version=1,
                baseline_repo=f.baseline, selected={"b": "D-b-1"}, stage_key="s2",
            )
        self.assertEqual(skipped.exception.category, "scope-conflict")
        first_assembly = workflow.assemble_candidate(
            f.task, op_id="assemble-s1", expected_state_version=1,
            baseline_repo=f.baseline, selected={"a": "D-a-1"}, stage_key="s1",
        )
        self.assertEqual(first_assembly["outcome"], "success")
        # A marker without the persisted A and successful final-accept receipt
        # is not an acceptance and cannot unlock the dependent stage.
        workflow.publish_task_path_json(f.task, f.task / "stage-acceptances" / "s1.json", {
            "stage_key": "s1", "acceptance_id": "A-s1", "candidate_bridge_id": "CB-assemble-s1",
            "selected_attempts": {"a": "D-a-1"}, "final_accept_op_id": "accept-s1", "final_candidate_evidence_id": "E-final-s1",
        })
        workflow.update_state_cas(f.task, expected_version=2, updates={"stage_status": {"stage_key": "s2", "status": "running", "review_status": "reviewing"}})
        _, second = f.receive("b", expected=3)
        self.assertEqual(second["outcome"], "success")
        with self.assertRaises(workflow.WorkflowError) as forged:
            workflow.assemble_candidate(
                f.task, op_id="assemble-s2", expected_state_version=4,
                baseline_repo=f.baseline, selected={"b": "D-b-1"}, stage_key="s2",
            )
        self.assertEqual(forged.exception.category, "missing-evidence")

    def test_initialize_and_state_cas_are_atomic_and_stale_safe(self) -> None:
        f = self.fixture()
        self.assertEqual(workflow.read_task(f.task)["state"]["version"], 0)
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.update_state_cas(f.task, expected_version=1, updates={"work_status": {"a": "ready", "b": "planned"}})
        self.assertEqual(caught.exception.category, "stale-baseline")
        self.assertEqual(caught.exception.side_effect, "none")
        self.assertEqual(workflow.read_task(f.task)["state"]["version"], 0)

    def test_bootstrap_requires_nonempty_root_component_chain(self) -> None:
        f = self.fixture()
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.bootstrap_task(f.root, [], f.contract, f.state)
        self.assertEqual(caught.exception.category, "invalid-input")

    def test_creator_operation_has_one_creator_and_conflicting_reuse_rejects(self) -> None:
        f = self.fixture()
        intent = {"record_type": "operation-intent", "op_id": "creator-1", "command_kind": "run-check", "request_digest": "sha256:" + "1" * 64, "contract_digest": f.contract["contract_digest"], "expected_state_version": 0, "planned_output_types": ["request"], "planned_output_paths": [str(f.task / "runs" / "creator-1" / "request.json")]}
        gate = threading.Barrier(2)
        results = []
        def call():
            gate.wait(); results.append(workflow.begin_creator_operation(f.task, intent))
        threads = [threading.Thread(target=call) for _ in range(2)]
        [item.start() for item in threads]; [item.join() for item in threads]
        self.assertEqual(sorted(results), [False, True])
        with self.assertRaises(workflow.WorkflowError):
            workflow.begin_creator_operation(f.task, dict(intent, request_digest="sha256:" + "2" * 64))

    def test_creator_operation_rejects_stale_state_before_publishing_intent(self) -> None:
        f = self.fixture()
        intent = {"record_type": "operation-intent", "op_id": "stale-creator", "command_kind": "run-check", "request_digest": "sha256:" + "1" * 64, "contract_digest": f.contract["contract_digest"], "expected_state_version": 0, "planned_output_types": ["request"], "planned_output_paths": [str(f.task / "runs" / "stale-creator" / "request.json")]}
        workflow.update_state_cas(
            f.task,
            expected_version=0,
            updates={"work_status": {"a": "ready", "b": "planned"}},
        )
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.begin_creator_operation(f.task, intent)
        self.assertEqual(caught.exception.category, "stale-baseline")
        self.assertFalse((f.task / "operation-intent" / "stale-creator.json").exists())

    def test_existing_identical_creator_is_noncreator_after_later_state_change(self) -> None:
        f = self.fixture()
        intent = {"record_type": "operation-intent", "op_id": "existing-creator", "command_kind": "run-check", "request_digest": "sha256:" + "1" * 64, "contract_digest": f.contract["contract_digest"], "expected_state_version": 0, "planned_output_types": ["request"], "planned_output_paths": [str(f.task / "runs" / "existing-creator" / "request.json")]}
        self.assertTrue(workflow.begin_creator_operation(f.task, intent))
        workflow.update_state_cas(
            f.task,
            expected_version=0,
            updates={"work_status": {"a": "ready", "b": "planned"}},
        )
        self.assertFalse(workflow.begin_creator_operation(f.task, intent))

    def test_creator_operation_rechecks_state_before_link_and_never_uses_public_publisher(self) -> None:
        f = self.fixture()
        intent = {"record_type": "operation-intent", "op_id": "rechecked-creator", "command_kind": "run-check", "request_digest": "sha256:" + "1" * 64, "contract_digest": f.contract["contract_digest"], "expected_state_version": 0, "planned_output_types": ["request"], "planned_output_paths": [str(f.task / "runs" / "rechecked-creator" / "request.json")]}
        original = workflow._publish_task_immutable_bytes_locked

        def change_state_before_link(task, clean, payload, *, before_link=None):
            workflow.replace_task_path_json(
                task,
                task / "state.json",
                dict(f.state, version=1, work_status={"a": "ready", "b": "planned"}),
            )
            return original(task, clean, payload, before_link=before_link)

        with mock.patch.object(workflow, "publish_task_path_json", side_effect=AssertionError("nested public publisher")):
            with mock.patch.object(workflow, "_publish_task_immutable_bytes_locked", side_effect=change_state_before_link):
                with self.assertRaises(workflow.WorkflowError) as caught:
                    workflow.begin_creator_operation(f.task, intent)
        self.assertEqual(caught.exception.category, "stale-baseline")
        self.assertFalse((f.task / "operation-intent" / "rechecked-creator.json").exists())

    def test_creator_operation_rejects_task_lock_swap_before_link_without_intent(self) -> None:
        f = self.fixture()
        intent = {"record_type": "operation-intent", "op_id": "lock-swapped-creator", "command_kind": "run-check", "request_digest": "sha256:" + "1" * 64, "contract_digest": f.contract["contract_digest"], "expected_state_version": 0, "planned_output_types": ["request"], "planned_output_paths": [str(f.task / "runs" / "lock-swapped-creator" / "request.json")]}
        replacement = f.task / "replacement-lock"
        replacement.write_text("replacement\n", encoding="utf-8")
        original = workflow._publish_task_immutable_bytes_locked

        def swap_lock_before_link(task, clean, payload, *, before_link=None):
            os.replace(replacement, task / ".workflow.lock")
            return original(task, clean, payload, before_link=before_link)

        with mock.patch.object(workflow, "_publish_task_immutable_bytes_locked", side_effect=swap_lock_before_link):
            with self.assertRaises(workflow.WorkflowError) as caught:
                workflow.begin_creator_operation(f.task, intent)
        self.assertEqual(caught.exception.category, "execution-incomplete")
        self.assertFalse((f.task / "operation-intent" / "lock-swapped-creator.json").exists())

    def test_creator_operation_rejects_task_root_swap_before_link_without_intent(self) -> None:
        f = self.fixture()
        intent = {"record_type": "operation-intent", "op_id": "root-swapped-creator", "command_kind": "run-check", "request_digest": "sha256:" + "1" * 64, "contract_digest": f.contract["contract_digest"], "expected_state_version": 0, "planned_output_types": ["request"], "planned_output_paths": [str(f.task / "runs" / "root-swapped-creator" / "request.json")]}
        retired = f.root / "retired-task"
        original = workflow._publish_task_immutable_bytes_locked

        def swap_root_before_link(task, clean, payload, *, before_link=None):
            task.rename(retired)
            task.mkdir()
            return original(task, clean, payload, before_link=before_link)

        with mock.patch.object(workflow, "_publish_task_immutable_bytes_locked", side_effect=swap_root_before_link):
            with self.assertRaises(workflow.WorkflowError) as caught:
                workflow.begin_creator_operation(f.task, intent)
        self.assertEqual(caught.exception.category, "execution-incomplete")
        self.assertFalse((f.task / "operation-intent" / "root-swapped-creator.json").exists())
        self.assertFalse((retired / "operation-intent" / "root-swapped-creator.json").exists())

    def test_bootstrap_record_is_ancestor_local_single_link(self) -> None:
        f = self.fixture()
        digest_value = hashlib.sha256(f.task.name.encode("utf-8")).hexdigest()
        record = f.task.parent / f"sa-bootstrap-record-{digest_value}"
        self.assertTrue(record.is_file())
        self.assertEqual(record.stat().st_nlink, 1)
        self.assertFalse((f.task / record.name).exists())

    def test_bootstrap_recovery_rejects_state_only_task(self) -> None:
        f = self.fixture()
        (f.task / "task-contract.json").unlink()
        with self.assertRaises(workflow.WorkflowError) as state_only:
            workflow.bootstrap_task(f.task.parent, [f.task.name], f.contract, f.state)
        self.assertEqual(state_only.exception.category, "execution-incomplete")

    def test_bootstrap_rejects_replaced_ancestor_lock_or_record(self) -> None:
        lock = self.fixture()
        name = hashlib.sha256(lock.task.name.encode("utf-8")).hexdigest()
        bootstrap_lock = lock.task.parent / f"sa-bootstrap-lock-{name}"
        bootstrap_lock.unlink()
        bootstrap_lock.write_text("replacement\n", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as lock_replaced:
            workflow.bootstrap_task(lock.task.parent, [lock.task.name], lock.contract, lock.state)
        self.assertEqual(lock_replaced.exception.category, "scope-conflict")

        record = self.fixture()
        name = hashlib.sha256(record.task.name.encode("utf-8")).hexdigest()
        bootstrap_record = record.task.parent / f"sa-bootstrap-record-{name}"
        bootstrap_record.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as record_replaced:
            workflow.bootstrap_task(record.task.parent, [record.task.name], record.contract, record.state)
        self.assertEqual(record_replaced.exception.category, "invalid-input")

    def test_bootstrap_fd_capability_and_record_fsync_fail_closed(self) -> None:
        f = self.fixture()
        with mock.patch.object(workflow.os, "supports_dir_fd", set()):
            with self.assertRaises(workflow.WorkflowError) as unavailable:
                workflow.bootstrap_task(f.root, ["capability-task"], f.contract, f.state)
        self.assertEqual(unavailable.exception.category, "runtime-unavailable")

        with mock.patch.object(workflow.os, "fsync", side_effect=OSError("fsync-failure")):
            with self.assertRaises(workflow.WorkflowError) as failed:
                workflow.bootstrap_task(f.root, ["fsync-task"], f.contract, f.state)
        self.assertEqual(failed.exception.category, "execution-incomplete")

    def test_bootstrap_exact_pair_and_contract_only_recovery_are_distinct_valid_neighbors(self) -> None:
        f = self.fixture()
        exact = workflow.bootstrap_task(f.task.parent, [f.task.name], f.contract, f.state)
        self.assertEqual(exact["task"], f.task)
        (f.task / "state.json").unlink()
        contract_only = workflow.bootstrap_task(f.task.parent, [f.task.name], f.contract, f.state)
        self.assertEqual(contract_only["task"], f.task)

    def test_cli_status_and_structured_missing_task_error(self) -> None:
        f = self.fixture()
        command = [
            sys.executable, str(SCRIPTS / "workflow.py"), "status",
            "--task-dir", str(f.task),
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["state"]["version"], 0)

        missing = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "workflow.py"), "validate-task",
                "--task-dir", str(f.root / "missing-task"),
            ],
            text=True, capture_output=True,
        )
        self.assertEqual(missing.returncode, 2)
        error = json.loads(missing.stderr)
        self.assertEqual(error["category"], "missing-evidence")
        self.assertEqual(error["side_effect"], "none")

    def test_immutable_publish_is_identical_idempotent_and_rejects_aliases(self) -> None:
        f = self.fixture()
        target = f.task / "immutable" / "probe.json"
        value = {"probe": 1}
        self.assertEqual(workflow.publish_task_path_json(f.task, target, value), "created")
        self.assertEqual(workflow.publish_task_path_json(f.task, target, value), "identical")
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.publish_task_path_json(f.task, target, {"probe": 2})
        self.assertEqual(caught.exception.category, "scope-conflict")
        target.unlink()
        os.symlink("elsewhere", target)
        with self.assertRaises(workflow.WorkflowError):
            workflow.publish_task_path_json(f.task, target, value)

    def test_fd_task_publication_rejects_descendant_swap_before_link(self) -> None:
        f = self.fixture()
        outside = f.root / "outside"
        outside.mkdir()
        parent = f.task / "safe"
        parent.mkdir()

        def replace_parent() -> None:
            parent.rename(f.task / "old-safe")
            os.symlink(outside, parent)

        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.publish_task_immutable_bytes(
                f.task, ["safe", "probe.json"], b"payload", before_link=replace_parent
            )
        self.assertEqual(caught.exception.category, "execution-incomplete")
        self.assertFalse((outside / "probe.json").exists())
        self.assertFalse((parent / "probe.json").exists())

    def test_reviewer_window_rejects_task_tree_mutation_and_keeps_valid_neighbor(self) -> None:
        f = self.fixture()
        with workflow.reviewer_window(f.task) as accepted:
            self.assertEqual(accepted, {})
        self.assertIn("before_tree_digest", accepted)
        self.assertEqual(accepted["before_tree_digest"], accepted["after_tree_digest"])

        with self.assertRaises(workflow.WorkflowError) as changed:
            with workflow.reviewer_window(f.task):
                (f.task / "reviewer-write").write_text("forbidden\n", encoding="utf-8")
        self.assertEqual(changed.exception.category, "review-invalid")

    def test_reviewer_window_late_task_lock_replacement_cannot_succeed(self) -> None:
        f = self.fixture()
        replacement = f.task / "replacement-lock"
        replacement.write_text("replacement\n", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as replaced:
            with workflow.reviewer_window(f.task):
                os.replace(replacement, f.task / ".workflow.lock")
        self.assertEqual(replaced.exception.category, "execution-incomplete")
        self.assertFalse((f.task / "reviewer-window-receipt.json").exists())

    def test_reviewer_window_late_root_replacement_cannot_succeed(self) -> None:
        f = self.fixture()
        outside = f.root / "outside-root"
        outside.mkdir()
        original = f.root / "old-task"
        with self.assertRaises(workflow.WorkflowError) as replaced:
            with workflow.reviewer_window(f.task):
                f.task.rename(original)
                os.symlink(outside, f.task)
        self.assertEqual(replaced.exception.category, "execution-incomplete")
        self.assertFalse((outside / "reviewer-window-receipt.json").exists())

    def test_receive_binds_runtime_bundle_and_is_idempotent(self) -> None:
        f = self.fixture()
        paths, receipt = f.receive("a", expected=0)
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(workflow.read_task(f.task)["state"]["version"], 1)
        replay = workflow.receive_delivery(
            f.task,
            op_id="receive-a-1",
            expected_state_version=0,
            material_path=paths["material"],
            delivery_path=paths["delivery"],
            delivery_evidence_path=paths["evidence"],
            bundle_path=paths["bundle"],
            runtime_receipt_path=paths["runtime"],
        )
        self.assertEqual(replay, receipt)
        self.assertEqual(workflow.read_task(f.task)["state"]["version"], 1)

        runtime = json.loads(paths["runtime"].read_text(encoding="utf-8"))
        runtime["model"] = "gpt-5.6-terra"
        write_json(paths["runtime"], runtime)
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.receive_delivery(
                f.task,
                op_id="receive-a-2",
                expected_state_version=1,
                material_path=paths["material"], delivery_path=paths["delivery"],
                delivery_evidence_path=paths["evidence"], bundle_path=paths["bundle"],
                runtime_receipt_path=paths["runtime"],
            )
        self.assertEqual(caught.exception.category, "review-invalid")
        self.assertFalse((f.task / "operation-intent" / "receive-a-2.json").exists())

    def test_same_operation_changed_request_and_stale_receive_are_side_effect_free(self) -> None:
        f = self.fixture()
        paths, _ = f.receive("a", expected=0)
        material = json.loads(paths["material"].read_text(encoding="utf-8"))
        material["ready_identity"] = "sha256:" + "0" * 64
        material["material_digest"] = digest({key: value for key, value in material.items() if key != "material_digest"})
        write_json(paths["material"], material)
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.receive_delivery(
                f.task,
                op_id="receive-a-1", expected_state_version=0,
                material_path=paths["material"], delivery_path=paths["delivery"],
                delivery_evidence_path=paths["evidence"], bundle_path=paths["bundle"],
                runtime_receipt_path=paths["runtime"],
            )
        self.assertEqual(caught.exception.category, "scope-conflict")

        fresh = f.delivery_inputs("b")
        with self.assertRaises(workflow.WorkflowError) as stale:
            workflow.receive_delivery(
                f.task,
                op_id="receive-b-stale", expected_state_version=0,
                material_path=fresh["material"], delivery_path=fresh["delivery"],
                delivery_evidence_path=fresh["evidence"], bundle_path=fresh["bundle"],
                runtime_receipt_path=fresh["runtime"],
            )
        self.assertEqual(stale.exception.category, "stale-baseline")
        self.assertFalse((f.task / "operation-intent" / "receive-b-stale.json").exists())

        duplicate = f.delivery_inputs("a", attempt=1, content="different-attempt-bytes\n")
        with self.assertRaises(workflow.WorkflowError) as duplicate_id:
            workflow.receive_delivery(
                f.task,
                op_id="receive-a-conflicting-attempt", expected_state_version=1,
                material_path=duplicate["material"], delivery_path=duplicate["delivery"],
                delivery_evidence_path=duplicate["evidence"], bundle_path=duplicate["bundle"],
                runtime_receipt_path=duplicate["runtime"],
            )
        self.assertEqual(duplicate_id.exception.category, "scope-conflict")
        self.assertEqual(workflow.read_task(f.task)["state"]["version"], 1)

    def test_receive_rejects_wrong_baseline_and_post_ready_bundle_change(self) -> None:
        f = self.fixture()
        paths = f.delivery_inputs("a", baseline_id="other-baseline")
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.receive_delivery(
                f.task, op_id="receive-wrong", expected_state_version=0,
                material_path=paths["material"], delivery_path=paths["delivery"],
                delivery_evidence_path=paths["evidence"], bundle_path=paths["bundle"],
                runtime_receipt_path=paths["runtime"],
            )
        self.assertEqual(caught.exception.category, "stale-baseline")

        _, _ = f.receive("a", expected=0)
        stored = f.task / "deliveries" / "D-a-1" / "bundle.json"
        stored.write_bytes(stored.read_bytes() + b"\n")
        _, _ = f.receive("b", expected=1)
        with self.assertRaises(workflow.WorkflowError) as drifted:
            workflow.assemble_candidate(
                f.task, op_id="assemble-drift", expected_state_version=2,
                baseline_repo=f.baseline, selected={"a": "D-a-1", "b": "D-b-1"},
            )
        self.assertEqual(drifted.exception.category, "candidate-changed")

    def test_assemble_combines_two_independent_deliveries_with_attribution(self) -> None:
        f = self.fixture()
        f.receive("a", expected=0)
        f.receive("b", expected=1)
        receipt = workflow.assemble_candidate(
            f.task, op_id="assemble-1", expected_state_version=2,
            baseline_repo=f.baseline, selected={"a": "D-a-1", "b": "D-b-1"},
        )
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(len(receipt["actual_output_ids"]), 4)
        state = workflow.read_task(f.task)["state"]
        self.assertEqual(state["version"], 3)
        self.assertEqual(state["selected_attempts"], {"a": "D-a-1", "b": "D-b-1"})
        assembly_dir = f.task / "assemblies" / "assemble-1"
        self.assertEqual((assembly_dir / "workspace" / "a.txt").read_text(encoding="utf-8"), "a1\n")
        self.assertEqual((assembly_dir / "workspace" / "b.txt").read_text(encoding="utf-8"), "b1\n")
        bridge = json.loads((assembly_dir / "CB.json").read_text(encoding="utf-8"))
        self.assertEqual(set(bridge["delivery_ids"]), {"D-a-1", "D-b-1"})
        manifest = json.loads((assembly_dir / "candidate-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(bridge["candidate_id"], manifest["candidate_id"])

    def test_assemble_rejects_overlapping_ownership_and_dirty_baseline(self) -> None:
        f = self.fixture(overlapping=True)
        f.receive("a", expected=0, content="a1\n")
        f.receive("b", expected=1, content="a2\n")
        with self.assertRaises(workflow.WorkflowError) as overlap:
            workflow.assemble_candidate(
                f.task, op_id="assemble-overlap", expected_state_version=2,
                baseline_repo=f.baseline, selected={"a": "D-a-1", "b": "D-b-1"},
            )
        self.assertEqual(overlap.exception.category, "scope-conflict")

        clean = self.fixture()
        clean.receive("a", expected=0)
        clean.receive("b", expected=1)
        (clean.baseline / "a.txt").write_text("user change\n", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as changed:
            workflow.assemble_candidate(
                clean.task, op_id="assemble-dirty", expected_state_version=2,
                baseline_repo=clean.baseline,
                selected={"a": "D-a-1", "b": "D-b-1"},
            )
        self.assertEqual(changed.exception.category, "candidate-changed")

    def test_assemble_recovers_artifacts_before_state_and_state_before_receipt(self) -> None:
        f = self.fixture()
        f.receive("a", expected=0)
        f.receive("b", expected=1)
        real_cas = workflow.update_state_cas
        with mock.patch.object(workflow, "update_state_cas", side_effect=RuntimeError("crash-before-state")):
            with self.assertRaises(RuntimeError):
                workflow.assemble_candidate(
                    f.task, op_id="assemble-recover-a", expected_state_version=2,
                    baseline_repo=f.baseline,
                    selected={"a": "D-a-1", "b": "D-b-1"},
                )
        self.assertEqual(workflow.read_task(f.task)["state"]["version"], 2)
        # Recovery validates the durable isolated output, not a now-changed source baseline.
        (f.baseline / "a.txt").write_text("later user edit\n", encoding="utf-8")
        recovered = workflow.assemble_candidate(
            f.task, op_id="assemble-recover-a", expected_state_version=2,
            baseline_repo=f.baseline, selected={"a": "D-a-1", "b": "D-b-1"},
        )
        self.assertEqual(recovered["outcome"], "success")
        self.assertEqual(workflow.read_task(f.task)["state"]["version"], 3)

        g = self.fixture()
        g.receive("a", expected=0)
        g.receive("b", expected=1)
        with mock.patch.object(workflow, "publish_operation_receipt", side_effect=RuntimeError("crash-before-receipt")):
            with self.assertRaises(RuntimeError):
                workflow.assemble_candidate(
                    g.task, op_id="assemble-recover-b", expected_state_version=2,
                    baseline_repo=g.baseline,
                    selected={"a": "D-a-1", "b": "D-b-1"},
                )
        self.assertEqual(workflow.read_task(g.task)["state"]["version"], 3)
        receipt = workflow.assemble_candidate(
            g.task, op_id="assemble-recover-b", expected_state_version=2,
            baseline_repo=g.baseline, selected={"a": "D-a-1", "b": "D-b-1"},
        )
        self.assertEqual(receipt["state_version_after"], 3)

    def test_assemble_recovery_rejects_output_drift_and_records_concurrent_state(self) -> None:
        f = self.fixture()
        f.receive("a", expected=0)
        f.receive("b", expected=1)
        with mock.patch.object(workflow, "update_state_cas", side_effect=RuntimeError("crash-before-state")):
            with self.assertRaises(RuntimeError):
                workflow.assemble_candidate(
                    f.task, op_id="assemble-drifted-output", expected_state_version=2,
                    baseline_repo=f.baseline,
                    selected={"a": "D-a-1", "b": "D-b-1"},
                )
        output_path = f.task / "assemblies" / "assemble-drifted-output" / "output-identity.json"
        output = json.loads(output_path.read_text(encoding="utf-8"))
        output["output_identity_id"] = "output-substituted"
        write_json(output_path, output)
        with self.assertRaises(workflow.WorkflowError) as drifted:
            workflow.assemble_candidate(
                f.task, op_id="assemble-drifted-output", expected_state_version=2,
                baseline_repo=f.baseline,
                selected={"a": "D-a-1", "b": "D-b-1"},
            )
        self.assertEqual(drifted.exception.category, "candidate-changed")

        g = self.fixture()
        g.receive("a", expected=0)
        g.receive("b", expected=1)
        concurrent = workflow.WorkflowError(
            "stale-baseline", "concurrent state", affected="state.json"
        )
        with mock.patch.object(workflow, "update_state_cas", side_effect=concurrent):
            receipt = workflow.assemble_candidate(
                g.task, op_id="assemble-concurrent", expected_state_version=2,
                baseline_repo=g.baseline,
                selected={"a": "D-a-1", "b": "D-b-1"},
            )
        self.assertEqual(receipt["outcome"], "ambiguous")
        self.assertEqual(receipt["side_effect"], "unknown")
        self.assertEqual(workflow.read_task(g.task)["state"]["version"], 2)

    def test_assemble_same_operation_changed_selection_conflicts(self) -> None:
        f = self.fixture()
        f.receive("a", expected=0)
        f.receive("b", expected=1)
        workflow.assemble_candidate(
            f.task, op_id="assemble-1", expected_state_version=2,
            baseline_repo=f.baseline, selected={"a": "D-a-1", "b": "D-b-1"},
        )
        b2 = f.delivery_inputs("b", attempt=2, content="b2\n")
        # New delivery cannot use the stale pre-assembly state.
        with self.assertRaises(workflow.WorkflowError):
            workflow.receive_delivery(
                f.task, op_id="receive-b-2", expected_state_version=2,
                material_path=b2["material"], delivery_path=b2["delivery"],
                delivery_evidence_path=b2["evidence"], bundle_path=b2["bundle"],
                runtime_receipt_path=b2["runtime"],
            )
        with self.assertRaises(workflow.WorkflowError) as conflict:
            workflow.assemble_candidate(
                f.task, op_id="assemble-1", expected_state_version=2,
                baseline_repo=f.baseline, selected={"a": "D-a-1", "b": "D-b-2"},
            )
        self.assertEqual(conflict.exception.category, "scope-conflict")

        b2_paths = f.delivery_inputs("b", attempt=2, content="b2\n")
        workflow.receive_delivery(
            f.task, op_id="receive-b-2-current", expected_state_version=3,
            material_path=b2_paths["material"], delivery_path=b2_paths["delivery"],
            delivery_evidence_path=b2_paths["evidence"], bundle_path=b2_paths["bundle"],
            runtime_receipt_path=b2_paths["runtime"],
        )
        corrected = workflow.assemble_candidate(
            f.task, op_id="assemble-2", expected_state_version=4,
            baseline_repo=f.baseline,
            selected={"a": "D-a-1", "b": "D-b-2"},
        )
        self.assertEqual(corrected["outcome"], "success")
        second = f.task / "assemblies" / "assemble-2" / "workspace"
        self.assertEqual((second / "a.txt").read_text(encoding="utf-8"), "a1\n")
        self.assertEqual((second / "b.txt").read_text(encoding="utf-8"), "b2\n")

    def test_final_accept_rejects_synthetic_evidence_before_intent(self) -> None:
        from test_full_protocol import (
            ProtocolFixture as AcceptanceFixture,
            candidate_evidence,
            complete_review_context,
        )

        fixture = AcceptanceFixture()
        self.addCleanup(fixture._temporary_repo.cleanup)
        verdict = {
            "record_type": "V", "verdict_id": "V-final", "contract_digest": fixture.contract["contract_digest"],
            "status": "valid", "verdict": "ship", "packet_id": "P-1",
            "candidate_bridge_id": fixture.bridge["bridge_id"], "challenge_receipt_id": "CR-1",
            "rejection_closure": [], "coverage_complete": True,
            "rejection_dispositions": {}, "open_rejections": [],
            "reviewed_at": "2026-01-01T00:00:00Z", "review_sequence": 10,
        }
        relationship = complete_review_context(fixture, verdict, [])
        verify = fixture.candidate_verify_receipt
        verify_id = digest(verify)
        final_evidence = candidate_evidence(fixture)
        final_evidence.update({
            "evidence_id": "E-final-p1", "phase": "final-candidate-verify",
            "observed_at": "2026-01-01T00:00:01Z", "sequence": 11,
            "candidate_verify_receipt_id": verify_id,
            "candidate_verify_receipt_digest": verify_id,
        })
        final_evidence["evidence_digest"] = digest({
            key: value for key, value in final_evidence.items() if key != "evidence_digest"
        })
        scope = {
            "route": "full", "action": "final-accept", "stage_key": "p1",
            "candidate_bridge_id": fixture.bridge["bridge_id"],
        }
        observed_root = {
            "context_id": "root-context", "thread_id": "root-thread", "role": "root",
            "model": "gpt-6-astra", "effort": "high",
            "observed_attestation": {"scope": scope, "observed_at": "2026-01-01T00:00:01Z"},
        }
        authority = {
            "root_authority_id": "root-p1", "contract_digest": fixture.contract["contract_digest"],
            "scope": scope, "observed_at": "2026-01-01T00:00:01Z",
            "expires_at": "2026-01-01T01:00:00Z",
            "candidate_verify_receipt_id": verify_id, "candidate_verify_receipt_digest": verify_id,
            "issuer": {"role": "root", "model": "gpt-6-astra"},
            "observed_attestation": observed_root,
            "observed_attestation_digest": digest(observed_root),
        }
        acceptance = {
            "record_type": "A", "acceptance_id": "A-p1", "status": "accepted",
            "contract_digest": fixture.contract["contract_digest"], "accepted_stage_key": "p1",
            "candidate_bridge_id": fixture.bridge["bridge_id"], "packet_id": relationship.packet["packet_id"],
            "verdict_id": verdict["verdict_id"], "final_candidate_evidence_id": final_evidence["evidence_id"],
            "root_authority_id": authority["root_authority_id"], "root_authority_scope": scope,
            "root_authority_expiry": authority["expires_at"],
            "candidate_verify_receipt_id": verify_id, "dependency_acceptance_ids": {},
        }
        state = {
            "version": 0,
            "contract_digest": fixture.contract["contract_digest"],
            "stage_status": {"status": "reviewing", "review_status": "reviewed-awaiting-final-accept"},
            "work_status": {"p1": "ready"}, "selected_attempts": {"p1": "D-1"},
            "current_ids": {
                "assembly_index": fixture.assembly["assembly_id"],
                "candidate_binding": fixture.bridge["bridge_id"],
                "review_packet": relationship.packet["packet_id"],
                "verdict": verdict["verdict_id"], "acceptance": None,
            },
            "applicable_rejection_roots": [], "last_operation_receipt": None,
        }
        task = Path(fixture._temporary_repo.name) / "acceptance-task"
        workflow.initialize_task(task, fixture.contract, state)
        with self.assertRaises(workflow.WorkflowError) as synthetic:
            workflow.final_accept(
                task, op_id="accept-p1", expected_state_version=0,
                acceptance=acceptance, relationship=relationship,
                final_candidate_evidence=final_evidence, root_authority=authority,
                candidate_verify_receipt=verify, dependency_acceptance_contexts={},
                trusted_observation_time="2026-01-01T00:00:02Z",
            )
        self.assertEqual(synthetic.exception.category, "missing-evidence")
        self.assertFalse((task / "operation-intent" / "accept-p1.json").exists())


if __name__ == "__main__":
    unittest.main()
