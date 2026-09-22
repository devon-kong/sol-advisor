"""Calibrate raw offline eval fixtures, not the skill or an agent's delivered fix.

Fresh agents receive copied case inputs only. These tests keep the starting
counterexamples discriminating; root separately inspects/reruns agent outputs.
"""
from __future__ import annotations

import importlib.util
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
    def test_full_v2_usage_covers_required_examples_without_inventing_recovery_cli(self):
        usage = (REPOSITORY / "docs" / "full-v2" / "USAGE.md").read_text(encoding="utf-8")
        required_examples = {
            "### One Terra, one stage": "workflow.py receive",
            "### Two independent peer Terra deliveries": "workflow.py assemble",
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
