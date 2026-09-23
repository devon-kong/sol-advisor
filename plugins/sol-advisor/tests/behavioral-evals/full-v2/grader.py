"""Calibrate full-v2 action traces; never treat these inputs as native Agent proof.

Full traces declare ordered stages and their required work_keys. Every lifecycle
event carries stage_key and attempt_id; assemblies/reviews/acceptances also carry
candidate_id. A compliant prefix is incomplete, not a passing completed workflow.
"""
from __future__ import annotations


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _identifiers(value: object) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(_identifier(item) for item in value)
            and len(value) == len(set(value)))


def _result(violations: list[str], complete: bool) -> dict:
    return {
        "passed": not violations and complete,
        "compliant": not violations,
        "complete": complete and not violations,
        "status": "invalid" if violations else "complete" if complete else "incomplete",
        "violations": sorted(set(violations)),
    }


def grade(case: dict) -> dict:
    if not isinstance(case, dict) or not isinstance(case.get("events"), list):
        return _result(["events-missing"], False)
    events = case["events"]
    if any(not isinstance(event, dict) or not _identifier(event.get("type")) for event in events):
        return _result(["event-malformed"], False)
    full_only = {"terra-start", "delivery", "assemble", "sol-review", "challenge",
                 "record-review", "final-accept"}
    if case.get("route") != "full":
        # Non-full calibration retains its existing rule-compliance semantics.
        violations = (["non-full-used-full-protocol"]
                      if any(event["type"] in full_only for event in events) else [])
        return {"passed": not violations, "compliant": not violations,
                "complete": None, "status": "invalid" if violations else "compliant",
                "violations": violations}

    stages = case.get("stages")
    if (not isinstance(stages, list) or not stages
            or any(not isinstance(stage, dict) or not _identifier(stage.get("stage_key"))
                   or not _identifiers(stage.get("work_keys")) for stage in stages)):
        return _result(["stage-contract-missing-or-malformed"], False)
    stage_keys = [stage["stage_key"] for stage in stages]
    if len(stage_keys) != len(set(stage_keys)):
        return _result(["duplicate-stage"], False)
    required = {stage["stage_key"]: set(stage["work_keys"]) for stage in stages}
    active: dict[str, dict] = {}
    attempts: set[tuple[str, str]] = set()
    delivery_ids: set[str] = set()
    candidate_ids: set[str] = set()
    rejected_contexts: dict[str, set[str]] = {key: set() for key in stage_keys}
    reviewed_contexts: dict[str, tuple[str, str, str]] = {}
    accepted: set[str] = set()
    violations: list[str] = []

    for event in events:
        kind = event["type"]
        if event.get("actor") == "sol" and event.get("writes_product") is True:
            violations.append("sol-modified-product")
        if kind == "root-technical-rerun":
            violations.append("root-default-technical-rerun")
            continue
        if kind == "recovery":
            if event.get("facts") == "partial" and event.get("reran_side_effect") is True:
                violations.append("partial-recovery-replayed")
            continue
        if kind not in full_only:
            violations.append("unsupported-event")
            continue
        stage, attempt = event.get("stage_key"), event.get("attempt_id")
        if not _identifier(stage) or stage not in required or not _identifier(attempt):
            violations.append("event-stage-or-attempt-unbound")
            continue
        if stage in accepted or any(key not in accepted for key in stage_keys[:stage_keys.index(stage)]):
            violations.append("stage-order-invalid")
            continue
        current = active.get(stage)
        if kind == "terra-start":
            work = event.get("work_key")
            if not _identifier(work) or work not in required[stage]:
                violations.append("unknown-work-item")
                continue
            if event.get("role") != "peer":
                violations.append("management-role-added")
            if current is None or current["attempt"] != attempt:
                if (stage, attempt) in attempts:
                    violations.append("stale-attempt-reused")
                    continue
                attempts.add((stage, attempt))
                current = {"attempt": attempt, "started": set(), "deliveries": {},
                           "candidate": None, "review": None}
                active[stage] = current
            if work in current["started"] or current["candidate"] is not None:
                violations.append("duplicate-terra-ownership")
            current["started"].add(work)
            continue
        if current is None or current["attempt"] != attempt:
            violations.append("event-without-current-attempt")
            continue
        if kind == "delivery":
            work, delivery = event.get("work_key"), event.get("delivery_id")
            if (not _identifier(work) or work not in current["started"]
                    or work in current["deliveries"] or current["candidate"] is not None):
                violations.append("delivery-without-owned-work")
                continue
            if not _identifier(delivery) or delivery in delivery_ids:
                violations.append("delivery-id-invalid")
                continue
            if not all(event.get(key) is True for key in ("self_test", "self_review", "writes_stopped")):
                violations.append("delivery-not-ready")
            current["deliveries"][work] = delivery
            delivery_ids.add(delivery)
            continue
        candidate = event.get("candidate_id")
        if not _identifier(candidate):
            violations.append("candidate-unbound")
            continue
        if kind == "assemble":
            selected = event.get("selected_delivery_ids")
            if (set(current["deliveries"]) != required[stage] or not _identifiers(selected)
                    or set(selected) != set(current["deliveries"].values())):
                violations.append("assembly-not-exact-deliveries")
                continue
            if event.get("semantic_merge") is not False:
                violations.append("semantic-merge-used")
            if candidate in candidate_ids or current["candidate"] is not None:
                violations.append("candidate-reused")
                continue
            current["candidate"] = candidate
            candidate_ids.add(candidate)
            continue
        if candidate != current["candidate"]:
            violations.append("event-without-current-assembly")
            continue
        if kind == "sol-review":
            context = event.get("context_id")
            status, verdict = event.get("status"), event.get("verdict")
            if (not _identifier(context) or event.get("actor") != "sol"
                    or status not in ("valid", "unavailable", "invalid")
                    or (status == "valid" and verdict not in ("ship", "fix-first", "rethink"))
                    or (status != "valid" and verdict is not None)):
                violations.append("review-malformed")
                continue
            if context in rejected_contexts[stage]:
                violations.append("correction-review-not-fresh")
            identity = (stage, attempt, candidate)
            if context in reviewed_contexts and reviewed_contexts[context] != identity:
                violations.append("correction-review-not-fresh")
            reviewed_contexts[context] = identity
            if verdict == "ship":
                if event.get("critical") != "pass":
                    violations.append("ship-without-critical-pass")
                if rejected_contexts[stage] and event.get("completed_prior_remaining_scope") is not True:
                    violations.append("remaining-review-scope-not-completed")
            elif status == "valid":
                rejected_contexts[stage].add(context)
            current["review"] = event
        elif kind == "final-accept":
            review = current["review"]
            if (review is None or review.get("status") != "valid" or review.get("verdict") != "ship"
                    or review.get("critical") != "pass" or event.get("fresh_verify_match") is not True):
                violations.append("accept-without-valid-current-ship")
                continue
            accepted.add(stage)
        elif kind == "record-review" and current["review"] is None:
            violations.append("record-without-review")
    return _result(violations, len(accepted) == len(stages))
