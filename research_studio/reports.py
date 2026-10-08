"""Independent report artifacts with exact content, semantic and all-page checks.

The catalog never determines permission to continue research. Only an explicit
report-first condition in the authorized workflow decision can add that gate.
"""
from copy import deepcopy
import secrets
from .util import canonical, identity, sha, loads, read, immutable, require, PMRSError
from .language import REPORT_LABELS, authored_english
from .restricted_tex import validate_tex, tex_semantic_identity
from . import report_catalog as catalog_service

SCHEMA=catalog_service.SCHEMA
PROFILES=('lecture','minimal')
SURVEY_PROFILES=('minimal','thematic','lecture')
SURVEY_EDITION_DUTIES={
    'minimal':'Give a concise account of the exact selected questions, principal statements, hypotheses, source locators, mechanisms, boundary cases and remaining gaps. Omit pedagogical expansion unless required by the frozen proof promises.',
    'thematic':'Organize the selected knowledge by mathematical themes and proof mechanisms. Compare assumptions, conclusions, dependencies and limits across sources, and distinguish established relations from unanswered comparisons.',
    'lecture':'Develop a pedagogical exposition for the frozen audience and prerequisites, with explicit definitions, motivated derivations, worked examples and boundary cases. Present only the proof detail actually promised and independently checked; label every sketch or missing step.'}

def selected_profiles(entry):
    return tuple(entry.get('selected_profiles',PROFILES))

def survey_report(entry):
    return entry.get('workflow_kind')=='SURVEY'

def require_current_survey(snapshot,entry):
    if survey_report(entry):
        from . import survey
        require(survey.report_current(snapshot,entry['scope']),'REPORT_SNAPSHOT_STALE',
                'Relevant Survey evidence, source status or readiness changed.')

COVERAGE={'goal','notation','inherited_basis','current_results','proofs','failures','open_obligations'}


def authoring_rules(ctx):
    common=('Return only the frozen ResponseEnvelope. Do not create scientific records or issue human decisions. '
            'Read every frozen research record, original source and stated checked/unchecked boundary. '
            'Use English prose and restricted TeX. Formal verification is not provided in this version. ')
    if ctx['role']=='REPORT_AUTHOR':
        if ctx.get('workflow_kind')=='SURVEY':
            common+=('Write only the explicitly selected '+ctx['profile']+' English survey. Follow the frozen output plan, audience, perspective, proof depth and declared omissions. '
                     +SURVEY_EDITION_DUTIES[ctx['profile']]+' '
                     'Source publication, reading, local readiness and proof qualification are separate facts. '
                     'Use INCONCLUSIVE for unevaluated claims; never turn absence of review into a mathematical OPEN assertion. '
                     'Report new mathematical claims or missing evidence as research gaps; do not invent them. ')
        pairing=('For minimal, bind the exact accepted lecture content key as parent_lecture, and copy its statements '
                 'and notation byte for byte. For lecture, parent_lecture is null. ') if ctx.get('workflow_kind')!='SURVEY' else (
                 'For this standalone Survey profile parent_lecture is null. Do not create an unrequested companion edition. ')
        return common+('Use payload_kind REPORT_OUTPUT with exactly profile, body, notation_tex, shared_statements, coverage, '
            'included_refs, omissions, parent_lecture. Begin body with \\section{Introduction}; include exactly one '
            '{{notation}} and one {{statement:ID}} for every shared statement. Each statement has id, statement_tex, '
            'status OPEN|CONDITIONAL|CANDIDATE|BACKGROUND|INCONCLUSIVE, and nonempty source_refs. '
            'Coverage keys: goal, notation, inherited_basis, current_results, proofs, failures, open_obligations. '
            'Each omission has ref and an English mathematical reason. Account for every selected target/candidate. '
            +pairing+'Never supply a new lemma to repair research. ')
    if ctx['role']=='REPORT_SEMANTIC':
        return common+('Use payload_kind REPORT_REVIEW with exactly profile, verdict PASS|REVISE, findings, uncheckable. '
            'Each finding has code, anchor, severity BLOCKING|WARNING, description. Check every inference, quantifier, '
            'coefficient, premise, source and open boundary against complete supplied research. Do not inspect previous '
            'verdicts about this report. Missing research uses NEW_LEMMA_REQUIRED or SOURCE_PROOF_ERROR. '
            'PASS requires no blocking finding or unchecked item. A disclosed open research problem is not itself a defect.')
    return common+('Use payload_kind REPORT_REVIEW with exactly profile and pages. Review every assigned actual PNG '
        'listed in pages; adjacent context_pages do not count as checked pages. Each page has id, sha256, '
        'verdict PASS|REVISE, findings. Each finding has code, anchor, severity BLOCKING|WARNING, description. '
        'Check clipping, glyphs, formula/table layout, margins and reading order. Never infer a page PASS from its source text.')


def _profile():
    return {'revision':0,'body_sha256':None,'raw_body_sha256':None,'shared_statements':[],
            'notation_tex':'','included_refs':[],'omissions':[],'parent_lecture':None,
            'semantic':None,'render':None,'visual':{},'history':[],'feedback':[],
            'semantic_policy':tex_semantic_identity(),'author_request_id':None,'lf_transport':[]}


def content_key(p):
    return identity({k:p[k] for k in ('body_sha256','shared_statements','notation_tex','parent_lecture')})


def semantic_key(p):
    return identity({'content':content_key(p),'mathematical_semantics':p['semantic_policy']})


def _findings(rows):
    require(isinstance(rows,list),'REPORT_FINDINGS','Findings must be a list')
    for d in rows:
        require(isinstance(d,dict) and set(d)=={'code','anchor','severity','description'} and d['severity'] in ('BLOCKING','WARNING'),
                'REPORT_FINDING_FIELDS','Stable anchored defects required')
        for k in ('code','anchor','description'):authored_english(d[k],k)
    return any(d['severity']=='BLOCKING' for d in rows)


def expand(body,data):
    require(body.count('{{notation}}')==1,'REPORT_NOTATION_REQUIRED','Exactly one shared notation insertion')
    result=body.replace('{{notation}}',data['notation_tex'])
    for number,row in enumerate(data['shared_statements'],1):
        token='{{statement:'+row['id']+'}}'
        require(result.count(token)==1,'REPORT_STATEMENT_REQUIRED',row['id'])
        result=result.replace(token,'\\paragraph{Statement '+str(number)+' ('+REPORT_LABELS[row['status']]+').}\n'+row['statement_tex']+'\n')
    require('{{statement:' not in result,'REPORT_UNKNOWN_STATEMENT','No unbound shared statement')
    return validate_tex(result)


