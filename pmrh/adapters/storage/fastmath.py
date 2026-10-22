"""Typed fast transactions on Control's one Journal, lock and HEAD."""
from copy import deepcopy
from pmrh.domain.primitives import canonical, sha, loads
from pmrh.domain.fastmath.model import (PreparedFastDelta, FastReadContext, MAX_DELTA, check, revision_ref)
from pmrh.domain.fastmath.validation import validate_delta, native_refs, fast_refs, fields, bounded, DELTA_FIELDS, required_guards
from pmrh.domain.fastmath.qualification import project
from pmrh.ports.dto import core as C, specs as S, execution as X, enums as E, capability as K
from pmrh.ports.capabilities import check_capabilities
from . import control as D

FAST_MAPS = frozenset(('fast_revisions','fast_selected','fast_proposals','fast_claim_links','fast_receipts'))


def _proposal(store, ref, project_id):
    raw = D.read_ref(store,ref,project_id,maximum=MAX_DELTA)
    value = loads(raw,maximum=MAX_DELTA)
    check(canonical(value) == raw and ref['object_id'] == 'fast-proposal:'+sha(raw), 'Proposal bytes differ','FAST_INTEGRITY_ERROR')
    return value


def _capture(store, state, payload):
    """Reconstruct the sealed original from the already ingested receipt set."""
    rid = payload['request_id']; request = state.get('requests',{}).get(rid)
    check(request is not None and not request['fenced'] and not request['admission']['evidence_conflict'] and
          request['execution_inbox']['state'] == 'OPEN' and request['execution_state'] in {'CAPTURED','SETTLED'},
          'Original request cannot retain this proposal','FAST_STATE_DENIED')
    wrappers = [state['execution_events'][key] for key in request['admission']['receipt_ids']
                if state['execution_events'][key].get('receipt_kind') == 'CAPTURE' and
                state['execution_events'][key].get('receipt_ref') == payload['receipt_ref']]
    check(len(wrappers) == 1, 'Original sealed capture receipt unavailable','FAST_CAPTURE_MISMATCH')
    wrapper = wrappers[0]
    receipt = X.CaptureReceipt.from_wire(D.read_json(store,payload['receipt_ref'],state['project_id']))
    spec = S.AgentInvocationSpec.from_wire(D.read_json(store,request['admission']['spec_ref'],state['project_id']))
    check(receipt.identity == spec.identity() and wrapper['identity'] == spec.identity().to_wire() and
          wrapper['binding_ref'] == spec.runner_binding_ref.to_wire() and
          wrapper['producer_ref'] == request['execution_inbox']['producer_ref'] and
          receipt.raw_output_ref.to_wire() == payload['capture_ref'] and
          request['capture_ref'] == receipt.raw_output_ref.sha256, 'Original invocation differs','FAST_CAPTURE_MISMATCH')
    raw = D.read_ref(store,payload['capture_ref'],state['project_id'],maximum=1024**2)
    captured = loads(raw,maximum=1024**2)
    check(type(captured) is dict and type(captured.get('payload')) is dict and type(captured['payload'].get('fast_delta')) is dict,
          'Original fast_delta field missing','FAST_CAPTURE_MISMATCH')
    value = captured['payload']['fast_delta']
    digest = sha(canonical(value)); pref = D.ref(payload['proposal_ref'],state['project_id'])
    check(pref.sha256 == digest and pref.revision == 'sha256:'+digest and pref.object_id == 'fast-proposal:'+digest,
          'Proposal is not the exact original capture field','FAST_CAPTURE_MISMATCH')
    task = state['tasks'][request['task_id']]
    check(value['request_id'] == rid and value['attempt_id'] == spec.attempt_id == task['attempt_key'] and
          value['input_commit'] == task['knowledge_commit'] and value['scope'] == dict(project_id=state['project_id'],
          instance_id=task['instance_id'],mission_id=task['mission_id']), 'Frozen original input differs','FAST_CAPTURE_MISMATCH')
    instance = state['instances'][request['instance_id']]
    if task.get('actor_kind') == 'MAIN':
        check(instance['status'] == 'ACTIVE' and request['admission']['owner_epoch'] == instance['ownership']['owner_epoch'],
              'Old or paused MAIN result','FAST_STATE_DENIED')
    return value, wrapper, receipt


