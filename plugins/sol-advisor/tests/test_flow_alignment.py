"""Counterexamples for the opt-in full-v2 staged protocol repair.

These tests deliberately exercise the public protocol seams.  They do not use a
mocked assembler or reviewer to turn an absent lifecycle into a passing summary.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import full_protocol


def digest(value: object) -> str:
    return full_protocol.canonical_digest(value)


def v2_contract() -> dict[str, object]:
    value: dict[str, object] = {
        "protocol": "SA-FULL-V2-P2",
        "goal": "two serial stages with an explicit final review",
        "authority": {"allowed_paths": ["src"]},
        "preserved_behavior": ["solo", "delegate", "audit"],
        "excluded_behavior": ["network", "credentials"],
        "stages": {
            "s1": {"depends_on": [], "review_scope": "stage"},
            "s2": {"depends_on": ["s1"], "review_scope": "stage+final"},
        },
        "work_items": {
            "a": {"stage_key": "s1", "paths": ["src/a.py"], "baseline_id": "base"},
            "b": {"stage_key": "s1", "paths": ["src/b.py"], "baseline_id": "base"},
            "c": {"stage_key": "s2", "paths": ["src/a.py"], "baseline_id": "base"},
        },
        "checks": {
            "final": {"scope": "candidate", "phase": "pre-ship", "required": True, "final_candidate_verify": True},
            "smoke": {"scope": "candidate", "phase": "pre-review", "required": True},
            "full": {"scope": "candidate", "phase": "pre-ship", "required": True},
            "optional": {"scope": "candidate", "phase": "pre-ship", "required": False},
        },
        "environment_policy": [],
        "required_coverage": ["delivery", "candidate"],
        "review_policy": {
            "allowed_verdicts": ["ship", "fix-first", "rethink"],
            "review_identity_schema": "SA-REVIEW-ATTESTATION-2",
            "isolation_admission": "hard-or-behavioral",
            "behavioral_read_only_prompt_digest": "sha256:" + "1" * 64,
        },
        "probe_policy": {
            "scratch_root": "review-probes",
            "allowed_argv_prefixes": [[sys.executable]],
            "allowed_cwd": ".",
            "allowed_environment": [],
            "read_paths": ["review-probes", "assemblies"],
            "max_timeout_seconds": 30,
            "network": "forbidden",
        },
    }
    value["contract_digest"] = digest(value)
    return value


class FlowAlignmentProtocolTests(unittest.TestCase):
    def test_v2_contract_requires_membership_and_check_tiers(self) -> None:
        checked = full_protocol.validate_task_contract(v2_contract())
        self.assertEqual(checked["protocol"], "SA-FULL-V2-P2")
        missing = v2_contract()
        del missing["work_items"]["c"]["stage_key"]
        missing["contract_digest"] = digest({k: v for k, v in missing.items() if k != "contract_digest"})
        with self.assertRaises(full_protocol.ContractValidationError):
            full_protocol.validate_task_contract(missing)
        bad_phase = v2_contract()
        bad_phase["checks"]["full"]["phase"] = "whenever"
        bad_phase["contract_digest"] = digest({k: v for k, v in bad_phase.items() if k != "contract_digest"})
        with self.assertRaises(full_protocol.ContractValidationError):
            full_protocol.validate_task_contract(bad_phase)

    def test_p2_final_check_must_be_reachable_for_every_stage(self) -> None:
        for change in ("missing", "pre-review", "delivery", "challenge", "stage-gap", "non-boolean"):
            with self.subTest(change=change):
                contract = v2_contract()
                final = contract["checks"]["final"]
                if change == "missing":
                    del contract["checks"]["final"]
                elif change == "pre-review":
                    final["phase"] = "pre-review"
                elif change in {"delivery", "challenge"}:
                    final["scope"] = change
                elif change == "stage-gap":
                    final["stage_key"] = "s2"
                else:
                    final["final_candidate_verify"] = "true"
                contract["contract_digest"] = digest({k: v for k, v in contract.items() if k != "contract_digest"})
                with self.assertRaises(full_protocol.ContractValidationError):
                    full_protocol.validate_task_contract(contract)
        contract = v2_contract()
        final = contract["checks"].pop("final")
        for stage in ("s1", "s2"):
            contract["checks"]["final-" + stage] = dict(final, stage_key=stage)
        contract["contract_digest"] = digest({k: v for k, v in contract.items() if k != "contract_digest"})
        full_protocol.validate_task_contract(contract)

    def test_v2_behavioral_window_requires_lifecycle_bound_observation(self) -> None:
        contract = v2_contract()
        identity = {"candidate_id": "sha256:" + "2" * 64, "manifest_hash": "sha256:" + "3" * 64, "verify_receipt_digest": "sha256:" + "4" * 64}
        attestation = {
            "schema": "SA-REVIEW-ATTESTATION-2", "mode": "behavioral-window",
            "reviewer": {"thread_id": "sol", "context_id": "ctx", "context_source": "observed-context", "role": "sol_advisor_sol_reviewer", "model": "gpt-5.6-sol", "effort": "high", "runtime_receipt_digest": "sha256:" + "5" * 64},
            "observed": {"sandbox_policy_type": "danger-full-access", "permission_profile": "disabled", "prompt_digest": contract["review_policy"]["behavioral_read_only_prompt_digest"]},
            "windows": [{"candidate_before": identity, "candidate_after": identity, "task_tree_before": "sha256:" + "6" * 64, "task_tree_after": "sha256:" + "6" * 64}],
        }
        attestation["attestation_digest"] = digest(attestation)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_review_attestation(attestation, contract)

    def test_v2_probe_request_binds_immutable_source_and_cannot_alias(self) -> None:
        contract = v2_contract()
        request = {
            "record_type": "challenge-request", "request_id": "probe-1", "contract_digest": contract["contract_digest"],
            "packet_id": "P-1", "candidate_bridge_id": "CB-1", "check_key": "__new_probe__", "authority_decision": "root-registered",
            "probe": {"source_path": "review-probes/../outside.py", "source_sha256": hashlib.sha256(b"print('ok')\n").hexdigest(), "argv": [sys.executable, "review-probes/../outside.py"], "cwd": ".", "environment": [], "timeout_seconds": 10, "network": "forbidden"},
        }
        request["request_digest"] = digest(request)
        with self.assertRaises(full_protocol.RelationshipValidationError):
            full_protocol.validate_challenge_request(request, contract)