def _exact_or_lf(actual,expected,label):
    require(isinstance(actual,str) and isinstance(expected,str),'REPORT_SHARED_TEXT_INVALID',label)
    if actual==expected:return expected,None
    require(actual==expected+'\n' or expected==actual+'\n','REPORT_MINIMAL_PARENT_MISMATCH',label+' differs from the accepted lecture')
    return expected,{'field':label,'received_sha256':sha(actual.encode()),'frozen_sha256':sha(expected.encode()),'normalization':'ONE_TERMINAL_LF_ONLY'}


def validate_payload(task,snapshot,payload,*,blob_get):
    """Pure report validator used by normal admission, preflight and recovery."""
    ctx=task.get('report_context')
    require(isinstance(ctx,dict),'REPORT_CONTEXT_REQUIRED','Frozen report context required')
    rid,profile,role=ctx['report_id'],ctx['profile'],task['role']
    require(rid in snapshot.get('reports',{}) and profile in selected_profiles(snapshot['reports'][rid]),'REPORT_UNKNOWN','Exact report and profile required')
    entry=snapshot['reports'][rid];current=entry['profiles'][profile]
    require(entry['status']!='ABANDONED','REPORT_ABANDONED','The report was explicitly abandoned; preserve its attempt without new work.')
    owner=getattr(blob_get,'__self__',None)
    if owner is not None and hasattr(owner,'root'):
        # Admission is an actual use boundary, never a read-only catalog cache hit.
        catalog_service.check_files(owner,entry)
    else:
        for digest in set(ctx.get('files',{}).values()):
            require(sha(blob_get(digest))==digest,'BLOB_CHANGED','Frozen report input changed before admission.')
    require_current_survey(snapshot,entry)
    require(entry['scope_fingerprint']==catalog_service.fingerprint(snapshot,entry['scope']), 'REPORT_SNAPSHOT_STALE','Relevant research changed')
    require(current['revision']==ctx['revision'],'REPORT_REVISION_STALE','Profile revision changed')
    require(isinstance(payload,dict),'REPORT_PAYLOAD_INVALID','Report payload must be an object')
    blobs={};normalized=deepcopy(payload)
    require(role==ctx.get('role') and task.get('report_context')==ctx,'REPORT_CONTEXT_REQUIRED','Exact frozen report role required')
    if role=='REPORT_AUTHOR':
        fields={'profile','body','notation_tex','shared_statements','coverage','included_refs','omissions','parent_lecture'}
        require(isinstance(payload,dict) and set(payload)==fields,'REPORT_NO_NEW_SCIENCE','Report output is an artifact, never scientific operations')
        require(payload['profile']==profile,'REPORT_PROFILE_MISMATCH','Frozen profile required')
        authored_english(payload['body'],'report body');authored_english(payload['notation_tex'],'report notation')
        require('\\section{Introduction}' in payload['body'] or '\\section{1. Introduction}' in payload['body'],
                'REPORT_INTRODUCTION_REQUIRED','Introduce the background and principal findings first')
        require(isinstance(payload['coverage'],dict) and set(payload['coverage'])==COVERAGE,'REPORT_COVERAGE','All seven coverage categories required')
        for value in payload['coverage'].values():authored_english(value,'report coverage')
        frozen=loads(blob_get(entry['snapshot_ref']));known=set(frozen['records'])|set(frozen['sources'])
        require(isinstance(payload['shared_statements'],list) and len(payload['shared_statements'])<=64,'REPORT_STATEMENTS','Bounded exact statements required')
        identifiers=set()
        for row in payload['shared_statements']:
            require(isinstance(row,dict) and set(row)=={'id','statement_tex','status','source_refs'} and row['status'] in REPORT_LABELS,
                    'REPORT_STATEMENT_FIELDS','Exact statement and boundary required')
            require(row['id'].isalnum() and row['id'] not in identifiers,'REPORT_STATEMENT_ID','Unique statement identifier required')
            identifiers.add(row['id']);require(isinstance(row['source_refs'],list),'REPORT_SOURCE_UNREAD','Exact source reference list required');authored_english(row['statement_tex'],'statement')
            require(row['source_refs'] and set(row['source_refs'])<=known,'REPORT_SOURCE_UNREAD','Every statement needs supplied evidence')
        require(isinstance(payload['included_refs'],list) and all(isinstance(r,str) for r in payload['included_refs']) and isinstance(payload['omissions'],list),'REPORT_SCOPE','Exact inclusion and omission lists required')
        included=set(payload['included_refs']);omitted=set()
        for row in payload['omissions']:
            require(isinstance(row,dict) and set(row)=={'ref','reason'} and row['ref'] not in omitted,'REPORT_OMISSION','Exact reasoned omissions required')
            authored_english(row['reason'],'omission');omitted.add(row['ref'])
        selected=set(frozen['scope']['target_refs']+frozen['scope']['candidate_refs'])
        require(not included&omitted and selected<=included|omitted and included|omitted<=known,
                'REPORT_SCOPE','Account for the complete selected scope')
        transport=[]
        if profile=='minimal' and not survey_report(entry):
            lecture=entry['profiles']['lecture']
            require(profile_complete(lecture),'LECTURE_NOT_ACCEPTED','Minimal derives only from an independently accepted lecture')
            require(payload['parent_lecture']==content_key(lecture),'REPORT_MINIMAL_PARENT_MISMATCH','Wrong lecture parent')
            require(len(payload['shared_statements'])==len(lecture['shared_statements']),'REPORT_MINIMAL_PARENT_MISMATCH','Shared statement set differs')
            normalized['notation_tex'],change=_exact_or_lf(payload['notation_tex'],lecture['notation_tex'],'notation_tex')
            if change:transport.append(change)
            for actual,expected in zip(normalized['shared_statements'],lecture['shared_statements']):
                require({k:v for k,v in actual.items() if k!='statement_tex'}=={k:v for k,v in expected.items() if k!='statement_tex'},
                        'REPORT_MINIMAL_PARENT_MISMATCH','Statement identity or scope differs')
                actual['statement_tex'],change=_exact_or_lf(actual['statement_tex'],expected['statement_tex'],'statement:'+expected['id'])
                if change:transport.append(change)
        else:require(payload['parent_lecture'] is None,'REPORT_PARENT_INVALID','Standalone profiles have no lecture parent')
        body=expand(payload['body'],normalized).encode();raw_body=payload['body'].encode()
        blobs[sha(body)]=body;blobs[sha(raw_body)]=raw_body
        normalized.pop('body');normalized.update(body_sha256=sha(body),raw_body_sha256=sha(raw_body),lf_transport=transport)
    elif role=='REPORT_SEMANTIC':
        require(set(payload)=={'profile','verdict','findings','uncheckable'} and payload['profile']==profile,
                'REPORT_SEMANTIC_FIELDS','Exact semantic review required')
        require(payload['verdict'] in ('PASS','REVISE') and isinstance(payload['uncheckable'],list),'REPORT_VERDICT','Scoped verdict required')
        blocking=_findings(payload['findings'])
        require(payload['verdict']!='PASS' or not blocking and not payload['uncheckable'],'REPORT_CONTRADICTORY_PASS','Unchecked or blocking content cannot pass')
        require(payload['verdict']!='REVISE' or payload['findings'] or payload['uncheckable'],'REPORT_EMPTY_REVISION','Revision needs a concrete defect')
        require(ctx['semantic_key']==semantic_key(current),'REPORT_SEMANTICS_STALE','Content or mathematical macros changed')
    elif role=='REPORT_VISUAL':
        require(set(payload)=={'profile','pages'} and payload['profile']==profile,'REPORT_VISUAL_FIELDS','Exact page review required')
        require(isinstance(payload['pages'],list),'REPORT_PAGE_COVERAGE','Pages must be an exact list')
        expected={p['id']:p['sha256'] for p in ctx['pages']};seen=set()
        require(0<len(expected)<=8 and len(payload['pages'])==len(expected),'REPORT_PAGE_COVERAGE','Review every assigned page')
        for p in payload['pages']:
            require(isinstance(p,dict) and set(p)=={'id','sha256','verdict','findings'} and p['id'] not in seen and expected.get(p['id'])==p['sha256'],
                    'REPORT_PAGE_IDENTITY','Missing, duplicate or substituted page')
            seen.add(p['id']);blocking=_findings(p['findings'])
            require(p['verdict'] in ('PASS','REVISE'),'REPORT_PAGE_VERDICT','Page decision required')
            require(p['verdict']!='PASS' or not blocking,'REPORT_PAGE_CONTRADICTORY_PASS','Blocking page defect cannot pass')
            require(p['verdict']!='REVISE' or p['findings'],'REPORT_EMPTY_REVISION','Revision needs a page defect')
        require(current['render'] and ctx['render_identity']==current['render']['identity'],'REPORT_RENDER_STALE','Page rendering changed')
    else:require(False,'CAPABILITY_VIOLATION','Not a report role')
    if role!='REPORT_AUTHOR':
        require(ctx['content_key']==content_key(current),'REPORT_CONTENT_STALE','Reviewed content changed')
        require(task['request_id']!=current['author_request_id'],'REPORT_INDEPENDENCE_REQUIRED','The author cannot review its own report')
    event={'event_type':'REPORT_RESPONSE','actor':'host','capability_ref':'CAP-HOST','report_id':rid,'profile':profile,
           'payload':{'task_id':task['task_id'],'request_id':task['request_id'],'role':role,
                      'context':deepcopy(ctx),'result':normalized}}
    event['event_id']=identity(event,'REPORT-EVENT-')
    if role=='REPORT_SEMANTIC':
        for finding in payload['findings']:
            if finding['code'] in ('NEW_LEMMA_REQUIRED','SOURCE_PROOF_ERROR'):
                criterion=(finding['code']+': '+finding['description']).encode()
                blobs[sha(criterion)]=criterion
    return {'event':event,'blobs':blobs}