def _read_closure(state, task, delta):
    # Only persisted exact task packets are accepted. Preparation is conservative:
    # dynamically discovered dependencies need a fresh authorized task packet.
    allowed = {r['record_ref'] for r in task.get('read_set',[])} | set(task.get('source_refs',[])) | set(task.get('target_refs',[]))
    allowed |= {r['ref'] for r in task.get('input_manifest',[]) if 'ref' in r}
    allowed |= set(task.get('material_source_refs',[]))
    from pmrh.domain.relations import premise_closure
    if task.get('actor_kind')=='MAIN':
        for producer in state.get('production_events',{}).values():
            origin=state.get('tasks',{}).get(producer.get('task_id'),{})
            if (origin.get('instance_id'),origin.get('mission_id'))==(task['instance_id'],task['mission_id']):
                allowed.add(producer.get('record_ref'))
        for frozen in state.get('tasks',{}).values():
            if (frozen.get('instance_id'),frozen.get('mission_id'))==(task['instance_id'],task['mission_id']):
                allowed |= {r['ref'] for r in frozen.get('input_manifest',[]) if 'ref' in r and not r.get('body_coverage')}
    allowed |= premise_closure(allowed & set(state.get('records',{})),state)
    partial = {r['ref'] for r in task.get('input_manifest',[]) if r.get('body_coverage')}
    dependencies=native_refs(delta)
    for collection,identity in required_guards(state,delta['revision_entries'],delta['same_claim_links']):
        dependencies |= native_refs(state[collection][identity])
    check(dependencies <= allowed - partial, 'Exact full dependency closure is not authorized','FAST_REF_UNAVAILABLE')
    # Preserve the native source ancestry exclusions at this adapter boundary.
    # MAIN may consume review records; a worker's exact packet cannot launder
    # a review verdict through provenance or translation edges.
    from pmrh.domain.relations import edges
    def tainted(ref,seen):
        if ref in seen:return False
        seen.add(ref);source=state.get('sources',{}).get(ref,{})
        if source.get('access_class') in {'OPERATOR_PREPARATION','HISTORICAL_REVIEW','UNKNOWN'}:return True
        if state.get('records',{}).get(ref,{}).get('kind')=='Assessment':return True
        parents=list(source.get('provenance_refs',[]))+list(state.get('translations',{}).get(ref,{}).get('source_refs',[]))
        parents += [r['target_ref'] for r in edges(state) if r['source_ref']==ref and r['type'] in {'TRANSLATES','SOURCE_PROVENANCE'}]
        return any(tainted(r,seen) for r in parents)
    if task.get('actor_kind')!='MAIN':
        check(not any(tainted(r,set()) for r in dependencies),'Source/review derivative unavailable','FAST_REF_UNAVAILABLE')
    if task.get('communication_contract',{}).get('mode') in {'REVIEW_ISOLATED','INDEPENDENT_EXPLORE'}:
        frozen = {s for r in task.get('read_set',[]) for s in r.get('required_support_refs',[])}
        for entry in delta['revision_entries']:
            if entry['body']['kind'] == 'RefinementBinding':
                check(set(entry['body']['payload']['support_ids']) <= frozen, 'Review support visibility','FAST_REF_UNAVAILABLE')


