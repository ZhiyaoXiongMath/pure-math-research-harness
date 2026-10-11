"""Lossless, model-readable tables for repeated MAIN metadata, never bodies.

Opaque native IDs and repeated object field names dominate growing packets.
Store them once, with explicit tables in the same input. Native records, guards,
material files and authoring/admission schemas retain their original form.
"""
from collections import Counter
from copy import deepcopy
from .util import canonical,require,sha

SCHEMA='pmrs.main-metadata-tables/1'


def encode(packet,*,packed=False):
    original=deepcopy(packet)
    counts=Counter();shapes=Counter()
    def scan(value):
        if isinstance(value,str):
            # Prose, full handbooks and mathematical bodies stay verbatim.
            if len(value)>=32 and not any(c.isspace() for c in value):counts[value]+=1
        elif isinstance(value,list):
            for item in value:scan(item)
        elif isinstance(value,dict):
            shapes[tuple(sorted(value))]+=1
            for item in value.values():scan(item)
    # Keep the operational top-level layout and complete handbook in plain
    # JSON. Only the large structured metadata collections use table rows.
    names=('records','relations','strategy_context')
    for name in names:
        value=original.get(name)
        if name=='strategy_context':
            value={k:v for k,v in value.items() if k!='method_manual'}
        scan(value)
    strings=sorted(s for s,n in counts.items() if n>1 and (n-1)*len(canonical(s))>n*16+16)
    fields=sorted(s for s,n in shapes.items() if s in {('$s',),('$r',)} or
                  n>1 and s and (n-1)*sum(len(canonical(k))+1 for k in s)>n*16+16)
    string_ids={s:i for i,s in enumerate(strings)};field_ids={s:i for i,s in enumerate(fields)}
    def compact(value):
        if isinstance(value,str):return {'$s':string_ids[value]} if value in string_ids else value
        if isinstance(value,list):return [compact(v) for v in value]
        if isinstance(value,dict):
            shape=tuple(sorted(value))
            if shape in field_ids:return {'$r':[field_ids[shape],*[compact(value[k]) for k in shape]]}
            return {k:compact(v) for k,v in value.items()}
        return value
    result=deepcopy(original)
    for name in names:
        if name=='strategy_context':
            result[name]={k:deepcopy(v) if k=='method_manual' else compact(v) for k,v in original[name].items()}
        else:result[name]=compact(original[name])
    result['metadata_tables']={'schema':SCHEMA,'strings':strings,'fields':[list(s) for s in fields],
        'decoded_packet_sha256':sha(canonical(original)),
        'instructions':
            'Lossless metadata only. Interpret an object containing only "$s":i as the exact strings[i] value. '
            'Interpret an object containing only "$r":[i,v0,...] as an object whose keys are fields[i] and whose values are v0,... in that order; recursively interpret values. '
            'Other objects and lists keep their exact keys and order. Native IDs, locators, premise bindings, context membership and all metadata are fully present in these tables, not summaries or missing material. '
            'The complete method_manual and all prose remain verbatim; scientific bodies remain complete in the original material files. '
            'Use fully resolved native IDs and ordinary objects in tool arguments and OUTPUT_CONTRACT; $s/$r are input representation only. '
            'Remove metadata_tables after decoding to verify decoded_packet_sha256 with canonical UTF-8 JSON (sorted keys, compact separators, ensure_ascii=false).'}
    require(decode(result)==original,'INPUT_ENCODING_INVALID','MAIN metadata tables must reproduce the complete original packet')
    if packed:
        import base64,zlib
        # Keep the whole handbook, current guidance/checkpoint, original task
        # and resource/control facts directly readable. Exact larger native
        # metadata is a same-packet transport container, never a summary.
        paths=[[key] for key in ('records','relations','input_plan','material_refs') if key in result]+[['strategy_context',key] for key in
            ('main_inbox','execution_recoveries','stage_handoffs','open_obligations','tasks','routes')
            if key in result['strategy_context']]
        entries=[]
        for path in paths:
            parent=result if len(path)==1 else result[path[0]]
            entries.append({'path':path,'value':parent[path[-1]]})
            parent[path[-1]]={'packed_metadata':len(entries)-1}
        raw=canonical(entries)
        result['metadata_tables']['packed_metadata']={
            'schema':'pmrs.exact-metadata-container/1','encoding':'base64+zlib+utf8-json',
            'decoded_bytes':len(raw),'decoded_sha256':sha(raw),
            'data':base64.b64encode(zlib.compress(raw,9)).decode('ascii'),
            'instructions':'Before interpreting $s/$r, decode data with base64.b64decode then zlib.decompress, verify decoded_bytes and SHA256, and parse the UTF-8 JSON list. Each entry has path and exact value. Replace only the indicated packet[path[0]] or packet[path[0]][path[1]] placeholder {"packed_metadata": entry_index} with that value. Then recursively decode $s/$r using strings/fields and verify decoded_packet_sha256. This container is original metadata, not a scientific summary. No field may be omitted. Method, guidance/checkpoint prose and every original material file remain available separately.'}
        result['metadata_tables']['instructions']=result['metadata_tables']['instructions'].replace(
            'The complete method_manual and all prose remain verbatim;',
            'First unpack packed_metadata exactly as its instructions specify. The complete method_manual remains verbatim; all other prose is identical after decoding;')
        require(decode(result)==original,'INPUT_ENCODING_INVALID','Packed MAIN metadata must reproduce the complete original packet')
    return result