def profile_complete(p):
    return bool(p['body_sha256'] and p['render'] and p['semantic'] and
        p['semantic']['key']==semantic_key(p) and p['semantic']['verdict']=='PASS' and
        not p['semantic']['uncheckable'] and not _findings(p['semantic']['findings']) and
        len(p['visual'])==len(p['render']['pages']) and all(
            p['visual'].get(page['id'],{}).get('sha256')==page['sha256'] and
            p['visual'][page['id']]['verdict']=='PASS' and not _findings(p['visual'][page['id']]['findings'])
            for page in p['render']['pages']))


def pair_complete(entry):
    names=selected_profiles(entry)
    if not names or not all(profile_complete(entry['profiles'][name]) for name in names):return False
    return survey_report(entry) or entry['profiles']['minimal']['parent_lecture']==content_key(entry['profiles']['lecture'])


def _event(kind,rid,payload,profile=None):
    e={'event_type':kind,'actor':'host','capability_ref':'CAP-HOST','report_id':rid,'profile':profile,'payload':payload}
    return {'event_id':identity(e,'REPORT-EVENT-'),**e}


def apply_event(snapshot,event):
    fields={'event_id','event_type','actor','capability_ref','report_id','profile','payload'}
    require(set(event)==fields,'REPORT_EVENT_INVALID','Typed report event required')
    require(snapshot.get('capabilities',{}).get(event['capability_ref'],{}).get('actor')==event['actor']=='host',
            'AUTHORIZATION_REQUIRED','Report host capability required')
    existing=snapshot.get('report_events',{}).get(event['event_id'])
    if existing:
        require(existing==event,'ALREADY_SETTLED_CONTENT_CONFLICT','Report event reused with different bytes');return deepcopy(snapshot)
    state=deepcopy(snapshot);kind=event['event_type'];rid=event['report_id'];payload=event['payload'];profile=event['profile']
    if kind=='REPORT_CREATED':
        entry=deepcopy(payload['entry'])
        require_current_survey(state,entry)
        require(entry['report_id']==rid and rid not in state['reports'],'REPORT_EVENT_INVALID','New exact report required')
        require(entry['scope_fingerprint']==catalog_service.fingerprint(state,entry['scope']),'REPORT_SNAPSHOT_STALE','Relevant report inputs changed')
        require(entry['status']=='AUTHOR_REQUIRED' and not any(p['body_sha256'] for p in entry['profiles'].values()),'REPORT_EVENT_INVALID','A new report cannot claim completed work')
        state['reports'][rid]=entry;state.setdefault('active_reports',{})[entry['scope']['instance_ids'][0]]=rid
    else:
        require(rid in state['reports'],'REPORT_UNKNOWN',rid);entry=state['reports'][rid]
        require(entry['status']!='ABANDONED','REPORT_ABANDONED','An abandoned report cannot accept new events.')
        if kind!='REPORT_ABANDONED':
            require_current_survey(state,entry)
            require(entry['scope_fingerprint']==catalog_service.fingerprint(state,entry['scope']),'REPORT_SNAPSHOT_STALE','Relevant research inputs changed')
        p=entry['profiles'].get(profile) if profile else None
        if kind=='REPORT_RESPONSE':
            result=payload['result'];ctx=payload['context'];role=payload['role']
            task=state.get('tasks',{}).get(payload['task_id'],{});request=state.get('requests',{}).get(payload['request_id'],{})
            require(task.get('request_id')==payload['request_id'] and task.get('role')==role and request.get('capture_ref'),
                    'REPORT_CAPTURE_REQUIRED','Report output requires the actual frozen request and sealed capture')
            require(not request.get('fenced'),'TASK_FENCED','Report request was cancelled')
            require(task.get('report_context')==ctx,'REPORT_CONTEXT_REQUIRED','Capture must bind the exact frozen report context')
            if role!='REPORT_AUTHOR':
                provenance=request.get('evidence_path',request.get('execution_kind'))
                require(provenance in ('MODEL_CAPTURE','MODEL') or state.get('synthetic_test_only') and provenance in ('SYNTHETIC_TEST_ONLY','SYNTHETIC'),
                        'REPORT_REVIEW_SOURCE_REQUIRED','Operator JSON cannot certify an independent review')
                proof=state.get('review_executions',{}).get(request.get('execution_id'),{})
                require(task.get('independent') and proof.get('independent') and proof.get('integrity_valid')
                        and proof.get('excluded_verdicts') and proof.get('task_id')==task['task_id']
                        and proof.get('input_manifest_hash')==task.get('input_manifest_hash'),
                        'REPORT_INDEPENDENCE_REQUIRED','Review requires an isolated actual execution and intact input manifest')
            require(p['revision']==ctx['revision'],'REPORT_REVISION_STALE','Frozen revision differs')
            if role=='REPORT_AUTHOR':
                p.update({k:deepcopy(v) for k,v in result.items() if k in p})
                p.update(semantic=None,render=None,visual={},author_request_id=payload['request_id'])
                entry['blobs']=sorted(set(entry['blobs']+[p['body_sha256'],p['raw_body_sha256']]))
                entry['status']='RENDER_REQUIRED'
            elif role=='REPORT_SEMANTIC':
                p['semantic']={'key':ctx['semantic_key'],'request_id':payload['request_id'],**deepcopy(result)}
                entry['status']='VISUAL_REQUIRED' if result['verdict']=='PASS' else 'BLOCKED'
                # The semantic review exposes a research need. It cannot insert
                # the missing lemma into scientific records or mark it proved.
                for finding in result['findings']:
                    if finding['code'] in ('NEW_LEMMA_REQUIRED','SOURCE_PROOF_ERROR'):
                        from .obligations import make
                        oid=identity({'report':rid,'request':payload['request_id'],'finding':finding},'O-REPORT-')
                        criterion=sha((finding['code']+': '+finding['description']).encode())
                        state['obligations'][oid]=make(oid,'ESTABLISH',entry['scope']['target_refs']+entry['scope']['candidate_refs'],criterion,
                            created_by={'report_id':rid,'review_request_id':payload['request_id'],'finding_code':finding['code'],'anchor':finding['anchor']})
                        entry.setdefault('open_research_requests',[]).append({'obligation_id':oid,'reason':finding['code'],'anchor':finding['anchor'],
                            'description':finding['description'],'request_id':payload['request_id'],'state':'OPEN'})
            else:
                for page in result['pages']:p['visual'][page['id']]={**deepcopy(page),'request_id':payload['request_id'],'render_identity':ctx['render_identity']}
                entry['status']='BLOCKED' if any(page['verdict']=='REVISE' for page in result['pages']) else 'VISUAL_REQUIRED'
            # A valid role disposition closes only this reporting consumer. It
            # neither qualifies a proof nor closes an objection's research duty.
            for binding in task.get('obligation_bindings',[]):
                duty=state['obligations'][binding['obligation_id']]
                require(duty['definition']['type']=='REPORT','REPORT_SCOPE_INVALID','Report task must discharge a report responsibility')
                projection=duty['projection'];projection['work_state']='ATTEMPTED'
                projection['attempt_refs']=list(dict.fromkeys(projection['attempt_refs']+[payload['request_id']]))
                projection['consumer_resolutions'][binding['binding_id']]='SATISFIED_FOR_CONSUMER'
                if len(projection['consumer_resolutions'])==len(duty['definition']['consumer_bindings']):projection['resolution']='SATISFIED_FOR_CONSUMER'
        elif kind=='REPORT_RENDERED':
            require(p['revision']==payload.get('revision',p['revision']),'REPORT_REVISION_STALE','Render revision changed')
            require(content_key(p)==payload['content_key'],'REPORT_CONTENT_STALE','Report changed during rendering')
            output=deepcopy(payload['render'])
            require(not output['synthetic'] or state.get('synthetic_test_only'),'SYNTHETIC_RENDER_FORBIDDEN','Test images cannot enter a real project')
            require(0<len(output['pages'])<=entry['limits']['max_pages'],'REPORT_PAGE_LIMIT','Report exceeds its frozen page limit')
            old=p['render'];old_visual=p['visual'];p['render']=output
            if output['semantic_policy']!=p['semantic_policy']:
                p['semantic_policy']=output['semantic_policy'];p['semantic']=None
            # Byte-identical pages can be reused only if the previous content
            # and semantics are unchanged; changed pagination includes neighbors.
            affected=set(range(len(output['pages'])))
            if old and old.get('content_key')==content_key(p) and old.get('semantic_policy')==output['semantic_policy']:
                changed={i for i in range(max(len(old['pages']),len(output['pages'])))
                         if i>=len(old['pages']) or i>=len(output['pages']) or old['pages'][i]['sha256']!=output['pages'][i]['sha256']}
                affected={j for i in changed for j in (i-1,i,i+1) if 0<=j<len(output['pages'])}
            p['visual']={page['id']:old_visual[page['id']] for i,page in enumerate(output['pages'])
                         if i not in affected and old_visual.get(page['id'],{}).get('sha256')==page['sha256']}
            entry['files'].update(payload['files']);entry['blobs']=sorted(set(entry['blobs']+payload['blobs']))
            entry['status']='SEMANTIC_REQUIRED' if not p['semantic'] else 'VISUAL_REQUIRED'
        elif kind=='REPORT_REVISED':
            require(len(entry['failure_history'])<entry['limits']['max_repairs'],'REPORT_REPAIR_LIMIT','Persistent repair allowance exhausted')
            require(payload['reason'] and payload.get('expected_revision',p['revision'])==p['revision'] and payload['expected_content']==content_key(p),'REPORT_CONTENT_STALE','Exact bounded repair required')
            old=deepcopy(p);entry['failure_history'].append({'profile':profile,**payload})
            replacement=_profile();replacement['revision']=p['revision']+1;replacement['history']=p['history']+[old];replacement['feedback']=[payload['reason']]
            entry['profiles'][profile]=replacement
            if profile=='lecture' and not survey_report(entry):
                old_minimal=entry['profiles']['minimal'];entry['profiles']['minimal']=_profile();entry['profiles']['minimal']['revision']=old_minimal['revision']+1;entry['profiles']['minimal']['history']=old_minimal['history']+[old_minimal]
            entry['status']='AUTHOR_REQUIRED'
        elif kind=='REPORT_COMPLETED':
            require(payload.get('profile_revisions')=={name:value['revision'] for name,value in entry['profiles'].items()},'REPORT_REVISION_STALE','Completion must bind every selected profile revision')
            require(pair_complete(entry),'REPORT_REVIEWS_INCOMPLETE','Every selected profile requires independent semantic and every-page checks')
            entry['status']='COMPLETE';entry['bundle_id']=identity({'report':rid,'profiles':{p:content_key(entry['profiles'][p]) for p in selected_profiles(entry)}},'BUNDLE-')
        elif kind=='REPORT_FAILED':
            require(payload.get('code') and payload.get('message'),'REPORT_EVENT_INVALID','Concrete report failure required')
            entry['status']='BLOCKED';entry['failure_history'].append(deepcopy(payload))
        elif kind=='REPORT_ABANDONED':
            require(payload.get('reason') and payload.get('prior_classification'),'REPORT_EVENT_INVALID','Explicit reason and damage facts required')
            entry['abandonment']=deepcopy(payload);entry['status']='ABANDONED'
            iid=entry['scope']['instance_ids'][0]
            if state['active_reports'].get(iid)==rid:state['active_reports'].pop(iid)
        else:require(False,'REPORT_EVENT_INVALID','Unsupported report event')
    state.setdefault('report_events',{})[event['event_id']]=deepcopy(event)
    return state


