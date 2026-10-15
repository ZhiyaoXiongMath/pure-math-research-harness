"""Typed relation algebra: proof premises, provenance and withdrawal differ."""
from copy import deepcopy
from .primitives import require
from . import contracts as C
from .knowledge import source_use

# (source kinds, target kinds, enters mathematical closure)
REGISTRY = {
 'ARGUMENT_FOR': ({'Argument'},{'Statement'},True),
 'MATHEMATICAL_DEPENDENCY': ({'Argument'},{'Statement','Context','Argument'},True),
 'USED_SOURCE': ({'Argument','Example'},{'SourceOccurrence'},True),
 'SOURCE_PROVENANCE': (None,{'SourceOccurrence'},False),
 'REVIEW_TARGET': ({'Assessment'},set(C.KINDS)|{'InferenceBinding'},False),
 'RESPONDS_TO_FEEDBACK': ({'Argument','Statement'},{'Assessment'},False),
 'REVISION_OF': (set(C.KINDS),set(C.KINDS),False),
 'SUPERSEDES': ({'SelectionEvent'},None,False),
 'ADDRESSES_OBLIGATION': (set(C.KINDS)|{'AttemptOutcome'},{'Obligation'},False),
 'INVALIDATES_SUPPORT': ({'Withdrawal'},{'SupportBinding','Qualification'},False),
 'COUNTEREXAMPLE_TO': ({'Example','Argument'},{'Statement'},True),
 'APPLIES_TO': ({'Argument'},{'Statement','Argument'},True),
 'IMPLIES': ({'Statement'},{'Statement'},False),
 'EQUIVALENT_ON_SCOPE': ({'Statement'},{'Statement'},False),
 'MOTIVATED_BY': ({'Statement'},set(C.KINDS),False),
 'CALIBRATES': ({'Example','Test'},{'Statement'},False),
 'TRANSLATES': ({'TranslationArtifact'},set(C.KINDS)|{'SourceOccurrence'},False),
}
TYPES=frozenset(REGISTRY)
PREMISES=frozenset(k for k,v in REGISTRY.items() if v[2])
FIELDS={'relation_id','type','source_ref','target_ref','scope_context_refs','evidence_bindings','assertion_state','created_by_event'}

def kind_of(ref,snapshot):
    if ref in snapshot.get('records',{}):return snapshot['records'][ref]['kind']
    for name,kind in [('sources','SourceOccurrence'),('inferences','InferenceBinding'),('obligations','Obligation'),('supports','SupportBinding'),('qualifications','Qualification'),('withdrawals','Withdrawal'),('translations','TranslationArtifact'),('selection_events','SelectionEvent'),('attempt_outcomes','AttemptOutcome')]:
        if ref in snapshot.get(name,{}):return kind
    return None

def validate_relation(row,snapshot,blob_get=None):
    C.fields(row,FIELDS,'Relation');typ=row['type']
    require(typ in REGISTRY,'RELATION_TYPE_UNKNOWN',str(typ))
    a,b=kind_of(row['source_ref'],snapshot),kind_of(row['target_ref'],snapshot)
    expected_a,expected_b,_=REGISTRY[typ]
    require(a is not None and b is not None and (expected_a is None or a in expected_a) and (expected_b is None or b in expected_b),'RELATION_ENDPOINT_INVALID',typ)
    C.refs(row['scope_context_refs'],'relation scope',sorted_unique=True)
    require(all(kind_of(r,snapshot)=='Context' for r in row['scope_context_refs']),'RELATION_ENDPOINT_INVALID','Relation context')
    C.sequence(row['evidence_bindings'],'evidence_bindings')
    C.enum(row['assertion_state'],('PROPOSED','BOUND_TO_ARGUMENT','WITHDRAWN'),'relation state')
    if typ=='REVISION_OF':require(a==b,'RELATION_ENDPOINT_INVALID','Revision changes kind')
    record=snapshot.get('records',{}).get(row['source_ref'])
    if typ=='ARGUMENT_FOR':require(record['data']['conclusion_ref']==row['target_ref'],'RELATION_ENDPOINT_INVALID','Wrong argument conclusion')
    if typ=='MATHEMATICAL_DEPENDENCY':
        require(row['target_ref'] in [p['premise_ref'] for p in record['data']['premise_bindings']],'RELATION_ENDPOINT_INVALID','Premise must be explicitly bound')
    if typ=='USED_SOURCE':
        require(row['evidence_bindings'],'RESPONSE_SCHEMA_INVALID','USED_SOURCE needs SourceUse')
        for use in row['evidence_bindings']:
            source_use(use,snapshot.get('sources',{}),blob_get)
            require(use['source_ref']==row['target_ref'],'RELATION_ENDPOINT_INVALID','SourceUse target differs')
    if typ in ('IMPLIES','EQUIVALENT_ON_SCOPE','COUNTEREXAMPLE_TO','APPLIES_TO') and row['assertion_state']=='BOUND_TO_ARGUMENT':
        args=[v if isinstance(v,str) else v.get('argument_ref') for v in row['evidence_bindings']]
        require(all(kind_of(r,snapshot)=='Argument' for r in args) and len(args)>=(2 if typ=='EQUIVALENT_ON_SCOPE' else 1),'RELATION_ENDPOINT_INVALID','Bound relationship requires actual arguments')
    return row

