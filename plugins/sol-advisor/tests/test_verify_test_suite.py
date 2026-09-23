"""Exercise the official verifier's unittest-result gate with real temporary suites."""
from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from fixture_support import fixture_directory


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "verify-test-suite.py"
REQUIRED_ID = "test_fixture.RequiredPass.test_required"


class VerifyTestSuiteTests(unittest.TestCase):
    """A nonzero unittest exit alone must not hide missing or unexecuted mechanisms."""

    def run_suite(self, source: str, *required: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory(prefix="sol-advisor-verifier-suite.") as tmp:
            tests = Path(tmp) / "tests"
            tests.mkdir()
            (tests / "test_fixture.py").write_text(textwrap.dedent(source), encoding="utf-8")
            command = [sys.executable, "-B", str(RUNNER), "--tests-dir", str(tests)]
            for test_id in required:
                command.extend(("--required-id", test_id))
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        report = json.loads(result.stdout)
        if report.get("diagnostic"):
            self.addCleanup(Path(report["diagnostic"]["path"]).unlink)
        return result, report

    def test_accepts_discovered_required_test_that_actually_passes(self) -> None:
        """Break caught: a runner rejects a normally executed required mechanism."""
        result, report = self.run_suite(
            """
            import unittest

            class RequiredPass(unittest.TestCase):
                def test_required(self):
                    self.assertEqual("actual", "actual")

            class Neighbor(unittest.TestCase):
                def test_neighbor(self):
                    self.assertTrue(True)
            """,
            REQUIRED_ID,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["discovered_required"], [REQUIRED_ID])
        self.assertEqual(report["skipped"], [])
        self.assertEqual(report["expected_failures"], [])
        self.assertIsNone(report["diagnostic"])

    def test_rejects_required_test_missing_from_dynamic_discovery(self) -> None:
        """Break caught: a stale required-ID list is silently omitted from discovery."""
        result, report = self.run_suite(
            """
            import unittest

            class Neighbor(unittest.TestCase):
                def test_neighbor(self):
                    self.assertTrue(True)
            """,
            REQUIRED_ID,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["missing_required"], [REQUIRED_ID])

    def test_rejects_skipped_required_test_instead_of_accepting_ok_skipped(self) -> None:
        """Break caught: ``OK (skipped=N)`` is mistaken for executed mechanism evidence."""
        result, report = self.run_suite(
            """
            import unittest

            class RequiredPass(unittest.TestCase):
                @unittest.skip("fixture cannot execute")
                def test_required(self):
                    self.fail("must not run")
            """,
            REQUIRED_ID,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["skipped_required"], [REQUIRED_ID])

    def test_rejects_expected_failure_required_test(self) -> None:
        """Break caught: an expected failure is promoted to a passing required mechanism."""
        result, report = self.run_suite(
            """
            import unittest

            class RequiredPass(unittest.TestCase):
                @unittest.expectedFailure
                def test_required(self):
                    self.assertEqual("wrong", "right")
            """,
            REQUIRED_ID,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["expected_failures_required"], [REQUIRED_ID])

    def test_rejects_skip_even_when_another_required_test_passes(self) -> None:
        """Break caught: a passing neighbor masks a suite-level skip condition."""
        neighbor = "test_fixture.Neighbor.test_neighbor"
        result, report = self.run_suite(
            """
            import unittest

            class RequiredPass(unittest.TestCase):
                @unittest.skip("fixture cannot execute")
                def test_required(self):
                    self.fail("must not run")

            class Neighbor(unittest.TestCase):
                def test_neighbor(self):
                    self.assertTrue(True)
            """,
            REQUIRED_ID,
            neighbor,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["discovered_required"], [neighbor, REQUIRED_ID])
        self.assertEqual(report["skipped_required"], [REQUIRED_ID])

    def test_failure_preserves_original_traceback_and_output(self) -> None:
        result, report = self.run_suite('''
            import unittest
            class Broken(unittest.TestCase):
                def test_error(self):
                    print("first-run-output")
                    raise FileNotFoundError("first-run-cause")
        ''')
        self.assertNotEqual(result.returncode, 0)
        diagnostic = report.get("diagnostic")
        self.assertIsInstance(diagnostic, dict, report)
        path = Path(diagnostic["path"])
        contents = path.read_bytes()
        self.assertIn(b"Traceback", contents)
        self.assertIn(b"FileNotFoundError: first-run-cause", contents)
        self.assertIn(b"first-run-output", contents)
        self.assertEqual(diagnostic["sha256"], hashlib.sha256(contents).hexdigest())

    def test_clean_checkout_fixtures_initialize_their_own_parent(self) -> None:
        """Each fixture must work independently without a developer's ignored directory."""
        plugin = RUNNER.parent.parent
        constructors = {
            "test_workflow": "WorkflowFixture()",
            "test_run_check": "RunCheckFixture('print(1)')",
            "test_full_protocol": "ProtocolFixture()",
        }
        for module, constructor in constructors.items():
            with self.subTest(module=module), tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / "plugins/sol-advisor"
                shutil.copytree(plugin / "scripts", copy / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
                shutil.copytree(plugin / "tests", copy / "tests", ignore=shutil.ignore_patterns("__pycache__"))
                self.assertFalse((Path(tmp) / ".agent-artifacts").exists())
                result = subprocess.run(
                    [sys.executable, "-B", "-c", f"from {module} import *; f = {constructor}; f.cleanup()"],
                    cwd=copy / "tests", capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_previous_reviewer_migrates_but_custom_edits_are_preserved(self) -> None:
        plugin = RUNNER.parent.parent
        previous = (plugin / "tests/fixtures/reviewer-v080.toml").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "agents"
            shutil.copytree(plugin / "agents", target)
            reviewer = target / "sol-advisor-sol-reviewer.toml"
            reviewer.write_bytes(previous)
            command = ["sh", str(plugin / "scripts/install-agents.sh"), "--target-dir", str(target)]
            check = subprocess.run(command + ["--check"], capture_output=True, text=True)
            self.assertNotEqual(check.returncode, 0)
            self.assertEqual(reviewer.read_bytes(), previous)
            migrated = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            self.assertEqual(reviewer.read_bytes(), (plugin / "agents" / reviewer.name).read_bytes())
            reviewer.write_bytes(previous + b"\n# user customization\n")
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, before)

    def test_previous_implementer_name_migrates_without_leaving_terra(self) -> None:
        plugin = RUNNER.parent.parent
        old_bytes = (plugin / "tests/fixtures/implementer-v080.toml").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "agents"
            shutil.copytree(plugin / "agents", target)
            old = target / "sol-advisor-terra-implementer.toml"
            new = target / "sol-advisor-sol-implementer.toml"
            old.write_bytes(old_bytes)
            command = ["sh", str(plugin / "scripts/install-agents.sh"), "--target-dir", str(target)]
            self.assertNotEqual(subprocess.run(command + ["--check"], capture_output=True).returncode, 0)
            migrated = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            self.assertFalse(old.exists())
            self.assertEqual(new.read_bytes(), (plugin / "agents" / new.name).read_bytes())
            self.assertEqual(subprocess.run(command + ["--check"], capture_output=True).returncode, 0)

            old.write_bytes(old_bytes + b"\n# user customization\n")
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, before)

    def test_previous_luna_migrates_but_custom_edits_are_preserved(self) -> None:
        plugin = RUNNER.parent.parent
        previous = (plugin / "tests/fixtures/luna-v080.toml").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "agents"
            shutil.copytree(plugin / "agents", target)
            luna = target / "sol-advisor-luna-implementer.toml"
            luna.write_bytes(previous)
            command = ["sh", str(plugin / "scripts/install-agents.sh"), "--target-dir", str(target)]
            self.assertNotEqual(subprocess.run(command + ["--check"], capture_output=True).returncode, 0)
            migrated = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            self.assertEqual(luna.read_bytes(), (plugin / "agents" / luna.name).read_bytes())

            luna.write_bytes(previous + b"\n# user customization\n")
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, before)

    def test_fixture_parent_preserves_existing_content_and_refuses_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "artifacts"
            parent.mkdir()
            sentinel = parent / "existing-evidence"
            sentinel.write_bytes(b"retain me")
            with fixture_directory(parent) as allocated:
                self.assertEqual(Path(allocated).parent, parent)
                self.assertEqual(sentinel.read_bytes(), b"retain me")
            self.assertEqual(list(parent.iterdir()), [sentinel])
            alias = Path(tmp) / "alias"
            alias.symlink_to(parent, target_is_directory=True)
            with self.assertRaises(ValueError):
                fixture_directory(alias)
            with self.assertRaises(FileExistsError):
                fixture_directory(sentinel)
            self.assertEqual(list(parent.iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main()