def create(store,instance_id,mission_id=None,*,limits=None,profiles=None,plan_ref=None):
    snapshot=store.read_snapshot();iid=instance_id
    selected=catalog_service.scope(snapshot,iid,mission_id,plan_ref=plan_ref)
    is_survey=snapshot['instances'][iid]['kind']=='SURVEY'
    if is_survey:
        from . import survey
        require(survey.report_current(snapshot,selected),'SURVEY_NOT_READY','The selected Survey knowledge and readiness must still be current.')
        names=tuple(selected.get('profiles') or ([selected['profile']] if selected.get('profile') else []))
        require(len(names)==1 and names[0] in SURVEY_PROFILES,'REPORT_PROFILE_REQUIRED','Select one explicit Survey output plan.')
        require(profiles is None or tuple(profiles)==names,'REPORT_PROFILE_MISMATCH','Requested profile must match the frozen output plan.')
    else:
        require(profiles is None or tuple(profiles)==PROFILES,'REPORT_PROFILE_MISMATCH','TRW and TFDW retain the lecture/minimal pair.')
        require(plan_ref is None,'REPORT_SCOPE_INVALID','Survey output plans belong to Survey instances.')
        names=PROFILES
    active=snapshot.get('active_reports',{}).get(iid)
    if active:
        existing=snapshot['reports'][active];classification=catalog_service.classify(store,snapshot,existing)
        require(classification not in ('DAMAGED_ACTIVE_ARTIFACT','UNKNOWN_FORMAT'),'DAMAGED_ACTIVE_ARTIFACT','Explicit repair or abandonment required; active damage cannot be silently skipped')
        if classification in ('RECOVERABLE_ACTIVE_CANDIDATE','COMPLETED_CURRENT_REPORT') and existing['scope']['mission_ids']==selected['mission_ids'] and (not is_survey or existing['scope'].get('survey_plan_ref')==selected.get('survey_plan_ref')):return active
    frozen=catalog_service.freeze(snapshot,selected);digest=store.blob(canonical(frozen));rid='REPORT-'+secrets.token_hex(12)
    bound_limits={'max_tasks':64,'max_repairs':4,'max_pages':120}
    for key,value in (limits or {}).items():
        require(key in bound_limits and type(value) is int and value>0,'REPORT_LIMIT_INVALID','Positive known resource limit required');bound_limits[key]=value
    entry={'schema':SCHEMA,'report_id':rid,'scope':selected,'scope_fingerprint':identity(frozen),'snapshot_ref':digest,
           'profiles':{name:_profile() for name in names},'status':'AUTHOR_REQUIRED','files':{},'blobs':[digest],
           'record_refs':sorted(frozen['records']),'limits':bound_limits,'failure_history':[],
           'plan_ref':identity({'snapshot':digest,'limits':bound_limits},'REPORT-PLAN-'),'open_research_requests':[]}
    if is_survey:entry.update(workflow_kind='SURVEY',selected_profiles=list(names),output_plan_ref=selected['survey_plan_ref'])
    path=f'reports/{selected["scope_id"]}/{rid}/snapshot.json';immutable(store.root/path,canonical(frozen));entry['files'][path]=digest
    store.commit_report(_event('REPORT_CREATED',rid,{'entry':entry}));return rid