def relation(source,target,kind,*,scope_context_refs=(),evidence_bindings=(),assertion_state='PROPOSED',created_by_event=None,provenance=None):
    require(kind in TYPES,'RELATION_TYPE_UNKNOWN',kind)
    content={'type':kind,'source_ref':source,'target_ref':target,'scope_context_refs':list(scope_context_refs),'evidence_bindings':list(evidence_bindings),'assertion_state':assertion_state,'created_by_event':created_by_event}
    return {'relation_id':'REL-'+C.digest(content),**content}

def is_premise(row):
    if row['type']=='USED_SOURCE':
        return any(u.get('usage_mode')!='METHOD_INSPIRATION' for u in row.get('evidence_bindings',[]))
    return row['type'] in PREMISES

def edges(snapshot):
    rows=snapshot.get('relations',[])
    return list(rows.values()) if isinstance(rows,dict) else rows

def premise_closure(roots,snapshot,*,include_method_sources=False):
    result=set(roots);todo=list(roots);records=snapshot.get('records',{})
    graph={}
    for row in edges(snapshot):
        if row['assertion_state']!='WITHDRAWN' and (is_premise(row) or include_method_sources and row['type']=='USED_SOURCE'):
            graph.setdefault(row['source_ref'],set()).add(row['target_ref'])
    while todo:
        ref=todo.pop();record=records.get(ref);targets=set(graph.get(ref,()))
        if record:
            targets.update(record['context_refs']);d=record['data']
            if record['kind']=='Context':targets.update(d['parent_context_refs'])
            if record['kind']=='Statement' and d['source_binding']:targets.add(d['source_binding']['source_ref'])
            if record['kind']=='SourceEvidence':targets.update(d['source_occurrence_refs'])
            if record['kind']=='Argument':
                targets.add(d['conclusion_ref']);targets.update(p['premise_ref'] for p in d['premise_bindings'])
                if d['mode']=='REDUCTION':targets.update(d['mode_payload']['inference_spec']['alternative_argument_refs'])
                if d['mode']=='APPLICABILITY':targets.update(d['mode_payload']['donor_refs']);targets.update(d['mode_payload']['hypothesis_discharge_refs'])
                if d['mode']=='COMPATIBILITY':targets.update(d['mode_payload']['witness_compatibility']['component_argument_refs'])
            if record['kind']=='Example':
                targets.update(d['target_refs'])
                if d['realization_argument_ref']:targets.add(d['realization_argument_ref'])
        if ref in snapshot.get('inferences',{}):targets.add(snapshot['inferences'][ref]['argument_ref'])
        for target in targets-result:result.add(target);todo.append(target)
    return result

def acyclic(rows,kinds=PREMISES):
    graph={}
    for row in rows:
        if row['type'] in kinds and is_premise(row) and row.get('assertion_state')!='WITHDRAWN':graph.setdefault(row['source_ref'],set()).add(row['target_ref'])
    _acyclic(graph)

def _acyclic(graph):
    active=set();done=set()
    def visit(v):
        require(v not in active,'CYCLIC_MATH_SUPPORT',v)
        if v in done:return
        active.add(v)
        for w in graph.get(v,()):visit(w)
        active.remove(v);done.add(v)
    for v in list(graph):visit(v)

def validate_support_graph(snapshot):
    _acyclic({ref:set(s.get('premise_support_refs',[])) for ref,s in snapshot.get('supports',{}).items()})

def affected_supports(snapshot,withdrawn_ids):
    """Reverse only actual selected support bindings; never substitute a path."""
    affected=set(withdrawn_ids);todo=list(affected);reverse={}
    for sid,support in snapshot.get('supports',{}).items():
        for premise in support.get('premise_support_refs',[]):reverse.setdefault(premise,set()).add(sid)
    while todo:
        for sid in reverse.get(todo.pop(),set())-affected:affected.add(sid);todo.append(sid)
    return affected

def closure(roots,relations,kinds=PREMISES):
    result=set(roots);todo=list(roots);graph={}
    for row in relations:
        if row['type'] in kinds and is_premise(row):graph.setdefault(row['source_ref'],set()).add(row['target_ref'])
    while todo:
        for ref in graph.get(todo.pop(),set())-result:result.add(ref);todo.append(ref)
    return result
