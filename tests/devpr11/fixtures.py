"""Synthetic fixtures: S1 native semantics; S2 actual setup/ingestion/Journal.

S1 snapshots below are explicitly not disk integration evidence. S2 never
injects a final projection, patches a reducer, or bypasses the shared pool.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import subprocess
import sys

from tests.devpr06.test_control import Harness as OriginalHarness, NOW, Boundary
from pmrh.application.control import AuthorityRegistry, Control
from pmrh.adapters.storage import control as D
from pmrh.adapters.storage.control_fast import CombinedControlStorage, profile as combined_profile, EVENT_SCHEMA, FAST_PAYLOAD_FIELDS
from pmrh.adapters.storage.pool import Pool, RootBinding
from pmrh.domain.primitives import canonical,sha
from pmrh.domain import knowledge as K,assurance as A
from pmrh.domain.fastmath.model import make_revision,FastReadContext
from pmrh.domain.fastmath.validation import native_projection,guard,native_refs,claim_fingerprint,required_guards
from research_studio.storage_compat import CombinedSyntheticSetup,CombinedNativeBridge
from research_studio.store import Store
from research_studio import strategy


class Harness(OriginalHarness):
    def __init__(self, root, *, kind='TRH', activate=True, pool=None):
        self.root = Path(root)
        inputs = {'TRH': (b'For every integer n, n + 0 = n.',),
                  'FDH': (b'Compare integer addition patterns.', b'Keep the integers and addition fixed.',
                          b'Vary only the candidate statements.'), 'SURVEY': ()}[kind]
        self.setup = CombinedSyntheticSetup(self.root/'project', kind=kind, inputs=inputs,
            survey_scope={'topic':'Synthetic addition survey', 'questions':['Which original statements remain open?']} if kind == 'SURVEY' else None)
        self.store = self.setup.store
        self.iid = self.setup.instance_id
        self.project = self.store._marker()['project_id']
        self.scope = dict(project_id=self.project, instance_id=self.iid)
        self.binding = RootBinding.register('fixture-project' if pool is None else 'fixture-project:'+self.project, self.store.root)
        if pool is None:
            runtime = self.root/'runtime'; runtime.mkdir()
            self.pool = Pool(RootBinding.register('fixture-runtime', runtime), 'synthetic-test-pool', [self.binding])
        else:
            # This is the trusted fixture assembly channel, outside commands
            # and project data. Registration still checks the native prefix.
            self.pool = pool
            self.pool.roots[self.binding.binding_id] = self.binding
        self.genesis = self.setup.heads[0]
        self.key = self.pool.register(self.binding.binding_id, genesis=self.genesis, project=self.project)
        self.registry = AuthorityRegistry(clock=lambda: NOW)
        self.storage = CombinedControlStorage(self.store, CombinedNativeBridge(self.store, setup=self.setup))
        self.control = Control(self.storage, self.pool, self.registry, binding_id=self.binding.binding_id)
        self.serial = 0
        self.producer = self.blob('producer', b'SYNTHETIC_TEST_ONLY original producer', raw=True)
        self.binding_ref = self.blob('runner-binding', b'SYNTHETIC_TEST_ONLY bounded execution binding', raw=True)
        self.operator = self.session(human=True)
        self.service = self.session()
        self.boundary = Boundary(); self.storage.register_boundary(self.boundary, self.scope)
        if activate:
            profile = D.record('PROFILE', profile='SYNTHETIC_TEST_ONLY', project_id=self.project,
                genesis_commit=self.genesis, setup_head=self.setup.heads[-1], resource_policy='COMPAT_8_20_SURVEY1', pool_id=self.pool.pool_id)
            self.activation = self.command('ACTIVATED', dict(profile_ref=self.blob('profile', combined_profile(profile)), owner_id='fixture-owner', backend_binding_ref=None))
            self.control.apply(self.activation, self.operator)


    def command(self,action,payload):
        value=super().command(action,payload)
        value['schema']=EVENT_SCHEMA
        return value

    def session(self,**kwargs):
        kwargs.setdefault('actions',set(D.PAYLOAD_FIELDS)|set(FAST_PAYLOAD_FIELDS)|{'RECOVER_RECEIPT'})
        return super().session(**kwargs)

    def ingress(self,request_id):
        return self.registry.register_fast_ingress(request_id=request_id,scope=self.scope,
            root_binding_id=self.binding.binding_id,principal_ref=self.producer,authn_evidence_ref=self.producer,
            authority_ref=self.producer,actions={'FAST_PROPOSAL_CAPTURED','RECOVER_RECEIPT'},
            issued_at=NOW-timedelta(minutes=1),expires_at=NOW+timedelta(hours=1),
            owner_id=None,human=False,proposal_only=False,request_ids={request_id})

    def fast_arguments(self,label,session,**extra):
        value=self.command('FAST_DELTA_APPLIED',{})
        return {k:v for k,v in value.items() if k not in {'schema','type','payload'}} | {'session':session} | extra

    def capture_fast(self,worker,delta):
        service=self.store.fastmath_service()
        context=FastReadContext(self.project,self.iid,worker['task']['mission_id'],worker['task']['task_id'])
        self.storage.fast.bind_read_context(context,self.service)
        prepared=service.prepare_delta(delta,read_context=context,as_of_commit=self.store.read_snapshot()['knowledge_commit'])
        output,raw=self.capture(worker,canonical({'payload':{'fast_delta':delta}}))
        state=self.store.read_snapshot();request=state['requests'][worker['spec'].request_id]
        wrapper=next(state['execution_events'][r] for r in request['admission']['receipt_ids']
                     if state['execution_events'][r].get('receipt_kind')=='CAPTURE')
        args=self.fast_arguments('capture',self.ingress(worker['spec'].request_id),
            request_id=worker['spec'].request_id,capture_ref=output,receipt_ref=wrapper['receipt_ref'])
        result=service.capture_delta(prepared,**args)
        return prepared,result,args

    def apply_fast(self,proposal,main):
        session=self.session(acting_request_id=main['spec'].request_id)
        args=self.fast_arguments('apply',session,grant_ref=self.grant(),manifest_ref=main['manifest_ref'])
        return self.store.fastmath_service().commit_delta(proposal,**args),args

    def running_pair(self,*,communication=False,main_status='SENT'):
        self.authorize(8,attempts=8,communication=communication)
        main=self.prepare();self.send(main)
        self.dispatch(main,'SEND_OUTCOME_UNKNOWN' if main_status=='UNKNOWN' else main_status)
        self.dispatch_workers(main,1)
        worker=self.prepare(actor='WORKER');self.slot(worker);self.send(worker);self.dispatch(worker,'SENT')
        return main,worker

    def reopen(self):
        self.store=Store(self.store.root)
        self.storage=CombinedControlStorage(self.store,CombinedNativeBridge(self.store))
        self.control=Control(self.storage,self.pool,self.registry,binding_id=self.binding.binding_id)
        self.storage.register_boundary(self.boundary,self.scope)
        return self.store.read_snapshot()

    def restart_read(self):
        run=subprocess.run([sys.executable,'-B','/source/scripts/fastmath_sandbox.py','--reopen',str(self.store.root)],
            capture_output=True,text=True,timeout=30,check=True)
        return json.loads(run.stdout)


def six_entries(state,task,*,argument_ref=None,support_ids=()):
    iid=task['instance_id'];instance=state['instances'][iid];target=instance['target_ref']
    scope=dict(project_id=state['project_id'],instance_id=iid,mission_id=task['mission_id'])
    author=dict(request_id=task['request_id'],attempt_id=task['attempt_key'])
    slot=native_projection(state,target,argument_ref)
    def make(oid,kind,payload,deps=()):
        return make_revision(object_id=oid,kind=kind,scope=scope,payload=payload,
            body='Synthetic explanatory prose. No independent mathematical qualification.',
            author_attempt=author,original_target_ref=target,d0_ref=instance.get('discovery_scope'),
            reason='First explicit bounded synthetic revision.',dependencies=deps)
    module=make('module','KnowledgeModule',dict(title='Addition interface',obstacle='Exact target remains to be supported.',
        use='Invoke only with stated hypotheses.',input_refs=[target],output_ref=target,mechanism='Preserve the exact native claim.',
        boundaries='Only the native scope.',project_use='Organize the original question.',source_refs=list(state['sources']),
        open_conditions=slot['argument_fields']['open_conditions'] if argument_ref else [],claim_slots={'result':slot},variable_annotations=[]),[target])
    transition=make('transition','Transition',dict(title='Open connection',start_ref=target,end_ref=target,relation='UNKNOWN',direction='OPEN',
        shared_context_refs=[],mechanism='No implication has been established.',missing_interface='An independent exact argument is missing.',
        probe_refs=[],evidence_refs=[],explanatory_order=0,claim_slots={'arrow':slot},variable_annotations=[]),[target])
    frontier=make('probe','Frontier/Probe',dict(title='Bounded missing argument probe',unknown_ref=target,
        question='Which exact native support is available?',frozen_input_refs=[target],
        outcomes=[dict(outcome='NO_PROGRESS',consequence='Retain the original open question.',evidence_refs=[])],
        stop='Stop after this bounded examination.',retry_basis='A new exact source or argument is required.',task_ref=None,claim_slots={}),[target])
    roadmap=make('map','ResearchMap',dict(title='Current open map',node_refs=[module['ref']],transition_refs=[transition['ref']],routes=[],
        and_obligations=[],or_alternatives=[],shared_context_refs=[],witness_constraints=[],parameter_constraints=[],
        gaps=['Exact support is open.'],revision_cause='Initial organization.',affected_decisions=[],next_probe_or_wait='Wait for exact support.',
        navigation_cycles=[['module','module']],claim_slots={}),[module['ref'],transition['ref']])
    reader=make('reader','ReaderProfile',dict(title='Reader entry points',general_prerequisites=['Integer addition'],
        specialty_entry_points=['Exact statement'],project_definitions=['Original target'],explanation_depth='EVIDENCE'))
    req=(deepcopy(state['supports'][support_ids[0]]['consumer_requirement']) if support_ids else
         A.requirement('PROOF_SUPPORT',[dict(target_ref=target,locators=[state['records'][target]['data']['statement_locator']],aspects=['proof'])]))
    binding=make('binding','RefinementBinding',dict(upper_revision_ref=module['ref'],upper_claim_slot='result',claim_fingerprint=claim_fingerprint(slot),
        statement_ref=target,argument_ref=argument_ref,context_refs=sorted(slot['context_fields']),source_refs=list(state['sources']),
        support_ids=list(support_ids),requirement=req,policy_digest=sha(canonical(req)),required_review_scope=req['required_scope'],
        open_conditions=(slot['argument_fields'] or {}).get('open_conditions',[]),applicability_refs=[],invalidation_refs=list(support_ids),
        version_provenance=author),[module['ref'],target])
    return [module,transition,frontier,roadmap,reader,binding]


def delta_for(state,task,entries,*,links=(),empty_reason=None):
    needed=required_guards(state,entries,links)
    instance=state['instances'][task['instance_id']]
    return dict(schema='pmrh.fast-delta/1',scope=dict(project_id=state['project_id'],instance_id=task['instance_id'],mission_id=task['mission_id']),
        original_target_ref=instance.get('target_ref'),d0_ref=instance.get('discovery_scope'),request_id=task['request_id'],attempt_id=task['attempt_key'],
        input_commit=task['knowledge_commit'],capture_payload_path='/payload/fast_delta',
        expected_selected={e['body']['object_id']:e['body']['predecessor'] for e in entries},
        read_guards=[guard(state,c,r) for c,r in sorted(needed)],revision_entries=deepcopy(entries),same_claim_links=list(links),
        reason='Bounded synthetic proposal retaining original input.',empty_reason=empty_reason)


def scientific_worker(h,main,label,*,role='RESEARCH',inputs=None):
    """One original authorized stage request, without fabricated task state."""
    h.dispatch_workers(main,1,label=label,stage='P4',role=role,
        duty='VERIFY' if role=='PROOF' else 'ESTABLISH',inputs=inputs)
    worker=h.prepare(actor='WORKER');h.slot(worker);h.send(worker);h.dispatch(worker,'SENT')
    return worker


def admit_scientific_response(h,worker,envelope):
    """Original sealed bytes and public control admission own every native map."""
    capture,raw=h.capture(worker,canonical(envelope))
    receipt=h.control.apply(h.command('SCIENCE_ADMITTED',dict(
        request_id=worker['spec'].request_id,capture_ref=capture)),h.service)
    h.observation(worker,'TERMINATED')
    h.storage.release_slot(h.control,h.scope,worker['spec'].request_id,h.service)
    return dict(capture=capture,raw=raw,receipt=receipt)


def native_qualified_pair(h, *, calls=8):
    """Two native support paths, each reviewed by a distinct original request.

    Only synthetic responses are authored. All supports, review executions and
    qualifications are derived by the original native capture/admission path.
    The return value is references/evidence, never a replacement reader state.
    """
    from research_studio import demo,input_delivery
    from research_studio.task_tools import TaskTools
    h.authorize(calls,attempts=8,communication=True)
    main=h.prepare();h.send(main);h.dispatch(main,'SENT')
    author=scientific_worker(h,main,'source09-two-arguments')
    envelope=json.loads(demo.response(author['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
    original=envelope['payload']['operations'][0]
    operations=[]
    for index in range(2):
        op=deepcopy(original);op['local_key']='argument'+str(index)
        op['body']+=' Independent synthetic support branch '+str(index)+'.'
        op['data']['steps'][0]['locator']=K.locator(op['body'])
        operations.append(op)
    envelope['payload']['operations']=operations
    for effect in envelope['payload']['obligation_effects']:
        effect['evidence_refs']=['local:'+op['local_key'] for op in operations]
    authored=admit_scientific_response(h,author,envelope)
    state=h.store.read_snapshot();target=state['instances'][h.iid]['target_ref']
    paths=[];deliveries=[]
    for support in sorted(state['supports'].values(),key=lambda x:x['argument_ref']):
        argument=support['argument_ref'];sid=support['support_id']
        # MAIN must actually receive the new exact body before dispatching it.
        tools=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id)
        command=h.command('COMMUNICATION_APPLIED',{})
        frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
        with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
            delivery,response=tools.call('knowledge_get',{'ref':argument})
        if response['isError']:raise AssertionError(response)
        command=h.command('COMMUNICATION_APPLIED',{})
        frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
        with h.control.native_context(h.service,**frame):
            input_delivery.confirm(h.store,main['spec'].request_id,main['spec'].execution_id,delivery)
        deliveries.append((delivery,response))
        review=scientific_worker(h,main,'source09-review-'+str(len(paths)),role='PROOF',inputs=[target,argument])
        requirement=review['task']['required_assurance']
        envelope=json.loads(demo.response(review['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
        op=envelope['payload']['operations'][0]
        op['body']='Synthetic positive review of exactly the frozen statement and argument; not evidence for real mathematics.'
        op['data'].update(verdict='SUPPORTED_WITHIN_SCOPE',unchecked=[],checked=[
            dict(ref=row['target_ref'],locators=row['locators'],aspect=aspect,
                 **{key:row[key] for key in A.SCOPE_META})
            for row in requirement['required_scope'] for aspect in row['aspects']])
        admitted=admit_scientific_response(h,review,envelope)
        paths.append(dict(support_id=sid,argument_ref=argument,review=review,
            requirement=requirement,admitted=admitted))
    return dict(main=main,author=author,authored=authored,target=target,paths=paths,deliveries=deliveries)


def semantic_fixture():
    """S1 only: genuine native codecs/evaluator on explicit synthetic evidence."""
    from tests.test_final_kernel import Fixture,statement,argument
    f=Fixture();target=f.add(statement('For every integer x, x + 0 = x.'))
    arg=f.add(argument(target,records=f.s['records'],blob_get=f.get))
    req=A.normalize_requirement(A.requirement('PROOF_SUPPORT',[dict(target_ref=arg,locators=[],aspects=['proof'])]),f.s,f.get)
    digest=sha(canonical(req));sid='SUP-synthetic'
    f.s['supports'][sid]=dict(support_id=sid,statement_ref=target,argument_ref=arg,premise_support_refs=[],open_assumption_refs=[],
        qualification_refs=['Q-synthetic'],author_task_id='author',author_execution_event='author-event',consumer_requirement=req,policy_digest=digest)
    checked=[dict(ref=row['target_ref'],locators=row['locators'],aspect='proof',**{k:row[k] for k in A.SCOPE_META}) for row in req['required_scope']]
    assessment=f.add(K.make_record('Assessment','Synthetic independent exact-scope review.',dict(review_kind='PROOF',target_refs=[arg],checked=checked,
        unchecked=[],verdict='SUPPORTED_WITHIN_SCOPE',findings=[],scope_context_refs=[]),records=f.s['records'],blob_get=f.get))
    f.s['qualifications']['Q-synthetic']=dict(assessment_ref=assessment,review_execution_event='review-event',input_manifest_hash='input',
        target_revision_hashes=[arg],actual_checked_scope=deepcopy(req['required_scope']),evidence_origin='MODEL_CAPTURE',policy_digest=digest,integrity_valid=True)
    f.s['review_executions']['review-event']=dict(event_id='review-event',task_id='independent',role='PROOF',input_manifest_hash='input',
        target_revision_hashes=[arg],independent=True,excluded_verdicts=True,synthetic=True,integrity_valid=True)
    f.s.update(project_id='P-synthetic',instances={'I-synthetic':dict(instance_id='I-synthetic',target_ref=target,current_mission_id='M-synthetic')},
               missions={'M-synthetic':dict(instance_id='I-synthetic')})
    task=dict(task_id='worker',request_id='request',attempt_key='attempt',instance_id='I-synthetic',mission_id='M-synthetic',knowledge_commit='a'*64)
    return f,task,target,arg,sid


def add_exact_path(f,target,body,mode='PROOF',payload=None,premises=(),*,purpose='PROOF_SUPPORT'):
    """S1: create a new normalized consumer before its independent review.

    No legacy review is relabeled as whole-target evidence. This is native
    codec/evaluator unit coverage, not a persisted scientific acceptance.
    """
    data=dict(conclusion_ref=target,premise_bindings=list(premises),steps=[],
        discharged_assumptions=[],open_conditions=[],witness_bindings=[],mode=mode,mode_payload=payload or {})
    arg=f.add(K.make_record('Argument',body,data,[],records=f.s['records'],blob_get=f.get))
    aspect='applicability' if purpose=='APPLICABILITY' else 'proof'
    req=A.normalize_requirement(A.requirement(purpose,
        [dict(target_ref=arg,locators=[],aspects=[aspect])]),f.s,f.get)
    digest=sha(canonical(req));sid='SUP-'+arg;event='REVIEW-'+arg;qid='Q-'+arg
    f.s['supports'][sid]=dict(support_id=sid,statement_ref=target,argument_ref=arg,
        premise_support_refs=[p['support_ref'] for p in premises if p['support_ref']],
        open_assumption_refs=[],qualification_refs=[qid],author_task_id='AUTHOR',
        author_execution_event='AUTHOR-E',consumer_requirement=req,policy_digest=digest)
    checked=[dict(ref=r['target_ref'],locators=r['locators'],aspect=aspect,
        **{k:r[k] for k in A.SCOPE_META}) for r in req['required_scope']]
    slot=req['review_slots'][0]
    assessment=f.add(K.make_record('Assessment','Fresh independent review of the exact whole argument.',
        dict(review_kind=slot['review_kind'],target_refs=[arg],checked=checked,unchecked=[],
             verdict='SUPPORTED_WITHIN_SCOPE',findings=[],scope_context_refs=[]),
        records=f.s['records'],blob_get=f.get))
    f.s['qualifications'][qid]=dict(assessment_ref=assessment,review_execution_event=event,
        input_manifest_hash='synthetic-exact-input',target_revision_hashes=[arg],
        actual_checked_scope=deepcopy(req['required_scope']),evidence_origin='MODEL_CAPTURE',
        policy_digest=digest,integrity_valid=True)
    f.s['review_executions'][event]=dict(event_id=event,task_id=event,role=slot['allowed_roles'][0],
        input_manifest_hash='synthetic-exact-input',target_revision_hashes=[arg],independent=True,
        excluded_verdicts=True,synthetic=True,integrity_valid=True,policy_digest=digest)
    return arg,sid,req


def fm13_two_batch_pilot():
    """Two actual native /2 public admission batches, never full4097.

    Transparent wrappers measure confined metadata and body budgets. Consumer
    phases separate query/delivery costs from fixture preparation. Snapshot/
    history observations after each phase are included in totals, not in that
    phase's counters. No read return, cap, admission or authority is replaced.
    """
    import resource,time,tempfile
    from contextlib import contextmanager
    from unittest.mock import patch
    from pmrh.adapters.storage import io as I
    from research_studio import changes,demo,knowledge_access as Q
    from research_studio.task_tools import TaskTools
    counts=dict(metadata_calls=0,metadata_attempts_spent=0,metadata_successful_bytes=0,
        body_calls=0,body_attempts_spent=0,body_bytes_read=0,body_verified_bytes=0,
        integrity_probe_attempts=0,integrity_probe_bytes=0)
    original_read=I._ConfinedReader.read;original_body=I._ConfinedReader.read_verified_body
    def counted_read(self,*args,**kwargs):
        counts['metadata_calls']+=1;before=self.remaining_files
        try:
            result=original_read(self,*args,**kwargs)
            if result is not None:counts['metadata_successful_bytes']+=len(result)
            return result
        finally:counts['metadata_attempts_spent']+=before-self.remaining_files
    def counted_body(self,*args,**kwargs):
        counts['body_calls']+=1;budget=kwargs['budget']
        before=(budget.remaining_files,budget.remaining_bytes,budget.integrity_probe_attempts,budget.integrity_probe_bytes)
        try:
            result=original_body(self,*args,**kwargs)
            counts['body_verified_bytes']+=result.size
            return result
        finally:
            counts['body_attempts_spent']+=before[0]-budget.remaining_files
            counts['body_bytes_read']+=before[1]-budget.remaining_bytes
            counts['integrity_probe_attempts']+=budget.integrity_probe_attempts-before[2]
            counts['integrity_probe_bytes']+=budget.integrity_probe_bytes-before[3]
    started=time.monotonic();rows=[];phases=[];status='FAIL';h=None
    with tempfile.TemporaryDirectory() as tmp:
        @contextmanager
        def measured(label):
            begin=time.monotonic();before=dict(counts)
            try:yield
            finally:
                row=dict(phase=label,elapsed_seconds=time.monotonic()-begin,
                    reads={k:counts[k]-before[k] for k in counts},
                    peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
                files=[f for f in Path(tmp).rglob('*') if f.is_file()]
                row.update(logical_disk_bytes=sum(f.stat().st_size for f in files),
                    allocated_disk_bytes=sum(f.stat().st_blocks*512 for f in files))
                if h is not None:
                    try:
                        history=h.store.history();state=Store(h.store.root).read_snapshot()
                        row.update(published_commits=len(history),head=state['knowledge_commit'],
                            record_count=len(state['records']),request_count=len(state['requests']),
                            source_count=len(state['sources']))
                    except Exception as exc:row['observation_error']=repr(exc)
                phases.append(row)
        try:
            with patch.object(I._ConfinedReader,'read',counted_read),patch.object(I._ConfinedReader,'read_verified_body',counted_body):
                with measured('public_native_control_setup'):
                    h=OriginalHarness(tmp);h.authorize(6,attempts=6,communication=True)
                    main=h.prepare();h.send(main);h.dispatch(main,'SENT')
                    h.dispatch_workers(main,2,label='fm13-pilot',stage='P1',role='PLAN')
                    before=set(h.store.read_snapshot()['records'])
                for batch in range(2):
                    with measured('public_native_capture_admission_batch_'+str(batch+1)):
                        worker=h.prepare(actor='WORKER');h.slot(worker);h.send(worker);h.dispatch(worker,'SENT')
                        envelope=json.loads(demo.response(worker['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
                        payload=envelope['payload'];assert envelope['payload_kind']=='KNOWLEDGE_CHANGE'
                        template=payload['operations'][0];assert template['kind']=='Context'
                        operations=[]
                        for n in range(64):
                            body='Synthetic pilot convention batch '+str(batch)+' item '+str(n)+'. No mathematical qualification is asserted.'
                            loc=K.locator(body)
                            operations.append(dict(op='NEW',local_key=template['local_key'] if n==0 else 'pilot_'+str(n),
                                kind='Context',context_refs=[],body=body,data=dict(
                                definitions=[dict(key='pilot_definition_'+str(batch)+'_'+str(n),locator=loc)],
                                objects=[],assumptions=[],quantifiers=[],conventions=[],parent_context_refs=[])))
                        payload['operations']=operations;raw=canonical(envelope)
                        capture,_=h.capture(worker,raw)
                        state=h.store.read_snapshot()
                        validated=changes.validate_response(worker['task'],state,raw,'live',h.store.read_blob)
                        frame=h.command('SCIENCE_ADMITTED',dict(request_id=worker['spec'].request_id,capture_ref=capture))
                        args={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                        # Existing WORKER admission authenticates the current service
                        # and original reservation/spec; delegated MAIN extras must be None.
                        with h.control.native_context(h.service,**args):h.store.commit(validated)
                        state=Store(h.store.root).read_snapshot();added=set(state['records'])-before
                        assert len(added)==64*(batch+1)
                        assert state['requests'][worker['spec'].request_id]['acceptance_state']=='ACCEPTED'
                        assert sum(f.stat().st_size for f in Path(tmp).rglob('*') if f.is_file())<=8*1024**3
                    rows.append(dict(batch=batch+1,candidate_KR=len(added),measurement_phase=phases[-1]['phase']))
                reopened=Store(h.store.root);seen=set();cursor=None;page_number=0
                while True:
                    args={'query':['Synthetic pilot convention'],'kind':['Context'],'instance_id':[h.iid],'limit':['20']}
                    if cursor:args['continuation']=[cursor]
                    page_number+=1
                    with measured('web_tool_search_page_'+str(page_number)):
                        page=Q.web_tool(reopened,'search',args)
                    seen.update(r['ref'] for r in page['results']);cursor=page['continuation']
                    if not cursor:break
                assert seen==added
                tools=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id)
                frame=h.command('COMMUNICATION_APPLIED',{'native_event':{}})
                args={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with measured('TaskTools_get_and_persisted_delivery'):
                    with h.control.native_context(h.service,**args,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                        delivery,response=tools.call('knowledge_get',{'ref':sorted(added)[-1]})
                assert not response['isError'] and delivery is not None
                value=json.loads(response['content'][0]['text'])['result'];assert value['ref'] in added
                assert h.store.history()[-1][1]['schema']=='pmrh.commit/2'
                status='PILOT_ASSERTIONS_PASSED_NOT_FM13_ACCEPTANCE'
        finally:
            files=[f for f in Path(tmp).rglob('*') if f.is_file()]
            print('DEV11_FM13_PILOT '+json.dumps(dict(status=status,profile='pmrh.commit/2',
                batches_completed=len(rows),batches=rows,phases=phases,maximum_batches=2,maximum_records_per_batch=64,
                elapsed_seconds=time.monotonic()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                logical_disk_bytes=sum(f.stat().st_size for f in files),allocated_disk_bytes=sum(f.stat().st_blocks*512 for f in files),
                read_counters=counts,full4097='HELD_NOT_EXECUTED',provider_calls=0,
                measurement_scope='Confined-reader counters only; phase inspection overhead included in total counters, not consumer deltas.',
                limitation='Native /2 pilot only; no all-native/combined/4097 or full TaskTools paging claim.')),flush=True)



def native_running_main(root, *, max_calls=3):
    """Public native synthetic setup shared by the pilot and authority pairs."""
    from tests.devpr05.fixtures import scientific_policy
    from research_studio.engine import Engine
    from research_studio import demo,execution,tasks
    engine=Engine();store=engine.create(Path(root)/'native',demo.ARITHMETIC,synthetic=True)
    target=next(iter(store.read_snapshot()['records']))
    iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
    policy=scientific_policy();policy['communication']={}
    engine.start_round(store,iid,'Synthetic native retrieval fixture only.',max_calls=max_calls,
        max_workers=1,max_research_attempts=1,allow_reports=False,policy=policy)
    prepared=engine.prepare(store,iid)['prepared'];assert len(prepared)==1
    task=tasks.load(store,prepared[0]['task_id']);assert task['actor_kind']=='MAIN'
    assert task['model_policy']['reasoning_effort']=='ultra'
    reserved=execution.reserve(store,task['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
    store.commit_execution(execution.event('SENT',dict(request_id=task['request_id'],execution_id=reserved['execution_id'])))
    return engine,store,iid,task,reserved['execution_id']


def fm13_all_native_two_batch_pilot():
    """Public all-native two64KR pilot; no /1,/2/combined or4097 claim."""
    return _fm13_all_native_case()


def fm13_all_native_full_case():
    """Controller-only retained 65x64 case; nondiscovered, no tmpfs selector.

    Run only after the separate frozen-candidate/resource/probe gates, with
    the approved exclusive disk mounted at /tmp/tests. Never automatically retry.
    """
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path('/tmp/tests')
    root=Path('/tmp/tests/fm13-full');root.mkdir(exist_ok=False)
    return _fm13_all_native_case(batch_count=65,retained_root=root)


def _fm13_all_native_case(*,batch_count=2,retained_root=None):
    """Shared public workflow; only the two-batch pilot or corrected65x64 case.

    Reader objects are retained only for serial/profiling identity, never as
    data caches. Wrappers delegate original calls/returns/errors unchanged.
    Observation overhead has its own phase and is not charged to consumers.
    """
    import resource,time,tempfile
    from contextlib import contextmanager,nullcontext
    from unittest.mock import patch
    from pmrh.adapters.storage import io as I
    from pmrh.adapters.storage.native_format import COMMIT_SCHEMA
    from research_studio import changes,demo,execution,scheduler,tasks,knowledge_access as Q
    from research_studio.task_tools import TaskTools
    from pmrh.domain.primitives import PMRSError
    from research_studio import input_delivery
    full=retained_root is not None
    assert (batch_count,full) in {(2,False),(65,True)}
    readers={};phase='setup';query_role=None;phases=[];batches=[];store=None
    status='FAIL';task_response=None;started=time.monotonic();groups=[];paging={};negatives=[]
    read=I._ConfinedReader.read;body_read=I._ConfinedReader.read_verified_body
    get=Q.get;search=Q.search
    def budget(reader):return dict(files=reader.remaining_files,bytes=reader.remaining_bytes)
    def segment(reader,kind,before):
        # Strong object keys prevent id reuse without changing reader state.
        if reader not in readers:
            readers[reader]=dict(serial=len(readers)+1,root=str(reader.root),initial_metadata_budget=budget(reader),segments={})
        identity=(phase,query_role or 'other_validation_or_delivery',kind)
        segments=readers[reader]['segments']
        if identity not in segments:
            segments[identity]=dict(phase=phase,role=identity[1],kind=kind,budget_before=before,
                budget_after=before,calls=0,attempts_spent=0,bytes_spent=0,successful_bytes=0,
                integrity_probe_attempts=0,integrity_probe_bytes=0,paths={})
        return segments[identity]
    def account(row,path,before,after,size,error,probes=(0,0)):
        row['budget_after']=after;row['calls']+=1
        row['attempts_spent']+=before['files']-after['files'];row['bytes_spent']+=before['bytes']-after['bytes']
        row['successful_bytes']+=size;row['integrity_probe_attempts']+=probes[0];row['integrity_probe_bytes']+=probes[1]
        item=row['paths'].setdefault(path,dict(attempts=0,attempts_spent=0,successful_bytes=0,first_successful_bytes=None,errors=[]))
        item['attempts']+=1;item['attempts_spent']+=before['files']-after['files'];item['successful_bytes']+=size
        if error is None and item['first_successful_bytes'] is None:item['first_successful_bytes']=size
        if error is not None:item['errors'].append(error)
    def counted_read(reader,relative,*args,**kwargs):
        before=budget(reader);row=segment(reader,'metadata',before);size=0;error=None
        try:
            result=read(reader,relative,*args,**kwargs)
            size=len(result) if result is not None else 0
            return result
        except BaseException as exc:error=repr(exc);raise
        finally:account(row,relative,before,budget(reader),size,error)
    def counted_body(reader,digest,*,budget,**kwargs):
        before=dict(files=budget.remaining_files,bytes=budget.remaining_bytes)
        row=segment(reader,'body',before);size=0;error=None
        probes=(budget.integrity_probe_attempts,budget.integrity_probe_bytes)
        try:
            result=body_read(reader,digest,budget=budget,**kwargs);size=result.size
            return result
        except BaseException as exc:error=repr(exc);raise
        finally:
            after=dict(files=budget.remaining_files,bytes=budget.remaining_bytes)
            account(row,'blobs/'+digest,before,after,size,error,
                (budget.integrity_probe_attempts-probes[0],budget.integrity_probe_bytes-probes[1]))
    def query_wrapper(name,call):
        def measured_query(*args,**kwargs):
            nonlocal query_role
            previous=query_role;query_role=name
            try:return call(*args,**kwargs)
            finally:query_role=previous
        return measured_query
    def reader_rows():
        result=[]
        for reader,info in readers.items():
            segments=[]
            for row in info['segments'].values():
                detail={k:v for k,v in row.items() if k!='paths'} if full else row
                segments.append(dict(detail,unique_paths=len(row['paths']),
                    repeated_attempts=row['calls']-len(row['paths']),
                    unique_successful_bytes=sum(p['first_successful_bytes'] or 0 for p in row['paths'].values())))
            result.append(dict(serial=info['serial'],root=info['root'],initial_metadata_budget=info['initial_metadata_budget'],
                final_metadata_budget=budget(reader),segments=segments))
        return result
    def aggregates(rows):
        result={}
        for reader in rows:
            for row in reader['segments']:
                key=(row['phase'],row['role'],row['kind'])
                group=result.setdefault(key,dict(phase=key[0],role=key[1],kind=key[2],reader_serials=[],
                    calls=0,attempts_spent=0,bytes_spent=0,successful_bytes=0,
                    sum_per_reader_unique_paths=0,repeated_attempts=0,unique_successful_bytes=0,
                    integrity_probe_attempts=0,integrity_probe_bytes=0))
                group['reader_serials'].append(reader['serial'])
                for key in ('calls','attempts_spent','bytes_spent','successful_bytes','repeated_attempts',
                            'unique_successful_bytes','integrity_probe_attempts','integrity_probe_bytes'):
                    group[key]+=row[key]
                group['sum_per_reader_unique_paths']+=row['unique_paths']
        return list(result.values())
    with (nullcontext(str(retained_root)) if full else tempfile.TemporaryDirectory()) as tmp:
        host_pool=Path.home()/'.local/state/pmrs/host-runtime-4.2.2'
        assert Path.home().resolve()==Path('/tmp/home') and host_pool.resolve().is_relative_to('/tmp/home')
        assert Path(tmp).resolve().is_relative_to('/tmp/tests') and not Path('/home').exists()
        @contextmanager
        def measured(label):
            nonlocal phase
            previous=phase;phase=label;begin=time.monotonic()
            before=store._head()['sequence'] if store is not None else 0
            try:yield
            finally:
                elapsed=time.monotonic()-begin;phase='observation_after_'+label
                row=dict(phase=label,elapsed_seconds=elapsed,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
                files=[f for f in Path(tmp).rglob('*') if f.is_file()]
                row.update(logical_disk_bytes=sum(f.stat().st_size for f in files),allocated_disk_bytes=sum(f.stat().st_blocks*512 for f in files))
                observed=store
                if observed is None and (Path(tmp)/'native/HEAD').is_file():observed=Store(Path(tmp)/'native')
                if observed is not None:
                    try:
                        history=observed.history();state=Store(observed.root).read_snapshot()
                        row.update(published_commits=len(history),commit_increment=state['_head']['sequence']-before,schemas=sorted({r['schema'] for _,r in history}),
                            head=state['knowledge_commit'],record_count=len(state['records']),source_count=len(state['sources']),request_count=len(state['requests']))
                        assert history and all(r['schema']==COMMIT_SCHEMA=='pmrs.commit/4.2.2' for _,r in history)
                    except Exception as exc:row['observation_error']=repr(exc)
                phases.append(row);phase=previous
                if full and ('dispatch_group_' in label or 'capture_commit_batch_' in label):
                    print('DEV11_FM13_PROGRESS '+json.dumps(row),flush=True)
        def reserve_sent(task):
            result=execution.reserve(store,task['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
            store.commit_execution(execution.event('SENT',dict(request_id=task['request_id'],execution_id=result['execution_id'])))
            return result['execution_id']
        def dispatch_group(first,count):
            assert 1<=count<=8
            state=store.read_snapshot();st=strategy.current(state,iid)
            proposal=dict(schema='pmrs.strategy-proposal/1',base_strategy_revision=st['revision'],
                trigger_refs=list(st['pending_trigger_refs']),route_updates=[],input_plan_proposals=[],
                work_items=[dict(key='native_pilot_'+str(n),stage_id='P1',role='PLAN',purpose='DEFAULT',obligation_type='MATERIAL',
                    question='Inspect synthetic convention batch '+str(n)+'.',success_criterion='Record only exact candidate conventions and open assumptions.',
                    target_refs=[target],input_refs=[target],source_refs=[],depends_on=[],route_key='',communication_group=None) for n in range(first,first+count)],
                progress_account=dict(summary='Bounded synthetic candidate group; no completeness claim.' if full else 'Two bounded synthetic candidate batches.',record_refs=[],remaining_difficulties=['No mathematical qualification.'],
                    scope_limitations=['SYNTHETIC_TEST_ONLY'],failed_or_unperformed=['Research not executed.'],covered_binding_ids=[],frontier_complete=False),
                direction_answers=[],next_action='CONTINUE',human_decision_needed=[],no_change_reason=None)
            key='native-full-group-'+str(first//8+1) if full else 'native-pilot-dispatch'
            receipt=strategy.dispatch_from_main(store,main['request_id'],proposal,key)
            persisted=Store(store.root).read_snapshot()['live_main_dispatches'][receipt['dispatch_id']]
            assert persisted['request_id']==main['request_id'] and persisted['proposal']==proposal
            groups.append(dict(group=first//8+1,first_batch=first+1,work_items=count,
                dispatch_id=receipt['dispatch_id'],receipt_sha256=sha(canonical(receipt)),head=store._head()))
        try:
            with patch.object(I._ConfinedReader,'read',counted_read),patch.object(I._ConfinedReader,'read_verified_body',counted_body), \
                 patch.object(Q,'get',query_wrapper('knowledge_get_query',get)),patch.object(Q,'search',query_wrapper('knowledge_search_query',search)):
                with measured('public_all_native_MAIN' if full else 'public_all_native_MAIN_and_two_worker_dispatch'):
                    engine,store,iid,main,main_execution=native_running_main(tmp,max_calls=batch_count+1)
                    target=store.read_snapshot()['instances'][iid]['target_ref']
                    if not full:dispatch_group(0,2)
                    initial=set(store.read_snapshot()['records'])
                if full:
                    tools=TaskTools(store,main['request_id'],main_execution)
                    for first in range(0,batch_count,8):
                        with measured('public_MAIN_dispatch_group_'+str(first//8+1)):
                            if first==8:
                                # Read and confirm the first live frontier update.
                                # Later CONTINUE proposals keep this observed basis
                                # explicitly incomplete; the public dispatcher
                                # validates current revision/triggers on every call.
                                did,response=tools.call('main_runtime_context',{})
                                assert did is not None and not response['isError'],response
                                current=store.read_snapshot();delivery=current['input_deliveries'][did]
                                assert store.read_blob(delivery['response_ref'])==canonical(response)
                                input_delivery.confirm(store,main['request_id'],main_execution,did)
                                assert Store(store.root).read_snapshot()['input_deliveries'][did]['confirmed']
                            dispatch_group(first,min(8,batch_count-first))
                for batch in range(batch_count):
                    with measured('public_all_native_capture_commit_batch_'+str(batch+1)):
                        plan=engine.schedule(store,iid);assert plan['selected'],plan['waits']
                        # Select one genuine scheduler candidate; commit_dispatch
                        # performs native task freeze/PREPARE and all checks.
                        plan['selected']=plan['selected'][:1]
                        made=scheduler.commit_dispatch(store,plan,policy=engine.policy(store,iid))['prepared'];assert len(made)==1
                        worker=tasks.load(store,made[0]['task_id']);assert worker.get('actor_kind')!='MAIN' and worker['stage_id']=='P1'
                        execution_id=reserve_sent(worker)
                        envelope=json.loads(demo.response(worker,store.read_snapshot(),blob_get=store.read_blob))
                        payload=envelope['payload'];template=payload['operations'][0];assert template['kind']=='Context'
                        operations=[]
                        for n in range(64):
                            body='Synthetic native pilot convention batch '+str(batch)+' item '+str(n)+'. No mathematical qualification.'
                            operations.append(dict(op='NEW',local_key=template['local_key'] if n==0 else 'native_pilot_'+str(n),kind='Context',context_refs=[],body=body,
                                data=dict(definitions=[dict(key='native_pilot_'+str(batch)+'_'+str(n),locator=K.locator(body))],
                                    objects=[],assumptions=[],quantifiers=[],conventions=[],parent_context_refs=[])))
                        payload['operations']=operations;raw=canonical(envelope)
                        execution.capture(store,worker['request_id'],raw,execution_id=execution_id)
                        state=store.read_snapshot();assert state['requests'][worker['request_id']]['capture_ref']==sha(raw)
                        validated=changes.validate_response(worker,state,raw,'live',store.read_blob)
                        store.commit(validated)
                        state=Store(store.root).read_snapshot();added=set(state['records'])-initial
                        assert len(added)==64*(batch+1)
                        assert state['requests'][worker['request_id']]['acceptance_state']=='ACCEPTED'
                        assert all(r['schema']==COMMIT_SCHEMA for _,r in store.history())
                        assert host_pool.resolve().is_relative_to('/tmp/home') and not host_pool.is_symlink()
                    batches.append(dict(batch=batch+1,candidate_KR=len(added),request_id=worker['request_id']))
                reopened=Store(store.root);seen=set();cursor=None;page_number=0
                pinned=reopened._head()['commit'];position=0;first_page=None
                ordered=sorted(ref for ref,row in reopened.read_snapshot()['records'].items() if row['kind']=='Context')
                if full:assert len(ordered)==4160 and set(ordered)==added and len(ordered)>4096
                while True:
                    page_number+=1;arguments={'query':['Synthetic native pilot convention'],'kind':['Context'],'instance_id':[iid],'limit':['20']}
                    if full:arguments['as_of_commit']=[pinned]
                    if cursor:arguments['continuation']=[cursor]
                    with measured('web_tool_search_page_'+str(page_number)):
                        page=Q.web_tool(reopened,'search',arguments)
                    if full:
                        assert page['as_of_commit']==pinned and page['start_position']==position
                        stop=page['next_position'];expected=ordered[position:stop]
                        assert 0<stop-position<=20 and stop<=len(ordered)
                        assert [r['ref'] for r in page['results']]==expected
                        assert [r['ref'] for r in page['scanned_ranges_this_call']]==expected
                        assert not seen.intersection(expected) and not any(page['categories'].values())
                        assert page['not_scanned_by_this_call']=={'before':[0,position],'after':[stop,len(ordered)]}
                        assert page['complete_for_this_call_scope'] is (position==0 and stop==len(ordered))
                        assert page['body_attempts_this_call']==len(expected)<=64
                        assert page['body_bytes_read_this_call']<=4*1024**3
                        assert page['integrity_probe_attempts_this_call']==len(expected) and page['integrity_probe_bytes_this_call']==0
                        for row in page['scanned_ranges_this_call']:
                            native=state['records'][row['ref']]
                            assert row['start']==0 and row['end']==len(store.read_blob(native['body_sha256']))
                            assert row['blob_hash']==native['body_sha256'] and row['unit']=='UTF8_BYTE'
                        if first_page is None:first_page=page
                        position=stop
                    seen.update(r['ref'] for r in page['results']);cursor=page['continuation']
                    if not cursor:break
                assert seen==added
                if full:
                    assert position==len(ordered) and page_number==208
                    paging.update(pinned_head=pinned,visible_contexts=len(ordered),pages=page_number,
                        contiguous_scanned_refs=len(seen),union_sha256=sha(canonical(sorted(seen))),late_index=4096,late_ref=ordered[4096])
                late_ref=ordered[4096] if full else sorted(added)[-1]
                tools=TaskTools(store,main['request_id'],main_execution)
                with measured('TaskTools_get_and_persisted_delivery'):
                    delivery,response=tools.call('knowledge_get',{'ref':late_ref,**({'as_of_commit':pinned} if full else {})})
                task_response=json.loads(response['content'][0]['text'])
                state=Store(store.root).read_snapshot()
                assert delivery is not None and store.read_blob(state['input_deliveries'][delivery]['response_ref'])==canonical(response)
                assert state['synthetic_test_only'] is True
                assert all(r['execution_kind']=='SYNTHETIC_TEST_ONLY' for r in state['requests'].values())
                assert all(r['schema']==COMMIT_SCHEMA=='pmrs.commit/4.2.2' for _,r in store.history())
                assert host_pool.resolve().is_relative_to('/tmp/home') and not host_pool.is_symlink()
                assert not response['isError'],task_response
                assert task_response['result']['ref'] in added
                if full:
                    result=task_response['result'];native=state['records'][late_ref]
                    assert result['ref']==late_ref and result['body'].encode()==store.read_blob(native['body_sha256'])
                    assert result['body_sha256']==native['body_sha256'] and result['read_scope']=='EXACT_BODY'
                    input_delivery.confirm(store,main['request_id'],main_execution,delivery)
                    assert Store(store.root).read_snapshot()['input_deliveries'][delivery]['confirmed']
                    paging.update(task_delivery_id=delivery,task_response_sha256=sha(canonical(response)))
                    # Human exposure is unchanged by this delivery. A HEAD
                    # change alone must not invalidate its historical cursor.
                    assert store._head()['commit']!=pinned
                    human={'query':['Synthetic native pilot convention'],'kind':['Context'],'instance_id':[iid],
                        'limit':['20'],'as_of_commit':[pinned]}
                    with measured('full_cursor_and_current_permission_pairs'):
                        continued=Q.web_tool(Store(store.root),'search',{**human,'continuation':[first_page['continuation']]})
                        assert [r['ref'] for r in continued['results']]==ordered[20:40] and continued['as_of_commit']==pinned
                        import base64
                        wire=json.loads(base64.urlsafe_b64decode(first_page['continuation'][3:]))
                        def encoded(value):return 'k1.'+base64.urlsafe_b64encode(canonical(value)).decode()
                        # An offset attests no earlier scan and grants no rights.
                        navigated=Q.web_tool(Store(store.root),'search',{**human,'limit':['1'],
                            'continuation':[encoded({**wire,'position':4096})]})
                        assert navigated['results'][0]['ref']==late_ref
                        assert navigated['not_scanned_by_this_call']['before']==[0,4096]
                        assert navigated['start_position']==4096 and navigated['next_position']==4097
                        assert navigated['complete_for_this_call_scope'] is False
                        def denied(label,call,codes):
                            try:call()
                            except PMRSError as exc:
                                assert exc.code in codes,(label,str(exc));negatives.append(dict(check=label,error=str(exc)))
                            else:raise AssertionError(label+' unexpectedly authorized')
                        denied('different_query',lambda:Q.web_tool(Store(store.root),'search',
                            {**human,'query':['different'],'continuation':[first_page['continuation']]}),{'KNOWLEDGE_QUERY_INVALID'})
                        denied('wrong_instance',lambda:Q.web_tool(Store(store.root),'search',
                            {**human,'instance_id':['foreign'],'continuation':[first_page['continuation']]}),{'INSTANCE_UNKNOWN','KNOWLEDGE_QUERY_INVALID'})
                        for field in ('query_digest','scope_digest','exposure_digest'):
                            forged=encoded({**wire,field:'0'*64})
                            denied('tampered_'+field,lambda:Q.web_tool(Store(store.root),'search',
                                {**human,'continuation':[forged]}),{'KNOWLEDGE_QUERY_INVALID'})
                        active=Q.search(Store(store.root),'Synthetic native pilot convention',kind='Context',task=main,limit=1)
                        assert active['continuation'] and active['results'][0]['ref']==ordered[0]
                        # A real public permission transition, not unrelated HEAD
                        # movement, invalidates the task-bound continuation.
                        engine.pause(store,iid,'Synthetic full retrieval permission boundary.')
                        denied('paused_task_cursor',lambda:Q.search(Store(store.root),'Synthetic native pilot convention',
                            kind='Context',task=main,limit=1,continuation=active['continuation']),{'TASK_FENCED','KNOWLEDGE_FORBIDDEN'})
                        denied('paused_task_late_get',lambda:Q.get(Store(store.root),late_ref,task=main,as_of_commit=pinned),
                            {'TASK_FENCED','KNOWLEDGE_FORBIDDEN'})
                        denied_delivery,denied_response=tools.call('knowledge_get',{'ref':late_ref,'as_of_commit':pinned})
                        assert denied_delivery is None and denied_response['isError']
                        denied_body=json.loads(denied_response['content'][0]['text'])
                        assert denied_body['error']=='TASK_FENCED' and 'body' not in denied_body
                        negatives.append(dict(check='paused_actual_TaskTools',error=denied_body['error']))
                    assert not any('observation_error' in row for row in phases),phases
                    assert len(groups)==9 and [g['work_items'] for g in groups]==[8]*8+[1]
                    assert len(batches)==65 and len(added)==4160
                status='FULL_FM13_ASSERTIONS_PASSED_NOT_PACKAGE_ACCEPTANCE' if full else 'PILOT_ASSERTIONS_PASSED_NOT_FM13_ACCEPTANCE'
        finally:
            rows=reader_rows();files=[f for f in Path(tmp).rglob('*') if f.is_file()]
            print(('DEV11_FM13_NATIVE_FULL ' if full else 'DEV11_FM13_NATIVE_PILOT ')+json.dumps(dict(status=status,profile='pmrs.commit/4.2.2',batches_completed=len(batches),
                batches=batches,maximum_batches=batch_count,maximum_records_per_batch=64,groups=groups,phases=phases,readers=rows,phase_read_totals=aggregates(rows),
                project=str(Path(tmp)/'native'),retained=full,paging=paging,negative_assertions=negatives,
                task_response=task_response,elapsed_seconds=time.monotonic()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                logical_disk_bytes=sum(f.stat().st_size for f in files),allocated_disk_bytes=sum(f.stat().st_blocks*512 for f in files),
                host_pool_created=host_pool.exists(),host_pool_path=str(host_pool),fake_home=str(Path.home()),
                fake_home_pool_logical_bytes=sum(p.stat().st_size for p in host_pool.rglob('*') if p.is_file()),
                provider_calls=0,full4097=('ASSERTIONS_COMPLETED' if status.startswith('FULL_FM13_ASSERTIONS_PASSED') else 'FAILED_OR_INCOMPLETE') if full else 'HELD_NOT_EXECUTED',
                measurement_scope='Strong reader keys assign stable serials; per-phase unique bytes sum first successful reads per path/reader. Observation phases and query/delivery readers separated; profiling memory included in RSS.',
                limitation='Native profile only; no /2/combined scalability or package acceptance. Full fixture still requires actual isolated evidence.' if full else 'Two native batches only; actual success requires TaskTools body delivery. No /2/combined scalability or full4097 claim.')),flush=True)