def prepare(store,instance_id,mission_id=None,*,check_only=False,report_id=None,plan_ref=None):
    if check_only:
        snapshot=store.read_snapshot();selected=catalog_service.scope(snapshot,instance_id,mission_id,plan_ref=plan_ref)
        return {'state':'CHECK_ONLY','scope':selected,'scope_fingerprint':catalog_service.fingerprint(snapshot,selected),
                'catalog':catalog_service.catalog(store,snapshot,instance_id),'model_calls':0,'writes':0}
    rid=report_id or create(store,instance_id,mission_id,plan_ref=plan_ref);snapshot=store.read_snapshot()
    require(rid in snapshot['reports'] and snapshot['reports'][rid]['scope']['instance_ids']==[instance_id],
            'REPORT_SCOPE_INVALID','The pinned report belongs to another instance.')
    entry=snapshot['reports'][rid]
    if entry['status']=='ABANDONED':return {'state':'REPORT_ABANDONED','report_id':rid,'model_calls':0}
    classification=catalog_service.classify(store,snapshot,entry)
    require(classification not in ('DAMAGED_ACTIVE_ARTIFACT','UNKNOWN_FORMAT'),'DAMAGED_ACTIVE_ARTIFACT','Active report is not intact')
    require(classification!='STALE_CANDIDATE','REPORT_SNAPSHOT_STALE','Pinned report inputs changed; preserve its attempt and select a new plan explicitly.')
    if entry['status']=='COMPLETE':return {'state':'COMPLETED_CURRENT_REPORT','report_id':rid,'model_calls':0}
    if entry['status']=='BLOCKED':return {'state':'REPORT_BLOCKED','report_id':rid,'failure_history':entry['failure_history'],'model_calls':0}
    if pair_complete(entry):return {'state':'REPORT_PAIR_READY','report_id':rid,'model_calls':0}
    profile=next(name for name in selected_profiles(entry) if not profile_complete(entry['profiles'][name]));p=entry['profiles'][profile]
    if p['body_sha256'] and not p['render']:return {'state':'RENDER_REQUIRED','profile':profile,'report_id':rid,'model_calls':0}
    role='REPORT_AUTHOR' if not p['body_sha256'] else 'REPORT_SEMANTIC' if not p['semantic'] else 'REPORT_VISUAL'
    count=sum(t.get('report_context',{}).get('report_id')==rid for t in snapshot['tasks'].values())
    require(count<entry['limits']['max_tasks'],'REPORT_TASK_LIMIT','Persistent report task allowance exhausted')
    ctx={'report_id':rid,'profile':profile,'role':role,'revision':p['revision'],'snapshot_ref':entry['snapshot_ref'],
         'content_key':content_key(p),'body_sha256':p['body_sha256'],'semantic_key':semantic_key(p),
         'scope_fingerprint':entry['scope_fingerprint'],'files':{'snapshot.json':entry['snapshot_ref']}}
    frozen=loads(store.read_blob(entry['snapshot_ref']))
    if survey_report(entry):ctx.update(workflow_kind='SURVEY',output_plan=deepcopy(frozen.get('survey_output_plan',{})))
    if role!='REPORT_VISUAL':
        ctx['files'].update({'record-'+r+'.txt':v['body_sha256'] for r,v in frozen['records'].items()})
        ctx['files'].update({'source-'+r+'.bin':v['blob_hash'] for r,v in frozen['sources'].items()})
        ctx['files'].update({'source-'+r+'-extracted.txt':digest for r,digest in frozen.get('source_texts',{}).items()})
    if p['body_sha256']:ctx['files']['body.tex']=p['body_sha256']
    if role=='REPORT_AUTHOR':
        ctx['feedback']=deepcopy(p['feedback'])
        ctx['statement_bodies']={r:store.read_blob(snapshot['records'][r]['body_sha256']).decode('utf-8')
            for r in entry['scope']['target_refs']+entry['scope']['candidate_refs']}
        if profile=='minimal' and not survey_report(entry):
            lecture=entry['profiles']['lecture'];ctx.update(parent_lecture=content_key(lecture),shared_statements=lecture['shared_statements'],notation_tex=lecture['notation_tex'])
            ctx['files']['accepted-lecture.tex']=lecture['body_sha256']
    elif role=='REPORT_VISUAL':
        # Layout review consumes the exact rendered draft and page neighborhood.
        # Mathematical evidence remains in the independent semantic task.
        ctx['files'].pop('snapshot.json')
        ctx['visual_manifest']={'snapshot_ref':entry['snapshot_ref'],'scope_fingerprint':entry['scope_fingerprint'],
            'content_key':content_key(p),'notation_tex':p['notation_tex'],'render_identity':p['render']['identity']}
        pages=p['render']['pages'];pending=[i for i,page in enumerate(pages) if page['id'] not in p['visual']][:8]
        ctx['pages']=[pages[i] for i in pending];ctx['render_identity']=p['render']['identity']
        adjacent={j for i in pending for j in (i-1,i+1) if 0<=j<len(pages)}-set(pending)
        ctx['context_pages']=[pages[i] for i in sorted(adjacent)]
        ctx['files'].update({page['id']+'.png':page['sha256'] for page in ctx['pages']+ctx['context_pages']})
    return {'state':'ROLE_REQUIRED','report_id':rid,'profile':profile,'role':role,'report_context':ctx,'model_calls':0}


