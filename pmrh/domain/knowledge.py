"""Six immutable scientific records, exact locators and host registries."""
from __future__ import annotations
from copy import deepcopy
from .primitives import require, sha, canonical
from . import contracts as C
from .primitives import authored_english, authored_with_quotes, research_data

def locator(data, start=0, end=None, unit='UTF8_BYTE'):
    raw=data.encode('utf-8') if isinstance(data,str) else data
    text=raw.decode('utf-8')
    measure=raw if unit=='UTF8_BYTE' else text
    end=len(measure) if end is None else end
    piece=measure[start:end]
    if isinstance(piece,str):piece=piece.encode('utf-8')
    result={'blob_hash':sha(raw),'unit':unit,'start':start,'end':end,'quoted_sha256':sha(piece)}
    validate_locator(result,lambda h:raw if h==sha(raw) else None)
    return result

def validate_locator(item, blob_get):
    C.fields(item,C.LOCATOR_FIELDS,'Locator')
    C.enum(item['unit'],('UTF8_BYTE','UNICODE_CODEPOINT'),'Locator.unit')
    require(C.HASH.fullmatch(str(item['blob_hash'])) and C.HASH.fullmatch(str(item['quoted_sha256'])),
        'RESPONSE_SCHEMA_INVALID','Locator hashes')
    require(type(item['start']) is int and type(item['end']) is int and 0<=item['start']<item['end'],
        'RESPONSE_SCHEMA_INVALID','Locator half-open range')
    if blob_get is None:return None
    raw=blob_get(item['blob_hash'])
    require(isinstance(raw,bytes) and sha(raw)==item['blob_hash'],'ORIGINAL_BYTES_MISMATCH','Locator blob differs')
    try:
        text=raw.decode('utf-8')
        measure=raw if item['unit']=='UTF8_BYTE' else text
        require(item['end']<=len(measure),'RESPONSE_SCHEMA_INVALID','Locator exceeds full body')
        value=measure[item['start']:item['end']]
        if isinstance(value,str):value=value.encode('utf-8')
        value.decode('utf-8')
    except UnicodeError as exc:
        raise C.PMRSError('RESPONSE_SCHEMA_INVALID','Locator cuts UTF-8 boundary') from exc
    require(sha(value)==item['quoted_sha256'],'ORIGINAL_BYTES_MISMATCH','Locator quote hash differs')
    return value

def _locs(value, blob_get, label):
    C.sequence(value,label)
    for item in value:validate_locator(item,blob_get)

def _ref(ref, records, kinds=None, label='record'):
    require(isinstance(ref,str) and ref.startswith('KR-'),'RESPONSE_SCHEMA_INVALID',label+' exact KR required')
    if records is not None:
        require(ref in records,'INCOMPLETE_CONTEXT',label+': '+ref)
        if kinds:require(records[ref]['kind'] in kinds,'RELATION_ENDPOINT_INVALID',label)

def source_use(value, sources, blob_get):
    C.fields(value,C.SOURCE_USE_FIELDS,'SourceUse')
    C.enum(value['usage_mode'],C.SOURCE_MODES,'SourceUse.usage_mode')
    require(isinstance(value['trust_boundary'],str) and value['trust_boundary'].strip(),
        'RESPONSE_SCHEMA_INVALID','Explicit source trust boundary required')
    if sources is not None:require(value['source_ref'] in sources,'INCOMPLETE_CONTEXT','Unknown source occurrence')
    require(value['locators'],'RESPONSE_SCHEMA_INVALID','SourceUse needs exact locators')
    _locs(value['locators'],blob_get,'SourceUse.locators')
    if sources is not None:
        source=sources[value['source_ref']]
        allowed={source['blob_hash'],*source.get('extraction_blob_hashes',[])}
        require(all(x['blob_hash'] in allowed for x in value['locators']),
            'ORIGINAL_BYTES_MISMATCH','Source locator does not belong to occurrence')

