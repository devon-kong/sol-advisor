#!/usr/bin/env python3
"""Run a unittest discovery suite and fail closed on unexecuted required mechanisms.

This runner owns the discovery and outcome facts.  It never accepts a test-provided
summary: ``unittest`` supplies the discovered IDs and result categories directly.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import unittest


def flatten_tests(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    tests: list[unittest.TestCase] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(flatten_tests(item))
        else:
            tests.append(item)
    return tests


def result_ids(items: list[tuple[unittest.TestCase, object]]) -> list[str]:
    return sorted(test.id() for test, _ in items)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed unittest verification for required mechanism IDs."
    )
    parser.add_argument("--tests-dir", required=True, type=Path)
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--required-id", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    tests_dir = args.tests_dir.resolve()
    required = sorted(set(args.required_id))
    report: dict[str, object] = {
        "runner": "verify-test-suite.py",
        "tests_dir": str(tests_dir),
        "pattern": args.pattern,
        "required": required,
        "discovered": [],
        "discovered_required": [],
        "missing_required": [],
        "skipped": [],
        "skipped_required": [],
        "expected_failures": [],
        "expected_failures_required": [],
        "unexpected_successes": [],
        "failures": [],
        "errors": [],
        "status": "fail",
    }

    if not tests_dir.is_dir():
        report["errors"] = [f"test directory is not a directory: {tests_dir}"]
        print(json.dumps(report, sort_keys=True))
        return 2

    loader = unittest.defaultTestLoader
    try:
        suite = loader.discover(str(tests_dir), pattern=args.pattern)
        tests = flatten_tests(suite)
        discovered = sorted(test.id() for test in tests)
        discovered_set = set(discovered)
        report["discovered"] = discovered
        report["discovered_required"] = sorted(discovered_set.intersection(required))
        report["missing_required"] = sorted(set(required).difference(discovered_set))

        diagnostic = io.StringIO()
        result = unittest.TextTestRunner(stream=diagnostic, verbosity=2, buffer=True).run(suite)
        skipped = result_ids(result.skipped)
        expected_failures = result_ids(result.expectedFailures)
        unexpected_successes = sorted(test.id() for test in result.unexpectedSuccesses)
        failures = result_ids(result.failures)
        errors = result_ids(result.errors)
        report["skipped"] = skipped
        report["skipped_required"] = sorted(set(skipped).intersection(required))
        report["expected_failures"] = expected_failures
        report["expected_failures_required"] = sorted(set(expected_failures).intersection(required))
        report["unexpected_successes"] = unexpected_successes
        report["failures"] = failures
        report["errors"] = errors

        accepted = (
            bool(discovered)
            and not report["missing_required"]
            and result.wasSuccessful()
            and not skipped
            and not expected_failures
            and not unexpected_successes
        )
        report["status"] = "pass" if accepted else "fail"
    except Exception as exc:  # Fail closed while preserving a machine-readable cause.
        report["errors"] = [f"runner exception: {type(exc).__name__}: {exc}"]

    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