def render(store,renderer,instance_id,profile=None,*,report_id=None):
    rid=report_id or create(store,instance_id);snapshot=store.read_snapshot();entry=snapshot['reports'][rid]
    require(entry['scope']['instance_ids']==[instance_id],'REPORT_SCOPE_INVALID','Pinned report instance differs.')
    require(catalog_service.classify(store,snapshot,entry)=='RECOVERABLE_ACTIVE_CANDIDATE','REPORT_NOT_CURRENT','Intact current report required')
    profile=profile or next((p for p in selected_profiles(entry) if entry['profiles'][p]['body_sha256'] and not entry['profiles'][p]['render']),None)
    require(profile in selected_profiles(entry),'REPORT_RENDER_NOT_READY','Select an authored profile');p=entry['profiles'][profile]
    body=store.read_blob(p['body_sha256'])
    try:
        from .resources import reserve
        estimate=renderer.resource_estimate() if hasattr(renderer,'resource_estimate') else {'temporary_bytes':256*1024**2,'memory_bytes':256*1024**2}
        with reserve(store.root,owner='render-'+rid,temporary_bytes=estimate['temporary_bytes'],memory_bytes=estimate['memory_bytes'],max_preparations=min(2,snapshot.get('max_workers',1))):
            output=renderer(body,synthetic=bool(snapshot.get('synthetic_test_only')))
    except Exception as error:
        store.commit_report(_event('REPORT_FAILED',rid,{'code':getattr(error,'code','REPORT_RENDER_FAILED'),'message':str(error),'profile':profile,'revision':p['revision']},profile));raise
    require(set(output)=={'pdf','tex','pages','semantic_environment','environment','synthetic'},'REPORT_RENDER_FIELDS','Exact renderer outputs required')
    require(output['pdf'].startswith(b'%PDF-') and output['pages'],'REPORT_RENDER_INVALID','Actual PDF and all pages required')
    pages=[];blobs=[store.blob(output['pdf']),store.blob(output['tex'])]
    for number,page in enumerate(output['pages'],1):
        require(page.startswith(b'\x89PNG\r\n\x1a\n'),'REPORT_PAGE_INVALID','PNG page required')
        digest=store.blob(page);blobs.append(digest);pages.append({'id':profile+'-'+str(number),'sha256':digest})
    value={'pdf_sha256':blobs[0],'tex_sha256':blobs[1],'pages':pages,'semantic_environment':output['semantic_environment'],
           'semantic_policy':output['semantic_environment'].get('mathematical_semantics',tex_semantic_identity()),
           'environment':output['environment'],'synthetic':output['synthetic'],'content_key':content_key(p)}
    value['identity']=identity(value);files={}
    root=f'reports/{entry["scope"]["scope_id"]}/{rid}/{profile}/{value["identity"]}'
    for name,digest in [('report.pdf',blobs[0]),('report.tex',blobs[1])]+[(p['id']+'.png',p['sha256']) for p in pages]:
        relative=root+'/'+name;immutable(store.root/relative,store.read_blob(digest));files[relative]=digest
    store.commit_report(_event('REPORT_RENDERED',rid,{'content_key':content_key(p),'revision':p['revision'],'render':value,'files':files,'blobs':blobs},profile))
    return {'report_id':rid,'profile':profile,'render':value,'model_calls':0}


