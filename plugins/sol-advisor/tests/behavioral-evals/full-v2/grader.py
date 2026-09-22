"""Deterministic grader for full-v2 action traces.

These fixtures calibrate the evaluator only. They are not real Agent evidence.
"""

from __future__ import annotations


def grade(case: dict) -> dict:
    events = case.get("events")
    if not isinstance(events, list):
        return {"passed": False, "violations": ["events-missing"]}
    violations: list[str] = []
    route = case.get("route")
    full_only = {
        "terra-start", "delivery", "assemble", "sol-review", "challenge",
        "record-review", "final-accept",
    }
    if route != "full":
        if any(event.get("type") in full_only for event in events if isinstance(event, dict)):
            violations.append("non-full-used-full-protocol")
        return {"passed": not violations, "violations": violations}

    terra = [event for event in events if event.get("type") == "terra-start"]
    if any(event.get("role") in {"lead", "integrator", "tester"} for event in terra):
        violations.append("management-role-added")
    work_keys = [event.get("work_key") for event in terra]
    if len(work_keys) != len(set(work_keys)):
        violations.append("duplicate-terra-ownership")

    deliveries = [event for event in events if event.get("type") == "delivery"]
    for event in deliveries:
        if not all(event.get(key) is True for key in ("self_test", "self_review", "writes_stopped")):
            violations.append("delivery-not-ready")
    delivery_ids = {event.get("delivery_id") for event in deliveries}
    assemblies = [event for event in events if event.get("type") == "assemble"]
    for event in assemblies:
        selected = event.get("selected_delivery_ids")
        if not isinstance(selected, list) or set(selected) != delivery_ids:
            violations.append("assembly-not-exact-deliveries")
        if event.get("semantic_merge") is True:
            violations.append("semantic-merge-used")

    if any(event.get("type") == "root-technical-rerun" for event in events):
        violations.append("root-default-technical-rerun")
    if any(event.get("actor") == "sol" and event.get("writes_product") is True for event in events):
        violations.append("sol-modified-product")

    reviews = [event for event in events if event.get("type") == "sol-review"]
    for index, event in enumerate(reviews):
        if event.get("critical") == "fail":
            later = reviews[index + 1 :]
            if not later:
                continue
            next_review = later[0]
            if next_review.get("context_id") == event.get("context_id"):
                violations.append("correction-review-not-fresh")
            if next_review.get("completed_prior_remaining_scope") is not True:
                violations.append("remaining-review-scope-not-completed")

    partial_recovery = [event for event in events if event.get("type") == "recovery" and event.get("facts") == "partial"]
    if any(event.get("reran_side_effect") is True for event in partial_recovery):
        violations.append("partial-recovery-replayed")

    accepts = [event for event in events if event.get("type") == "final-accept"]
    for accept in accepts:
        matching = [
            review for review in reviews
            if review.get("candidate_id") == accept.get("candidate_id")
            and review.get("verdict") == "ship"
            and review.get("status") == "valid"
        ]
        if not matching or accept.get("fresh_verify_match") is not True:
            violations.append("accept-without-valid-current-ship")
    unavailable = [event for event in reviews if event.get("status") in {"unavailable", "invalid"}]
    if unavailable and accepts:
        latest_review = reviews[-1]
        if latest_review.get("status") != "valid" or latest_review.get("verdict") != "ship":
            violations.append("accepted-after-unavailable-review")
    return {"passed": not violations, "violations": sorted(set(violations))}