def apply_effects(store, state, event):
    """Closed replayable effects; no native scientific/control collection changes."""
    after = deepcopy(state); project_id = state['project_id']; p = event['payload']
    for name in FAST_MAPS: after.setdefault(name,{})
    pref = p['proposal_ref']; key = pref['sha256']
    value = _proposal(store,pref,project_id)
    if event['type'] == 'FAST_PROPOSAL_CAPTURED':
        value, _, _ = _capture(store,state,p)
        task = state['tasks'][state['requests'][p['request_id']]['task_id']]
        _read_closure(state,task,value)
        validate_delta(value,state)
        for entry in value['revision_entries']:
            check(store._read_blob(entry['ref'][3:],64*1024) == canonical(entry['body']), 'Captured revision unavailable','FAST_INTEGRITY_ERROR')
        check(key not in after['fast_proposals'], 'Proposal already captured','FAST_IDEMPOTENCY_CONFLICT')
        after['fast_proposals'][key] = dict(proposal_ref=deepcopy(pref),capture_ref=deepcopy(p['capture_ref']),
            receipt_ref=deepcopy(p['receipt_ref']),request_id=p['request_id'],status='PENDING',
            captured_operation=event['operation_id'],applied_operation=None)
    else:
        original = after['fast_proposals'].get(key)
        check(original is not None and original['proposal_ref'] == pref and original['status'] == 'PENDING', 'Pending proposal unavailable','FAST_REF_UNAVAILABLE')
        # Recheck original safety and guard closure at the actual live HEAD.
        _capture(store,state,{**original,'proposal_ref':pref})
        validate_delta(value,state)
        for entry in value['revision_entries']:
            raw = store._read_blob(entry['ref'][3:],64*1024)
            check(raw == canonical(entry['body']), 'Revision blob changed','FAST_INTEGRITY_ERROR')
            after['fast_revisions'][entry['ref']] = deepcopy(entry['body'])
            after['fast_selected'][entry['body']['object_id']] = entry['ref']
        for ordinal, link in enumerate(value['same_claim_links']):
            # The link locator names this event, never changes the old binding.
            after['fast_claim_links']['fast-link:'+sha(canonical(event))+':'+str(ordinal)] = deepcopy(link)
        original.update(status='APPLIED',applied_operation=event['operation_id'])
    command = {k:v for k,v in event.items() if k!='decision_ref'}
    after['fast_receipts'][event['operation_id']] = dict(idempotency_key=event['idempotency_key'],
        command_sha256=sha(canonical(command)),event_sha256=sha(canonical(event)),proposal_ref=deepcopy(pref),
        revision_refs=[r['ref'] for r in value['revision_entries']],
        outcome='CAPTURED' if event['type']=='FAST_PROPOSAL_CAPTURED' else 'APPLIED' if value['revision_entries'] or value['same_claim_links'] else 'NO_CHANGE')
    return after


