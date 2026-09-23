"""Calibrate raw offline eval fixtures, not the skill or an agent's delivered fix.

Fresh agents receive copied case inputs only. These tests keep the starting
counterexamples discriminating; root separately inspects/reruns agent outputs.
"""
from __future__ import annotations

import importlib.util
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


FIXTURES = Path(__file__).parent / "behavioral-evals"
REPOSITORY = Path(__file__).resolve().parents[3]


def load(case: str, filename: str):
    path = FIXTURES / case / filename
    spec = importlib.util.spec_from_file_location(f"fixture_{case}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BehavioralFixtureTests(unittest.TestCase):
    def full_trace(self):
        return {
            "route": "full", "stages": [{"stage_key": "s1", "work_keys": ["core"]}],
            "events": [dict(event, stage_key="s1", attempt_id="a1") for event in [
                {"type": "terra-start", "role": "peer", "work_key": "core"},
                {"type": "delivery", "work_key": "core", "delivery_id": "D1", "self_test": True, "self_review": True, "writes_stopped": True},
                {"type": "assemble", "candidate_id": "C1", "selected_delivery_ids": ["D1"], "semantic_merge": False},
                {"type": "sol-review", "actor": "sol", "context_id": "R1", "candidate_id": "C1", "status": "valid", "critical": "pass", "verdict": "ship"},
                {"type": "final-accept", "candidate_id": "C1", "fresh_verify_match": True},
            ]],
        }

    def test_full_trace_requires_complete_ordered_delivery_chain(self):
        grader = load("full-v2", "grader.py")
        valid = self.full_trace()
        self.assertTrue(grader.grade(valid)["passed"])
        cases = {"empty": [], "review-only": valid["events"][-2:],
                 "accept-before-review": valid["events"][:3] + valid["events"][:2:-1]}
        for label, events in cases.items():
            with self.subTest(case=label):
                self.assertFalse(grader.grade(dict(valid, events=events))["passed"])
        partial = grader.grade(dict(valid, events=valid["events"][:2]))
        self.assertEqual(partial["status"], "incomplete")
        self.assertTrue(partial["compliant"])
        self.assertFalse(partial["passed"])

    def test_full_trace_binds_stage_work_attempt_candidate_and_latest_review(self):
        grader = load("full-v2", "grader.py")
        mutations = [(1, "work_key", "other"), (1, "attempt_id", "other"),
                     (2, "selected_delivery_ids", ["D1", "D1"]),
                     (3, "candidate_id", "other"), (3, "stage_key", "other"),
                     (3, "critical", "fail"), (4, "attempt_id", "other")]
        for index, key, value in mutations:
            case = self.full_trace()
            case["events"][index][key] = value
            with self.subTest(index=index, key=key):
                self.assertFalse(grader.grade(case)["passed"])
        case = self.full_trace()
        case["events"].insert(-1, dict(case["events"][-2], verdict="fix-first", critical="fail"))
        self.assertFalse(grader.grade(case)["passed"])

    def test_full_trace_accepts_fresh_correction_and_multiple_stages(self):
        grader = load("full-v2", "grader.py")
        case = self.full_trace()
        case["events"] = case["events"][:-1]
        case["events"][-1].update(verdict="fix-first", critical="fail")
        corrected = copy.deepcopy(self.full_trace()["events"])
        for event in corrected:
            event["attempt_id"] = "a2"
            if "delivery_id" in event: event["delivery_id"] = "D2"
            if "selected_delivery_ids" in event: event["selected_delivery_ids"] = ["D2"]
            if "candidate_id" in event: event["candidate_id"] = "C2"
            if "context_id" in event:
                event.update(context_id="R2", completed_prior_remaining_scope=True)
        case["events"].extend(corrected)
        self.assertTrue(grader.grade(case)["passed"])
        reused = copy.deepcopy(case)
        reused["events"][-2]["context_id"] = "R1"
        self.assertFalse(grader.grade(reused)["passed"])
        case["stages"].append({"stage_key": "s2", "work_keys": ["core"]})
        self.assertFalse(grader.grade(case)["passed"])
        second = copy.deepcopy(self.full_trace()["events"])
        for event in second:
            event["stage_key"] = "s2"
            if "delivery_id" in event: event["delivery_id"] = "D3"
            if "selected_delivery_ids" in event: event["selected_delivery_ids"] = ["D3"]
            if "candidate_id" in event: event["candidate_id"] = "C3"
            if "context_id" in event: event["context_id"] = "R3"
        case["events"].extend(second)
        self.assertTrue(grader.grade(case)["passed"])

    def test_full_trace_malformed_input_is_rejected_without_crashing(self):
        grader = load("full-v2", "grader.py")
        for event in [None, [], {"type": "assemble", "selected_delivery_ids": [{}]}]:
            with self.subTest(event=event):
                self.assertFalse(grader.grade(dict(self.full_trace(), events=[event]))["passed"])

    def test_full_trace_rejects_reusing_context_for_changed_candidate(self):
        case = self.full_trace()
        previous = copy.deepcopy(case["events"][:-1])
        for event in previous:
            event["attempt_id"] = "old"
            if "delivery_id" in event: event["delivery_id"] = "D-old"
            if "selected_delivery_ids" in event: event["selected_delivery_ids"] = ["D-old"]
            if "candidate_id" in event: event["candidate_id"] = "C-old"
        case["events"] = previous + case["events"]
        self.assertFalse(load("full-v2", "grader.py").grade(case)["passed"])

    def test_full_v2_usage_covers_required_examples_without_inventing_recovery_cli(self):
        usage = (REPOSITORY / "docs" / "full-v2" / "USAGE.md").read_text(encoding="utf-8")
        required_examples = {
            "### One Sol implementer, one stage": "workflow.py receive",
            "### Two independent peer Sol implementer deliveries": "workflow.py assemble",
            "### High-risk design challenge before implementation": "record-design-review",
            "### Interrupted mutation and recovery": "workflow.py status",
        }
        for heading, command in required_examples.items():
            with self.subTest(heading=heading):
                self.assertIn(heading, usage)
                section = usage.split(heading, 1)[1].split("\n### ", 1)[0]
                self.assertIn(command, section)
        documented_commands = [
            line.strip() for line in usage.splitlines() if line.startswith("python3 ")
        ]
        self.assertFalse(
            any("workflow.py recover" in command for command in documented_commands),
            documented_commands,
        )

    def test_full_v2_action_trace_grader_distinguishes_valid_and_invalid_mechanisms(self):
        grader = load("full-v2", "grader.py")
        document = json.loads((FIXTURES / "full-v2" / "cases.json").read_text(encoding="utf-8"))
        self.assertIn("never", document["notice"].lower())
        self.assertGreaterEqual(len(document["cases"]), 7)
        for case in document["cases"]:
            with self.subTest(case=case["id"]):
                result = grader.grade(case)
                self.assertEqual(result["passed"], case["expected"], result)
                if case["expected"]:
                    self.assertEqual(result["violations"], [])
                else:
                    self.assertTrue(result["violations"])

    def test_routine_starts_with_compatible_default(self):
        module = load("routine", "greeting.py")
        self.assertEqual(module.greet("Ada"), "Hello, Ada")
        with self.assertRaises(TypeError):
            module.greet("Ada", uppercase=True)

    def test_shared_counterexample_reaches_three_consumers(self):
        module = load("shared", "orders.py")
        for action in ("create", "amend", "retry"):
            function = getattr(module, action + "_order")
            self.assertEqual(function(True), {"quantity": True, "action": action})
            self.assertEqual(function(20), {"quantity": 20, "action": action})
        with self.assertRaises(ValueError):
            module.quote_order(True)
        self.assertEqual(module.quote_order(20), 60)

    def test_handoff_detects_dependency_change_despite_successful_command(self):
        with tempfile.TemporaryDirectory(prefix="sol-advisor-handoff-fixture.") as tmp:
            target = Path(tmp) / "delivery"
            shutil.copytree(FIXTURES / "handoff", target)
            before = (target / "policy.py").read_bytes()
            result = subprocess.run(
                [sys.executable, "-B", "render.py"], cwd=target,
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), "limit=20")
            self.assertNotEqual((target / "policy.py").read_bytes(), before)
            state = json.loads((target / "worker-state.json").read_text())
            self.assertEqual(state["writes"], 1)
            subprocess.run(
                [sys.executable, "-B", "worker.py", "handoff"],
                cwd=target, capture_output=True, check=True,
            )
            stable = (target / "policy.py").read_bytes()
            subprocess.run(
                [sys.executable, "-B", "render.py"],
                cwd=target, capture_output=True, check=True,
            )
            self.assertEqual((target / "policy.py").read_bytes(), stable)
            self.assertEqual(json.loads((target / "worker-state.json").read_text())["writes"], 1)

    def test_closure_counterexample_survives_entry_checks_on_both_paths(self):
        module = load("closure", "publisher.py")
        for function in (module.publish, module.merge):
            owner = {"scope": "PUBLISHER", "owner_id": "a", "token": "t", "acquired_at": 1, "expires_at": 100}
            now = [90]
            output = []

            def prepare(value):
                now[0] = 101
                return value

            self.assertTrue(function("x", owner, prepare, lambda: now[0], output))
            self.assertEqual(len(output), 1)
            self.assertFalse(function("x", owner, lambda x: x, lambda: 101, []))

    def test_review_green_suite_is_insufficient_for_late_publication(self):
        module = load("review", "publisher.py")
        now = [90]
        output = []

        def prepare(value):
            now[0] = 101
            return value

        self.assertTrue(module.publish("x", {"expires_at": 100}, prepare, lambda: now[0], output))
        self.assertEqual(output, ["x"])
        required = json.loads((FIXTURES / "review" / "REQUIRED.json").read_text())
        missing = [name for name in required["files"] if not (FIXTURES / "review" / name).exists()]
        self.assertEqual(missing, ["test_late.py"])
        result = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-p", "test_*.py"],
            cwd=FIXTURES / "review", capture_output=True, text=True, check=True,
        )
        self.assertIn("Ran 2 tests", result.stderr)
        self.assertIn("OK", result.stderr)


if __name__ == "__main__":
    unittest.main()