def finish(store,instance_id,*,report_id=None):
    snapshot=store.read_snapshot();rid=report_id or snapshot.get('active_reports',{}).get(instance_id)
    require(rid in snapshot['reports'],'REPORT_REQUIRED','No selected report')
    require(snapshot['reports'][rid]['scope']['instance_ids']==[instance_id],'REPORT_SCOPE_INVALID','Pinned report instance differs.')
    require(catalog_service.classify(store,snapshot,snapshot['reports'][rid]) in ('RECOVERABLE_ACTIVE_CANDIDATE','COMPLETED_CURRENT_REPORT'),'REPORT_NOT_CURRENT','Intact current scope required')
    store.commit_report(_event('REPORT_COMPLETED',rid,{'profile_revisions':{name:p['revision'] for name,p in snapshot['reports'][rid]['profiles'].items()}}))
    return {'state':'COMPLETED_CURRENT_REPORT','report_id':rid,'bundle_id':store.read_snapshot()['reports'][rid]['bundle_id'],'model_calls':0}


def revise(store,instance_id,profile,reason,*,report_id=None):
    snapshot=store.read_snapshot();rid=report_id or snapshot.get('active_reports',{}).get(instance_id)
    require(rid in snapshot['reports'],'REPORT_REQUIRED','No selected report')
    entry=snapshot['reports'][rid]
    require(entry['scope']['instance_ids']==[instance_id],'REPORT_SCOPE_INVALID','Pinned report instance differs.')
    require(profile in selected_profiles(entry),'REPORT_PROFILE_MISMATCH','Revise only an actual profile of the selected report.')
    require(catalog_service.classify(store,snapshot,entry) not in ('DAMAGED_ACTIVE_ARTIFACT','UNKNOWN_FORMAT'),'DAMAGED_ACTIVE_ARTIFACT','Do not conceal damage through revision')
    receipt=store.commit_report(_event('REPORT_REVISED',rid,{'reason':reason,'expected_revision':entry['profiles'][profile]['revision'],'expected_content':content_key(entry['profiles'][profile])},profile))
    return {**receipt,'report_id':rid}


def abandon(store,instance_id,reason,*,report_id=None):
    snapshot=store.read_snapshot();rid=report_id or snapshot.get('active_reports',{}).get(instance_id)
    require(rid in snapshot['reports'],'REPORT_REQUIRED','No selected report')
    entry=snapshot['reports'][rid]
    require(entry['scope']['instance_ids']==[instance_id],'REPORT_SCOPE_INVALID','Pinned report instance differs.')
    receipt=store.commit_report(_event('REPORT_ABANDONED',rid,{'reason':reason,'prior_classification':catalog_service.classify(store,snapshot,entry)}))
    return {**receipt,'report_id':rid}


catalog=catalog_service.catalog
classify=catalog_service.classify
_profile_complete=profile_complete


def _assign_role(store,instance_id,prepared):
    """Create one bounded report responsibility under the existing mission."""
    from . import execution,obligations
    snapshot=store.read_snapshot();ctx=prepared['report_context'];entry=snapshot['reports'][ctx['report_id']]
    require(entry['status']!='ABANDONED','REPORT_ABANDONED','An abandoned report cannot assign new work.')
    mission_id=next(iter(entry['scope']['mission_ids']),None)
    require(mission_id in snapshot['missions'],'AUTHORIZATION_REQUIRED','Formal report needs an authorized current mission')
    mission=snapshot['missions'][mission_id]
    require(mission['authorized_scope'].get('reports') is True or 'REPORT' in mission['authorized_scope'].get('obligation_types',[]),
            'AUTHORIZATION_REQUIRED','This mission has no reporting authorization')
    key=identity({'report':ctx['report_id'],'profile':ctx['profile'],'role':ctx['role'],'revision':ctx['revision'],
                  'content':ctx['content_key'],'semantics':ctx['semantic_key'],'pages':ctx.get('pages',[])})
    oid='O-REPORT-'+key;bid='B-REPORT-'+key;gid='G-REPORT-'+key;method='REPORT-METHOD-'+key
    if oid in snapshot['obligations']:return oid
    kind=snapshot['instances'][instance_id]['kind']
    stage={'TRW':'P13','TFDW':'D5'}.get(kind)
    if kind=='SURVEY':stage='S6' if ctx['role']=='REPORT_AUTHOR' else 'S7'
    require(stage is not None,'WORKFLOW_KIND_INVALID','Report workflow is not registered')
    criterion=store.blob(('Produce the exact '+ctx['role']+' disposition for '+ctx['profile']+' under frozen report scope '+key+'.').encode())
    author=entry['profiles'][ctx['profile']]['author_request_id']
    consumer={'binding_id':bid,'instance_id':instance_id,'mission_id':mission_id,'stage_id':stage,'role':ctx['role'],
              'retry_grant_id':gid,'method_ref':method,'scope':{'report_id':ctx['report_id'],'profile':ctx['profile']},
              'report_context':deepcopy(ctx),'entry_basis':{'formal_report_requested':True},
              'threshold':'WORK_DISPOSITION_RECORDED',
              'author_execution_event':snapshot.get('requests',{}).get(author,{}).get('execution_id')}
    # The report consumes the full frozen dependency closure, but its duty is
    # authorized against the selected roots rather than inventing new targets.
    roots=snapshot['survey_output_plans'][entry['scope']['survey_plan_ref']]['selected_refs'] if survey_report(entry) else entry['scope']['target_refs']+entry['scope']['candidate_refs']
    duty=obligations.make(oid,'REPORT',roots,criterion,
                         consumer_bindings=[consumer],created_by=ctx['report_id'],effect='REPORT_PRESENTATION')
    store.commit_execution(execution.event('ASSIGN_OBLIGATION',{'instance_id':instance_id,'mission_id':mission_id,
        'obligation':duty,'retry_grant':{'grant_id':gid,'obligation_id':oid,'method_ref':method,'max_research_attempts':1},
        'authorization_basis_ref':entry['plan_ref']}))
    return oid


