"""Exercise the official verifier's unittest-result gate with real temporary suites."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


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


if __name__ == "__main__":
    unittest.main()