def validate_effects(store, before, after, event, decision):
    from .journal import _diff
    check(set(_diff(before,after)) <= FAST_MAPS, 'Fast command changed native state','FAST_INTEGRITY_ERROR')
    instance = before['instances'][event['scope']['instance_id']]
    check(event['owner_epoch']==instance['ownership']['owner_epoch'] and event['control_version']==D.current_version(instance),
          'Fast event epoch/control differs','FAST_INTEGRITY_ERROR')
    if event['type']=='FAST_DELTA_APPLIED':
        check(instance['status']=='ACTIVE' and decision['budget_grant_ref'] is not None and
              decision['capability_manifest_ref'] is not None, 'MAIN apply decision missing','FAST_INTEGRITY_ERROR')
        grant = D.read_json(store,decision['budget_grant_ref'],before['project_id'])
        check(grant == before['budget_grants'].get(grant['budget_grant_id']) and grant['grant_status']=='ACTIVE' and
              grant['instance_id']==event['scope']['instance_id'] and grant['mission_id']==instance['current_mission_id'],
              'Current exact grant missing','FAST_INTEGRITY_ERROR')
        eligible=[]
        for rid,request in before['requests'].items():
            task=before['tasks'][request['task_id']]
            if (request['instance_id']!=event['scope']['instance_id'] or task.get('actor_kind')!='MAIN' or
                request['fenced'] or request['execution_state'] not in {'SENT','UNKNOWN'} or
                request['execution_inbox']['state']!='OPEN' or request['admission']['evidence_conflict'] or
                request['budget_grant_id']!=grant['budget_grant_id'] or
                request['admission']['capability_manifest_ref']!=decision['capability_manifest_ref']):continue
            spec=S.AgentInvocationSpec.from_wire(D.read_json(store,request['admission']['spec_ref'],before['project_id']))
            if (spec.owner_epoch,spec.expected_control_version)==(event['owner_epoch'],event['control_version']):
                manifest=K.CapabilityManifest.from_wire(D.read_json(store,decision['capability_manifest_ref'],before['project_id']))
                check(check_capabilities(manifest,spec.capability_requirements) is None,'Recorded MAIN capabilities differ','FAST_INTEGRITY_ERROR')
                eligible.append(task)
        check(len(eligible)==1,'Exact live MAIN invocation missing or ambiguous','FAST_INTEGRITY_ERROR')
        _read_closure(before,eligible[0],_proposal(store,event['payload']['proposal_ref'],before['project_id']))
    else:
        check(decision['budget_grant_ref'] is None and decision['capability_manifest_ref'] is None,'Ingress cannot grant execution','FAST_INTEGRITY_ERROR')
    check(after == apply_effects(store,before,event),'Fast replay differs','FAST_INTEGRITY_ERROR')
    D.validate_state(after)


def receipt_for(state,event,head):
    row = state['fast_receipts'][event['operation_id']]
    return dict(schema='pmrh.fast-receipt/1',operation_id=event['operation_id'],
        idempotency_key=row['idempotency_key'],command_sha256=row['command_sha256'],commit=head['commit'],
        sequence=head['sequence'],event_ref=C.ExactRef(project_id=state['project_id'],object_id='fast-event:'+event['operation_id'],
            revision='sha256:'+row['event_sha256'],sha256=row['event_sha256']).to_wire(),
        proposal_ref=deepcopy(row['proposal_ref']),revision_refs=list(row['revision_refs']),outcome=row['outcome'])