def validate_record(record, body, *, records=None, sources=None, blob_get=None, inferences=None, authored=True, source_quotes=()):
    C.fields(record,C.RECORD_FIELDS,'KnowledgeRecord')
    require(record['schema']==C.RECORD_SCHEMA,'RESPONSE_SCHEMA_INVALID','Wrong scientific schema')
    C.enum(record['kind'],C.KINDS,'KnowledgeRecord.kind')
    C.refs(record['context_refs'],'context_refs',sorted_unique=True)
    for r in record['context_refs']:_ref(r,records,{'Context'},'context')
    raw=body.encode('utf-8') if isinstance(body,str) else body
    require(isinstance(raw,bytes) and 0<len(raw)<=C.MAX_BODY,'PAYLOAD_LIMIT','Body must be nonempty UTF-8 and at most 8 MiB')
    try:text=raw.decode('utf-8')
    except UnicodeError as exc:raise C.PMRSError('RESPONSE_SCHEMA_INVALID','Body must be UTF-8') from exc
    require(sha(raw)==record['body_sha256'],'ORIGINAL_BYTES_MISMATCH','Scientific body hash differs')
    own=lambda h: raw if h==record['body_sha256'] else blob_get(h) if blob_get else None
    lookup=own if blob_get else lambda h: raw if h==record['body_sha256'] else (_ for _ in ()).throw(C.PMRSError('INCOMPLETE_CONTEXT',h))
    d=record['data'];kind=record['kind'];C.fields(d,C.DATA_FIELDS[kind],kind+'.data')
    if 'scope_context_refs' in d:
        C.refs(d['scope_context_refs'],'scope_context_refs',sorted_unique=True)
        require(set(d['scope_context_refs'])<=set(record['context_refs']),'RESPONSE_SCHEMA_INVALID','Scope contexts outside envelope')
    if kind=='Context':
        require(d['parent_context_refs']==record['context_refs'],'RESPONSE_SCHEMA_INVALID','Parent context mismatch')
        keys=set()
        for name in ('definitions','objects','assumptions','quantifiers','conventions'):
            for row in C.sequence(d[name],name):
                C.fields(row,{'key','locator'},name)
                require(isinstance(row['key'],str) and row['key'] and row['key'] not in keys,'RESPONSE_SCHEMA_INVALID','Duplicate context key')
                keys.add(row['key']);validate_locator(row['locator'],lookup)
                require(row['locator']['blob_hash']==record['body_sha256'],'RESPONSE_SCHEMA_INVALID','Context locator must point to full body')
    elif kind=='Statement':
        _locs([d['statement_locator']],lookup,'statement_locator')
        for name in ('hypothesis_locators','conclusion_locators','quantifier_locators'):_locs(d[name],lookup,name)
        C.enum(d['form'],'PROPOSITION QUESTION CONJECTURE CONDITIONAL EQUIVALENCE DICHOTOMY'.split(),'Statement.form')
        C.enum(d['representation'],('AUTHORED','SOURCE_BOUND'),'Statement.representation')
        if d['representation']=='SOURCE_BOUND':
            source_use(d['source_binding'],sources,lookup)
            pieces=[validate_locator(x,lookup) for x in d['source_binding']['locators']]
            require(raw in pieces or raw==b''.join(pieces),'ORIGINAL_BYTES_MISMATCH','SOURCE_BOUND body must be an exact supplied source passage')
            require(validate_locator(d['statement_locator'],lookup)==raw,'ORIGINAL_BYTES_MISMATCH','SOURCE_BOUND statement differs')
        else:require(d['source_binding'] is None,'RESPONSE_SCHEMA_INVALID','AUTHORED statement has null source binding')
    elif kind=='Argument':
        _ref(d['conclusion_ref'],records,{'Statement'},'conclusion')
        C.enum(d['mode'],'PROOF REFUTATION REDUCTION APPLICABILITY COMPATIBILITY COMPARISON DERIVATION'.split(),'Argument.mode')
        for premise_index,p in enumerate(C.sequence(d['premise_bindings'],'premise_bindings')):
            C.fields(p,C.PREMISE_FIELDS,'PremiseBinding')
            C.enum(p['kind'],C.PREMISE_ENDPOINTS,'PremiseBinding.kind')
            C.enum(p['binding_mode'],('PINNED','CURRENT'),'PremiseBinding.binding_mode')
            expected=C.PREMISE_ENDPOINTS[p['kind']]
            try:_ref(p['premise_ref'],records,expected,'premise')
            except C.PMRSError as exc:
                exc.diagnostic={'code':exc.code,'category':'SCIENTIFIC_SEMANTICS','pointer':'/data/premise_bindings/'+str(premise_index)+'/premise_ref','expected':{'record_kinds':sorted(expected),'premise_kind':p['kind']},'actual':{'ref':p['premise_ref'],'record_kind':(records or {}).get(p['premise_ref'],{}).get('kind')},'frozen_binding':p['premise_ref'],'format_repair_eligible':False,'reason':'Changing the premise kind or endpoint changes its scientific use.'}
                raise
            if p['context_ref'] is not None:_ref(p['context_ref'],records,{'Context'},'premise context')
            if p['scope_locator'] is not None:validate_locator(p['scope_locator'],lookup)
            if p['kind']=='SUPPORTED_STATEMENT':require(isinstance(p['support_ref'],str) and p['support_ref'],'RESPONSE_SCHEMA_INVALID','Supported premise needs exact support')
            else:require(p['support_ref'] is None,'RESPONSE_SCHEMA_INVALID','Only supported premise binds support')
            if p['kind']=='CONTEXT_ASSUMPTION':
                require(p['context_ref'] in record['context_refs'] and p['assumption_locator'] is not None,'RESPONSE_SCHEMA_INVALID','Context assumption binding')
                validate_locator(p['assumption_locator'],lookup)
                if records is not None:require(p['assumption_locator'] in [x['locator'] for x in records[p['context_ref']]['data']['assumptions']], 'RESPONSE_SCHEMA_INVALID','Assumption absent from context')
            else:require(p['assumption_locator'] is None,'RESPONSE_SCHEMA_INVALID','Unexpected assumption locator')
        step_ids=set()
        for row in C.sequence(d['steps'],'steps'):
            C.fields(row,{'step_id','locator','premise_refs'},'Argument.step')
            require(isinstance(row['step_id'],str) and row['step_id'] not in step_ids,'RESPONSE_SCHEMA_INVALID','Unique step IDs required')
            step_ids.add(row['step_id']);validate_locator(row['locator'],lookup);C.refs(row['premise_refs'],'step premises')
            require(set(row['premise_refs'])<={x['premise_ref'] for x in d['premise_bindings']},'RESPONSE_SCHEMA_INVALID','Undeclared step premise')
        _locs(d['discharged_assumptions'],lookup,'discharged_assumptions')
        for row in C.sequence(d['open_conditions'],'open_conditions'):
            C.fields(row,{'condition_ref','locator'},'open condition');validate_locator(row['locator'],lookup)
            if row['condition_ref'] is not None:_ref(row['condition_ref'],records,label='condition')
        for p in d['premise_bindings']:
            if p['kind']=='CONDITIONAL_CANDIDATE':require(p['premise_ref'] in [x['condition_ref'] for x in d['open_conditions']], 'RESPONSE_SCHEMA_INVALID','Conditional premise must remain open')
            if p['kind']=='DERIVATION_COMPONENT' and records is not None:
                inherited=records[p['premise_ref']]['data']['open_conditions']
                require(all(x in d['open_conditions'] for x in inherited),'RESPONSE_SCHEMA_INVALID','Derived component conditions must remain explicit')
        for row in C.sequence(d['witness_bindings'],'witness_bindings'):
            C.fields(row,{'variable','context_ref','locator'},'witness');_ref(row['context_ref'],records,{'Context'});validate_locator(row['locator'],lookup)
        validate_mode_payload(d,records,lookup)
    elif kind=='Example':
        for r in C.refs(d['target_refs'],'Example.targets',nonempty=True):_ref(r,records,{'Statement'})
        validate_locator(d['construction_locator'],lookup)
        C.enum(d['scope'],'ORIGINAL_TARGET MODEL_CASE BOUNDARY_TEST NUMERICAL_PROBE'.split(),'Example.scope')
        for row in C.sequence(d['hypothesis_checks'],'hypothesis_checks'):
            C.fields(row,{'hypothesis_locator','result','evidence_refs','explanation_locator'},'hypothesis check')
            validate_locator(row['hypothesis_locator'],lookup);validate_locator(row['explanation_locator'],lookup)
            C.enum(row['result'],('SATISFIED','VIOLATED','UNKNOWN'),'hypothesis result');C.refs(row['evidence_refs'],'evidence_refs')
            for ref in row['evidence_refs']:_ref(ref,records)
        for row in C.sequence(d['observations'],'observations'):
            C.fields(row,{'locator','evidence_refs'},'observation');validate_locator(row['locator'],lookup)
            for ref in C.refs(row['evidence_refs'],'evidence_refs'):_ref(ref,records)
        if d['realization_argument_ref'] is not None:_ref(d['realization_argument_ref'],records,{'Argument'})
    elif kind=='SourceEvidence':
        C.refs(d['source_occurrence_refs'],'source_occurrence_refs',nonempty=True)
        if sources is not None:require(all(r in sources for r in d['source_occurrence_refs']),'INCOMPLETE_CONTEXT','Source must be host registered')
        _locs(d['locators'],lookup,'SourceEvidence.locators')
        if sources is not None:
            allowed={h for ref in d['source_occurrence_refs'] for h in [sources[ref]['blob_hash'],*sources[ref].get('extraction_blob_hashes',[])]}
            require(all(loc['blob_hash'] in allowed for loc in d['locators']),'ORIGINAL_BYTES_MISMATCH','SourceEvidence locator does not belong to its exact source occurrences')
        C.enum(d['evidence_type'],'ORIGINAL_TEXT THEOREM_STATEMENT EXCERPT COMPUTATION OBSERVATION'.split(),'evidence_type')
        C.enum(d['coverage'],('FULL_DOCUMENT','DECLARED_RANGE','METADATA_ONLY'),'coverage')
        C.refs(d['reproducibility_refs'],'reproducibility_refs')
    elif kind=='Assessment':
        C.enum(d['review_kind'],'PROOF COUNTEREXAMPLE APPLICABILITY INTEGRATION FORMULATION WORK_CHECK'.split(),'review_kind')
        C.enum(d['verdict'],('SUPPORTED_WITHIN_SCOPE','DEFECT_FOUND','INCONCLUSIVE'),'verdict')
        C.refs(d['target_refs'],'review targets',nonempty=True)
        for ref in d['target_refs']:
            if ref.startswith('IB-'):require(inferences is None or ref in inferences,'INCOMPLETE_CONTEXT','Unknown inference binding')
            else:_ref(ref,records)
        for row in C.sequence(d['checked'],'checked'):
            C.optional_fields(row,{'ref','locators','aspect'},{'scope_version','extent','target_body_sha256','whole_locator'},'checked');
            if 'scope_version' in row:
                from .assurance import validate_scope
                validate_scope([{'target_ref':row['ref'],'aspects':[row['aspect']],**{k:v for k,v in row.items() if k not in {'ref','aspect'}}}])
                validate_locator(row['whole_locator'],lookup)
            require(row['ref'] in d['target_refs'],'RESPONSE_SCHEMA_INVALID','Unbound checked target')
            require(isinstance(row['aspect'],str) and row['aspect'],'RESPONSE_SCHEMA_INVALID','Checked aspect required');_locs(row['locators'],lookup,'checked locators')
            target_ref=row['ref']
            if target_ref.startswith('IB-') and inferences is not None:target_ref=inferences[target_ref]['argument_ref']
            if records is not None and target_ref in records:
                if row.get('scope_version'):
                    target_body=lookup(records[target_ref]['body_sha256'])
                    require(row['whole_locator']==locator(target_body,unit=row['whole_locator']['unit']) and row['target_body_sha256']==records[target_ref]['body_sha256'],'ORIGINAL_BYTES_MISMATCH','Whole review scope must be the complete exact target body')
                require(all(loc['blob_hash']==records[target_ref]['body_sha256'] for loc in row['locators']),
                    'RESPONSE_SCHEMA_INVALID','Checked locators must point to the exact target body')
        for row in C.sequence(d['unchecked'],'unchecked'):
            C.fields(row,{'ref','aspect','reason'},'unchecked');require(row['ref'] in d['target_refs'],'RESPONSE_SCHEMA_INVALID','Unbound unchecked target')
            require(all(isinstance(row[k],str) and row[k] for k in ('aspect','reason')),'RESPONSE_SCHEMA_INVALID','Unchecked reason required')
        for row in C.sequence(d['findings'],'findings'):
            C.fields(row,{'code','severity','locator','description_locator','evidence_refs'},'finding')
            validate_locator(row['locator'],lookup);validate_locator(row['description_locator'],lookup);C.refs(row['evidence_refs'],'finding evidence')
    if authored and not(kind=='Statement' and d['representation']=='SOURCE_BOUND'):
        authored_with_quotes(text,source_quotes,'scientific body')
        research_data(d)
    C.validate_tree(record)
    return C.scientific_identity(record)

