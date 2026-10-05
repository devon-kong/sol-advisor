#!/usr/bin/env python3
"""Small Root-side Reviewer pool gate; no spawning, voting or formal V schema changes."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

import full_protocol as protocol


def reviewer_count(value=2):
    if type(value) is not int or value < 1:
        raise ValueError('reviewers_per_round must be a positive integer')
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text')
    return value


def aggregate(value, *, previous=(), isolation_admission='hard-read-only', review_policy=None):
    if not isinstance(value, dict):
        raise ValueError('round input must be an object')
    result = copy.deepcopy(value)
    for key in ('round_id', 'candidate_id', 'acceptance_digest', 'scope'):
        text(result.get(key), key)
    protocol.canonical_component(result['round_id'], 'round_id')
    count = reviewer_count(result.get('reviewers_per_round', 2))
    members = result.get('members')
    if not isinstance(members, list) or len(members) != count:
        raise ValueError('round must contain exactly the requested Reviewer count')
    dispositions = result.get('dispositions')
    if not isinstance(dispositions, dict):
        raise ValueError('Root dispositions must be an object')
    prior_threads, prior_contexts = set(), set()
    for old in previous:
        if old != aggregate(old, isolation_admission=isolation_admission, review_policy=review_policy):
            raise ValueError('previous review round contents/digest drifted')
        if old['round_id'] == result['round_id']:
            raise ValueError('round ID already exists; replay must use the exact stored input')
        for member in old['members']:
            prior_threads.add(member['runtime']['thread_id'])
            prior_contexts.add(member['runtime'].get('context_id', member['runtime']['thread_id']))
    threads, contexts, review_ids, finding_keys = set(), set(), set(), set()
    blockers, unavailable, incomplete = {}, False, False
    for member in members:
        if not isinstance(member, dict):
            raise ValueError('Reviewer member must be an object')
        review_id = text(member.get('review_id'), 'review_id')
        if review_id in review_ids:
            raise ValueError('duplicate review ID')
        review_ids.add(review_id)
        if any(member.get(key) != result[key] for key in ('candidate_id', 'acceptance_digest')):
            raise ValueError('Reviewer candidate/acceptance binding differs from round')
        runtime = member.get('runtime')
        if not isinstance(runtime, dict):
            raise ValueError('Root-observed runtime receipt is required')
        if (runtime.get('agent_role'), runtime.get('model'), runtime.get('effort')) != ('sol_advisor_sol_reviewer', 'gpt-6.1-sol', 'high'):
            raise ValueError('Reviewer runtime role/model/effort mismatch')
        thread = text(runtime.get('thread_id'), 'native thread')
        context = text(runtime.get('context_id', thread), 'native context')
        text(runtime.get('permission_profile_type'), 'observed permission profile')
        sandbox = text(runtime.get('sandbox_policy_type'), 'observed sandbox')
        if sandbox != 'read-only':
            attestation = member.get('attestation')
            if not review_policy or isolation_admission != 'hard-or-behavioral':
                raise ValueError('behavioral review requires the exact contract policy and lifecycle attestation')
            checked = protocol._validate_v2_review_attestation(attestation, {'review_policy': review_policy})
            if (checked['reviewer']['runtime_receipt_digest'] != protocol.canonical_digest(runtime)
                or checked['reviewer']['thread_id'] != thread or checked['reviewer']['context_id'] != context
                or checked['windows'][0]['candidate_before'].get('candidate_id') != result['candidate_id']):
                raise ValueError('behavioral attestation is not bound to this Reviewer/candidate')
        if thread in threads or context in contexts or thread in prior_threads or context in prior_contexts:
            raise ValueError('Reviewer identities must be unique and fresh')
        threads.add(thread); contexts.add(context)
        status, verdict = member.get('status'), member.get('verdict')
        if status not in {'valid', 'unavailable', 'invalid'}:
            raise ValueError('invalid Reviewer status')
        if status != 'valid':
            if verdict is not None:
                raise ValueError('unavailable/invalid Reviewer must have null verdict')
            unavailable = True
        elif verdict not in {'ship', 'fix-first', 'rethink'}:
            raise ValueError('valid Reviewer must return the verdict triad')
        if type(member.get('coverage_complete')) is not bool:
            raise ValueError('coverage_complete must be boolean')
        incomplete |= not member['coverage_complete']
        findings = member.get('findings')
        if not isinstance(findings, list):
            raise ValueError('findings must be a list')
        if status == 'valid' and verdict in {'fix-first', 'rethink'} and not findings:
            raise ValueError('rejection requires an evidenced finding or unavailable status')
        for finding in findings:
            if not isinstance(finding, dict):
                raise ValueError('finding must be an object')
            key = review_id + ':' + text(finding.get('finding_id'), 'finding_id')
            if key in finding_keys:
                raise ValueError('duplicate finding ID')
            finding_keys.add(key)
            disposition = dispositions.get(key)
            if not isinstance(disposition, dict) or disposition.get('decision') not in {'accept', 'reject'}:
                raise ValueError('every finding requires a Root disposition')
            text(disposition.get('reason'), 'Root disposition reason')
            if disposition['decision'] == 'reject':
                continue
            for field in ('requirement', 'evidence', 'impact', 'scope', 'required_outcome', 'class'):
                text(finding.get(field), 'accepted finding ' + field)
            if finding['scope'] != result['scope']:
                raise ValueError('out-of-scope finding cannot block this round')
            if finding['class'] not in {'implementation', 'verification', 'architecture-contract', 'environment', 'candidate-review'}:
                raise ValueError('unsupported finding class')
            cause = finding.get('root_cause', key)
            text(cause, 'root cause')
            group = blockers.setdefault(cause, {'root_cause': cause, 'sources': [], 'findings': []})
            group['sources'].append(key); group['findings'].append(finding)
    if set(dispositions) != finding_keys:
        raise ValueError('Root dispositions must cover exactly this round findings')
    verdict = 'ship'
    if blockers:
        verdict = 'rethink' if any(f['class'] == 'architecture-contract' for g in blockers.values() for f in g['findings']) else 'fix-first'
    status = 'unavailable' if unavailable or (incomplete and not blockers) else 'valid'
    result.update(reviewers_per_round=count, status=status, verdict=verdict if status == 'valid' else None,
                  blockers=list(blockers.values()))
    result['round_digest'] = protocol.canonical_digest({k: v for k, v in result.items() if k != 'round_digest'})
    return result


def validate_record(value, *, count, candidate_id, acceptance_digest, scope, isolation_admission, review_policy=None):
    rebuilt = aggregate(value, isolation_admission=isolation_admission, review_policy=review_policy)
    if value != rebuilt:
        raise ValueError('review round contents/digest drifted')
    if (value['reviewers_per_round'], value['candidate_id'], value['acceptance_digest'], value['scope']) != (count, candidate_id, acceptance_digest, scope):
        raise ValueError('review round does not bind the current requested count/candidate/contract/scope')
    return value


def full_member_admission(task, contract, manifest, receipt, bridge_id, members):
    """Reuse the existing tagged admission for every member, not only canonical V."""
    import importlib.util
    import workflow
    spec = importlib.util.spec_from_file_location('sol_advisor_packet', Path(__file__).with_name('review-packet.py'))
    packet = importlib.util.module_from_spec(spec); spec.loader.exec_module(packet)
    identity = {'candidate_id': manifest['candidate_id'],
                'manifest_hash': protocol.canonical_digest(manifest),
                'verify_receipt_digest': protocol.canonical_digest(receipt)}
    # Full manifests use canonical JSON; this matches their persisted CB hash.
    results = copy.deepcopy(members)
    for member in results:
        runtime = member['runtime']; window = None
        if runtime.get('sandbox_policy_type') != 'read-only':
            wid = protocol.canonical_component(member.get('behavioral_window_id'), 'behavioral window ID')
            begin = workflow._checked_window_record(task / 'review-windows' / wid / 'begin.json', 'begin_record_digest')
            end = workflow._checked_window_record(task / 'review-windows' / wid / 'end.json', 'end_record_digest')
            if (begin.get('candidate') != identity or end.get('candidate') != identity
                or end.get('begin_record_digest') != begin['begin_record_digest']
                or end.get('reviewer_thread_id') != runtime['thread_id']
                or end.get('context_id') != runtime.get('context_id', runtime['thread_id'])):
                raise ValueError('persisted behavioral window does not bind this member/candidate')
            window = {'window_id': wid, 'context_id': end['context_id'], 'reviewer_thread_id': end['reviewer_thread_id'],
                      'candidate_before': begin['candidate'], 'candidate_after': end['candidate'],
                      'task_tree_before': begin['task_tree'], 'task_tree_after': end['task_tree'],
                      'begin_record_digest': begin['begin_record_digest'], 'end_record_digest': end['end_record_digest'],
                      'started_at': begin['started_at'], 'ended_at': end['ended_at']}
        attestation = packet.observed_reviewer_attestation(runtime, contract['review_policy'], window)
        protocol.validate_review_attestation(attestation, contract)
        if 'attestation' in member and member['attestation'] != attestation:
            raise ValueError('member attestation drifted from persisted runtime/window facts')
        member['attestation'] = attestation
        thread, context = runtime['thread_id'], runtime.get('context_id', runtime['thread_id'])
        for directory, filename in (('design-reviews', 'DR.json'), ('reviews', 'V.json')):
            for path in sorted((task / directory).glob('*/' + filename)):
                old, _ = workflow._json_bytes(path)
                if old.get('contract_digest') != contract['contract_digest']:
                    continue
                if directory == 'reviews' and old.get('candidate_bridge_id') == bridge_id:
                    continue  # Current-candidate continuation, including canonical V.
                if old.get('reviewer_thread_id') == thread or old.get('reviewer_context_id') == context:
                    raise ValueError('product Reviewer reuses a design or prior-candidate context')
    return results


def record(task_dir, value):
    import workflow
    task = Path(task_dir).absolute()
    round_id = protocol.canonical_component(value.get('round_id'), 'round_id')
    path = task / 'review-rounds' / (round_id + '.json')
    # Serialize pool admission/freshness with the existing task lock, no new CAS schema.
    with workflow._task_lock(task):
        records = workflow.read_task(task)
        contract, state = records['contract'], records['state']
        policy = contract['review_policy']
        if 'reviewers_per_round' not in policy:
            raise ValueError('legacy task contract does not select Reviewer rounds')
        count = reviewer_count(policy['reviewers_per_round'])
        previous = [workflow._json_bytes(p)[0] for p in sorted((task / 'review-rounds').glob('*.json')) if p != path]
        manifest_path = task / 'assemblies' / state['current_ids']['assembly_index'].removeprefix('I-') / 'candidate-manifest.json'
        manifest, _ = workflow._json_bytes(manifest_path)
        receipt = workflow._candidate_verify_receipt(manifest)
        workflow._require_current_candidate(manifest, receipt, affected=round_id)
        value = copy.deepcopy(value)
        value['members'] = full_member_admission(task, contract, manifest, receipt, state['current_ids']['candidate_binding'], value['members'])
        result = aggregate(value, previous=previous, isolation_admission=policy.get('isolation_admission', 'hard-read-only'), review_policy=policy)
        scope = state['stage_status'].get('stage_key', 'final')
        validate_record(result, count=count, candidate_id=manifest['candidate_id'], acceptance_digest=contract['contract_digest'], scope=scope,
                        isolation_admission=policy.get('isolation_admission', 'hard-read-only'), review_policy=policy)
        # This publisher requires the existing lock and never replaces differing bytes.
        workflow._publish_task_immutable_bytes_locked(task, ['review-rounds', round_id + '.json'], protocol.canonical_json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('aggregate', 'record'):
        arg = sub.add_parser(command); arg.add_argument('--input', required=True)
        if command == 'aggregate':
            arg.add_argument('--previous', action='append', default=[])
            arg.add_argument('--output', required=True)
            arg.add_argument('--isolation-admission', choices=['hard-read-only', 'hard-or-behavioral'], default='hard-read-only')
            arg.add_argument('--review-policy', help='exact contract review_policy for behavioral attestations')
        else:
            arg.add_argument('--task-dir', required=True)
    args = parser.parse_args()
    try:
        def read(path):
            return json.loads(Path(path).read_text(), object_pairs_hook=unique_object)
        value = read(args.input)
        if args.command == 'record':
            result = record(args.task_dir, value)
        else:
            result = aggregate(value, previous=[read(p) for p in args.previous], isolation_admission=args.isolation_admission,
                               review_policy=read(args.review_policy) if args.review_policy else None)
            with Path(args.output).open('x', encoding='utf-8') as output:
                output.write(protocol.canonical_json_bytes(result).decode() + '\n')
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print(json.dumps({'status': 'invalid', 'error': str(error)}))
        return 2


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


if __name__ == '__main__':
    sys.exit(main())
