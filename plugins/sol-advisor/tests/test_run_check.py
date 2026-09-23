from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
from fixture_support import fixture_directory
import threading
import time
from pathlib import Path
from unittest import mock
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TEST_ARTIFACTS = Path(__file__).resolve().parents[3] / ".agent-artifacts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import candidate
import full_protocol
import workflow


def load_run_check():
    path = SCRIPTS / "run-check.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("sol_advisor_run_check", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


run_check = load_run_check()


class RunCheckFixture:
    def __init__(
        self, script_body: str, *, scope: str = "delivery", timeout: float = 2.0,
        environment_policy: list[dict[str, object]] | None = None,
        acceptance_material_paths: list[str] | None = None,
        allowed_argv_suffixes: list[list[str]] | None = None,
    ) -> None:
        self.temp = fixture_directory(TEST_ARTIFACTS)
        self.root = Path(self.temp.name)
        self.script = self.root / "check.py"
        self.script.write_text(script_body, encoding="utf-8")
        material_paths = None if acceptance_material_paths is None else [
            str(self.script) if value == "$SCRIPT" else value for value in acceptance_material_paths
        ]
        self.contract = {
            "protocol": "SA-FULL-V2-P1",
            "goal": "execute one bounded offline check",
            "authority": {"allowed_paths": [str(self.root)]},
            "preserved_behavior": ["solo", "delegate", "audit"],
            "excluded_behavior": ["network", "credentials"],
            "stages": {"p3": {"depends_on": []}},
            "work_items": {"p3": {"paths": ["plugins/sol-advisor/scripts/run-check.py"]}},
            "checks": {
                "candidate-check": {
                    "scope": scope,
                    "argv": [sys.executable, str(self.script)],
                    "cwd": str(self.root),
                    "timeout_seconds": timeout,
                    "required": True,
                    **({"acceptance_material_paths": material_paths} if material_paths is not None else {}),
                    **({"allowed_argv_suffixes": allowed_argv_suffixes} if allowed_argv_suffixes is not None else {}),
                }
            },
            "environment_policy": environment_policy or [],
            "required_coverage": [scope],
            "review_policy": {"allowed_verdicts": ["ship", "fix-first", "rethink"]},
        }
        self.contract["contract_digest"] = full_protocol.canonical_digest(self.contract)
        self.state = {
            "version": 0,
            "contract_digest": self.contract["contract_digest"],
            "stage_status": {"review_status": "reviewing"},
            "work_status": {"p3": "ready"},
            "selected_attempts": {},
            "current_ids": {"assembly_index": None, "candidate_binding": None, "review_packet": None, "verdict": None, "acceptance": None},
            "applicable_rejection_roots": [],
            "last_operation_receipt": None,
        }
        self.task = self.root / "task"
        workflow.initialize_task(self.task, self.contract, self.state)

    def cleanup(self) -> None:
        self.temp.cleanup()


class RunCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(run_check, "run-check.py is missing")

    def fixture(self, body: str, **kwargs: object) -> RunCheckFixture:
        fixture = RunCheckFixture(body, **kwargs)
        self.addCleanup(fixture.cleanup)
        return fixture

    def challenge_request(self, fixture: RunCheckFixture, *, request_id: str = "Q-1") -> dict[str, object]:
        request = {
            "record_type": "challenge-request", "request_id": request_id, "request_digest": "",
            "contract_digest": fixture.contract["contract_digest"], "packet_id": "P-1",
            "candidate_bridge_id": "CB-1", "check_key": "candidate-check",
            "authority_decision": "allowed-by-task-contract", "argv_suffix": [],
        }
        request["request_digest"] = full_protocol.canonical_digest({
            key: value for key, value in request.items() if key != "request_digest"
        })
        return request

    def persist_completed_prepare(self, fixture: RunCheckFixture, request: dict[str, object]) -> None:
        request_id = str(request["request_id"])
        request_path = fixture.task / "challenges" / request_id / "request.json"
        intent = {
            "record_type": "operation-intent", "op_id": f"prepare-challenge-{request_id}",
            "command_kind": "prepare-challenge",
            "request_digest": full_protocol.canonical_digest({
                "action": "prepare-challenge", "request": request,
            }),
            "contract_digest": fixture.contract["contract_digest"], "expected_state_version": 0,
            "planned_output_types": ["challenge-request"],
            "planned_output_paths": [str(request_path)],
        }
        self.assertTrue(workflow.begin_creator_operation(fixture.task, intent))
        workflow.publish_task_path_json(fixture.task, request_path, request)
        workflow.publish_operation_receipt(
            fixture.task,
            workflow._operation_receipt(
                intent, outcome="success", side_effect="durable", actual_output_ids=[request_id],
                state_before=0, state_after=0,
            ),
        )

    def test_pass_and_nonzero_are_real_evidence_not_summary_text(self) -> None:
        passed = self.fixture("print('PASS text from real process')\n")
        result = run_check.execute_check(
            passed.task, run_id="pass-1", check_key="candidate-check",
            subject_id="CB-1",
        )
        self.assertEqual(result["evidence"]["result"], "pass")
        self.assertEqual(result["run_record"]["exit_code"], 0)
        self.assertIn(b"PASS text", (passed.task / "runs" / "pass-1" / "stdout.log").read_bytes())

        failed = self.fixture("print('PASS summary but exit is nonzero')\nraise SystemExit(7)\n")
        result = run_check.execute_check(
            failed.task, run_id="fail-1", check_key="candidate-check",
            subject_id="CB-1",
        )
        self.assertEqual(result["evidence"]["result"], "fail")
        self.assertEqual(result["run_record"]["exit_code"], 7)

        bounded = self.fixture("print('x' * 200)\n")
        result = run_check.execute_check(
            bounded.task, run_id="bounded-1", check_key="candidate-check",
            subject_id="M-1", log_limit=32,
        )
        self.assertEqual(result["evidence"]["result"], "incomplete")
        self.assertTrue(result["run_record"]["stdout_truncated"])
        self.assertEqual(len((bounded.task / "runs" / "bounded-1" / "stdout.log").read_bytes()), 32)

    def test_declared_material_byte_drift_with_same_size_and_mtime_conflicts_reuse(self) -> None:
        body = "print('first')\n"
        fixture = self.fixture(body, acceptance_material_paths=["$SCRIPT"])
        run_check.execute_check(
            fixture.task, run_id="material-1", check_key="candidate-check", subject_id="M-1"
        )
        before = fixture.script.stat()
        fixture.script.write_text("print('other')\n", encoding="utf-8")
        os.utime(fixture.script, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(workflow.WorkflowError) as raised:
            run_check.execute_check(
                fixture.task, run_id="material-1", check_key="candidate-check", subject_id="M-1"
            )
        self.assertEqual(raised.exception.category, "scope-conflict")

    def test_interpreter_argv1_script_byte_drift_conflicts_reuse_without_declaration(self) -> None:
        fixture = self.fixture("print('first')\n")
        run_check.execute_check(
            fixture.task, run_id="argv1-script-1", check_key="candidate-check", subject_id="M-1"
        )
        before = fixture.script.stat()
        fixture.script.write_text("print('other')\n", encoding="utf-8")
        os.utime(fixture.script, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(workflow.WorkflowError) as raised:
            run_check.execute_check(
                fixture.task, run_id="argv1-script-1", check_key="candidate-check", subject_id="M-1"
            )
        self.assertEqual(raised.exception.category, "scope-conflict")

    def test_same_host_and_child_executable_share_one_inventory_with_both_roles(self) -> None:
        fixture = self.fixture("print('ok')\n")
        check = fixture.contract["checks"]["candidate-check"]
        materials = run_check._effective_materials(check, [sys.executable, str(fixture.script)], fixture.root)
        shared = [item for item in materials if set(item["roles"]) == {"host-python", "child-executable"}]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]["requested_path"], os.path.abspath(sys.executable))

    def test_argv_is_literal_and_child_environment_is_exact_allowlist(self) -> None:
        policy = [{
            "name": "SAFE_VALUE", "present": True, "classification": "non-sensitive",
            "value_bytes_base64": "b2s=",
        }]
        literal = "; touch /tmp/never-executed"
        fixture = self.fixture(
            "import json, os, sys\nprint(json.dumps({'args': sys.argv[1:], 'safe': os.environ.get('SAFE_VALUE'), 'secret': os.environ.get('SECRET_VALUE')}))\n",
            environment_policy=policy,
            allowed_argv_suffixes=[[literal, "space and\nnewline"]],
        )
        result = run_check.execute_check(
            fixture.task, run_id="argv-1", check_key="candidate-check",
            subject_id="CB-1", argv_suffix=[literal, "space and\nnewline"],
        )
        self.assertEqual(result["evidence"]["result"], "pass")
        output = json.loads((fixture.task / "runs" / "argv-1" / "stdout.log").read_text(encoding="utf-8"))
        self.assertEqual(output["args"], [literal, "space and\nnewline"])
        self.assertEqual(output["safe"], "ok")
        self.assertIsNone(output["secret"])

    def test_unlisted_shell_suffix_is_rejected_before_intent(self) -> None:
        fixture = self.fixture("print('never')\n")
        with self.assertRaises(workflow.WorkflowError) as rejected:
            run_check.execute_check(fixture.task, run_id="shell", check_key="candidate-check", subject_id="M-1", argv_suffix=["-c", "touch nope"])
        self.assertEqual(rejected.exception.category, "invalid-input")
        self.assertFalse((fixture.task / "operation-intent" / "shell.json").exists())

    def test_timeout_is_incomplete_and_process_group_cleanup_is_recorded(self) -> None:
        fixture = self.fixture(
            "import subprocess, time\nsubprocess.Popen(['/bin/sleep', '30'])\nprint('started', flush=True)\ntime.sleep(30)\n",
            timeout=0.15,
        )
        result = run_check.execute_check(
            fixture.task, run_id="timeout-1", check_key="candidate-check",
            subject_id="CB-1",
        )
        self.assertEqual(result["evidence"]["result"], "incomplete")
        self.assertTrue(result["run_record"]["timed_out"])
        self.assertEqual(result["run_record"]["cleanup"], "terminated")
        self.assertNotEqual(result["run_record"]["exit_code"], 0)

    def test_timeout_kills_a_child_that_ignores_term(self) -> None:
        fixture = self.fixture(
            "import subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(30)\n",
            timeout=0.15,
        )
        result = run_check.execute_check(
            fixture.task, run_id="stubborn-1", check_key="candidate-check",
            subject_id="M-1",
        )
        child_pid = int((fixture.task / "runs" / "stubborn-1" / "stdout.log").read_text(encoding="utf-8").splitlines()[0])
        alive = True
        try:
            for _ in range(20):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    alive = False
                    break
                time.sleep(0.05)
        finally:
            if alive:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.assertFalse(alive, "timed-out child process remained alive")
        self.assertEqual(result["run_record"]["cleanup"], "terminated")

    def test_same_run_is_idempotent_and_changed_request_conflicts(self) -> None:
        fixture = self.fixture("print('once')\n")
        first = run_check.execute_check(
            fixture.task, run_id="same-1", check_key="candidate-check", subject_id="CB-1"
        )
        replay = run_check.execute_check(
            fixture.task, run_id="same-1", check_key="candidate-check", subject_id="CB-1"
        )
        self.assertEqual(replay, first)
        with self.assertRaises(workflow.WorkflowError) as changed:
            run_check.execute_check(
                fixture.task, run_id="same-1", check_key="candidate-check", subject_id="CB-other"
            )
        self.assertEqual(changed.exception.category, "scope-conflict")

    def test_canonical_request_and_intent_are_durable_before_child_start(self) -> None:
        fixture = self.fixture("print('started')\n")
        original_popen = subprocess.Popen
        observed: list[dict[str, object]] = []

        def observe_start(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
            if not args or args[0] != [sys.executable, str(fixture.script)]:
                return original_popen(*args, **kwargs)
            request_path = fixture.task / "runs" / "prestart-1" / "request.json"
            intent_path = fixture.task / "operation-intent" / "prestart-1.json"
            self.assertTrue(request_path.is_file(), "canonical request must precede child spawn")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
            self.assertEqual(intent["request_digest"], full_protocol.canonical_digest(request))
            self.assertEqual(
                intent["planned_output_types"],
                ["request", "E", "run-record", "stdout", "stderr"],
            )
            observed.append(request)
            return original_popen(*args, **kwargs)

        with mock.patch.object(run_check.subprocess, "Popen", side_effect=observe_start):
            result = run_check.execute_check(
                fixture.task, run_id="prestart-1", check_key="candidate-check", subject_id="M-1"
            )
        self.assertEqual(len(observed), 1)
        self.assertEqual(result["evidence"]["result"], "pass")

    def test_never_started_is_incomplete_and_challenge_e_binds_request(self) -> None:
        never = self.fixture("print('unused')\n")
        invalid_executable = never.root / "invalid-executable"
        invalid_executable.write_text("not an executable format\n", encoding="utf-8")
        invalid_executable.chmod(0o755)
        never.contract["checks"]["candidate-check"]["argv"] = [str(invalid_executable)]
        never.contract["contract_digest"] = full_protocol.canonical_digest({
            key: value for key, value in never.contract.items() if key != "contract_digest"
        })
        never.state["contract_digest"] = never.contract["contract_digest"]
        never_task = never.root / "never-task"
        workflow.initialize_task(never_task, never.contract, never.state)
        result = run_check.execute_check(
            never_task, run_id="never-1", check_key="candidate-check", subject_id="M-1"
        )
        self.assertEqual(result["evidence"]["result"], "incomplete")
        self.assertFalse(result["run_record"]["started"])
        self.assertEqual(result["run_record"]["cleanup"], "not-started")

        challenge = self.fixture("print('challenge')\n", scope="challenge")
        request = self.challenge_request(challenge)
        self.persist_completed_prepare(challenge, request)
        result = run_check.execute_check(
            challenge.task, run_id="challenge-1", check_key="candidate-check",
            subject_id="P-1:CB-1", challenge_request=request,
        )
        evidence = result["evidence"]
        self.assertEqual(evidence["result"], "pass")
        self.assertEqual(evidence["challenge_request_id"], "Q-1")
        self.assertEqual(evidence["challenge_request_digest"], request["request_digest"])

    def test_challenge_refuses_missing_or_drifted_completed_prepare_before_spawn(self) -> None:
        fixture = self.fixture("raise AssertionError('challenge child must not start')\n", scope="challenge")
        request = self.challenge_request(fixture)
        with self.assertRaises(workflow.WorkflowError) as missing:
            run_check.execute_check(
                fixture.task, run_id="challenge-Q-1", check_key="candidate-check",
                subject_id="P-1:CB-1", challenge_request=request,
            )
        self.assertEqual(missing.exception.category, "missing-evidence")
        self.assertFalse((fixture.task / "operation-intent" / "challenge-Q-1.json").exists())

        self.persist_completed_prepare(fixture, request)
        request_path = fixture.task / "challenges" / "Q-1" / "request.json"
        request_path.write_text(json.dumps(dict(request, packet_id="P-other")), encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as drifted:
            run_check.execute_check(
                fixture.task, run_id="challenge-Q-1", check_key="candidate-check",
                subject_id="P-1:CB-1", challenge_request=request,
            )
        self.assertEqual(drifted.exception.category, "candidate-changed")
        self.assertFalse((fixture.task / "operation-intent" / "challenge-Q-1.json").exists())

    def test_same_run_id_has_one_creator_and_one_child_spawn(self) -> None:
        fixture = self.fixture("print('once')\n")
        original_popen = subprocess.Popen
        starts: list[object] = []
        starts_lock = threading.Lock()

        def counted_popen(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
            with starts_lock:
                starts.append(args)
            return original_popen(*args, **kwargs)

        errors: list[BaseException] = []
        def run() -> None:
            try:
                run_check.execute_check(fixture.task, run_id="parallel-1", check_key="candidate-check", subject_id="M-1")
            except BaseException as error:  # The non-creator may observe a partial transaction.
                errors.append(error)

        # A status snapshot is not creator admission: before the repair, two callers
        # receiving the same stale "new" answer both launch a child.  The implementation
        # must instead use workflow.begin_creator_operation as its admission point.
        with mock.patch.object(run_check.subprocess, "Popen", side_effect=counted_popen), mock.patch.object(
            workflow, "_operation_status", return_value=("new", None),
        ):
            left = threading.Thread(target=run)
            right = threading.Thread(target=run)
            left.start(); right.start()
            left.join(timeout=5); right.join(timeout=5)
        self.assertFalse(left.is_alive() or right.is_alive(), "same-run callers did not complete")
        self.assertEqual(len(starts), 1)
        self.assertLessEqual(len(errors), 1)

    def test_parent_exit_with_residual_group_is_incomplete_and_reaped(self) -> None:
        fixture = self.fixture(
            "import subprocess, sys\n"
            "child = subprocess.Popen(['/bin/sleep', '30'])\n"
            "print(child.pid, flush=True)\n"
        )
        result = run_check.execute_check(
            fixture.task, run_id="residual-zero", check_key="candidate-check", subject_id="M-1"
        )
        child_pid = int((fixture.task / "runs" / "residual-zero" / "stdout.log").read_text().strip())
        self.assertEqual(result["evidence"]["result"], "incomplete")
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)
        # macOS can report EPERM for a just-killed process group even after this
        # only descendant is gone. Unknown must stay incomplete, never pass.
        self.assertIn(result["run_record"]["cleanup"], {"terminated", "unknown"})

    def test_shared_consumer_guard_rejects_incomplete_or_rewritten_run_provenance(self) -> None:
        mutations = {
            "missing-request": lambda task, run_id, evidence: (task / "runs" / run_id / "request.json").unlink(),
            "empty-log-list": lambda task, run_id, evidence: self._rewrite_evidence_logs(task, run_id, evidence, []),
            "nonterminal-record": lambda task, run_id, evidence: self._rewrite_run_record(task, run_id, {"terminal_observed": False}),
            "partial-receipt": lambda task, run_id, evidence: self._rewrite_run_receipt(task, run_id, ["request", f"E-{run_id}", "run-record"]),
            "noncanonical-intent": lambda task, run_id, evidence: self._reformat_json(task / "operation-intent" / f"{run_id}.json"),
            "noncanonical-receipt": lambda task, run_id, evidence: self._reformat_json(task / "operation-receipt" / f"{run_id}.json"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                fixture = self.fixture("print('verified')\n")
                run_id = f"guard-{label}"
                result = run_check.execute_check(
                    fixture.task, run_id=run_id, check_key="candidate-check", subject_id="M-1"
                )
                evidence = result["evidence"]
                workflow.require_persisted_run_evidence(fixture.task, evidence, affected="consumer")
                mutate(fixture.task, run_id, evidence)
                with self.assertRaises(workflow.WorkflowError):
                    workflow.require_persisted_run_evidence(fixture.task, evidence, affected="consumer")

    def test_replay_rejects_a_passing_record_without_terminal_observation(self) -> None:
        fixture = self.fixture("print('verified')\n")
        run_check.execute_check(fixture.task, run_id="replay-nonterminal", check_key="candidate-check", subject_id="M-1")
        self._rewrite_run_record(fixture.task, "replay-nonterminal", {"terminal_observed": False})
        with self.assertRaises(workflow.WorkflowError) as rejected:
            run_check.execute_check(fixture.task, run_id="replay-nonterminal", check_key="candidate-check", subject_id="M-1")
        self.assertEqual(rejected.exception.category, "candidate-changed")

    def test_replay_rejects_a_failing_label_without_a_child_exit(self) -> None:
        fixture = self.fixture("print('verified')\n")
        run_id = "replay-no-exit"
        first = run_check.execute_check(fixture.task, run_id=run_id, check_key="candidate-check", subject_id="M-1")
        altered = dict(first["evidence"], result="fail")
        altered["evidence_digest"] = full_protocol.canonical_digest({
            key: value for key, value in altered.items() if key != "evidence_digest"
        })
        (fixture.task / "evidence" / f"E-{run_id}.json").write_bytes(full_protocol.canonical_json_bytes(altered))
        self._rewrite_run_record(fixture.task, run_id, {
            "result": "fail", "exit_code": None, "terminal_observed": False,
        })
        with self.assertRaises(workflow.WorkflowError) as rejected:
            run_check.execute_check(fixture.task, run_id=run_id, check_key="candidate-check", subject_id="M-1")
        self.assertEqual(rejected.exception.category, "candidate-changed")

    @staticmethod
    def _rewrite_evidence_logs(task: Path, run_id: str, evidence: dict[str, object], logs: list[object]) -> None:
        changed = dict(evidence, logs=logs)
        changed["evidence_digest"] = full_protocol.canonical_digest({
            key: value for key, value in changed.items() if key != "evidence_digest"
        })
        (task / "evidence" / f"E-{run_id}.json").write_bytes(full_protocol.canonical_json_bytes(changed))
        evidence.clear(); evidence.update(changed)

    @staticmethod
    def _rewrite_run_record(task: Path, run_id: str, update: dict[str, object]) -> None:
        path = task / "runs" / run_id / "run-record.json"
        record = json.loads(path.read_text())
        record.update(update)
        path.write_bytes(full_protocol.canonical_json_bytes(record))

    @staticmethod
    def _rewrite_run_receipt(task: Path, run_id: str, output_ids: list[str]) -> None:
        path = task / "operation-receipt" / f"{run_id}.json"
        receipt = json.loads(path.read_text())
        receipt["actual_output_ids"] = output_ids
        path.write_bytes(full_protocol.canonical_json_bytes(receipt))

    @staticmethod
    def _reformat_json(path: Path) -> None:
        path.write_text(json.dumps(json.loads(path.read_text()), indent=2) + "\n")

    def test_nonzero_parent_with_residual_group_is_cleaned_and_incomplete(self) -> None:
        fixture = self.fixture(
            "import subprocess, sys\n"
            "child = subprocess.Popen(['/bin/sleep', '30'])\n"
            "print(child.pid, flush=True)\n"
            "raise SystemExit(7)\n"
        )
        result = run_check.execute_check(
            fixture.task, run_id="residual-nonzero", check_key="candidate-check", subject_id="M-1"
        )
        child_pid = int((fixture.task / "runs" / "residual-nonzero" / "stdout.log").read_text().strip())
        self.assertEqual(result["evidence"]["result"], "incomplete")
        self.assertEqual(result["run_record"]["cleanup"], "terminated")
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    def test_sensitive_environment_and_log_publication_failure_never_pass(self) -> None:
        sensitive = [{"name": "TOKEN", "present": True, "classification": "sensitive"}]
        fixture = self.fixture("print('must not run')\n", environment_policy=sensitive)
        with self.assertRaises(workflow.WorkflowError) as unavailable:
            run_check.execute_check(
                fixture.task, run_id="secret-1", check_key="candidate-check", subject_id="CB-1"
            )
        self.assertEqual(unavailable.exception.category, "runtime-unavailable")
        self.assertFalse((fixture.task / "operation-intent" / "secret-1.json").exists())

        logs = self.fixture("print('real output')\n")
        original = workflow.publish_task_path_bytes

        def fail_stdout(task, path, payload):
            if str(path).endswith("stdout.log"):
                raise workflow.WorkflowError(
                    "execution-incomplete", "simulated log failure", affected=str(path),
                    side_effect="unknown", recovery="preserve-and-root-reconcile",
                )
            return original(task, path, payload)

        with mock.patch.object(workflow, "publish_task_path_bytes", side_effect=fail_stdout):
            with self.assertRaises(workflow.WorkflowError) as failure:
                run_check.execute_check(
                    logs.task, run_id="log-fail", check_key="candidate-check", subject_id="CB-1"
                )
        self.assertEqual(failure.exception.category, "execution-incomplete")
        self.assertFalse((logs.task / "evidence" / "E-log-fail.json").exists())

    def test_recovery_rejects_tampered_terminal_logs(self) -> None:
        fixture = self.fixture("print('stable output')\n")
        with mock.patch.object(
            workflow, "publish_operation_receipt", side_effect=RuntimeError("crash-before-receipt")
        ):
            with self.assertRaises(RuntimeError):
                run_check.execute_check(
                    fixture.task, run_id="tampered-1", check_key="candidate-check",
                    subject_id="M-1",
                )
        stdout_path = fixture.task / "runs" / "tampered-1" / "stdout.log"
        stdout_path.write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as tampered:
            run_check.execute_check(
                fixture.task, run_id="tampered-1", check_key="candidate-check",
                subject_id="M-1",
            )
        self.assertEqual(tampered.exception.category, "candidate-changed")
        self.assertFalse((fixture.task / "operation-receipt" / "tampered-1.json").exists())

    def test_replay_rejects_tampered_persisted_argv_or_cwd(self) -> None:
        fixture = self.fixture("print('stable')\n")
        with mock.patch.object(workflow, "publish_operation_receipt", side_effect=RuntimeError("crash-before-receipt")):
            with self.assertRaises(RuntimeError):
                run_check.execute_check(fixture.task, run_id="argv-record", check_key="candidate-check", subject_id="M-1")
        record = fixture.task / "runs" / "argv-record" / "run-record.json"
        value = json.loads(record.read_text(encoding="utf-8"))
        value["argv"] = ["/bin/sh", "-c", "echo forged"]
        record.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError) as rejected:
            run_check.execute_check(fixture.task, run_id="argv-record", check_key="candidate-check", subject_id="M-1")
        self.assertEqual(rejected.exception.category, "candidate-changed")

    def test_candidate_change_during_check_forces_incomplete_evidence(self) -> None:
        fixture = self.fixture(
            "from pathlib import Path\nPath('tracked.txt').write_text('changed\\n', encoding='utf-8')\n",
            scope="candidate",
        )
        repo = fixture.root / "candidate"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        (repo / "tracked.txt").write_text("before\n", encoding="utf-8")
        candidate_script = repo / "check.py"
        candidate_script.write_bytes(fixture.script.read_bytes())
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt", "check.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        (repo / ".agent-artifacts").mkdir()
        manifest = candidate.build_candidate(repo, [str(Path(run_check.__file__).resolve())])
        manifest_path = repo / ".agent-artifacts" / "candidate.json"
        candidate.write_manifest(manifest_path, manifest)
        bridge = {
            "bridge_id": "CB-1", "candidate_id": manifest["candidate_id"],
            "manifest_candidate_id": manifest["candidate_id"],
        }
        bridge_path = fixture.root / "bridge.json"
        bridge_path.write_bytes(full_protocol.canonical_json_bytes(bridge))
        fixture.contract["checks"]["candidate-check"]["cwd"] = str(repo)
        fixture.contract["checks"]["candidate-check"]["argv"] = [sys.executable, str(candidate_script)]
        fixture.contract["contract_digest"] = full_protocol.canonical_digest({
            key: value for key, value in fixture.contract.items() if key != "contract_digest"
        })
        fixture.state["contract_digest"] = fixture.contract["contract_digest"]
        # Use a fresh task because task-contract.json is immutable.
        changed_task = fixture.root / "changed-task"
        workflow.initialize_task(changed_task, fixture.contract, fixture.state)
        result = run_check.execute_check(
            changed_task, run_id="drift-1", check_key="candidate-check",
            subject_id="CB-1", candidate_manifest_path=manifest_path,
            candidate_bridge_path=bridge_path,
        )
        self.assertEqual(result["evidence"]["result"], "incomplete")
        self.assertEqual(result["run_record"]["candidate_status_after"], "changed")

    def test_candidate_scope_rejects_unbound_actual_runner_source_before_execution(self) -> None:
        fixture = self.fixture("print('must not run')\n", scope="candidate")
        repo = fixture.root / "candidate-unbound"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        (repo / "tracked.txt").write_text("stable\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        (repo / ".agent-artifacts").mkdir()
        manifest = candidate.build_candidate(repo, [])
        manifest_path = repo / ".agent-artifacts" / "candidate.json"
        candidate.write_manifest(manifest_path, manifest)
        bridge_path = fixture.root / "bridge-unbound.json"
        bridge_path.write_bytes(full_protocol.canonical_json_bytes({
            "bridge_id": "CB-1", "candidate_id": manifest["candidate_id"],
            "manifest_candidate_id": manifest["candidate_id"],
        }))
        fixture.contract["checks"]["candidate-check"]["cwd"] = str(repo)
        fixture.contract["contract_digest"] = full_protocol.canonical_digest({key: value for key, value in fixture.contract.items() if key != "contract_digest"})
        fixture.state["contract_digest"] = fixture.contract["contract_digest"]
        task = fixture.root / "candidate-unbound-task"
        workflow.initialize_task(task, fixture.contract, fixture.state)
        with self.assertRaises(workflow.WorkflowError) as rejected:
            run_check.execute_check(task, run_id="unbound-runner", check_key="candidate-check", subject_id="CB-1", candidate_manifest_path=manifest_path, candidate_bridge_path=bridge_path)
        self.assertEqual(rejected.exception.category, "missing-evidence")
        self.assertFalse((task / "operation-intent" / "unbound-runner.json").exists())


if __name__ == "__main__":
    unittest.main()