def run(store,instance_id,*,executor=None,policy=None,renderer=None,max_tasks=None,report_id=None,plan_ref=None):
    """Drive only this exact report with native tasks, persistent budgets and captures.

    Existing research work is never dispatched as a side effect of this entry.
    UNKNOWN requests retain their reservation and stop the report for recovery.
    """
    from . import runner,scheduler,execution
    from .render import Renderer
    executor=executor or runner.CodexExecutor();renderer=renderer or Renderer();policy=policy or {}
    require(max_tasks is None or type(max_tasks) is int and 1<=max_tasks<=1000,'REPORT_TASK_LIMIT','Bounded report batch required')
    performed=[];recovered=[];previous_step=None
    with runner.coordinator(store):
        rid=report_id or create(store,instance_id,plan_ref=plan_ref)
        # Survey output plans can coexist. Resolve future role configuration
        # from the exact mission bound to this report, even after another
        # activity becomes current on the same instance.
        pinned=store.read_snapshot()['reports'][rid]
        dispatch_policy={'mission_policies':True} if survey_report(pinned) else policy
        while True:
            prepared=prepare(store,instance_id,report_id=rid);state=prepared['state']
            step=identity(prepared);require(step!=previous_step,'REPORT_NO_PROGRESS','Report operation made no durable progress; preserve its exact state for diagnosis')
            previous_step=step
            if state=='REPORT_PAIR_READY':prepared=finish(store,instance_id,report_id=rid);state=prepared['state']
            if state in ('COMPLETED_CURRENT_REPORT','REPORT_BLOCKED','REPORT_ABANDONED'):
                return {**prepared,'tasks':performed,'recovered_requests':recovered,'model_calls':len(performed)}
            if state=='RENDER_REQUIRED':
                render(store,renderer,instance_id,prepared['profile'],report_id=rid);continue
            require(state=='ROLE_REQUIRED','REPORT_STATE_INVALID',state)
            if max_tasks is not None and len(performed)>=max_tasks:
                return {'state':'REPORT_BATCH_LIMIT','report_id':rid,'tasks':performed,'model_calls':len(performed)}
            oid=_assign_role(store,instance_id,prepared)
            snapshot=store.read_snapshot()
            requests=[r for r in snapshot['requests'].values() if any(b['obligation_id']==oid for b in snapshot['tasks'][r['task_id']]['obligation_bindings'])]
            pending=[r for r in requests if r['execution_state'] in ('PREPARED','RESERVED','SENT','UNKNOWN','CAPTURED')]
            if pending:
                request=sorted(pending,key=lambda r:r['request_id'])[0]
                if request.get('fenced'):
                    return {'state':'WAIT','code':'TASK_FENCED','report_id':rid,'request_id':request['request_id'],'tasks':performed,'model_calls':len(performed)}
                if request['execution_state']=='CAPTURED':
                    execution.recover(store,request['request_id']);recovered.append(request['request_id']);continue
                if request['execution_state'] in ('RESERVED','SENT','UNKNOWN'):
                    return {'state':'WAIT','code':'UNKNOWN_REQUIRES_EVIDENCE' if request['execution_state']=='UNKNOWN' else 'EXISTING_REQUEST',
                            'report_id':rid,'request_id':request['request_id'],'tasks':performed,'model_calls':len(performed)}
                tid=request['task_id']
            else:
                # Narrow the planner's candidate set without changing stored
                # responsibilities, global worker reservations or budget facts.
                view=deepcopy(snapshot)
                for key,duty in view['obligations'].items():
                    if key!=oid:duty['definition']['consumer_bindings']=[]
                if survey_report(pinned):dispatch_policy={**dispatch_policy,'max_workers':snapshot.get('max_workers',1)}
                plan=scheduler.plan(view,[instance_id],dispatch_policy)
                plan['selected']=[r for r in plan['selected'] if r['obligation_id']==oid]
                plan['actions']=[]
                if not plan['selected']:
                    return {'state':'WAIT','report_id':rid,'reasons':plan['waits'],'tasks':performed,'model_calls':len(performed)}
                made=scheduler.commit_dispatch(store,plan,policy=dispatch_policy);tid=made['prepared'][0]['task_id']
            result=executor.execute(store,tid);performed.append(tid)
            if result.get('state') not in ('ACCEPTED','EXACT_DUPLICATE'):
                return {'state':'REPORT_BLOCKED','report_id':rid,'reason':result,'tasks':performed,'model_calls':len(performed)}


def demo_payload(task,snapshot):
    """Deterministic synthetic fixture output; it cannot run in a real project."""
    require(snapshot.get('synthetic_test_only') is True,'SYNTHETIC_CAPTURE_FORBIDDEN','Demo reports are test evidence only')
    ctx=task['report_context'];profile=ctx['profile'];role=task['role'];entry=snapshot['reports'][ctx['report_id']]
    if role=='REPORT_SEMANTIC':return {'profile':profile,'verdict':'PASS','findings':[],'uncheckable':[]}
    if role=='REPORT_VISUAL':return {'profile':profile,'pages':[{'id':p['id'],'sha256':p['sha256'],'verdict':'PASS','findings':[]} for p in ctx['pages']]}
    def tex_text(text):
        substitutions={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','$':r'\$','%':r'\%','&':r'\&','#':r'\#','_':r'\_','^':r'\textasciicircum{}','~':r'\textasciitilde{}'}
        return ''.join(substitutions.get(c,c) for c in text)
    omissions=[];included=[];shared=[]
    if profile=='minimal' and not survey_report(entry):
        lecture=entry['profiles']['lecture'];shared=deepcopy(lecture['shared_statements']);notation=lecture['notation_tex'];parent=content_key(lecture)
        included=deepcopy(lecture['included_refs']);omissions=deepcopy(lecture['omissions'])
    else:
        notation='No additional notation is introduced.';parent=None
        for ref,body in ctx.get('statement_bodies',{}).items():
            try:authored_english(body,'exact statement')
            except PMRSError:
                omissions.append({'ref':ref,'reason':'An exact English mathematical formulation has not been established; the original source remains available.'});continue
            boundary='INCONCLUSIVE' if survey_report(entry) else 'OPEN' if ref in entry['scope']['target_refs'] else 'CANDIDATE'
            shared.append({'id':'S'+str(len(shared)+1),'statement_tex':tex_text(body),'status':boundary,'source_refs':[ref]});included.append(ref)
    body=r'\section{Introduction}'+'\nThis synthetic workflow demonstration records an open research question and its available candidates. No proof or formal verification is claimed.\n'+r'\section{Notation}'+'\n{{notation}}\n'+r'\section{Research statements}'+'\n'
    body+='\n'.join('{{statement:'+s['id']+'}}' for s in shared)
    body+='\n'+r'\section{Evidence and open work}'+'\nThe supplied original materials and scoped research records remain the evidence boundary. Candidate statements are not established theorems. Missing arguments and open obligations require further authorized research.\n'
    coverage={k:'The scoped snapshot is accounted for; no missing proof is represented as established.' for k in COVERAGE}
    return {'profile':profile,'body':body,'notation_tex':notation,'shared_statements':shared,'coverage':coverage,'included_refs':included,'omissions':omissions,'parent_lecture':parent}
