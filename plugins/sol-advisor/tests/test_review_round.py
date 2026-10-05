"""Orchestration policy tests; runtime receipts are synthetic, not native evidence."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


def module():
    spec = importlib.util.spec_from_file_location('review_round', SCRIPTS / 'review-round.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def member(i, verdict='ship', findings=None):
    return {'review_id': f'r{i}', 'candidate_id': 'C1', 'acceptance_digest': 'A1',
            'status': 'valid', 'verdict': verdict, 'coverage_complete': True,
            'findings': findings or [], 'runtime': {'thread_id': f't{i}', 'context_id': f'c{i}',
            'agent_role': 'sol_advisor_sol_reviewer', 'model': 'gpt-6.1-sol', 'effort': 'high',
            'sandbox_policy_type': 'read-only', 'permission_profile_type': 'disabled'}}


def round_input(n=None):
    value = {'round_id': 'round-1', 'candidate_id': 'C1', 'acceptance_digest': 'A1',
             'scope': 'final', 'members': [member(i) for i in range(n or 2)], 'dispositions': {}}
    if n is not None:
        value['reviewers_per_round'] = n
    return value


class ReviewRoundTests(unittest.TestCase):
    def setUp(self):
        self.tool = module()

    def test_default_two_and_explicit_positive_counts(self):
        for n in (None, 1, 2, 3, 10):
            result = self.tool.aggregate(round_input(n))
            self.assertEqual(result['reviewers_per_round'], n or 2)
            self.assertEqual(result['verdict'], 'ship')

    def test_invalid_counts_and_incomplete_or_extra_pool_fail_closed(self):
        for n in (True, 0, -1, 1.5, '2'):
            value = round_input(); value['reviewers_per_round'] = n
            with self.assertRaises(ValueError): self.tool.aggregate(value)
        for count in (1, 3):
            value = round_input(); value['members'] = [member(i) for i in range(count)]
            with self.assertRaises(ValueError): self.tool.aggregate(value)

    def test_duplicate_native_identity_stale_candidate_or_basis_rejected(self):
        for field in ('thread_id', 'context_id'):
            value = round_input(); value['members'][1]['runtime'][field] = value['members'][0]['runtime'][field]
            with self.assertRaises(ValueError): self.tool.aggregate(value)
        for field in ('candidate_id', 'acceptance_digest'):
            value = round_input(); value['members'][1][field] = 'other'
            with self.assertRaises(ValueError): self.tool.aggregate(value)

    def test_unavailable_invalid_incomplete_or_wrong_role_never_ships(self):
        for status in ('unavailable', 'invalid'):
            value = round_input(); value['members'][1].update(status=status, verdict=None)
            self.assertEqual(self.tool.aggregate(value)['status'], 'unavailable')
        value = round_input(); value['members'][1]['coverage_complete'] = False
        self.assertNotEqual(self.tool.aggregate(value)['verdict'], 'ship')
        value = round_input(); value['members'][1]['runtime']['model'] = 'wrong'
        with self.assertRaises(ValueError): self.tool.aggregate(value)

    def test_valid_blocker_beats_ship_and_duplicate_causes_group(self):
        finding = {'finding_id': 'f', 'class': 'implementation', 'requirement': 'reject bool',
                   'evidence': 'bool accepted', 'impact': 'wrong quantity', 'scope': 'final',
                   'required_outcome': 'reject bool', 'root_cause': 'bool-is-int'}
        value = round_input(3)
        for i in (1, 2):
            value['members'][i].update(verdict='fix-first', findings=[finding])
            value['dispositions'][f'r{i}:f'] = {'decision': 'accept', 'reason': 'violates acceptance'}
        result = self.tool.aggregate(value)
        self.assertEqual(result['verdict'], 'fix-first')
        self.assertEqual(len(result['blockers']), 1)
        self.assertEqual(len(result['blockers'][0]['sources']), 2)
        value['members'][1]['findings'][0]['class'] = 'architecture-contract'
        self.assertEqual(self.tool.aggregate(value)['verdict'], 'rethink')

    def test_out_of_scope_rejection_requires_root_reason_and_complete_dispositions(self):
        value = round_input(); value['members'][1].update(verdict='fix-first', findings=[{'finding_id': 'f', 'scope': 'future'}])
        with self.assertRaises(ValueError): self.tool.aggregate(value)
        value['dispositions']['r1:f'] = {'decision': 'reject', 'reason': 'future behavior is outside scope'}
        self.assertEqual(self.tool.aggregate(value)['verdict'], 'ship')
        value['dispositions']['r1:f']['reason'] = ''
        with self.assertRaises(ValueError): self.tool.aggregate(value)

    def test_next_round_requires_fresh_contexts_and_same_round_replay_is_exact(self):
        old = self.tool.aggregate(round_input())
        new = round_input(); new['round_id'] = 'round-2'; new['candidate_id'] = 'C2'
        for item in new['members']: item['candidate_id'] = 'C2'
        with self.assertRaises(ValueError): self.tool.aggregate(new, previous=[old])
        for i, item in enumerate(new['members']): item['runtime'].update(thread_id=f'new-t{i}', context_id=f'new-c{i}')
        self.assertEqual(self.tool.aggregate(new, previous=[old])['verdict'], 'ship')

    def test_broad_host_requires_explicit_behavioral_admission(self):
        value = round_input()
        value['members'][0]['runtime']['sandbox_policy_type'] = 'danger-full-access'
        with self.assertRaises(ValueError): self.tool.aggregate(value)
        with self.assertRaises(ValueError): self.tool.aggregate(value, isolation_admission='hard-or-behavioral')
        value['members'][0]['runtime']['behavioral_read_only'] = True
        with self.assertRaises(ValueError): self.tool.aggregate(value, isolation_admission='hard-or-behavioral')

    def test_corrupt_previous_round_cannot_hide_reused_identity(self):
        old = self.tool.aggregate(round_input())
        old['members'][0]['runtime']['thread_id'] = 'corrupted-thread'
        new = round_input(); new['round_id'] = 'round-2'
        new['members'][0]['runtime']['context_id'] = 'new-context'
        new['members'][1]['runtime'].update(thread_id='new-thread',context_id='another-context')
        with self.assertRaises(ValueError): self.tool.aggregate(new, previous=[old])

    def test_unknown_or_malformed_findings_fail_closed(self):
        value = round_input(); value['members'][0]['findings'] = [{'finding_id': 'f'}]
        value['dispositions'] = {'r0:f': {'decision': 'accept', 'reason': 'observed'}}
        with self.assertRaises(ValueError): self.tool.aggregate(value)
        value = round_input(); value['dispositions']['r0:ghost'] = {'decision': 'reject', 'reason': 'not present'}
        with self.assertRaises(ValueError): self.tool.aggregate(value)


if __name__ == '__main__': unittest.main()
