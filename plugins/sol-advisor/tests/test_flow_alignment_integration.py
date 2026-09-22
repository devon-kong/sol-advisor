"""Real tool transactions; runtime identities here are synthetic, never native proof."""
from __future__ import annotations
import copy, hashlib, json, subprocess, sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest import mock
from test_workflow import WorkflowFixture, write_json
from test_run_check import load_run_check
from test_review_packet import load_review_packet
import workflow as w
import full_protocol as p
run=load_run_check(); review=load_review_packet()
SCRIPTS=Path(w.__file__).parent

class StagedFixture(WorkflowFixture):
 def __init__(self,three=False,pre_required=True,per_stage_final=False):
  super().__init__(staged=True)
  self.task=self.root/'flow-task'
  self.contract['work_items']['b']['stage_key']='s1'
  self.contract['work_items']['c']={'paths':['a.txt'],'baseline_id':self.baseline_id,'stage_key':'s2'}
  cmd=[sys.executable,'-B','-c',"import sys; assert '--fail' not in sys.argv; from pathlib import Path; assert Path('a.txt').read_text() in ('a1\\n','c1\\n','d1\\n'); assert Path('b.txt').read_text()=='b1\\n'"]
  for key,scope,phase in [('candidate','candidate','pre-review'),('late','candidate','pre-ship'),('final','candidate','pre-ship')]:
   self.contract['checks'][key]={'scope':scope,'phase':phase,'required':True,'argv':cmd,'cwd':'$candidate','timeout_seconds':10,'allowed_argv_suffixes':[['--fail']]}
  self.contract['checks']['candidate']['required']=pre_required
  if three:
   self.contract['stages']['s2']['review_scope']='stage'
   self.contract['stages']['s3']={'depends_on':['s2'],'review_scope':'stage+final'}
   self.contract['work_items']['d']={'paths':['a.txt'],'baseline_id':self.baseline_id,'stage_key':'s3'}
   self.state['work_status']['d']='planned'
  self.contract['checks']['future']=dict(self.contract['checks']['candidate'],stage_key='s2')
  self.contract['checks']['optional']=dict(self.contract['checks']['late'],required=False)
  self.contract['checks']['final']['final_candidate_verify']=True
  if per_stage_final:
   final=self.contract['checks'].pop('final')
   for stage in self.contract['stages']:self.contract['checks']['final-'+stage]=dict(final,stage_key=stage)
  self.contract['checks']['challenge'].update(argv=[sys.executable,'-B','-c','print("independent check")'],cwd=str(self.root),timeout_seconds=10)
  self.contract['contract_digest']=p.canonical_digest({k:v for k,v in self.contract.items() if k!='contract_digest'})
  self.state['contract_digest']=self.contract['contract_digest'];self.state['work_status']['c']='planned'
  w.initialize_task(self.task,self.contract,self.state)
 def version(self):return w.read_task(self.task)['state']['version']
 def receive_work(self,key):
  paths=self.delivery_inputs(key)
  if key in ('c','d'):
   bundle=json.loads(paths['bundle'].read_text());bundle['changes'][0]['before_sha256']=hashlib.sha256(b'a1\n' if key=='c' else b'c1\n').hexdigest();write_json(paths['bundle'],bundle)
   m=json.loads(paths['material'].read_text());m['bundle']['sha256']=hashlib.sha256(paths['bundle'].read_bytes()).hexdigest();m['material_digest']=p.canonical_digest({k:v for k,v in m.items() if k!='material_digest'});write_json(paths['material'],m)
   d=json.loads(paths['delivery'].read_text());d['material_digest']=m['material_digest'];d['delivery_digest']=p.canonical_digest({k:v for k,v in d.items() if k!='delivery_digest'});write_json(paths['delivery'],d)
  return w.receive_delivery(self.task,op_id='receive-'+key,expected_state_version=self.version(),material_path=paths['material'],delivery_path=paths['delivery'],delivery_evidence_path=paths['evidence'],bundle_path=paths['bundle'],runtime_receipt_path=paths['runtime'])
 def assemble(self,stage,selected,op_id=None):
  op_id=op_id or 'assemble-'+stage
  w.assemble_candidate(self.task,op_id=op_id,expected_state_version=self.version(),baseline_repo=self.baseline,selected=selected,stage_key=stage)
  directory=self.task/'assemblies'/op_id;manifest=json.loads((directory/'candidate-manifest.json').read_text());bridge=json.loads((directory/'CB.json').read_text());index=json.loads((directory/'I.json').read_text())
  items=w._load_selected_deliveries(self.task,self.contract,w.read_task(self.task)['state']['selected_attempts'],exact_work_keys=set(w.read_task(self.task)['state']['selected_attempts']))
  return p.RelationshipContext(task_contract=self.contract,candidate_bridge=bridge,manifest=manifest,manifest_bytes=(directory/'candidate-manifest.json').read_bytes(),candidate_verify_receipt=w._candidate_verify_receipt(manifest),assembly=index,deliveries=[x['delivery'] for x in items],materials=[x['material'] for x in items],delivery_evidence=[x['evidence'] for x in items])
 def check(self,ctx,key,run_id,fail=False):
  bp=Path(ctx.candidate_bridge['manifest_path']).parent/'CB.json'
  return run.execute_check(self.task,run_id=run_id,check_key=key,subject_id=ctx.candidate_bridge['bridge_id'],candidate_manifest_path=ctx.candidate_bridge['manifest_path'],candidate_bridge_path=bp,argv_suffix=['--fail'] if fail else [])['evidence']
 def packet(self,ctx,stage,op_id=None,predecessor_verdicts=None):
  op_id=op_id or 'bundle-'+stage
  e=self.check(ctx,'candidate','pre-'+op_id)
  return review.bundle_review_packet(self.task,op_id=op_id,expected_state_version=self.version(),context=ctx,candidate_evidence=[e]+([self.check(ctx,'future','future-'+op_id)] if stage=='s2' else []),expected_coverage=['delivery','candidate'],predecessor_verdicts=predecessor_verdicts or {})['context']
 def challenge(self,ctx,stage,source=None):
  if source is None:q=review.prepare_challenge(self.task,relationship=ctx,request_id='q-'+stage,check_key='challenge',authority_decision='contract')
  else:q=review.register_probe(self.task,relationship=ctx,request_id='q-'+stage,source_bytes=source,timeout_seconds=10)
  e=run.execute_check(self.task,run_id='challenge-q-'+stage,check_key=q['check_key'],subject_id=q['packet_id']+':'+q['candidate_bridge_id'],challenge_request=q)['evidence']
  assert e['result']=='pass',e
  return review.record_challenge_evidence(self.task,relationship=ctx,request=q,evidence=e)['context']
 def reviewed(self,ctx,stage,late,window=None):
  runtime={'thread_id':'synthetic-sol-'+stage,'agent_role':'sol_advisor_sol_reviewer','model':'gpt-5.6-sol','effort':'high','sandbox_policy_type':'danger-full-access' if window else 'read-only','permission_profile_type':'disabled','prompt_digest':self.contract['review_policy']['behavioral_read_only_prompt_digest']}
  v={'record_type':'V','verdict_id':'V-'+stage,'contract_digest':self.contract['contract_digest'],'status':'valid','verdict':'ship','packet_id':ctx.packet['packet_id'],'candidate_bridge_id':ctx.candidate_bridge['bridge_id'],'challenge_receipt_id':ctx.challenge_receipt['challenge_receipt_id'],'rejection_closure':[],'rejection_dispositions':{},'open_rejections':[],'coverage_complete':True,'pre_ship_evidence_ids':[e['evidence_id'] for e in late],'reviewed_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'review_sequence':self.version()}
  return review.record_review(self.task,op_id='review-'+stage,expected_state_version=self.version(),relationship=ctx,verdict=v,reviewer_runtime_receipt=runtime,pre_ship_evidence=late,behavioral_window_id=window)['context']
 def accept(self,ctx,stage,crash_after_cas=False):
  e=self.check(ctx,'final-'+stage if 'final-'+stage in self.contract['checks'] else 'final','final-'+stage);vid=p.canonical_digest(ctx.candidate_verify_receipt)
  scope={'route':'full','action':'final-accept','stage_key':stage,'candidate_bridge_id':ctx.candidate_bridge['bridge_id']};at=e['observed_at']
  observed={'context_id':'synthetic-root','thread_id':'synthetic-root','role':'root','model':'fixture','effort':'high','observed_attestation':{'scope':scope,'observed_at':at}}
  authority={'root_authority_id':'root-'+stage,'contract_digest':self.contract['contract_digest'],'scope':scope,'observed_at':at,'expires_at':'2099-01-01T00:00:00Z','candidate_verify_receipt_id':vid,'candidate_verify_receipt_digest':vid,'issuer':{'role':'root','model':'fixture'},'observed_attestation':observed,'observed_attestation_digest':p.canonical_digest(observed)}
  a={'record_type':'A','acceptance_id':'A-'+stage,'status':'accepted','contract_digest':self.contract['contract_digest'],'accepted_stage_key':stage,'candidate_bridge_id':ctx.candidate_bridge['bridge_id'],'packet_id':ctx.packet['packet_id'],'verdict_id':ctx.verdict['verdict_id'],'final_candidate_evidence_id':e['evidence_id'],'root_authority_id':authority['root_authority_id'],'root_authority_scope':scope,'root_authority_expiry':authority['expires_at'],'candidate_verify_receipt_id':vid,'dependency_acceptance_ids':{key:'A-'+key for key in p._dependency_closure(self.contract,stage)}}
  files={key:self.root/(stage+'-'+key+'.json') for key in ['acceptance','final-evidence','root-authority']}
  for key,value in zip(files,[a,e,authority]):write_json(files[key],value)
  cmd=[sys.executable,str(SCRIPTS/'workflow.py'),'final-accept','--task-dir',str(self.task),'--op-id','accept-'+stage,'--expected-state-version',str(self.version()),'--trusted-observation-time',at]
  for key,path in files.items():cmd.extend(['--'+key,str(path)])
  self.last_accept_command=cmd
  if crash_after_cas:
   with mock.patch.object(w,'publish_operation_receipt',side_effect=RuntimeError('crash after CAS')):
    return w.final_accept(self.task,op_id='accept-'+stage,expected_state_version=self.version(),acceptance=a,relationship=ctx,final_candidate_evidence=e,root_authority=authority,candidate_verify_receipt=ctx.candidate_verify_receipt,dependency_acceptance_contexts={},trusted_observation_time=at)
  result=subprocess.run(cmd,text=True,capture_output=True)
  if result.returncode:raise AssertionError(result.stderr)
  return json.loads(result.stdout)

class FlowIntegrationTests(unittest.TestCase):
 def fixture(self):
  f=StagedFixture();self.addCleanup(f.cleanup);f.receive_work('a');f.receive_work('b');return f
 def test_two_stages_real_checks_review_and_final_accept_cli(self):
  f=self.fixture();ctx=f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1');original=p.canonical_json_bytes(ctx.packet)
  ctx=f.challenge(ctx,'s1')
  with self.assertRaises(w.WorkflowError):f.reviewed(ctx,'s1',[])
  late=f.check(ctx,'late','late-s1');ctx=f.reviewed(ctx,'s1',[late]);self.assertEqual(original,p.canonical_json_bytes(ctx.packet));f.accept(ctx,'s1')
  f.receive_work('c');ctx=f.packet(f.assemble('s2',{'c':'D-c-1'}),'s2');ctx=f.challenge(ctx,'s2');ctx=f.reviewed(ctx,'s2',[f.check(ctx,'late','late-s2')]);f.accept(ctx,'s2')
  self.assertEqual((Path(ctx.manifest['repo'])/'a.txt').read_text(),'c1\n');self.assertEqual((Path(ctx.manifest['repo'])/'b.txt').read_text(),'b1\n')
  self.assertEqual(w.read_task(f.task)['state']['stage_status']['status'],'accepted')
 def test_failed_required_late_evidence_blocks_ship(self):
  f=self.fixture();ctx=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1')
  late=f.check(ctx,'late','late-failed',fail=True);self.assertEqual(late['result'],'fail')
  with self.assertRaises(w.WorkflowError):f.reviewed(ctx,'s1',[late])
 def test_corrected_p2_review_rejects_reused_predecessor_context_through_record_review(self):
  f=self.fixture();old=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1')
  runtime={'thread_id':'synthetic-sol-old','context_id':'synthetic-context-old','agent_role':'sol_advisor_sol_reviewer','model':'gpt-5.6-sol','effort':'high','sandbox_policy_type':'read-only','permission_profile_type':'disabled','prompt_digest':f.contract['review_policy']['behavioral_read_only_prompt_digest']}
  fix={'record_type':'V','verdict_id':'V-fix','contract_digest':f.contract['contract_digest'],'status':'valid','verdict':'fix-first','packet_id':old.packet['packet_id'],'candidate_bridge_id':old.candidate_bridge['bridge_id'],'challenge_receipt_id':old.challenge_receipt['challenge_receipt_id'],'rejection_closure':[],'rejection_dispositions':{},'coverage_complete':False,'blocking_findings':[{'finding_id':'synthetic-finding'}]}
  old=review.record_review(f.task,op_id='review-fix',expected_state_version=f.version(),relationship=old,verdict=fix,reviewer_runtime_receipt=runtime)['context']
  f.receive('a',2,expected=f.version(),content='c1\n')
  corrected=f.assemble('s1',{'a':'D-a-2','b':'D-b-1'},op_id='assemble-corrected')
  with self.assertRaises(w.WorkflowError):
   f.packet(corrected,'s1',op_id='bundle-forged-predecessor',predecessor_verdicts={'V-fix':dict(old.verdict,reviewer_context_id='forged-context')})
  corrected=f.packet(corrected,'s1',op_id='bundle-corrected',predecessor_verdicts={'V-fix':old.verdict})
  request=review.prepare_challenge(f.task,relationship=corrected,request_id='q-corrected',check_key='challenge',authority_decision='contract')
  evidence=run.execute_check(f.task,run_id='challenge-q-corrected',check_key='challenge',subject_id=request['packet_id']+':'+request['candidate_bridge_id'],challenge_request=request)['evidence']
  corrected=review.record_challenge_evidence(f.task,relationship=corrected,request=request,evidence=evidence)['context']
  late=f.check(corrected,'late','late-corrected')
  ship={'record_type':'V','verdict_id':'V-corrected','contract_digest':f.contract['contract_digest'],'status':'valid','verdict':'ship','packet_id':corrected.packet['packet_id'],'candidate_bridge_id':corrected.candidate_bridge['bridge_id'],'challenge_receipt_id':corrected.challenge_receipt['challenge_receipt_id'],'rejection_closure':['V-fix'],'rejection_dispositions':{'V-fix':'resolved'},'open_rejections':[],'coverage_complete':True,'pre_ship_evidence_ids':[late['evidence_id']],'reviewed_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'review_sequence':f.version()}
  review_version=f.version()
  tampered=replace(corrected,predecessor_verdicts={'V-fix':dict(old.verdict,reviewer_context_id='forged-context')})
  with self.assertRaises(w.WorkflowError):
   review.record_review(f.task,op_id='review-corrected-tampered',expected_state_version=review_version,relationship=tampered,verdict=ship,reviewer_runtime_receipt=dict(runtime,thread_id='synthetic-sol-fresh',context_id='synthetic-context-fresh'),pre_ship_evidence=[late])
  for suffix,reused in [('context',dict(runtime,thread_id='synthetic-sol-new')),('thread',dict(runtime,context_id='synthetic-context-new'))]:
   with self.subTest(reused=suffix),self.assertRaises(w.WorkflowError):
    review.record_review(f.task,op_id='review-corrected-'+suffix,expected_state_version=review_version,relationship=corrected,verdict=ship,reviewer_runtime_receipt=reused,pre_ship_evidence=[late])
  fresh=dict(runtime,thread_id='synthetic-sol-fresh',context_id='synthetic-context-fresh')
  accepted=review.record_review(f.task,op_id='review-corrected-fresh',expected_state_version=review_version,relationship=corrected,verdict=ship,reviewer_runtime_receipt=fresh,pre_ship_evidence=[late])
  self.assertEqual(accepted['verdict']['verdict'],'ship')
  replay=review.record_review(f.task,op_id='review-corrected-fresh',expected_state_version=review_version,relationship=corrected,verdict=ship,reviewer_runtime_receipt=fresh,pre_ship_evidence=[late])
  self.assertEqual(replay['receipt'],accepted['receipt'])
  self.assertEqual(review.inspect_task(f.task)['state']['current_ids']['verdict'],'V-corrected')
  f.accept(accepted['context'],'s1')
  persisted=f.task/'reviews'/'V-corrected'/'context.json';forged=json.loads(persisted.read_text());forged['predecessor_verdicts']['V-fix']['reviewer_context_id']='forged-context';write_json(persisted,forged)
  with self.assertRaises(w.WorkflowError):review.inspect_task(f.task)
  with self.assertRaises(w.WorkflowError):w._load_persisted_acceptance_context(f.task,'A-s1')
  f.receive_work('c')
  with self.assertRaises(w.WorkflowError):f.assemble('s2',{'c':'D-c-1'})
 def test_optional_late_evidence_may_be_supplied(self):
  f=self.fixture();ctx=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1')
  ctx=f.reviewed(ctx,'s1',[f.check(ctx,'late','late'),f.check(ctx,'optional','optional')]);self.assertEqual(ctx.verdict['verdict'],'ship')
 def test_probe_source_drift_refused_before_child_start(self):
  f=self.fixture();ctx=f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1')
  q=review.register_probe(f.task,relationship=ctx,request_id='drift',source_bytes=b'print("original")\n',timeout_seconds=5)
  (f.task/q['probe']['source_path']).write_text('print("changed")\n')
  with self.assertRaises(w.WorkflowError):run.execute_check(f.task,run_id='challenge-drift',check_key='__new_probe__',subject_id=q['packet_id']+':'+q['candidate_bridge_id'],challenge_request=q)
  self.assertFalse((f.task/'runs/challenge-drift/request.json').exists())
 def test_accepted_selection_cannot_be_rebound(self):
  f=self.fixture();ctx=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1')
  ctx=f.reviewed(ctx,'s1',[f.check(ctx,'late','late')]);f.accept(ctx,'s1')
  path=f.task/'stage-acceptances/s1.json';index=json.loads(path.read_text());index['selected_attempts']['a']='D-a-rebound';write_json(path,index)
  with self.assertRaises(w.WorkflowError):w._accepted_stage_index(f.task,'s1')
 def test_old_run_log_tamper_is_rejected_at_review(self):
  f=self.fixture();ctx=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1')
  late=f.check(ctx,'late','late');Path(ctx.candidate_evidence[0]['logs'][0]['path']).write_text('tampered')
  with self.assertRaises(w.WorkflowError):f.reviewed(ctx,'s1',[late])
 def test_staged_run_binds_protocol_and_workflow_dependencies(self):
  f=self.fixture();ctx=f.assemble('s1',{'a':'D-a-1','b':'D-b-1'});e=f.check(ctx,'candidate','dependencies')
  request=json.loads((f.task/'runs/dependencies/request.json').read_text())
  names={Path(item['requested_path']).name for item in request['acceptance_materials']}
  self.assertTrue({'run-check.py','full_protocol.py','workflow.py','candidate.py'}.issubset(names),names)
 def test_third_stage_reuses_second_stage_cumulative_acceptance(self):
  f=StagedFixture(three=True);self.addCleanup(f.cleanup)
  for stage,keys in [('s1',['a','b']),('s2',['c']),('s3',['d'])]:
   for key in keys:f.receive_work(key)
   ctx=f.challenge(f.packet(f.assemble(stage,{key:'D-'+key+'-1' for key in keys}),stage),stage)
   ctx=f.reviewed(ctx,stage,[f.check(ctx,'late','late-'+stage)]);f.accept(ctx,stage)
   if stage=='s1':first_command=list(f.last_accept_command)
  self.assertEqual((Path(ctx.manifest['repo'])/'a.txt').read_text(),'d1\n')
  before=w.read_task(f.task)['state'];replay=subprocess.run(first_command,text=True,capture_output=True)
  self.assertEqual(replay.returncode,0,replay.stderr);self.assertEqual(w.read_task(f.task)['state'],before)
 def test_intermediate_acceptance_recovers_only_missing_receipt(self):
  f=self.fixture();ctx=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1');ctx=f.reviewed(ctx,'s1',[f.check(ctx,'late','late')])
  with self.assertRaisesRegex(RuntimeError,'crash after CAS'):f.accept(ctx,'s1',crash_after_cas=True)
  before=w.read_task(f.task)['state'];self.assertEqual(before['stage_status']['stage_key'],'s2')
  result=subprocess.run(f.last_accept_command,text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['outcome'],'success')
  self.assertEqual(w.read_task(f.task)['state'],before);self.assertEqual(w._accepted_stage_index(f.task,'s1')['acceptance_id'],'A-s1')
 def test_no_required_pre_review_checks_allows_empty_packet(self):
  f=StagedFixture(pre_required=False);self.addCleanup(f.cleanup);f.receive_work('a');f.receive_work('b');ctx=f.assemble('s1',{'a':'D-a-1','b':'D-b-1'})
  packet=review.bundle_review_packet(f.task,op_id='optional-only',expected_state_version=f.version(),context=ctx,candidate_evidence=[],expected_coverage=['delivery','candidate'],predecessor_verdicts={})['packet']
  self.assertEqual(packet['candidate_evidence_ids'],[])
 def test_public_acceptance_rejects_another_stages_final_check(self):
  f=StagedFixture(per_stage_final=True);self.addCleanup(f.cleanup);f.receive_work('a');f.receive_work('b')
  ctx=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1');ctx=f.reviewed(ctx,'s1',[f.check(ctx,'late','late')]);f.accept(ctx,'s1')
  acceptance=json.loads((f.root/'s1-acceptance.json').read_text());evidence=json.loads((f.root/'s1-final-evidence.json').read_text());authority=json.loads((f.root/'s1-root-authority.json').read_text())
  kwargs=dict(context=ctx,candidate_bridge=ctx.candidate_bridge,packet=ctx.packet,verdict=ctx.verdict,root_authority=authority,candidate_verify_receipt=ctx.candidate_verify_receipt,task_contract=f.contract,dependency_acceptance_contexts={},trusted_observation_time=evidence['observed_at'])
  self.assertEqual(p.validate_acceptance(acceptance,final_candidate_evidence=evidence,**kwargs)['status'],'accepted')
  bad=dict(evidence,check_key='final-s2');bad['evidence_digest']=p.canonical_digest({k:v for k,v in bad.items() if k!='evidence_digest'})
  with self.assertRaises(p.RelationshipValidationError):p.validate_acceptance(acceptance,final_candidate_evidence=bad,**kwargs)

 def test_p2_design_review_is_separate_and_implementation_needs_fresh_context(self):
  f=self.fixture();runtime={'thread_id':'synthetic-sol-s1','agent_role':'sol_advisor_sol_reviewer','model':'gpt-5.6-sol','effort':'high','sandbox_policy_type':'read-only','permission_profile_type':'disabled','prompt_digest':f.contract['review_policy']['behavioral_read_only_prompt_digest']}
  dr={'record_type':'DR','review_id':'design','status':'valid','design_verdict':'design-approved','contract_digest':f.contract['contract_digest']}
  result=review.record_design_review(f.task,review=dr,reviewer_runtime_receipt=runtime,design_input={'mechanism':'exact patches'})
  self.assertEqual(result['design_verdict'],'design-approved');self.assertIsNone(w.read_task(f.task)['state']['current_ids']['acceptance'])
  ctx=f.challenge(f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1'),'s1');late=f.check(ctx,'late','late')
  with self.assertRaises(w.WorkflowError):f.reviewed(ctx,'s1',[late])
  self.assertEqual(f.reviewed(ctx,'fresh',[late]).verdict['verdict'],'ship')
 def test_p2_behavioral_design_observation_needs_no_product_candidate(self):
  f=StagedFixture();self.addCleanup(f.cleanup);design={'mechanism':'pre-implementation probe'}
  w.begin_reviewer_window(f.task,window_id='design',candidate_identity={'design_input_digest':p.canonical_digest(design)})
  runtime={'thread_id':'design-sol','agent_role':'sol_advisor_sol_reviewer','model':'gpt-5.6-sol','effort':'high','sandbox_policy_type':'danger-full-access','permission_profile_type':'disabled','prompt_digest':f.contract['review_policy']['behavioral_read_only_prompt_digest']}
  result=review.record_design_review(f.task,review={'record_type':'DR','review_id':'design','status':'valid','design_verdict':'design-approved','contract_digest':f.contract['contract_digest']},reviewer_runtime_receipt=runtime,design_input=design,behavioral_window_id='design')
  self.assertEqual(result['design_verdict'],'design-approved');self.assertIsNone(w.read_task(f.task)['state']['current_ids']['candidate_binding'])
 def test_packet_cannot_be_relabelled_as_future_stage(self):
  f=self.fixture();ctx=f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1')
  altered=dict(ctx.packet,stage_key='s2',review_scope='stage+final')
  with self.assertRaises(p.RelationshipValidationError):p.validate_review_packet(altered,context=replace(ctx,packet=altered))
 def test_probe_cannot_read_ignored_or_git_files_inside_declared_directory(self):
  f=StagedFixture();self.addCleanup(f.cleanup)
  (f.baseline/'.git/info/exclude').write_text('private-local.txt\n.env\n')
  (f.baseline/'private-local.txt').write_text('FAKE_PRIVATE_NOT_A_SECRET')
  (f.baseline/'.env').write_text('FAKE_ENV_NOT_A_SECRET')
  self.assertEqual(subprocess.check_output(['git','-C',str(f.baseline),'status','--porcelain']),b'')
  f.receive_work('a');f.receive_work('b');ctx=f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1')
  workspace=Path(ctx.manifest['repo']);self.assertTrue((workspace/'private-local.txt').exists())
  self.assertNotIn('private-local.txt',{entry['path'] for entry in ctx.manifest['entries']})
  source=b"from pathlib import Path\nbase=Path('assemblies/assemble-s1/workspace')\nfor name in ['private-local.txt','.env','.git/config']:\n try: (base/name).read_bytes()\n except PermissionError: pass\n else: raise AssertionError('unbound read allowed: '+name)\nassert (base/'a.txt').read_text()=='a1\\n'\nprint('only bound candidate inputs readable')\n"
  ctx=f.challenge(ctx,'private',source)
  self.assertEqual(ctx.challenge_evidence['result'],'pass')

 def test_new_sandboxed_probe_and_behavioral_review_keep_old_evidence(self):
  f=self.fixture();ctx=f.packet(f.assemble('s1',{'a':'D-a-1','b':'D-b-1'}),'s1')
  identity={'candidate_id':ctx.candidate_bridge['candidate_id'],'manifest_hash':ctx.candidate_bridge['manifest_hash'],'verify_receipt_digest':p.canonical_digest(ctx.candidate_verify_receipt)}
  w.begin_reviewer_window(f.task,window_id='w',candidate_identity=identity)
  source=b"import pathlib,socket\ntry:\n pathlib.Path('task-contract.json').write_text('bad')\nexcept PermissionError: pass\nelse: raise AssertionError('product write allowed')\ntry:\n s=socket.socket();s.bind(('127.0.0.1',0))\nexcept PermissionError: pass\nelse: raise AssertionError('network allowed')\ntry:\n pathlib.Path('task-contract.json').read_text()\nexcept PermissionError: pass\nelse: raise AssertionError('undeclared read allowed')\nassert pathlib.Path('assemblies/assemble-s1/workspace/a.txt').read_text()=='a1\\n'\nprint('sandbox verified')\n"
  ctx=f.challenge(ctx,'s1',source);late=f.check(ctx,'late','late-s1');ctx=f.reviewed(ctx,'s1',[late],window='w')
  self.assertEqual(ctx.verdict['verdict'],'ship');self.assertEqual(ctx.observed_attestation['mode'],'behavioral-window')

class WindowTests(unittest.TestCase):
 def setUp(self):
  self.f=WorkflowFixture();self.addCleanup(self.f.cleanup);self.c={'candidate_id':'fixture'};self.r={'thread_id':'synthetic-sol'}
 def test_old_evidence_drift_rejects(self):
  p=self.f.task/'evidence'/'old.json';w.publish_task_path_json(self.f.task,p,{'old':1})
  w.begin_reviewer_window(self.f.task,window_id='w',candidate_identity=self.c)
  p.write_text('{"old":2}')
  with self.assertRaises(w.WorkflowError):w.end_reviewer_window(self.f.task,window_id='w',candidate_identity=self.c,runtime_receipt=self.r)
 def test_begin_retry_is_idempotent(self):
  a=w.begin_reviewer_window(self.f.task,window_id='w',candidate_identity=self.c)
  self.assertEqual(a,w.begin_reviewer_window(self.f.task,window_id='w',candidate_identity=self.c))
 def test_end_retry_observed_thread_fallback(self):
  w.begin_reviewer_window(self.f.task,window_id='w',candidate_identity=self.c)
  a=w.end_reviewer_window(self.f.task,window_id='w',candidate_identity=self.c,runtime_receipt=self.r)
  self.assertEqual(a,w.end_reviewer_window(self.f.task,window_id='w',candidate_identity=self.c,runtime_receipt=self.r))

if __name__=='__main__':unittest.main()
