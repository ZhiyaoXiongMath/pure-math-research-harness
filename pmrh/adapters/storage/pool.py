"""Typed synthetic host pool and the egress → pool → project lock order.

Roots are capabilities installed by trusted fixture assembly. The ledger never
supplies a filesystem path. No environment variable participates in identity.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path

from pmrh.domain.primitives import canonical, loads, sha
from .io import atomic, immutable, safe_path, read, _ConfinedReader
from .journal import Journal
from .control import check, fields, string, digest, integer, ref, releasable, SCHEMA
from .pool_read import control_pool_view

POOL_SCHEMA = 'pmrh.host-pool/1'
POOL_BYTES = 4 * 1024**2


@dataclass(frozen=True)
class RootBinding:
    binding_id: str
    root: Path
    device: int
    inode: int

    @classmethod
    def register(cls, binding_id, root):
        string(binding_id)
        path = safe_path(Path(root)).resolve(strict=True)
        stat = path.stat()
        check(path.is_dir(), 'AUTHORIZATION_REQUIRED')
        return cls(binding_id, path, stat.st_dev, stat.st_ino)

    def verify(self):
        path = safe_path(self.root).resolve(strict=True)
        stat = path.stat()
        check(path == self.root and (stat.st_dev, stat.st_ino) == (self.device, self.inode), 'AUTHORIZATION_REQUIRED')
        return path


class Pool:
    """One explicitly supplied isolated runtime and immutable root registry."""
    def __init__(self, runtime, pool_id, roots):
        check(type(runtime) is RootBinding, 'AUTHORIZATION_REQUIRED')
        string(pool_id)
        self.runtime = runtime
        self.pool_id = pool_id
        self.roots = {item.binding_id: item for item in roots}
        check(len(self.roots) == len(roots) and len(roots) <= 4096)
        self.path = runtime.verify()
        immutable(self.path/'pool.lock', b'')
        (self.path/'egress').mkdir(exist_ok=True, mode=0o700)
        with self.locked():
            if not (self.path/'pool.json').exists():
                atomic(self.path/'pool.json', canonical(dict(schema=POOL_SCHEMA, pool_id=pool_id,
                    revision=0, projects={}, slots={}, demands={}, cursor=0)))
            self.read()

    @contextmanager
    def locked(self):
        self.runtime.verify()
        fd = os.open(safe_path(self.path, 'pool.lock'), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    @contextmanager
    def egress(self, project, genesis, instances):
        """Acquire every affected instance in one canonical order, never PID."""
        string(project); digest(genesis)
        identifiers = sorted(set(instances))
        check(identifiers and len(identifiers) <= 4096)
        fds = []
        try:
            for iid in identifiers:
                string(iid)
                key = sha(canonical([self.pool_id, project, genesis, iid]))
                path = safe_path(self.runtime.verify(), 'egress/'+key+'.lock')
                immutable(path, b'')
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                fds.append(fd)
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            for fd in reversed(fds):
                os.close(fd)

    def read(self):
        raw = read(safe_path(self.path, 'pool.json'), POOL_BYTES)
        value = loads(raw, maximum=POOL_BYTES)
        fields(value, 'schema pool_id revision projects slots demands cursor')
        check(value['schema'] == POOL_SCHEMA and value['pool_id'] == self.pool_id, 'AUTHORIZATION_REQUIRED')
        check(canonical(value) == raw)
        integer(value['revision']); integer(value['cursor'])
        for name in ('projects', 'slots', 'demands'):
            check(type(value[name]) is dict and len(value[name]) <= 4096)
        for key, row in value['projects'].items():
            fields(row, 'project_id genesis_commit root_binding_id')
            string(row['project_id']); digest(row['genesis_commit']); string(row['root_binding_id'])
            check(key == sha(canonical([row['project_id'], row['genesis_commit']])))
        for token, row in value['slots'].items():
            digest(token)
            fields(row, 'project_key instance_id operation_id request_id reservation_ref state release_evidence_ref')
            check(row['project_key'] in value['projects'])
            for key in ('instance_id', 'operation_id', 'request_id'):
                string(row[key])
            ref(row['reservation_ref'], value['projects'][row['project_key']]['project_id'])
            ref(row['release_evidence_ref'], nullable=True)
            check(row['state'] in {'HELD', 'RELEASED'} and (row['state'] == 'HELD') == (row['release_evidence_ref'] is None))
        for key, row in value['demands'].items():
            fields(row, 'project_key instance_id ready')
            check(row['project_key'] in value['projects'])
            string(row['instance_id']); integer(row['ready'])
            check(key == sha(canonical([row['project_key'], row['instance_id']])))
        return value

    def write(self, before, after):
        if before == after:
            return before
        check(before == self.read(), 'VERSION_CONFLICT')
        after = deepcopy(after)
        after['revision'] = before['revision'] + 1
        integer(after['revision'])
        raw = canonical(after)
        check(len(raw) <= POOL_BYTES and all(len(after[k]) <= 4096 for k in ('projects', 'slots', 'demands')), 'RESOURCE_LIMIT')
        atomic(self.path/'pool.json', raw)
        return after

    def register(self, binding_id, *, genesis, project):
        check(binding_id in self.roots, 'AUTHORIZATION_REQUIRED')
        binding = self.roots[binding_id]
        with self.locked():
            with _ConfinedReader(binding.verify()) as reader:
                store = Journal(reader.root, reader=reader)
                history = store.history()
                check(history[0][0]['commit'] == genesis and store._marker()['project_id'] == project)
                check(store._marker()['synthetic_test_only'] is True, 'AUTHORIZATION_REQUIRED')
            before = self.read(); after = deepcopy(before)
            key = sha(canonical([project, genesis]))
            row = dict(project_id=project, genesis_commit=genesis, root_binding_id=binding_id)
            check(key not in after['projects'] or after['projects'][key] == row, 'AUTHORIZATION_REQUIRED')
            check(not any(r['root_binding_id'] == binding_id and k != key for k, r in after['projects'].items()), 'AUTHORIZATION_REQUIRED')
            after['projects'][key] = row
            self.write(before, after)
            return key

    def inspect(self, *, sending=False):
        """Call under pool.lock, before taking any project writer lock."""
        ledger = self.read(); snapshots = {}
        blocked = False
        for key, row in ledger['projects'].items():
            check(row['root_binding_id'] in self.roots, 'AUTHORIZATION_REQUIRED')
            binding = self.roots[row['root_binding_id']]
            with _ConfinedReader(binding.verify()) as reader:
                store = Journal(reader.root, reader=reader)
                history = store.history(); state = store.read_snapshot()
                check(state['project_id'] == row['project_id'] and history[0][0]['commit'] == row['genesis_commit'])
                if history[-1][1]['schema'] == SCHEMA:
                    check(store._control_index.profile['pool_id'] == self.pool_id, 'AUTHORIZATION_REQUIRED')
                else:
                    # Registration precedes activation. Only the exact fresh
                    # source/instance prefix is an admissible intermediate root.
                    from .control import validate_prefix
                    validate_prefix(store, history)
                    check(not state['requests'])
                snapshots[key] = state
            for request in state['requests'].values():
                call = request['admission']
                blocked |= call['evidence_conflict']
                task = state['tasks'][request['task_id']]
                token = self.token(key, request['instance_id'], call['operation_id'], request['request_id'], ledger)
                slot = ledger['slots'].get(token)
                if task.get('actor_kind') == 'MAIN':
                    check(call['slot_token'] is None and slot is None)
                else:
                    if call['slot_token'] is not None:
                        check(call['slot_token'] == token and slot is not None)
                    if call['send_phase'] == 'ATTEMPTED':
                        check(slot is not None and slot['state'] == 'HELD')
                    if slot is not None:
                        check(slot['reservation_ref'] == call['reservation_ref'])
                        # A later GAP does not erase an already released
                        # tombstone. New releases still require current OPEN.
                        check(slot['state'] != 'RELEASED' or slot['release_evidence_ref'] in
                              (call['not_sent_ref'],call['termination_ref']))
        effective = []
        for token, slot in ledger['slots'].items():
            state = snapshots[slot['project_key']]
            request = state['requests'].get(slot['request_id'])
            check(request is not None and request['instance_id'] == slot['instance_id'])
            call = request['admission']
            check(token == self.token(slot['project_key'], slot['instance_id'], slot['operation_id'], slot['request_id'], ledger))
            check(slot['operation_id'] == call['operation_id'] and slot['reservation_ref'] == call['reservation_ref'])
            check(state['tasks'][request['task_id']].get('actor_kind') != 'MAIN')
            check(call['slot_token'] in (None, token))
            if call['slot_token'] is None:
                check(call['send_phase'] == 'READY' and slot['state'] == 'HELD' or
                      call['send_phase'] == 'CLOSED' and call['not_sent_ref'] is not None)
            if slot['state'] == 'HELD' or call['evidence_conflict']:
                effective.append(slot)
        if sending:
            check(not blocked, 'POOL_BLOCKED')
            check(len(effective) <= 20, 'POOL_BLOCKED')
        return ledger, snapshots, effective, blocked

    def token(self, key, iid, operation, request, ledger=None):
        row = (ledger or self.read())['projects'][key]
        return sha(canonical([self.pool_id, row['project_id'], row['genesis_commit'], iid, operation, request]))

    def acquire_locked(self, key, request_id):
        before, states, effective, blocked = self.inspect(sending=True)
        state = states[key]; request = state['requests'][request_id]; call = request['admission']
        check(state['tasks'][request['task_id']].get('actor_kind') != 'MAIN', 'UNSUPPORTED_CAPABILITY')
        check(call['send_phase'] == 'READY' and not request['fenced'])
        token = self.token(key, request['instance_id'], call['operation_id'], request_id, before)
        if token in before['slots']:
            check(before['slots'][token]['state'] == 'HELD')
            return token, before['revision']
        check(len(effective) < 20, 'BUDGET_OR_WORKER_LIMIT')
        count = sum(r['project_key'] == key and r['instance_id'] == request['instance_id'] for r in effective)
        limit = 1 if state['instances'][request['instance_id']]['kind'] == 'SURVEY' else 8
        check(count < limit, 'BUDGET_OR_WORKER_LIMIT')
        view = control_pool_view(before, states)
        demand_key = sha(canonical([key, request['instance_id']]))
        check(count < view['shares'].get(demand_key, 0), 'RESOURCE_WAIT')
        after = deepcopy(before)
        after['demands'] = view['demands']
        after['slots'][token] = dict(project_key=key, instance_id=request['instance_id'],
            operation_id=call['operation_id'], request_id=request_id, reservation_ref=call['reservation_ref'],
            state='HELD', release_evidence_ref=None)
        after = self.write(before, after)
        return token, after['revision']

    def release_locked(self, token):
        before, states, _, _ = self.inspect()
        slot = before['slots'][token]
        request = states[slot['project_key']]['requests'][slot['request_id']]
        check(releasable(request), 'EXECUTION_UNRESOLVED')
        if slot['state'] == 'RELEASED':
            return before['revision']
        after = deepcopy(before); slot = after['slots'][token]
        slot['state'] = 'RELEASED'
        slot['release_evidence_ref'] = request['admission']['not_sent_ref'] or request['admission']['termination_ref']
        after['cursor'] += 1
        return self.write(before, after)['revision']
