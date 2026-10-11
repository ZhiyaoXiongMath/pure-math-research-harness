"""Exact manuscript ranges and deterministic local revision assembly.

Only this host code splices a local revision. Author text, manuscript text and
quoted user material never select a different project, version or byte range.
"""
from copy import deepcopy
import re
from .util import require, sha

SECTION = re.compile(rb'(?m)^\\section\{([^{}\r\n]+)\}[^\S\r\n]*(?:\r?\n|$)')


def sections(body):
    raw = body.encode('utf-8') if isinstance(body, str) else body
    require(isinstance(raw, bytes), 'REPORT_BODY_REQUIRED', 'Exact manuscript bytes required.')
    matches = list(SECTION.finditer(raw)); result = []
    for index, match in enumerate(matches):
        start = match.start(); end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        title = match.group(1).decode('utf-8')
        result.append({'id': 'SECTION-' + str(index + 1) + '-' + sha(match.group(1))[:12],
                       'number': index + 1, 'title': title, 'start_byte': start,
                       'end_byte': end, 'sha256': sha(raw[start:end])})
    return result


def normalize_scope(body, scope):
    require(isinstance(scope, dict), 'REPORT_REVISION_SCOPE', 'Explicit full or exact section scope required.')
    if scope == {'kind': 'FULL'}:
        return deepcopy(scope)
    require(set(scope) == {'kind', 'sections'} and scope['kind'] == 'SECTIONS'
            and isinstance(scope['sections'], list) and scope['sections']
            and all(isinstance(s, str) for s in scope['sections'])
            and len(set(scope['sections'])) == len(scope['sections']),
            'REPORT_REVISION_SCOPE', 'A unique nonempty list of selected section identities is required.')
    directory = sections(body); selected = set(scope['sections'])
    require(selected <= {s['id'] for s in directory}, 'REPORT_REVISION_SCOPE', 'Selected section is absent from the exact old manuscript.')
    return {'kind': 'SECTIONS', 'sections': [s['id'] for s in directory if s['id'] in selected],
            'ranges': [s for s in directory if s['id'] in selected]}


def assemble(old, scope, replacements):
    """Preserve every unselected byte, including comments and whitespace."""
    require(isinstance(replacements, list) and len(replacements) == len(scope['ranges']),
            'REPORT_REVISION_RANGE', 'Return each selected section exactly once.')
    supplied = {}
    for row in replacements:
        require(isinstance(row, dict) and set(row) == {'section_id', 'body'}
                and isinstance(row['body'], str) and row['section_id'] not in supplied,
                'REPORT_REVISION_RANGE', 'Each replacement requires one exact section identity and body.')
        supplied[row['section_id']] = row['body'].encode('utf-8')
    require(set(supplied) == set(scope['sections']), 'REPORT_REVISION_RANGE', 'Author cannot enlarge the selected section scope.')
    cursor = 0; parts = []; preserved = []
    for row in scope['ranges']:
        start, end = row['start_byte'], row['end_byte']
        require(sha(old[start:end]) == row['sha256'], 'REPORT_CONTENT_STALE', 'Selected original section bytes changed.')
        unchanged = old[cursor:start]; parts.append(unchanged)
        preserved.append({'start_byte': cursor, 'end_byte': start, 'sha256': sha(unchanged)})
        replacement = supplied[row['id']]
        heading = SECTION.match(old[start:end]); new_heading = SECTION.match(replacement)
        require(heading and new_heading and heading.group(1) == new_heading.group(1)
                and len(sections(replacement)) == 1,
                'REPORT_REVISION_RANGE', 'Local revision retains its selected heading and cannot insert other sections.')
        parts.append(replacement); cursor = end
    parts.append(old[cursor:]); preserved.append({'start_byte': cursor, 'end_byte': len(old), 'sha256': sha(old[cursor:])})
    return b''.join(parts), preserved


AUTHORIZATION_SCHEMA='pmrs.report-human-authorization/1'
AUTHORIZATION_FIELDS={'schema','authorization_id','operation_id','origin','instance_id','report_id','profile',
    'expected_revision','expected_body_sha256','expected_snapshot_ref','instruction_ref','scope','requirement_refs','report_calls'}


def compact_authorization(value):
    if value.get('schema')==AUTHORIZATION_SCHEMA:
        return {k:deepcopy(v) for k,v in value.items() if k in AUTHORIZATION_FIELDS|{'event_ref'}}
    return {k:deepcopy(v) for k,v in value.items() if k not in {'instruction','constraints','report_calls','report_allowance'}}


def validate_authorization_snapshot(snapshot,authorization):
    """Read historical assistant receipts, or a real direct human report event."""
    require(isinstance(authorization,dict),'REPORT_AUTHORIZATION_REQUIRED','An original human report authorization is required.')
    if authorization.get('schema')!=AUTHORIZATION_SCHEMA:
        # Compatibility only: this call does not create or run an assistant.
        from .assistant import validate_revision_authorization_snapshot
        return validate_revision_authorization_snapshot(snapshot,authorization)
    value=compact_authorization(authorization)
    row=snapshot.get('report_authorizations',{}).get(value.get('authorization_id'))
    require(row==value,'REPORT_AUTHORIZATION_REQUIRED','Direct authorization must match the original immutable native event.')
    event=snapshot.get('report_events',{}).get(value.get('event_ref'),{})
    require(event.get('event_type')=='REPORT_HUMAN_AUTHORIZED' and event.get('payload',{}).get('authorization')=={k:v for k,v in value.items() if k!='event_ref'},
        'REPORT_AUTHORIZATION_REQUIRED','A model proposal cannot invent a human report instruction.')
    return deepcopy(value)


