"""Exact local materials for a persistent MAIN, not a single prompt preload.

Every original file stays frozen and readable. Only the initial scope sources
are charged as mandatory startup reads; subsequent scientific reading happens
in the native session, with its actual context management and usage evidence.
This does not certify reading or change any scientific admission rule.
"""
from .util import require

SCHEMA='pmrs.main-material-delivery/1'
INSTRUCTIONS=(
    'Persistent MAIN material access: first read the complete method handbook, original target and scope sources, '
    'effective user guidance, latest valid research checkpoint, and all subsequent event/handoff/route metadata. '
    'Read every initial_material_sha256 file completely. All other exact historical scientific files remain '
    'available in this same frozen directory, listed by material_refs; they are not all a simultaneous prompt preload. '
    'You choose which full bodies to read, in manageable portions, for the current decision. Before using a scientific '
    'claim, read its exact statement, Argument, necessary premises, qualifications, failure/counterevidence and scope; '
    'a path, hash, summary, past read or compacted memory never substitutes for those contents. '
    'Reconcile checkpoint increments and in-flight/invalidated evidence; retrieve complete relevant originals again '
    'after compaction. Record unread or unavailable evidence honestly. Native session context management handles '
    'later reads; PMRS does not impose a new native delegation or research token quota. '
    'The startup byte bound does not claim that lifetime reads fit simultaneously or establish actual reading.')


def policy(packet,target_refs):
    refs=packet['material_refs'];initial=set()
    for ref in target_refs:
        record=packet['records'].get(ref)
        require(record and record['body_sha256'] in refs,'INCOMPLETE_CONTEXT','MAIN original target body must remain an initial exact file')
        initial.add(record['body_sha256'])
    # Preserve all frozen scope sources, including original user materials.
    # This selection is mechanical provenance, never a scientific route choice.
    for digest,row in refs.items():
        if any(use.startswith(('source:','exact-source-excerpt')) for use in row.get('uses',[])):initial.add(digest)
    return {'schema':SCHEMA,'mode':'PERSISTENT_NATIVE_DEMAND_READ',
        'initial_material_sha256':sorted(initial),
        'all_materials_remain_exact_local_files':True,
        'deferred_material_count':len(refs)-len(initial),
        'reading_is_not_inferred_from_availability':True,'instructions':INSTRUCTIONS}


def initial_hashes(task,packet):
    value=packet.get('main_material_delivery')
    require(task.get('actor_kind')=='MAIN' and task.get('model_input_revision')=='pmrs.task-input/5'
        and isinstance(value,dict) and value==task.get('main_material_delivery'),
        'ORIGINAL_BYTES_MISMATCH','MAIN delivery policy must match the frozen task and packet')
    expected=policy(packet,task['target_refs'])
    require(value==expected,'ORIGINAL_BYTES_MISMATCH','MAIN initial materials differ from the exact scope sources')
    return set(value['initial_material_sha256'])