def validate_mode_payload(d, records, blob_get):
    p=d['mode_payload'];mode=d['mode']
    if mode in ('PROOF','REFUTATION','DERIVATION'):C.fields(p,set(),'mode_payload');return
    if mode=='REDUCTION':
        C.fields(p,{'inference_spec'},'mode_payload');i=p['inference_spec'];C.fields(i,C.INFERENCE_FIELDS,'inference_spec')
        require(i['conclusion_ref']==d['conclusion_ref'],'RESPONSE_SCHEMA_INVALID','Reduction conclusion mismatch')
        C.enum(i['operator'],('AND','OR'),'reduction operator')
        for key in ('premise_refs','alternative_argument_refs','additional_assumption_refs'):C.refs(i[key],key)
        require(not i['alternative_argument_refs'] if i['operator']=='AND' else not i['premise_refs'],'RESPONSE_SCHEMA_INVALID','AND/OR structure')
        if i['operator']=='OR':require(i['alternative_argument_refs'],'RESPONSE_SCHEMA_INVALID','OR needs complete alternatives')
        for r in i['premise_refs']+i['additional_assumption_refs']:_ref(r,records)
        for r in i['alternative_argument_refs']:
            _ref(r,records,{'Argument'})
            if records is not None:
                a=records[r]['data'];require(a['mode']=='REDUCTION' and a['mode_payload']['inference_spec']['operator']=='AND' and a['conclusion_ref']==d['conclusion_ref'],'RESPONSE_SCHEMA_INVALID','Each OR alternative needs full AND route')
        for name in ('lifting_check','compatibility_check'):
            check=i[name];require(isinstance(check,dict),'RESPONSE_SCHEMA_INVALID',name)
            if check.get('status')=='REQUIRED':
                C.fields(check,{'status','obligation_ids','evidence_refs'},name);C.refs(check['obligation_ids'],name,nonempty=True)
            else:
                C.fields(check,{'status','reason_locator','evidence_refs'},name);require(check['status']=='NOT_REQUIRED','RESPONSE_SCHEMA_INVALID',name);validate_locator(check['reason_locator'],blob_get)
            C.refs(check['evidence_refs'],'check evidence')
    elif mode=='APPLICABILITY':
        C.fields(p,{'donor_refs','recipient_ref','substitution_map','hypothesis_discharge_refs','constant_dependency_locators','open_conditions'},'applicability')
        for r in C.refs(p['donor_refs'],'donors',nonempty=True)+C.refs(p['hypothesis_discharge_refs'],'hypothesis_discharge_refs'):_ref(r,records)
        _ref(p['recipient_ref'],records);_locs(p['constant_dependency_locators'],blob_get,'constant_dependency_locators')
        require(isinstance(p['substitution_map'],dict) and isinstance(p['open_conditions'],list),'RESPONSE_SCHEMA_INVALID','Applicability bindings')
    elif mode=='COMPATIBILITY':
        C.fields(p,{'witness_compatibility'},'compatibility');w=p['witness_compatibility']
        C.fields(w,{'target_ref','component_argument_refs','context_refs','variable_mapping','common_data_refs','quantifier_locators','evidence_refs','open_condition_refs'},'WitnessCompatibility')
        _ref(w['target_ref'],records)
        for r in C.refs(w['component_argument_refs'],'components',nonempty=True):_ref(r,records,{'Argument'})
        for r in C.refs(w['context_refs'],'context_refs'): _ref(r,records,{'Context'})
        require(isinstance(w['variable_mapping'],dict),'RESPONSE_SCHEMA_INVALID','Explicit variable mapping')
        for name in ('common_data_refs','evidence_refs','open_condition_refs'):
            for r in C.refs(w[name],name):_ref(r,records)
        _locs(w['quantifier_locators'],blob_get,'quantifiers')
    elif mode=='COMPARISON':
        C.fields(p,{'relation_type','from_statement_ref','to_statement_ref','direction_argument_refs','scope_context_refs'},'comparison')
        C.enum(p['relation_type'],('IMPLIES','EQUIVALENT_ON_SCOPE'),'comparison relation')
        for name in ('from_statement_ref','to_statement_ref'):_ref(p[name],records,{'Statement'})
        for r in C.refs(p['direction_argument_refs'],'directions'):_ref(r,records,{'Argument'})
        if p['relation_type']=='EQUIVALENT_ON_SCOPE':require(len(p['direction_argument_refs'])==2,'RESPONSE_SCHEMA_INVALID','Equivalence requires two directions')
        C.refs(p['scope_context_refs'],'scope_context_refs')