def validate_authorization(store,authorization):
    if authorization.get('schema')!=AUTHORIZATION_SCHEMA:
        from .assistant import validate_revision_authorization
        return validate_revision_authorization(store,authorization)
    value=validate_authorization_snapshot(store.read_snapshot(),authorization)
    raw=store.read_blob(value['instruction_ref'])
    require(sha(raw)==value['instruction_ref'],'ORIGINAL_BYTES_MISMATCH','Original report instruction changed.')
    value['instruction']=raw.decode('utf-8')
    value['constraints']=[store.read_blob(h).decode('utf-8') for h in value['requirement_refs']]
    value['report_allowance']=value['report_calls']
    return value


def authorization_allowance(snapshot,authorization):
    if authorization.get('schema')!=AUTHORIZATION_SCHEMA:
        from .assistant import report_allowance
        return report_allowance(snapshot,authorization['turn_id'])
    value=validate_authorization_snapshot(snapshot,authorization)
    return {'calls':value['report_calls'],'event_ref':value['event_ref'],'operation_id':value['operation_id']}


def instruction_ref(authorization):
    return authorization['instruction_ref'] if authorization.get('schema')==AUTHORIZATION_SCHEMA else authorization['message_body_ref']


def accumulated_requirements(entry,profile):
    requests=[r for r in entry.get('revision_requests',{}).values() if profile in r.get('profile_revisions',{})]
    if not requests:return []
    latest=max(requests,key=lambda r:r['profile_revisions'][profile])
    return list(latest.get('requirement_refs',[]))


def validate_human_authorization(snapshot,event):
    """Reducer validation at the human boundary, before any report call."""
    from . import contracts as C
    value=event['payload'].get('authorization');C.fields(value,AUTHORIZATION_FIELDS,'Human report authorization')
    require(value['schema']==AUTHORIZATION_SCHEMA and value['origin']=='HUMAN_UI','REPORT_AUTHORIZATION_REQUIRED','Direct explicit human authorization required.')
    require(all(isinstance(value[k],str) and value[k] for k in ('authorization_id','operation_id','instance_id','report_id','profile','expected_body_sha256','expected_snapshot_ref','instruction_ref')),
        'REPORT_AUTHORIZATION_REQUIRED','Exact report instruction identities required.')
    require(value['report_id']==event['report_id'] and value['profile']==event['profile'],'REPORT_AUTHORIZATION_MISMATCH','Authorization envelope differs.')
    entry=snapshot.get('reports',{}).get(value['report_id'],{});profile=entry.get('profiles',{}).get(value['profile'],{})
    require(entry.get('scope',{}).get('instance_ids')==[value['instance_id']] and value['expected_snapshot_ref']==entry.get('snapshot_ref')
        and type(value['expected_revision']) is int and value['expected_revision']==profile.get('revision')
        and value['expected_body_sha256']==profile.get('raw_body_sha256'),'REPORT_CONTENT_STALE','Select the actual exact report version before authorizing an edit.')
    require(snapshot.get('instances',{}).get(value['instance_id'],{}).get('status') in {'ACTIVE','PAUSED'},'REPORT_INSTANCE_ENDED','Report authorization cannot restart an ended research instance.')
    require(value['report_calls'] is None or type(value['report_calls']) is int and 1<=value['report_calls']<=1000,'REPORT_BUDGET_REQUIRED','Report authorization requires a finite call allowance.')
    C.refs(value['requirement_refs'],'report requirement refs',nonempty=True)
    require(all(C.HASH.fullmatch(h) for h in value['requirement_refs']) and C.HASH.fullmatch(value['instruction_ref']) and value['instruction_ref'] in value['requirement_refs'],
        'REPORT_AUTHORIZATION_MISMATCH','Exact original instruction and accumulated requirement blobs are required.')
    require(value['requirement_refs']==list(dict.fromkeys(accumulated_requirements(entry,value['profile'])+[value['instruction_ref']])),
        'REPORT_AUTHORIZATION_MISMATCH','Previously active report requirements must be carried forward.')
    scope=value['scope'];require(isinstance(scope,dict),'REPORT_REVISION_SCOPE','Exact scope required.')
    require(scope=={'kind':'FULL'} or set(scope)=={'kind','sections'} and scope['kind']=='SECTIONS' and isinstance(scope['sections'],list) and scope['sections']
        and len(scope['sections'])==len(set(scope['sections'])),'REPORT_REVISION_SCOPE','Explicit full or exact section scope required.')
    require(value['authorization_id'] not in snapshot.get('report_authorizations',{}),'REPORT_OPERATION_CONFLICT','Authorization identity already exists.')
    return {**deepcopy(value),'event_ref':event['event_id']}
