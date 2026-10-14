"""Small native-format fixtures; no model, Engine, native or Store writer calls.

Import effects reviewed: Store's legacy dependencies initialize constants,
registry dictionaries and in-memory locks only. Fixture bodies are constructed
with the original knowledge validator; commit bytes use the original encoder
and delta helper. Only explicit fixture helpers write synthetic files.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat

from research_studio import knowledge as K
from research_studio.store import initial_state, _diff, _persistent
from research_studio.util import canonical, sha
from research_studio.version import COMMIT_SCHEMA

IID = 'I-synthetic'
RID = 'R-synthetic'


@contextmanager
def changed(obj, name, value):
    prior = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, prior)


def put(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def state():
    s = initial_state('Synthetic read-only fixture', synthetic=True)
    context_ref, context, context_body = K.make_record('Context',
        b'The variables range over integers with ordinary addition.',
        {'definitions': [], 'objects': [], 'assumptions': [], 'quantifiers': [],
         'conventions': [], 'parent_context_refs': []})
    s['records'][context_ref] = context
    body = b'For every integer n, n + 0 = n.'
    data = {'statement_locator': K.locator(body), 'hypothesis_locators': [],
            'conclusion_locators': [K.locator(body)], 'quantifier_locators': [],
            'scope_context_refs': [], 'form': 'PROPOSITION', 'representation': 'AUTHORED',
            'source_binding': None}
    ref, record, raw = K.make_record('Statement', body, data, [context_ref], records=s['records'])
    s['records'][ref] = record
    s['instances'][IID] = {'instance_id': IID, 'kind': 'TRH', 'status': 'PAUSED',
                           'target_ref': ref, 'current_mission_id': None,
                           'run_control': {'mode': 'MANUAL', 'control_version': 7}}
    s['tasks']['T-synthetic'] = {'task_id': 'T-synthetic', 'instance_id': IID,
                               'request_id': RID, 'actor_kind': 'WORKER'}
    s['requests'][RID] = {'request_id': RID, 'task_id': 'T-synthetic', 'instance_id': IID,
                          'execution_state': 'UNKNOWN', 'acceptance_state': 'PENDING',
                          'execution_kind': 'SYNTHETIC_TEST_ONLY', 'fenced': False}
    return s, {sha(raw): raw, sha(context_body): context_body}


def publish(root, s, blobs=None, *, previous=None, before=None, checkpoint=True):
    root.mkdir(exist_ok=True)
    s = _persistent(s)
    for digest, raw in (blobs or {}).items():
        put(root, 'blobs/' + digest, raw)
    for ref, record in s.get('records', {}).items():
        put(root, 'records/' + ref + '.json', canonical(record))
    delta = canonical(_diff(before or {}, s))
    put(root, 'blobs/' + sha(delta), delta)
    entry = {'schema': COMMIT_SCHEMA, 'sequence': 1 if previous is None else previous['sequence'] + 1,
             'previous_commit': previous, 'base_knowledge_commit': previous['commit'] if previous else None,
             'knowledge_delta_ref': None, 'control_delta_ref': None, 'report_delta_ref': None,
             'registry_delta_ref': sha(delta), 'accepted_request_bindings': [],
             'events': [{'type': 'CHECKPOINT', 'state_sha256': sha(canonical(s))}] if checkpoint else [],
             'actor': 'HOST', 'at': '2026-01-01T00:00:00Z'}
    raw = canonical(entry)
    digest = sha(raw)
    head = {'sequence': entry['sequence'], 'commit': digest,
            'path': f"journal/{entry['sequence']:012d}-{digest}.json"}
    put(root, head['path'], raw)
    if checkpoint:
        put(root, 'checkpoints/' + digest + '.json', canonical(
            {'commit': digest, 'state': s, 'state_sha256': sha(canonical(s))}))
    put(root, 'project.json', canonical({k: s[k] for k in ('schema', 'project_id', 'synthetic_test_only')}))
    put(root, 'HEAD.next', canonical(head))
    os.replace(root/'HEAD.next', root/'HEAD')
    return head


def pool(home, project, *, state='UNKNOWN'):
    root = home / '.local/state/pmrs/host-runtime-4.2.2'
    key = sha(str(project).encode())
    data = {'cursor': 0, 'projects': {key: str(project)}, 'demands': {}, 'slots': {
        key + ':' + RID: {'project': key, 'instance': key + ':' + IID, 'instance_id': IID,
                         'request_id': RID, 'root': str(project), 'pid': 999999999,
                         'start': 'synthetic-stale-owner', 'state': state}}}
    put(root, 'model-pool.json', canonical(data))
    return root, data


def footprint(root):
    """Content, structure, permissions and metadata; OS-managed atime excluded."""
    result = {}
    for p in [root, *sorted(root.rglob('*'))]:
        info = p.lstat()
        result[str(p.relative_to(root))] = (
            info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_gid, info.st_nlink,
            hashlib.sha256(p.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else
            os.readlink(p) if p.is_symlink() else None)
    return result