def make_record(kind, body, data, context_refs=(), *, records=None, sources=None, blob_get=None, inferences=None, allow_source_bound=True, authored=True, source_quotes=()):
    raw=body.encode('utf-8') if isinstance(body,str) else body
    record={'schema':C.RECORD_SCHEMA,'kind':kind,'context_refs':list(context_refs),'body_sha256':sha(raw),'data':deepcopy(data)}
    if not allow_source_bound and kind=='Statement':require(data.get('representation')!='SOURCE_BOUND','AUTHORIZATION_REQUIRED','Source preservation capability required')
    ref=validate_record(record,raw,records=records,sources=sources,blob_get=blob_get,inferences=inferences,authored=authored,source_quotes=source_quotes)
    return ref,record,raw

def identify(record, body):
    """Verify the immutable envelope and exact bytes without resolving a view."""
    C.fields(record,C.RECORD_FIELDS,'KnowledgeRecord')
    require(record['schema']==C.RECORD_SCHEMA and record['kind'] in C.KINDS,'RESPONSE_SCHEMA_INVALID','Final scientific record required')
    raw=body.encode('utf-8') if isinstance(body,str) else body
    require(isinstance(raw,bytes) and sha(raw)==record['body_sha256'],'ORIGINAL_BYTES_MISMATCH','Record body differs')
    return C.scientific_identity(record)

def derive_inference(ref, record):
    if record['kind']!='Argument' or record['data']['mode']!='REDUCTION':return None
    i=deepcopy(record['data']['mode_payload']['inference_spec'])
    alts=i.pop('alternative_argument_refs');ident=C.inference_identity(ref)
    return ident,{'inference_id':ident,'argument_ref':ref,**i,'alternative_inference_refs':[C.inference_identity(a) for a in alts]}

def result_family(family, records):
    C.fields(family,{'family_id','members'},'ResultFamilyIndex')
    require(isinstance(family['family_id'],str) and family['family_id'],'RESPONSE_SCHEMA_INVALID','Family ID required')
    roles={'MAIN_RESULT':'Statement','COROLLARY':'Statement','SUPPORTING_ARGUMENT':'Argument','ALTERNATIVE_PROOF':'Argument'}
    seen=set()
    for row in C.sequence(family['members'],'family members'):
        C.fields(row,{'record_ref','display_role'},'family member');C.enum(row['display_role'],roles,'display_role')
        _ref(row['record_ref'],records,{roles[row['display_role']]});key=(row['record_ref'],row['display_role'])
        require(key not in seen,'RESPONSE_SCHEMA_INVALID','Repeated family member');seen.add(key)
    return deepcopy(family)