class FastStorage:
    def __init__(self, control_storage):
        self.control_storage = control_storage
        self.store = control_storage.store
        self._read_contexts = {}

    def bind_read_context(self, context, session):
        """Trusted local assembly binds object identity to a registered session."""
        check(type(context) is FastReadContext,'Read context type required','FAST_AUTHORITY_DENIED')
        service=self.control_storage.service
        state=self.store.read_snapshot();task=state.get('tasks',{}).get(context.task_id)
        check(task is not None,'Read context unavailable','FAST_REF_UNAVAILABLE')
        service.registry.authenticate_current(session,'RECOVER_RECEIPT',
            {'project_id':context.project_id,'instance_id':context.instance_id},service.binding_id,
            request_id=task['request_id'])
        self._read_contexts[context]=session
        return context

    def prepare(self, delta, read_context, as_of_commit):
        check(type(read_context) is FastReadContext, 'Trusted read context required','FAST_AUTHORITY_DENIED')
        check(read_context in self._read_contexts,'Unregistered read context','FAST_AUTHORITY_DENIED')
        current = self.store.read_snapshot()
        task = current.get('tasks',{}).get(read_context.task_id)
        check(task is not None and current['project_id']==read_context.project_id and
              task['instance_id']==read_context.instance_id and task['mission_id']==read_context.mission_id,
              'Read context unavailable','FAST_REF_UNAVAILABLE')
        service=self.control_storage.service
        service.registry.authenticate_current(self._read_contexts[read_context],'RECOVER_RECEIPT',
            {'project_id':read_context.project_id,'instance_id':read_context.instance_id},service.binding_id,request_id=task['request_id'])
        request = current['requests'].get(task['request_id'])
        check(request is not None and not request['fenced'], 'Read request revoked','FAST_AUTHORITY_DENIED')
        snapshot = current if as_of_commit==current['knowledge_commit'] else self.store.read_snapshot(as_of_commit)
        check(delta['input_commit']==task['knowledge_commit'] and delta['request_id']==task['request_id'] and
              delta['attempt_id']==task['attempt_key'],'Original input identity differs','FAST_CAPTURE_MISMATCH')
        _read_closure(current,task,delta)
        validate_delta(delta,snapshot)
        raw = canonical(delta)
        return PreparedFastDelta(raw,sha(raw),as_of_commit)

    def authorize(self, service, command, session, state, grant_ref, manifest_ref):
        action=command['type']; iid=command['scope']['instance_id']; p=command['payload']
        rid=p.get('request_id') if action=='FAST_PROPOSAL_CAPTURED' else service.registry.acting_request(session)
        auth=service.registry.authenticate_current(session,action,command['scope'],service.binding_id,request_id=rid)
        instance=state['instances'][iid]
        check(command['owner_epoch']==instance['ownership']['owner_epoch'] and command['control_version']==D.current_version(instance),
              'Current epoch/control required','FAST_VERSION_CONFLICT')
        if action=='FAST_PROPOSAL_CAPTURED':
            check(auth.get('fast_capture_ingress')==rid and auth['request_ids']==frozenset({rid}) and
                  not auth['human'] and not auth['proposal_only'] and auth['owner_id'] is None and
                  auth['actions']==frozenset({'FAST_PROPOSAL_CAPTURED','RECOVER_RECEIPT'}) and
                  grant_ref is None and manifest_ref is None,'Narrow registered ingress required','FAST_AUTHORITY_DENIED')
            value,wrapper,receipt=_capture(self.store,state,p)
            self.control_storage._verified_receipt(service,state,wrapper)
            check(value['scope']['instance_id']==iid,'Capture scope differs','FAST_AUTHORITY_DENIED')
            return auth,None
        check(not auth['proposal_only'] and auth['owner_id']==instance['ownership']['owner_id'] and
              instance['status']=='ACTIVE' and rid in state['requests'],'Current ACTIVE MAIN required','FAST_STATE_DENIED')
        request=state['requests'][rid]; task=state['tasks'][request['task_id']]
        check(task.get('actor_kind')=='MAIN' and request['instance_id']==iid and not request['fenced'] and
              request['execution_state'] in {'SENT','UNKNOWN'} and request['execution_inbox']['state']=='OPEN' and
              not request['admission']['evidence_conflict'],'MAIN invocation unavailable','FAST_STATE_DENIED')
        spec_ref=request['admission']['spec_ref']; spec=S.AgentInvocationSpec.from_wire(D.read_json(self.store,spec_ref,state['project_id']))
        check(spec.role is E.AgentRole.MAIN and spec.owner_epoch==command['owner_epoch'] and
              spec.expected_control_version==command['control_version'],'Original MAIN version differs','FAST_VERSION_CONFLICT')
        registered=service.registry.manifest(spec_ref)
        check(manifest_ref is not None and registered['manifest_ref']==manifest_ref==request['admission']['capability_manifest_ref'] and
              registered['binding_ref']==spec.runner_binding_ref.to_wire() and registered['identity']==spec.identity().to_wire() and
              registered['producer_ref']==request['execution_inbox']['producer_ref'],'Registered manifest required','FAST_AUTHORITY_DENIED')
        manifest=K.CapabilityManifest.from_wire(D.read_json(self.store,manifest_ref,state['project_id']))
        check(check_capabilities(manifest,spec.capability_requirements) is None,'Delegated capability unavailable','FAST_AUTHORITY_DENIED')
        check(grant_ref is not None,'Current grant required','FAST_AUTHORITY_DENIED')
        grant=D.read_json(self.store,grant_ref,state['project_id'])
        check(grant==state['budget_grants'].get(request['budget_grant_id']) and grant['grant_status']=='ACTIVE' and
              grant['instance_id']==iid and grant['mission_id']==instance['current_mission_id']==task['mission_id'],
              'Current exact scoped grant required','FAST_AUTHORITY_DENIED')
        if instance['ownership']['backend_binding_ref'] is not None:
            check(instance['ownership']['backend_binding_ref']==spec.runner_binding_ref.to_wire(),'MAIN backend differs','FAST_AUTHORITY_DENIED')
        original=state.get('fast_proposals',{}).get(p['proposal_ref']['sha256'])
        check(original is not None,'Proposal unavailable','FAST_REF_UNAVAILABLE')
        proposal=_proposal(self.store,p['proposal_ref'],state['project_id'])
        check(proposal['scope']['mission_id']==task['mission_id'],'Proposal mission differs','FAST_AUTHORITY_DENIED')
        _read_closure(state,task,proposal)
        return auth,spec

    def reduce(self,service,state,event):
        if event['type'] == 'FAST_PROPOSAL_CAPTURED':
            value, _, _ = _capture(self.store,state,event['payload'])
            validate_delta(value,state)
            self.store.put_blob(canonical(value))
            for entry in value['revision_entries']:
                check(self.store.put_blob(canonical(entry['body'])) == entry['ref'][3:], 'Immutable revision differs')
        return apply_effects(self.store,state,event)

    def capture(self,prepared,**arguments):
        check(type(prepared) is PreparedFastDelta and sha(prepared.raw)==prepared.sha256,'Exact prepared bytes required')
        value=loads(prepared.raw,maximum=MAX_DELTA);fields(value,DELTA_FIELDS);bounded(value,MAX_DELTA)
        check(canonical(value)==prepared.raw,'Prepared bytes must be canonical')
        # Calculate identity without I/O. Original bytes are read and persisted
        # only after current ingress authentication under the shared writer lock.
        proposal_ref=C.ExactRef(project_id=value['scope']['project_id'],object_id='fast-proposal:'+prepared.sha256,
            revision='sha256:'+prepared.sha256,sha256=prepared.sha256).to_wire()
        payload={k:arguments.pop(k) for k in ('request_id','capture_ref','receipt_ref')}
        payload['proposal_ref']=proposal_ref
        return self._submit('FAST_PROPOSAL_CAPTURED',payload,arguments)

    def apply(self,proposal_ref,**arguments):
        return self._submit('FAST_DELTA_APPLIED',{'proposal_ref':proposal_ref},arguments)

    def _submit(self,action,payload,arguments):
        service=self.control_storage.service
        session=arguments.pop('session'); grant=arguments.pop('grant_ref',None); manifest=arguments.pop('manifest_ref',None)
        command=dict(schema=self.control_storage.event_schema,type=action,payload=payload,**arguments)
        return service.apply(command,session,grant_ref=grant,manifest_ref=manifest)

    def recover(self,scope,operation_id,session):
        service=self.control_storage.service
        # Scope/request constrained ingress recovery also checks the operation's
        # actual request, instead of pretending RECOVER_RECEIPT has no request.
        self.control_storage._root(service,scope)
        rid=service.registry.acting_request(session)
        service.registry.authenticate_current(session,'RECOVER_RECEIPT',scope,service.binding_id,request_id=rid)
        state=self.store.read_snapshot(); index=self.store._control_index
        row=index.operations.get(operation_id) if index else None
        check(row is not None and row['command']['scope']==scope and row['command']['type'].startswith('FAST_'),
              'Receipt unavailable','FAST_REF_UNAVAILABLE')
        command=row['command']; rid=command['payload'].get('request_id') or service.registry.acting_request(session)
        service.registry.authenticate_current(session,'RECOVER_RECEIPT',scope,service.binding_id,request_id=rid)
        return deepcopy(row['receipt'])

    def project(self,ref,*,as_of_commit=None):
        return project(ref,self.store.read_snapshot(as_of_commit))