def decode(packet):
    """Exact local interpretation for integrity checks and input inspection."""
    tables=packet['metadata_tables'];require(tables['schema']==SCHEMA,'INPUT_ENCODING_INVALID','Unknown MAIN metadata tables')
    if tables.get('packed_metadata'):
        import base64,zlib
        from .util import loads
        container=tables['packed_metadata']
        require(container.get('schema')=='pmrs.exact-metadata-container/1' and container.get('encoding')=='base64+zlib+utf8-json',
                'INPUT_ENCODING_INVALID','Unknown exact metadata container')
        raw=zlib.decompress(base64.b64decode(container['data'],validate=True))
        require(len(raw)==container['decoded_bytes'] and sha(raw)==container['decoded_sha256'],
                'ORIGINAL_BYTES_MISMATCH','Packed metadata bytes differ')
        packet=deepcopy(packet);seen=set()
        for index,entry in enumerate(loads(raw)):
            path=entry['path']
            require(isinstance(path,list) and (path in [['records'],['relations'],['input_plan'],['material_refs']] or
                    len(path)==2 and path[0]=='strategy_context' and path[1] in
                    {'main_inbox','execution_recoveries','stage_handoffs','open_obligations','tasks','routes'})
                    and tuple(path) not in seen,'INPUT_ENCODING_INVALID','Unexpected packed metadata path')
            seen.add(tuple(path));parent=packet if len(path)==1 else packet[path[0]]
            require(parent.get(path[-1])=={'packed_metadata':index},'INPUT_ENCODING_INVALID','Packed metadata placeholder differs')
            parent[path[-1]]=entry['value']
    def expand(value):
        if isinstance(value,list):return [expand(v) for v in value]
        if isinstance(value,dict):
            if set(value)=={'$s'}:
                i=value['$s'];require(type(i) is int and 0<=i<len(tables['strings']),'INPUT_ENCODING_INVALID','Invalid string index')
                return tables['strings'][i]
            if set(value)=={'$r'}:
                row=value['$r'];require(isinstance(row,list) and row,'INPUT_ENCODING_INVALID','Missing metadata row')
                i=row[0];require(type(i) is int and 0<=i<len(tables['fields']),'INPUT_ENCODING_INVALID','Invalid field index')
                keys=tables['fields'][i];require(len(keys)==len(row)-1,'INPUT_ENCODING_INVALID','Metadata row width differs')
                return {k:expand(v) for k,v in zip(keys,row[1:])}
            return {k:expand(v) for k,v in value.items()}
        return value
    result=deepcopy({k:v for k,v in packet.items() if k!='metadata_tables'})
    for name in ('records','relations'):result[name]=expand(packet[name])
    result['strategy_context']={k:deepcopy(v) if k=='method_manual' else expand(v)
                                for k,v in packet['strategy_context'].items()}
    require(sha(canonical(result))==tables['decoded_packet_sha256'],'ORIGINAL_BYTES_MISMATCH','Decoded MAIN packet differs')
    return result
